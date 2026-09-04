"""Üniversite-sanayi iş birliği ve bölgesel katkı endeksleri.

Bu iki gösterge daha önce KPI tablosunda elle girilmiş tek bir sayıydı.
"52.2" değerinin neyi ölçtüğü, nasıl hesaplandığı ve hangi veriden geldiği
belli değildi — yani bir karar destek sisteminde kullanılamazdı.

Artık ölçülebilir alt bileşenlerden FORMÜLLE hesaplanıyor:

    endeks = Σ ( bileşen_değeri / referans_değer × 100 × ağırlık )

Referans değerler kurumun stratejik plan hedefleridir ve ağırlıklarla birlikte
shared_demo_data/09_engagement.json içinde tanımlıdır — kodda gömülü değildir.
Bir bileşenin ağırlığı değiştiğinde kod değişmez.

Endeks 100'ü aşabilir: hedefin üzerinde performans anlamına gelir. Yapay olarak
100'de kesmek, hedefi aşan başarıyı gizlerdi.
"""

import json
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:  # yalnızca tip ipucu; döngüsel import olmasın
    from app.services.scope import Scope

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.decimal_types import quantize_money
from app.models import (
    Faculty,
    IndustryCollaborationRecord,
    RegionalContributionRecord,
    Student,
)

ZERO = Decimal("0")
HUNDRED = Decimal("100")
INDUSTRY_METRICS = {
    "industry_active_partnerships": "active_partnerships",
    "industry_joint_projects": "joint_projects",
    "industry_funded_research_musd": "funded_research_musd",
    "industry_intern_students": "intern_students",
    "industry_signed_protocols": "signed_protocols",
}
REGIONAL_METRICS = {
    "regional_graduates_employed": "graduates_employed_in_region",
    "regional_public_projects": "local_public_projects",
    "municipality_partnerships": "municipality_partnerships",
    "community_service_hours": "community_service_hours",
    "regional_sme_collaborations": "regional_sme_collaborations",
    "public_events_hosted": "public_events_hosted",
}


def _result_provenance(records: list) -> dict:
    synthetic = [record for record in records if getattr(record, "is_synthetic", False)]
    if not synthetic:
        return {
            "source_type": "authoritative",
            "source_label": "Yetkili iş birliği ve katkı kayıtları",
            "provenance": "Yetkili kurumsal kayıt",
            "is_synthetic": False,
            "uploaded_source_id": None,
            "filename": None,
        }
    if len(synthetic) != len(records):
        return {
            "source_type": "mixed",
            "source_label": "Yetkili kayıtlar + izlenebilir yüklenmiş tamamlayıcı veriler",
            "provenance": "Karma kaynak; fakülte kimliğinde yetkili kayıt önceliklidir",
            "is_synthetic": True,
            "uploaded_source_id": None,
            "filename": None,
        }
    ids = {getattr(record, "uploaded_source_id", None) for record in synthetic}
    labels = {getattr(record, "source_label", None) for record in synthetic}
    filenames = {getattr(record, "filename", None) for record in synthetic}
    return {
        "source_type": "uploaded",
        "source_label": next(iter(labels)) if len(labels) == 1 else "Yüklenmiş yönetilen metrikler",
        "provenance": "SYNTHETIC_GENERATED",
        "is_synthetic": True,
        "uploaded_source_id": next(iter(ids)) if len(ids) == 1 else None,
        "filename": next(iter(filenames)) if len(filenames) == 1 else None,
    }

# Formül yapılandırması ortak veri klasöründen okunur.
CONFIG_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "shared_demo_data"
    / "09_engagement.json"
)


