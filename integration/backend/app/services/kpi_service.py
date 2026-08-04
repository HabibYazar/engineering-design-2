"""Modül 8 — Kurumsal performans (KPI) izleme servisi.

Entegrasyon notu: Durum sınıflandırma mantığı Halil'in `kpi/backend/db.py`
dosyasındaki `evaluate()` fonksiyonuyla aynıdır:

    başarı >= on_track_threshold   -> hedefte   (varsayılan %90)
    başarı <  at_risk_threshold    -> riskli    (varsayılan %70)
    aksi halde                     -> gecikmeli

Eşikler KPI başına saklanıyor; proje tanımı eşiklerin yönetim tarafından
yapılandırılabilir olmasını istiyor.

Değişen iki şey var:
1) Fakülte kırılımı sırasız listeden fakülte foreign key'ine taşındı.
2) Değerler Decimal; eşik sınırındaki bir KPI'nın float yuvarlaması yüzünden
   yanlış banda düşmesi engellendi.
"""

from decimal import Decimal
from typing import Dict, List, Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.decimal_types import quantize_money
from app.models import Faculty, KpiFacultyValue, StrategicKpi
from app.schemas.kpi import (
    KpiMeasurement,
    StrategicKpiCreate,
    StrategicKpiUpdate,
)

STATUS_ON_TRACK = "hedefte"
STATUS_DELAYED = "gecikmeli"
STATUS_AT_RISK = "riskli"


def _base_query():
    """Fakülte kırılımını tek sorguda getirir (N+1 önlenir)."""
    return select(StrategicKpi).options(
        selectinload(StrategicKpi.faculty_values).selectinload(KpiFacultyValue.faculty)
    )


def evaluate(kpi: StrategicKpi) -> dict:
    """KPI'yı hesaplanmış başarı oranı ve durumuyla birlikte döndürür."""
    achievement = (
        quantize_money(kpi.current_value / kpi.target_value * Decimal("100"))
        if kpi.target_value
        else Decimal("0.00")
    )

    if achievement >= kpi.on_track_threshold:
        state = STATUS_ON_TRACK
    elif achievement < kpi.at_risk_threshold:
        state = STATUS_AT_RISK
    else:
        state = STATUS_DELAYED

    # Geçmiş veri yoksa değişim hesaplanmaz; %0 yazmak "değişim olmadı"
    # anlamına gelir ve veri eksikliğini gizlerdi.
    change = None
    if kpi.previous_value is not None and kpi.previous_value != 0:
        change = quantize_money(
            (kpi.current_value - kpi.previous_value) / kpi.previous_value * Decimal("100")
        )

    gap = None
    if kpi.university_average is not None:
        gap = quantize_money(kpi.current_value - kpi.university_average)

    return {
        "id": kpi.id,
        "name": kpi.name,
        "dimension": kpi.dimension,
        "unit": kpi.unit,
        "academic_year": kpi.academic_year,
        "current_value": kpi.current_value,
        "target_value": kpi.target_value,
        "previous_value": kpi.previous_value,
        "university_average": kpi.university_average,
        "achievement_percent": achievement,
        "status": state,
        "on_track_threshold": kpi.on_track_threshold,
        "at_risk_threshold": kpi.at_risk_threshold,
        "change_vs_previous_percent": change,
        "gap_vs_university_average": gap,
        "corrective_action": kpi.corrective_action,
        "faculty_values": [
            {
                "faculty_id": fv.faculty_id,
                "faculty_name": fv.faculty.name if fv.faculty else None,
                "value": fv.value,
            }
            for fv in sorted(kpi.faculty_values, key=lambda x: x.faculty_id)
        ],
        "is_active": kpi.is_active,
    }


# ----------------------------------------------------------------------------
# CRUD
# ----------------------------------------------------------------------------


def list_kpis(
    db: Session,
    academic_year: Optional[str] = None,
    dimension: Optional[str] = None,
    kpi_status: Optional[str] = None,
    include_inactive: bool = False,
) -> List[dict]:
    """Filtrelenebilir KPI listesi."""
    query = _base_query()
    if not include_inactive:
        query = query.where(StrategicKpi.is_active.is_(True))
    if academic_year:
        query = query.where(StrategicKpi.academic_year == academic_year)
    if dimension:
        query = query.where(StrategicKpi.dimension == dimension)

    rows = [evaluate(k) for k in db.execute(query.order_by(StrategicKpi.dimension, StrategicKpi.name)).scalars().unique()]

    if kpi_status:
        valid = (STATUS_ON_TRACK, STATUS_DELAYED, STATUS_AT_RISK)
        if kpi_status not in valid:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"status alanı {', '.join(valid)} değerlerinden biri olmalı.",
            )
        rows = [r for r in rows if r["status"] == kpi_status]
    return rows


