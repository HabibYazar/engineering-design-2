"""Modül 4 — Akademik personel CRUD ve performans hesaplama servisi.

Entegrasyon notu: Puanlama formülü Eda'nın `scores_calculator.py` dosyasındaki
ağırlıklı toplam mantığını birebir korur. Değişen tek şey verinin kaynağı:
modül seviyesindeki `staffs` listesi yerine veritabanı sorgusu kullanılıyor.

Ayrıca orijinal kodda `config/weights.json` yolu var olmayan bir klasörü işaret
ettiği için `/ranking` endpoint'i çalışmıyordu (FileNotFoundError). Ağırlık dosyası
app/config altına taşındı ve yol bir kez okunup önbelleğe alınıyor.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:  # yalnızca tip ipucu; döngüsel import olmasın
    from app.services.scope import Scope

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    AcademicStaff,
    AcademicStaffCourse,
    Department,
    Faculty,
    UploadedDataSource,
    UploadedMetricRecord,
)
from app.models.program_allocation import ProgramAcademicStaffAllocation
from app.schemas.academic_staff import AcademicStaffCreate, AcademicStaffUpdate

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "academic_staff_weights.json"

PERFORMANCE_METRIC_LABELS = {
    "publication_count": "Yayın sayısı",
    "citation_count": "Atıf sayısı",
    "teaching_load_hours": "Ders yükü",
    "advising_count": "Danışmanlık",
    "project_count": "Proje sayısı",
    "patent_count": "Patent sayısı",
    "community_engagement_score": "Toplumsal katkı",
}

# YÖK Akademik aktarımında yayın ve danışmanlık sayıları
# gerçek sayımlardır; 0 bu alanlarda "ölçüldü ve yok" demektir.
# Diğer eski NOT NULL alanların 0 değeri ise kaynak yokken kullanılan
# eski puanlama varsayımı olabilir; onlar ayrıca kanıtlanmadıkça
# arayüzde "ölçülmedi" gösterilir.
ALWAYS_MEASURED_FIELDS = frozenset({"publication_count", "advising_count"})


@lru_cache(maxsize=1)
def load_weights() -> Dict[str, object]:
    """Ağırlık ve eşik yapılandırmasını okur.

    lru_cache kullanılıyor çünkü dosya her istekte değil, süreç ömründe bir kez
    okunmalı; sıralama endpoint'i her personel için bu değerlere ihtiyaç duyuyor.
    """
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _base_query():
    """Bölüm ve fakülteyi tek sorguda getiren temel select.

    selectinload olmadan her personel için ayrı sorgu atılırdı (N+1); sıralama
    endpoint'i tüm personeli dolaştığı için bu fark hissedilir.
    """
    return select(AcademicStaff).options(
        selectinload(AcademicStaff.department).selectinload(Department.faculty)
    )


def _department_name(staff: AcademicStaff) -> str:
    return staff.department.name if staff.department else "Bilinmiyor"


def _faculty_name(staff: AcademicStaff) -> str:
    if staff.department and staff.department.faculty:
        return staff.department.faculty.name
    return "Bilinmiyor"


def to_response_dict(staff: AcademicStaff) -> dict:
    """SQLAlchemy nesnesini API cevabına uygun sözlüğe çevirir."""
    return {
        "id": staff.id,
        "staff_number": staff.staff_number,
        "first_name": staff.first_name,
        "last_name": staff.last_name,
        "full_name": staff.full_name,
        "title": staff.title,
        "department_id": staff.department_id,
        "department_name": _department_name(staff),
        "faculty_name": _faculty_name(staff),
        "academic_year": staff.academic_year,
        "publication_count": staff.publication_count,
        "citation_count": staff.citation_count,
        "teaching_load_hours": staff.teaching_load_hours,
        "advising_count": staff.advising_count,
        "project_count": staff.project_count,
        "patent_count": staff.patent_count,
        "community_engagement_score": staff.community_engagement_score,
        "has_administrative_duty": staff.has_administrative_duty,
        "has_industry_collaboration": staff.has_industry_collaboration,
        "is_active": staff.is_active,
    }


# ----------------------------------------------------------------------------
# CRUD
# ----------------------------------------------------------------------------


def list_staff(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    department_id: Optional[int] = None,
    faculty_id: Optional[int] = None,
    academic_year: Optional[str] = None,
    include_inactive: bool = False,
    scope: Optional["Scope"] = None,
) -> List[AcademicStaff]:
    """Filtrelenebilir personel listesi.

    KAPSAM
    ------
    Personel kaydı BÖLÜME bağlıdır; programa değil. Bu yüzden PROGRAM
    kapsamında bölümün tüm kadrosunu döndürmek, üst birimin verisini
    alt birime taşımak olurdu. Program seviyesinde kadro
    `program_academic_staff_allocations` tablosundan, yani o programa
    fiilen iş yükü ayıran kişilerden okunur. Tahsis girilmemişse liste
    BOŞ döner — "bu program için kadro tahsisi tanımlı değil" demektir,
    "bölümün kadrosu" değil.
    """
    query = _base_query()
    if not include_inactive:
        query = query.where(AcademicStaff.is_active.is_(True))
    if scope is not None:
        if scope.is_program:
            tahsisli = select(ProgramAcademicStaffAllocation.academic_staff_id).where(
                ProgramAcademicStaffAllocation.program_id
                == scope.academic_program_id
            )
            if academic_year:
                tahsisli = tahsisli.where(
                    ProgramAcademicStaffAllocation.academic_year == academic_year
                )
            query = query.where(AcademicStaff.id.in_(tahsisli))
        elif scope.department_ids is not None:
            query = query.where(
                AcademicStaff.department_id.in_(scope.department_ids)
            )
    if department_id is not None:
        query = query.where(AcademicStaff.department_id == department_id)
    if faculty_id is not None:
        # Fakülte filtresi bölüm üzerinden yapılıyor; personelde ayrı fakülte
        # kolonu tutulmadığı için tek doğruluk kaynağı bölüm tablosu.
        query = query.join(Department).where(Department.faculty_id == faculty_id)
    if academic_year:
        query = query.where(AcademicStaff.academic_year == academic_year)
    query = query.order_by(AcademicStaff.staff_number).offset(skip).limit(limit)
    return list(db.execute(query).scalars().unique())


def get_staff(db: Session, staff_id: int) -> AcademicStaff:
    """Tek personel; bulunamazsa 404."""
    staff = db.execute(_base_query().where(AcademicStaff.id == staff_id)).scalars().first()
    if staff is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{staff_id} numaralı akademik personel bulunamadı.",
        )
    return staff


def create_staff(db: Session, payload: AcademicStaffCreate) -> AcademicStaff:
    """Yeni personel kaydı; sicil no tekrarında 409, bölüm yoksa 404."""
    existing = db.execute(
        select(AcademicStaff).where(AcademicStaff.staff_number == payload.staff_number)
    ).scalars().first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"'{payload.staff_number}' sicil numarası zaten kayıtlı.",
        )

    department = db.get(Department, payload.department_id)
    if department is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{payload.department_id} numaralı bölüm bulunamadı.",
        )

    staff = AcademicStaff(**payload.model_dump())
    db.add(staff)
    db.commit()
    db.refresh(staff)
    return staff


def update_staff(db: Session, staff_id: int, payload: AcademicStaffUpdate) -> AcademicStaff:
    """Kısmi güncelleme."""
    staff = get_staff(db, staff_id)
    data = payload.model_dump(exclude_unset=True)

    if "department_id" in data and db.get(Department, data["department_id"]) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{data['department_id']} numaralı bölüm bulunamadı.",
        )

    for field, value in data.items():
        setattr(staff, field, value)
    db.commit()
    db.refresh(staff)
    return staff


def deactivate_staff(db: Session, staff_id: int) -> AcademicStaff:
    """Kayıt silinmez, pasifleştirilir; geçmiş raporlar bozulmasın diye."""
    staff = get_staff(db, staff_id)
    staff.is_active = False
    db.commit()
    db.refresh(staff)
    return staff


# ----------------------------------------------------------------------------
# Performans hesaplama
# ----------------------------------------------------------------------------


def _field_is_measured(field: str, value, measured_fields: set[str]) -> bool:
    if field in ALWAYS_MEASURED_FIELDS or field in measured_fields:
        return True
    return value is not None and float(value) != 0


def _performance_band(total_score: float) -> str:
    """Puanı yapılandırmadaki eşiklere göre sınıflandırır."""
    thresholds = load_weights()["score_thresholds"]
    if total_score >= thresholds["high_performance"]:
        return "yüksek performans"
    if total_score >= thresholds["expected_performance"]:
        return "beklenen performans"
    return "desteklenmesi gereken"


def academic_performance_score(
    staff: AcademicStaff,
    *,
    uploaded_metrics: Optional[Dict[str, dict]] = None,
    measured_fields: Optional[set[str]] = None,
) -> dict:
    """Tek akademisyenin yönetim-politikası performans sonucunu döndürür.

    Eski puanlayıcı eksik NOT NULL bileşenleri 0 katkı olarak ele alıyordu.
    Bu davranış korunur; ancak bileşen cevabında gerçek değer yerine
    ``available=False`` / ``value=None`` dönerek eksik veri açık edilir.
    Kullanıcı dosyasındaki kişi-eşleşmeli bir değer yalnızca mevcut
    personel alanı ölçülmemişse ikincil kaynak olarak kullanılır.
    """
    config = load_weights()
    weights = config["weights"]
    uploads = uploaded_metrics or {}
    measured = measured_fields or set()
    components: Dict[str, dict] = {}

    for field, weight in weights.items():
        stored_value = getattr(staff, field, None)
        available = _field_is_measured(field, stored_value, measured)
        source_type = "authoritative" if available else None
        source_label = "YÖK Akademik / personel kaydı" if available else None
        value = stored_value if available else None

        upload = uploads.get(field)
        if not available and upload is not None:
            value = upload["value"]
            available = True
            source_type = "uploaded"
            source_label = upload["source_label"]

        # Eski politikanın eksik bileşeni 0 katkı sayma davranışı burada
        # tek ve görünür noktada korunur.
        scoring_value = float(value) if available and value is not None else 0.0
        contribution = round(scoring_value * float(weight), 2)
        components[field] = {
            "metric_key": field,
            "label": PERFORMANCE_METRIC_LABELS[field],
            "value": float(value) if available and value is not None else None,
            "available": available,
            "weight": float(weight),
            "contribution": contribution,
            "source_type": source_type,
            "source_label": source_label,
            "provenance": upload.get("provenance") if upload and source_type == "uploaded" else source_label,
            "is_synthetic": bool(upload.get("is_synthetic")) if upload and source_type == "uploaded" else False,
            "uploaded_source_id": upload.get("uploaded_source_id") if upload and source_type == "uploaded" else None,
            "filename": upload.get("filename") if upload and source_type == "uploaded" else None,
        }

    total = round(sum(item["contribution"] for item in components.values()), 2)
    return {
        "staff_id": staff.id,
        "total_score": total,
        "classification": _performance_band(total),
        "component_breakdown": components,
        "weights": weights,
        "thresholds": config["score_thresholds"],
        "policy_version": config.get("version", "academic-staff-policy-v1"),
        "policy_label": config.get(
            "policy_label", "Yönetim politikası ağırlıklarıyla hesaplanır."
        ),
    }


def calculate_score_breakdown(staff: AcademicStaff) -> Dict[str, float]:
    """Geriye uyumlu katkı sözlüğü; hesap tek ortak servisten gelir."""
    result = academic_performance_score(staff)
    return {
        field: item["contribution"]
        for field, item in result["component_breakdown"].items()
    }


def _measured_teaching_staff(db: Session, staff_ids: list[int]) -> set[int]:
    if not staff_ids:
        return set()
    return {
        staff_id for (staff_id,) in db.execute(
            select(AcademicStaffCourse.academic_staff_id).distinct().where(
                AcademicStaffCourse.academic_staff_id.in_(staff_ids),
                AcademicStaffCourse.weekly_hours.isnot(None),
            )
        )
    }


def _uploaded_staff_metrics(db: Session, staff_ids: list[int]) -> Dict[int, Dict[str, dict]]:
    """Her personel/metrik için en yeni aktif kullanıcı kaynağını seçer."""
    if not staff_ids:
        return {}
    metric_keys = tuple(load_weights()["weights"].keys())
    statement = (
        select(UploadedMetricRecord, UploadedDataSource)
        .join(
            UploadedDataSource,
            UploadedMetricRecord.uploaded_source_id == UploadedDataSource.id,
        )
        .where(
            UploadedMetricRecord.academic_staff_id.in_(staff_ids),
            UploadedMetricRecord.metric_key.in_(metric_keys),
            UploadedMetricRecord.is_active.is_(True),
            UploadedDataSource.is_active.is_(True),
            UploadedDataSource.status == "imported",
        )
        .order_by(
            UploadedDataSource.uploaded_at.desc(),
            UploadedDataSource.id.desc(),
            UploadedMetricRecord.id.desc(),
        )
    )
    from app.services.data_source_service import source_provenance

    result: Dict[int, Dict[str, dict]] = {}
    for record, source in db.execute(statement):
        staff_metrics = result.setdefault(record.academic_staff_id, {})
        staff_metrics.setdefault(
            record.metric_key,
            {"value": record.numeric_value, **source_provenance(source)},
        )
    return result


def rank_staff(
    db: Session,
    academic_year: Optional[str] = None,
    department_id: Optional[int] = None,
    faculty_id: Optional[int] = None,
    scope: Optional["Scope"] = None,
) -> List[dict]:
    """Ağırlıklı toplam puana göre azalan sıralama."""
    staff_list = list_staff(
        db,
        skip=0,
        limit=10_000,
        department_id=department_id,
        faculty_id=faculty_id,
        academic_year=academic_year,
        scope=scope,
    )

    staff_ids = [staff.id for staff in staff_list]
    teaching_measured = _measured_teaching_staff(db, staff_ids)
    uploaded_by_staff = _uploaded_staff_metrics(db, staff_ids)
    rows = []
    for staff in staff_list:
        measured_fields = {"teaching_load_hours"} if staff.id in teaching_measured else set()
        performance = academic_performance_score(
            staff,
            uploaded_metrics=uploaded_by_staff.get(staff.id),
            measured_fields=measured_fields,
        )
        components = performance["component_breakdown"]
        rows.append(
            {
                "staff_id": staff.id,
                "staff_number": staff.staff_number,
                "full_name": staff.full_name,
                "title": staff.title,
                "department_name": _department_name(staff),
                "faculty_name": _faculty_name(staff),
                "academic_year": staff.academic_year,
                "total_score": performance["total_score"],
                "performance_band": performance["classification"],
                "classification": performance["classification"],
                "score_breakdown": {
                    key: item["contribution"] for key, item in components.items()
                },
                "component_breakdown": components,
                "weights": performance["weights"],
                "thresholds": performance["thresholds"],
                "policy_version": performance["policy_version"],
                "policy_label": performance["policy_label"],
                **{
                    key: components[key]["value"]
                    for key in performance["weights"]
                },
            }
        )

    rows.sort(key=lambda row: row["total_score"], reverse=True)
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
    return rows


# Karşılaştırma anahtarı -> personelden değeri çıkaran fonksiyon.
COMPARISON_FIELDS = {
    "department": _department_name,
    "faculty": _faculty_name,
    "title": lambda staff: staff.title,
}


def compare_staff(
    db: Session, group_by: str, academic_year: Optional[str] = None
) -> List[dict]:
    """Bölüm, fakülte veya unvan bazlı ortalama üretim karşılaştırması."""
    if group_by not in COMPARISON_FIELDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"'{group_by}' geçerli bir gruplama değil. "
                f"Kullanılabilir değerler: {', '.join(COMPARISON_FIELDS)}."
            ),
        )

    key_func = COMPARISON_FIELDS[group_by]
    staff_list = list_staff(db, skip=0, limit=10_000, academic_year=academic_year)

    groups: Dict[str, dict] = {}
    for staff in staff_list:
        key = key_func(staff)
        bucket = groups.setdefault(
            key,
            {"count": 0, "publication": 0, "citation": 0, "score": 0.0},
        )
        bucket["count"] += 1
        bucket["publication"] += staff.publication_count
        bucket["citation"] += staff.citation_count
        bucket["score"] += sum(calculate_score_breakdown(staff).values())

    result = [
        {
            "group_key": key,
            "staff_count": data["count"],
            "average_publication": round(data["publication"] / data["count"], 2),
            "average_citation": round(data["citation"] / data["count"], 2),
            "average_score": round(data["score"] / data["count"], 2),
            "total_publication": data["publication"],
            "total_citation": data["citation"],
        }
        for key, data in groups.items()
    ]
    result.sort(key=lambda row: row["average_score"], reverse=True)
    return result


def staff_trend(db: Session) -> List[dict]:
    """Akademik yıla göre toplam yayın/atıf trendi."""
    staff_list = list_staff(db, skip=0, limit=10_000)

    years: Dict[str, dict] = {}
    for staff in staff_list:
        bucket = years.setdefault(
            staff.academic_year, {"publication": 0, "citation": 0, "count": 0}
        )
        bucket["publication"] += staff.publication_count
        bucket["citation"] += staff.citation_count
        bucket["count"] += 1

    return [
        {
            "academic_year": year,
            "staff_count": data["count"],
            "total_publication": data["publication"],
            "total_citation": data["citation"],
            "average_publication_per_staff": round(
                data["publication"] / data["count"], 2
            ),
        }
        for year, data in sorted(years.items())
    ]


def staff_overview(
    db: Session,
    academic_year: Optional[str] = None,
    faculty_id: Optional[int] = None,
    department_id: Optional[int] = None,
    scope: Optional["Scope"] = None,
) -> dict:
    """Akademik personel özet göstergeleri.

    Fakülte/bölüm verilirse özet o kapsama daraltılır; böylece arayüzdeki
    hiyerarşik filtre üst kartları da etkiler.

    Veri yoksa sıfır değil, boş özet döner; böylece arayüzde "0 personel"
    ile "veri girilmemiş" durumu karışmaz.

    YIL VERİLMEZSE EN GÜNCEL YIL kullanılır. AcademicStaff yıllık bir anlık
    görüntü tablosudur: aynı 180 kişi her akademik yıl için ayrı satır taşır.
    Yıl süzülmezse iki yılın satırları toplanıp "360 personel" gibi anlamsız
    bir sayı çıkardı.
    """
    if academic_year is None:
        years = [
            row for row in db.execute(
                select(AcademicStaff.academic_year).distinct()
            ).scalars() if row
        ]
        if years:
            academic_year = max(years)

    staff_list = list_staff(
        db,
        skip=0,
        limit=10_000,
        department_id=department_id,
        faculty_id=faculty_id,
        academic_year=academic_year,
        scope=scope,
    )
    if not staff_list:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"'{academic_year or 'tüm yıllar'}' için akademik personel verisi yok."
                + (
                    f" ('{scope.label}' kapsamında kadro tahsisi tanımlı değil.)"
                    if scope is not None and scope.is_program else ""
                )
            ),
        )

    titles: Dict[str, int] = {}
    total_score = 0.0
    for staff in staff_list:
        titles[staff.title] = titles.get(staff.title, 0) + 1
        total_score += sum(calculate_score_breakdown(staff).values())

    count = len(staff_list)
    return {
        "academic_year": academic_year or "tüm yıllar",
        "total_staff": count,
        "total_publication": sum(s.publication_count for s in staff_list),
        "total_citation": sum(s.citation_count for s in staff_list),
        "average_teaching_load_hours": round(
            sum(s.teaching_load_hours for s in staff_list) / count, 2
        ),
        "staff_with_administrative_duty": sum(
            1 for s in staff_list if s.has_administrative_duty
        ),
        "staff_with_industry_collaboration": sum(
            1 for s in staff_list if s.has_industry_collaboration
        ),
        "average_score": round(total_score / count, 2),
        "title_distribution": [
            {"title": title, "count": number}
            for title, number in sorted(titles.items(), key=lambda x: -x[1])
        ],
    }