@lru_cache(maxsize=1)
def load_config() -> dict:
    """Endeks formüllerini ve referans değerlerini okur."""
    if not CONFIG_PATH.exists():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                f"İş birliği yapılandırma dosyası bulunamadı: {CONFIG_PATH}. "
                "integration/shared_demo_data/ klasörünün yerinde olduğundan emin olun."
            ),
        )
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _score_components(values: Dict[str, Decimal], formula: dict) -> dict:
    """Bileşenleri normalize edip ağırlıklı endeks üretir.

    Her bileşen için hem ham değer hem de hedefe ulaşma oranı döndürülür;
    böylece endeksin hangi bileşenden geldiği görülebilir ve "kara kutu puan"
    olmaktan çıkar.
    """
    components = formula["components"]
    breakdown: List[dict] = []
    index_total = ZERO
    weight_total = ZERO

    for key, spec in components.items():
        raw = values.get(key, ZERO)
        reference = Decimal(str(spec["reference_value"]))
        weight = Decimal(str(spec["weight"]))
        weight_total += weight

        achievement = (
            quantize_money(Decimal(str(raw)) / reference * HUNDRED)
            if reference != ZERO
            else None
        )
        contribution = (
            quantize_money(achievement * weight) if achievement is not None else ZERO
        )
        index_total += contribution

        breakdown.append(
            {
                "key": key,
                "label": spec["label"],
                "unit": spec["unit"],
                "value": quantize_money(Decimal(str(raw))),
                "reference_value": quantize_money(reference),
                "weight": quantize_money(weight),
                "achievement_percent": achievement,
                "contribution_to_index": contribution,
            }
        )

    # Ağırlık toplamı 1,00 değilse yapılandırma hatalıdır; sessizce yanlış
    # endeks üretmek yerine bunu açıkça bildiriyoruz.
    weight_warning = (
        None
        if abs(weight_total - Decimal("1")) < Decimal("0.001")
        else (
            f"Yapılandırmadaki ağırlık toplamı {weight_total}, 1.00 olmalıydı. "
            "Endeks değeri güvenilir değildir."
        )
    )

    return {
        "index_value": quantize_money(index_total),
        "components": breakdown,
        "weight_total": quantize_money(weight_total),
        "weight_warning": weight_warning,
    }


# ----------------------------------------------------------------------------
# Üniversite-sanayi iş birliği
# ----------------------------------------------------------------------------


def industry_collaboration(
    db: Session, academic_year: str, scope: Optional["Scope"] = None
) -> dict:
    """Sanayi iş birliği endeksi ve fakülte kırılımı.

    KAPSAM
    ------
    Kayıtlar FAKÜLTE seviyesindedir (`faculty_id`). Fakülte kapsamında
    yalnızca o fakültenin kaydı toplanır. Bölüm/program kapsamında bu
    veri ölçülmediği için 404 döner — fakültenin endeksini programın
    endeksi gibi göstermek yanlış olurdu.
    """
    if scope is not None and scope.level in ("department", "program"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "Sanayi iş birliği verisi fakülte seviyesinde ölçülüyor; "
                f"'{scope.label}' için ayrı bir kayıt yok."
            ),
        )

    sorgu = (
        select(IndustryCollaborationRecord)
        .options(selectinload(IndustryCollaborationRecord.faculty))
        .where(IndustryCollaborationRecord.academic_year == academic_year)
    )
    if scope is not None and scope.faculty_ids is not None:
        sorgu = sorgu.where(
            IndustryCollaborationRecord.faculty_id.in_(scope.faculty_ids)
        )
    records = list(db.execute(sorgu).scalars())

    from app.services import data_source_service

    governed = data_source_service.governed_records(
        db,
        metric_keys=tuple(INDUSTRY_METRICS),
        academic_year=academic_year,
        scope=scope,
        record_scope_type="faculty",
        entity_type="faculty",
    )
    grouped: Dict[int, dict] = {}
    for item in governed:
        if item["faculty_id"] is not None:
            grouped.setdefault(item["faculty_id"], {})[item["metric_key"]] = item
    native_faculty_ids = {record.faculty_id for record in records}
    missing_ids = [
        faculty_id
        for faculty_id, values in grouped.items()
        if faculty_id not in native_faculty_ids
        and all(key in values for key in INDUSTRY_METRICS)
    ]
    faculties = {
        faculty.id: faculty
        for faculty in db.execute(
            select(Faculty).where(Faculty.id.in_(missing_ids or [-1]))
        ).scalars()
    }
    for faculty_id in missing_ids:
        values = grouped[faculty_id]
        source_ids = {values[key]["uploaded_source_id"] for key in INDUSTRY_METRICS}
        labels = {values[key]["source_label"] for key in INDUSTRY_METRICS}
        filenames = {values[key]["filename"] for key in INDUSTRY_METRICS}
        records.append(
            SimpleNamespace(
                faculty_id=faculty_id,
                faculty=faculties.get(faculty_id),
                academic_year=academic_year,
                active_partnerships=int(
                    values["industry_active_partnerships"]["value"]
                ),
                joint_projects=int(values["industry_joint_projects"]["value"]),
                funded_research_musd=Decimal(
                    str(values["industry_funded_research_musd"]["value"])
                ),
                intern_students=int(values["industry_intern_students"]["value"]),
                signed_protocols=int(values["industry_signed_protocols"]["value"]),
                is_synthetic=True,
                source_label=(
                    next(iter(labels)) if len(labels) == 1
                    else "Yüklenmiş yönetilen metrikler"
                ),
                uploaded_source_id=(
                    next(iter(source_ids)) if len(source_ids) == 1 else None
                ),
                filename=(next(iter(filenames)) if len(filenames) == 1 else None),
            )
        )
    if not records:
        available = _available_years(db, IndustryCollaborationRecord)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"'{academic_year}' için sanayi iş birliği verisi yok. "
                f"Mevcut dönemler: {', '.join(available) if available else 'hiç yok'}."
            ),
        )

    config = load_config()
    totals = {
        "active_partnerships": Decimal(sum(r.active_partnerships for r in records)),
        "joint_projects": Decimal(sum(r.joint_projects for r in records)),
        "funded_research_musd": sum(
            (r.funded_research_musd for r in records), Decimal("0")
        ),
        "intern_students": Decimal(sum(r.intern_students for r in records)),
        "signed_protocols": Decimal(sum(r.signed_protocols for r in records)),
    }

    result = _score_components(totals, config["industry_collaboration_formula"])
    result["academic_year"] = academic_year
    result["target_value"] = Decimal(
        str(config["targets"]["industry_collaboration_index"])
    )
    result["achievement_vs_target_percent"] = (
        quantize_money(result["index_value"] / result["target_value"] * HUNDRED)
        if result["target_value"] != ZERO
        else None
    )

    result["by_faculty"] = [
        {
            "faculty_id": r.faculty_id,
            "faculty_name": r.faculty.name if r.faculty else "Bilinmiyor",
            "active_partnerships": r.active_partnerships,
            "joint_projects": r.joint_projects,
            "funded_research_musd": r.funded_research_musd,
            "intern_students": r.intern_students,
            "signed_protocols": r.signed_protocols,
        }
        for r in sorted(records, key=lambda x: x.joint_projects, reverse=True)
    ]
    result.update(_result_provenance(records))
    return result