def get_kpi(db: Session, kpi_id: int) -> StrategicKpi:
    """Tek KPI; bulunamazsa 404."""
    kpi = db.execute(_base_query().where(StrategicKpi.id == kpi_id)).scalars().first()
    if kpi is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{kpi_id} numaralı KPI bulunamadı.",
        )
    return kpi


def list_dimensions(db: Session) -> List[str]:
    """Tanımlı stratejik boyutlar."""
    return sorted(
        {
            row
            for row in db.execute(
                select(StrategicKpi.dimension).where(StrategicKpi.is_active.is_(True))
            ).scalars()
        }
    )


def create_kpi(db: Session, payload: StrategicKpiCreate) -> StrategicKpi:
    """Yeni KPI tanımlar; aynı yıl aynı isim varsa 409."""
    existing = db.execute(
        select(StrategicKpi).where(
            StrategicKpi.name == payload.name,
            StrategicKpi.academic_year == payload.academic_year,
        )
    ).scalars().first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"'{payload.name}' KPI'sı {payload.academic_year} yılı için "
                "zaten tanımlı."
            ),
        )

    data = payload.model_dump(exclude={"faculty_values"})
    kpi = StrategicKpi(**data)
    db.add(kpi)
    db.flush()

    for item in payload.faculty_values:
        if db.get(Faculty, item.faculty_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{item.faculty_id} numaralı fakülte bulunamadı.",
            )
        db.add(
            KpiFacultyValue(
                kpi_id=kpi.id,
                faculty_id=item.faculty_id,
                value=quantize_money(item.value),
            )
        )

    db.commit()
    db.refresh(kpi)
    return kpi


def update_kpi(db: Session, kpi_id: int, payload: StrategicKpiUpdate) -> StrategicKpi:
    """KPI tanımını veya eşiklerini günceller."""
    kpi = get_kpi(db, kpi_id)
    data = payload.model_dump(exclude_unset=True)

    # Eşik tutarlılığı güncel değerlerle birlikte kontrol edilmeli; kısmi
    # güncellemede yalnızca bir eşik gönderilebilir.
    new_on = data.get("on_track_threshold", kpi.on_track_threshold)
    new_risk = data.get("at_risk_threshold", kpi.at_risk_threshold)
    if new_on <= new_risk:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"on_track_threshold ({new_on}) at_risk_threshold ({new_risk}) "
                "değerinden büyük olmalı."
            ),
        )

    for field, value in data.items():
        setattr(kpi, field, value)
    db.commit()
    db.refresh(kpi)
    return kpi


def record_measurement(db: Session, kpi_id: int, payload: KpiMeasurement) -> StrategicKpi:
    """Yeni ölçüm değeri kaydeder; durum otomatik yeniden hesaplanır."""
    kpi = get_kpi(db, kpi_id)
    kpi.current_value = quantize_money(payload.value)
    db.commit()
    db.refresh(kpi)
    return kpi


def set_faculty_value(
    db: Session, kpi_id: int, faculty_id: int, value: Decimal
) -> StrategicKpi:
    """Bir fakültenin KPI değerini ekler veya günceller."""
    kpi = get_kpi(db, kpi_id)
    if db.get(Faculty, faculty_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{faculty_id} numaralı fakülte bulunamadı.",
        )

    row = db.execute(
        select(KpiFacultyValue).where(
            KpiFacultyValue.kpi_id == kpi_id,
            KpiFacultyValue.faculty_id == faculty_id,
        )
    ).scalars().first()

    if row is None:
        db.add(
            KpiFacultyValue(
                kpi_id=kpi_id, faculty_id=faculty_id, value=quantize_money(value)
            )
        )
    else:
        row.value = quantize_money(value)

    db.commit()
    db.refresh(kpi)
    return kpi


def deactivate_kpi(db: Session, kpi_id: int) -> StrategicKpi:
    """KPI izlemeden çıkarılır; ölçüm geçmişi korunur."""
    kpi = get_kpi(db, kpi_id)
    kpi.is_active = False
    db.commit()
    db.refresh(kpi)
    return kpi