# ----------------------------------------------------------------------------
# Bölgesel katkı
# ----------------------------------------------------------------------------


def regional_contribution(
    db: Session, academic_year: str, scope: Optional["Scope"] = None
) -> dict:
    """Bölgesel katkı endeksi ve alt bileşenleri.

    Bu endeks KURUM geneli tek kayıttır; fakülte/bölüm/program kırılımı
    yoktur. Dar kapsamda üniversite değerini döndürmek sızıntı olacağı
    için 404 döner.
    """
    if scope is not None and not scope.is_university:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "Bölgesel katkı endeksi kurum geneli ölçülüyor; "
                f"'{scope.label}' için ayrı bir kayıt yok."
            ),
        )

    record = db.execute(
        select(RegionalContributionRecord).where(
            RegionalContributionRecord.academic_year == academic_year
        )
    ).scalars().first()

    if record is None:
        from app.services import data_source_service

        governed = data_source_service.governed_records(
            db,
            metric_keys=tuple(REGIONAL_METRICS),
            academic_year=academic_year,
            scope=scope,
            record_scope_type="university",
            entity_type="university",
        )
        values = {item["metric_key"]: item for item in governed}
        if all(key in values for key in REGIONAL_METRICS):
            source_ids = {values[key]["uploaded_source_id"] for key in REGIONAL_METRICS}
            labels = {values[key]["source_label"] for key in REGIONAL_METRICS}
            filenames = {values[key]["filename"] for key in REGIONAL_METRICS}
            payload = {
                field: int(values[key]["value"])
                for key, field in REGIONAL_METRICS.items()
            }
            record = SimpleNamespace(
                **payload,
                academic_year=academic_year,
                is_synthetic=True,
                source_label=(
                    next(iter(labels)) if len(labels) == 1
                    else "Yüklenmiş yönetilen metrikler"
                ),
                uploaded_source_id=(
                    next(iter(source_ids)) if len(source_ids) == 1 else None
                ),
                filename=(next(iter(filenames)) if len(filenames) == 1 else None),
            )

    if record is None:
        available = _available_years(db, RegionalContributionRecord)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"'{academic_year}' için bölgesel katkı verisi yok. "
                f"Mevcut dönemler: {', '.join(available) if available else 'hiç yok'}."
            ),
        )

    config = load_config()
    values = {
        "graduates_employed_in_region": Decimal(record.graduates_employed_in_region),
        "local_public_projects": Decimal(record.local_public_projects),
        "municipality_partnerships": Decimal(record.municipality_partnerships),
        "community_service_hours": Decimal(record.community_service_hours),
        "regional_sme_collaborations": Decimal(record.regional_sme_collaborations),
        "public_events_hosted": Decimal(record.public_events_hosted),
    }

    result = _score_components(values, config["regional_contribution_formula"])
    result["academic_year"] = academic_year
    result["target_value"] = Decimal(
        str(config["targets"]["regional_contribution_index"])
    )
    result["achievement_vs_target_percent"] = (
        quantize_money(result["index_value"] / result["target_value"] * HUNDRED)
        if result["target_value"] != ZERO
        else None
    )

    # Bölgede istihdam oranının paydası, O AKADEMİK YILIN mezun sayısıdır.
    # Önceki sürümde payda olarak "durumu mezun olan tüm öğrenciler" alınıyordu;
    # bu, bir yılın istihdamını tüm yılların mezun havuzuna bölmek anlamına
    # geliyordu ve %160 gibi imkânsız bir oran üretiyordu.
    from app.models import AcademicSuccessRecord

    graduate_count = int(
        db.execute(
            select(func.sum(AcademicSuccessRecord.graduate_count)).where(
                AcademicSuccessRecord.academic_year == academic_year
            )
        ).scalar()
        or 0
    )
    if not graduate_count:
        from app.services import academic_success_service

        try:
            graduate_count = int(
                academic_success_service.university_overview(
                    db, academic_year, scope
                ).get("graduate_count")
                or 0
            )
        except HTTPException:
            graduate_count = 0
    result["total_graduates"] = graduate_count
    share = (
        quantize_money(
            Decimal(record.graduates_employed_in_region) / Decimal(graduate_count) * HUNDRED
        )
        if graduate_count
        else None
    )
    # Oran %100'ü aşıyorsa veri tutarsızdır; sessizce göstermek yerine
    # hesaplamayı reddedip nedenini bildiriyoruz.
    result["regional_employment_share_percent"] = (
        share if share is not None and share <= HUNDRED else None
    )
    result["regional_employment_note"] = (
        f"{record.graduates_employed_in_region} mezun bölgede istihdam edildi "
        f"(o yılın toplam {graduate_count} mezunu üzerinden)."
        if share is not None and share <= HUNDRED
        else "Bölgesel istihdam oranı hesaplanamadı: istihdam sayısı o yılın mezun sayısını aşıyor."
    )
    result["region"] = "İç Anadolu"
    result.update(_result_provenance([record]))
    return result


def _available_years(db: Session, model) -> List[str]:
    """Verilen modelde veri bulunan akademik yıllar."""
    return list(
        db.execute(
            select(model.academic_year).distinct().order_by(model.academic_year)
        ).scalars()
    )


def engagement_trend(db: Session) -> List[dict]:
    """İki endeksin yıllara göre gelişimi."""
    from app.services import data_source_service

    years = sorted(
        set(_available_years(db, IndustryCollaborationRecord))
        | set(_available_years(db, RegionalContributionRecord))
        | set(
            data_source_service.governed_metric_years(
                db, tuple(INDUSTRY_METRICS) + tuple(REGIONAL_METRICS)
            )
        )
    )
    rows = []
    for year in years:
        row: dict = {"academic_year": year}
        try:
            row["industry_collaboration_index"] = industry_collaboration(db, year)[
                "index_value"
            ]
        except HTTPException:
            row["industry_collaboration_index"] = None
        try:
            row["regional_contribution_index"] = regional_contribution(db, year)[
                "index_value"
            ]
        except HTTPException:
            row["regional_contribution_index"] = None
        rows.append(row)
    return rows