# ----------------------------------------------------------------------------
# Özet raporlar
# ----------------------------------------------------------------------------


def scorecard(db: Session, academic_year: Optional[str] = None) -> dict:
    """Tüm KPI'ların karne özeti ve boyut bazlı dağılımı."""
    rows = list_kpis(db, academic_year=academic_year)
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"'{academic_year or 'tüm yıllar'}' için tanımlı KPI yok. "
                "Önce KPI tanımlayın."
            ),
        )

    dimensions: Dict[str, dict] = {}
    for row in rows:
        bucket = dimensions.setdefault(
            row["dimension"],
            {"count": 0, "achievement": Decimal("0"), "on": 0, "delayed": 0, "risk": 0},
        )
        bucket["count"] += 1
        bucket["achievement"] += row["achievement_percent"]
        if row["status"] == STATUS_ON_TRACK:
            bucket["on"] += 1
        elif row["status"] == STATUS_DELAYED:
            bucket["delayed"] += 1
        else:
            bucket["risk"] += 1

    by_dimension = [
        {
            "dimension": name,
            "kpi_count": data["count"],
            "average_achievement_percent": quantize_money(
                data["achievement"] / data["count"]
            ),
            "on_track_count": data["on"],
            "delayed_count": data["delayed"],
            "at_risk_count": data["risk"],
        }
        for name, data in dimensions.items()
    ]
    by_dimension.sort(key=lambda row: row["average_achievement_percent"])

    total = len(rows)
    overall = quantize_money(
        sum((r["achievement_percent"] for r in rows), Decimal("0")) / total
    )
    at_risk = sum(1 for r in rows if r["status"] == STATUS_AT_RISK)
    on_track = sum(1 for r in rows if r["status"] == STATUS_ON_TRACK)

    # Kurum geneli durumu, tek tek KPI'larla aynı eşik mantığına göre belirlenir.
    if overall >= Decimal("90"):
        overall_status = STATUS_ON_TRACK
    elif overall < Decimal("70"):
        overall_status = STATUS_AT_RISK
    else:
        overall_status = STATUS_DELAYED

    return {
        "academic_year": academic_year or "tüm yıllar",
        "total_kpis": total,
        "on_track_count": on_track,
        "delayed_count": total - on_track - at_risk,
        "at_risk_count": at_risk,
        "overall_achievement_percent": overall,
        "overall_status": overall_status,
        "by_dimension": by_dimension,
    }


def faculty_comparison(db: Session, academic_year: Optional[str] = None) -> List[dict]:
    """Fakültelerin ölçülmüş KPI'lardaki ortalama performansı.

    Yalnızca o fakülte için değer girilmiş KPI'lar dikkate alınır; ölçülmemiş
    KPI'yı sıfır saymak fakülteyi haksız yere düşük gösterirdi.
    """
    rows = list_kpis(db, academic_year=academic_year)
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"'{academic_year or 'tüm yıllar'}' için tanımlı KPI yok.",
        )

    faculties: Dict[int, dict] = {}
    for row in rows:
        target = row["target_value"]
        average = row["university_average"]
        for fv in row["faculty_values"]:
            bucket = faculties.setdefault(
                fv["faculty_id"],
                {
                    "name": fv["faculty_name"] or "Bilinmiyor",
                    "count": 0,
                    "achievement": Decimal("0"),
                    "above_average": 0,
                },
            )
            bucket["count"] += 1
            if target:
                bucket["achievement"] += fv["value"] / target * Decimal("100")
            if average is not None and fv["value"] > average:
                bucket["above_average"] += 1

    result = [
        {
            "faculty_id": fid,
            "faculty_name": data["name"],
            "measured_kpi_count": data["count"],
            "average_achievement_percent": quantize_money(
                data["achievement"] / data["count"]
            ),
            "kpis_above_university_average": data["above_average"],
        }
        for fid, data in faculties.items()
    ]
    result.sort(key=lambda row: row["average_achievement_percent"], reverse=True)
    return result


def attention_list(db: Session, academic_year: Optional[str] = None) -> List[dict]:
    """Riskli ve gecikmeli KPI'lar, en düşük başarıdan başlayarak."""
    rows = [
        r
        for r in list_kpis(db, academic_year=academic_year)
        if r["status"] != STATUS_ON_TRACK
    ]
    rows.sort(key=lambda row: row["achievement_percent"])
    return rows
