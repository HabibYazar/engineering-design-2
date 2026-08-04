"""Modül 5 — Fiziksel kaynak ve kapasite analizi servisi.

Entegrasyon notu: Hesaplama mantığı Eda'nın `capacity_service.py` dosyasından
korundu. İki davranış bilerek değiştirildi:

1) Orijinal kodda `TOTAL_STUDENTS = 3200` ve `TOTAL_STAFF = 180` sabitleri vardı.
   Sabit sayı ile hesaplanan "kişi başına alan" değeri gerçek sistem verisi gibi
   görünüp yanlış karar aldırabileceği için bu sayılar artık veritabanındaki
   aktif öğrenci ve personel kayıtlarından sayılıyor.

2) Doluluk oranı orijinalde "72.22%" gibi metin döndürüyordu. Metin alan üzerinde
   grafik çizilemediği ve karşılaştırma yapılamadığı için sayısal tip kullanıldı.
"""

from typing import Dict, List, Optional

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import AcademicStaff, Department, PhysicalFacility, Student
from app.models.physical_facility import FACILITY_TYPES
from app.schemas.physical_resources import (
    PhysicalFacilityCreate,
    PhysicalFacilityUpdate,
)

# Doluluk eşikleri. Eda'nın kodundaki 50 / 90 değerleri korundu.
UNDERUTILIZED_THRESHOLD = 50.0
OVERCROWDED_THRESHOLD = 90.0


def _base_query():
    """Bölüm ve fakülteyi tek sorguda getirir (N+1 önlenir)."""
    return select(PhysicalFacility).options(
        selectinload(PhysicalFacility.department).selectinload(Department.faculty)
    )


def _department_name(facility: PhysicalFacility) -> Optional[str]:
    return facility.department.name if facility.department else None


def _faculty_name(facility: PhysicalFacility) -> Optional[str]:
    if facility.department and facility.department.faculty:
        return facility.department.faculty.name
    return None


def occupancy_status(percent: float) -> str:
    """Doluluk oranını üç bantta sınıflandırır."""
    if percent < UNDERUTILIZED_THRESHOLD:
        return "az kullanılıyor"
    if percent >= OVERCROWDED_THRESHOLD:
        return "aşırı dolu"
    return "yeterli"


def to_response_dict(facility: PhysicalFacility) -> dict:
    """SQLAlchemy nesnesini API cevabına uygun sözlüğe çevirir."""
    percent = facility.occupancy_percent
    return {
        "id": facility.id,
        "code": facility.code,
        "name": facility.name,
        "facility_type": facility.facility_type,
        "department_id": facility.department_id,
        "department_name": _department_name(facility),
        "faculty_name": _faculty_name(facility),
        "capacity": facility.capacity,
        "occupied": facility.occupied,
        "area_square_meters": facility.area_square_meters,
        "occupancy_percent": percent,
        "occupancy_status": occupancy_status(percent),
        "is_active": facility.is_active,
    }


# ----------------------------------------------------------------------------
# CRUD
# ----------------------------------------------------------------------------


def list_facilities(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    facility_type: Optional[str] = None,
    department_id: Optional[int] = None,
    include_inactive: bool = False,
) -> List[PhysicalFacility]:
    """Filtrelenebilir mekân listesi."""
    query = _base_query()
    if not include_inactive:
        query = query.where(PhysicalFacility.is_active.is_(True))
    if facility_type:
        _validate_type(facility_type)
        query = query.where(PhysicalFacility.facility_type == facility_type)
    if department_id is not None:
        query = query.where(PhysicalFacility.department_id == department_id)
    query = query.order_by(PhysicalFacility.code).offset(skip).limit(limit)
    return list(db.execute(query).scalars().unique())


def _validate_type(facility_type: str) -> None:
    """Tesis türünü sabit listeye göre doğrular."""
    if facility_type not in FACILITY_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"'{facility_type}' geçerli bir tesis türü değil. "
                f"Kullanılabilir değerler: {', '.join(FACILITY_TYPES)}."
            ),
        )


def get_facility(db: Session, facility_id: int) -> PhysicalFacility:
    """Tek mekân; bulunamazsa 404."""
    facility = (
        db.execute(_base_query().where(PhysicalFacility.id == facility_id))
        .scalars()
        .first()
    )
    if facility is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{facility_id} numaralı mekân bulunamadı.",
        )
    return facility


def create_facility(db: Session, payload: PhysicalFacilityCreate) -> PhysicalFacility:
    """Yeni mekân; kod tekrarında 409, bölüm yoksa 404."""
    _validate_type(payload.facility_type)

    existing = db.execute(
        select(PhysicalFacility).where(PhysicalFacility.code == payload.code)
    ).scalars().first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"'{payload.code}' kodlu mekân zaten kayıtlı.",
        )

    if payload.department_id is not None and db.get(Department, payload.department_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{payload.department_id} numaralı bölüm bulunamadı.",
        )

    facility = PhysicalFacility(**payload.model_dump())
    db.add(facility)
    db.commit()
    db.refresh(facility)
    return facility


def update_facility(
    db: Session, facility_id: int, payload: PhysicalFacilityUpdate
) -> PhysicalFacility:
    """Kısmi güncelleme; doluluk/kapasite tutarlılığı burada da kontrol edilir."""
    facility = get_facility(db, facility_id)
    data = payload.model_dump(exclude_unset=True)

    if "facility_type" in data:
        _validate_type(data["facility_type"])
    if data.get("department_id") is not None and db.get(Department, data["department_id"]) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{data['department_id']} numaralı bölüm bulunamadı.",
        )

    # Kısmi güncellemede yalnızca bir alan gelebilir; bu yüzden tutarlılık
    # kontrolü güncel değerlerle birlikte yapılmalı.
    new_capacity = data.get("capacity", facility.capacity)
    new_occupied = data.get("occupied", facility.occupied)
    if new_occupied > new_capacity:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Doluluk ({new_occupied}) kapasiteden ({new_capacity}) büyük olamaz.",
        )

    for field, value in data.items():
        setattr(facility, field, value)
    db.commit()
    db.refresh(facility)
    return facility


def deactivate_facility(db: Session, facility_id: int) -> PhysicalFacility:
    """Mekân kaydı silinmez, pasifleştirilir."""
    facility = get_facility(db, facility_id)
    facility.is_active = False
    db.commit()
    db.refresh(facility)
    return facility


# ----------------------------------------------------------------------------
# Kapasite analizleri
# ----------------------------------------------------------------------------


def _active_facilities(db: Session) -> List[PhysicalFacility]:
    return list_facilities(db, skip=0, limit=100_000)


def _require_data(facilities: List[PhysicalFacility]) -> None:
    """Veri yokken sıfır dolu bir rapor üretmemek için 404 döner."""
    if not facilities:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fiziksel mekân verisi girilmemiş. Önce mekân kaydı ekleyin.",
        )


def utilization_by_type(db: Session) -> List[dict]:
    """Tesis türüne göre toplam kapasite ve ortalama kullanım oranı."""
    facilities = _active_facilities(db)
    _require_data(facilities)

    groups: Dict[str, dict] = {}
    for facility in facilities:
        bucket = groups.setdefault(
            facility.facility_type, {"capacity": 0, "occupied": 0, "count": 0}
        )
        bucket["capacity"] += facility.capacity
        bucket["occupied"] += facility.occupied
        bucket["count"] += 1

    result = []
    for ftype, data in groups.items():
        utilization = (
            round((data["occupied"] / data["capacity"]) * 100, 2)
            if data["capacity"]
            else 0.0
        )
        result.append(
            {
                "facility_type": ftype,
                "facility_count": data["count"],
                "total_capacity": data["capacity"],
                "total_occupied": data["occupied"],
                "average_utilization_percent": utilization,
            }
        )
    result.sort(key=lambda row: row["total_capacity"], reverse=True)
    return result


def allocation_by_department(db: Session) -> List[dict]:
    """Bölüm bazlı alan/kapasite dağılımı."""
    facilities = _active_facilities(db)
    _require_data(facilities)

    groups: Dict[str, dict] = {}
    for facility in facilities:
        # Bölümü olmayan ortak alanlar ayrı bir grupta toplanıyor; başka bir
        # bölüme dağıtmak dağılım raporunu yanıltır.
        key = _department_name(facility) or "Ortak kullanım"
        bucket = groups.setdefault(
            key,
            {
                "faculty": _faculty_name(facility) or "Ortak",
                "count": 0,
                "capacity": 0,
                "area": 0,
                "has_area": False,
            },
        )
        bucket["count"] += 1
        bucket["capacity"] += facility.capacity
        if facility.area_square_meters:
            bucket["area"] += facility.area_square_meters
            bucket["has_area"] = True

    result = [
        {
            "department_name": key,
            "faculty_name": data["faculty"],
            "facility_count": data["count"],
            "total_capacity": data["capacity"],
            # Hiç metrekare girilmemişse 0 yerine None: "ölçüm yok" ile
            # "sıfır metrekare" farklı şeyler.
            "total_area_square_meters": data["area"] if data["has_area"] else None,
        }
        for key, data in groups.items()
    ]
    result.sort(key=lambda row: row["total_capacity"], reverse=True)
    return result


def space_per_person(db: Session) -> dict:
    """Aktif öğrenci ve personel başına düşen kapasite."""
    facilities = _active_facilities(db)
    _require_data(facilities)

    total_capacity = sum(f.capacity for f in facilities)
    areas = [f.area_square_meters for f in facilities if f.area_square_meters]
    total_area = sum(areas) if areas else None

    # Sayılar sabit değil, veritabanından geliyor.
    student_count = db.execute(
        select(func.count(Student.id)).where(Student.is_active.is_(True))
    ).scalar_one()
    staff_count = db.execute(
        select(func.count(AcademicStaff.id)).where(AcademicStaff.is_active.is_(True))
    ).scalar_one()

    return {
        "total_capacity": total_capacity,
        "total_area_square_meters": total_area,
        "active_student_count": student_count,
        "active_staff_count": staff_count,
        # Payda sıfırsa oran hesaplanmaz; uydurma değer yerine None döner.
        "capacity_per_student": (
            round(total_capacity / student_count, 3) if student_count else None
        ),
        "capacity_per_staff": (
            round(total_capacity / staff_count, 3) if staff_count else None
        ),
        "note": (
            "Öğrenci ve personel sayıları veritabanındaki aktif kayıtlardan sayıldı; "
            "sabit varsayım kullanılmadı."
        ),
    }


def _flagged(db: Session, above: bool) -> List[dict]:
    """Eşiğin altında veya üstünde kalan mekânları listeler."""
    facilities = _active_facilities(db)
    _require_data(facilities)

    rows = []
    for facility in facilities:
        percent = facility.occupancy_percent
        matches = (
            percent >= OVERCROWDED_THRESHOLD if above else percent < UNDERUTILIZED_THRESHOLD
        )
        if not matches:
            continue
        rows.append(
            {
                "id": facility.id,
                "code": facility.code,
                "name": facility.name,
                "facility_type": facility.facility_type,
                "department_name": _department_name(facility),
                "capacity": facility.capacity,
                "occupied": facility.occupied,
                "occupancy_percent": percent,
            }
        )
    rows.sort(key=lambda row: row["occupancy_percent"], reverse=above)
    return rows


def underutilized_facilities(db: Session) -> List[dict]:
    """Doluluk oranı %50'nin altındaki mekânlar."""
    return _flagged(db, above=False)


def overcrowded_facilities(db: Session) -> List[dict]:
    """Doluluk oranı %90 ve üzerindeki mekânlar."""
    return _flagged(db, above=True)


def forecast_capacity_need(db: Session, expected_growth_percent: float) -> dict:
    """Öğrenci artışının mevcut kapasiteye etkisini projeksiyonlar."""
    facilities = _active_facilities(db)
    _require_data(facilities)

    total_capacity = sum(f.capacity for f in facilities)
    total_occupied = sum(f.occupied for f in facilities)
    projected = round(total_occupied * (1 + expected_growth_percent / 100), 1)
    projected_percent = (
        round((projected / total_capacity) * 100, 2) if total_capacity else 0.0
    )
    shortfall = round(max(0.0, projected - total_capacity), 1)

    if shortfall > 0:
        assessment = (
            f"Öngörülen artışta {shortfall:.0f} kişilik kapasite açığı oluşuyor; "
            "ek mekân planlaması gerekir."
        )
    elif projected_percent >= OVERCROWDED_THRESHOLD:
        assessment = (
            "Kapasite yetiyor ancak doluluk kritik seviyeye çıkıyor; "
            "yedek kapasite kalmıyor."
        )
    else:
        assessment = "Mevcut kapasite öngörülen artışı karşılıyor."

    return {
        "expected_growth_percent": expected_growth_percent,
        "current_capacity": total_capacity,
        "current_occupied": total_occupied,
        "projected_occupied": projected,
        "projected_occupancy_percent": projected_percent,
        "is_sufficient": shortfall == 0,
        "shortfall": shortfall,
        "assessment": assessment,
    }


def capacity_overview(db: Session) -> dict:
    """Modül 5 özet göstergeleri."""
    facilities = _active_facilities(db)
    _require_data(facilities)

    total_capacity = sum(f.capacity for f in facilities)
    total_occupied = sum(f.occupied for f in facilities)

    return {
        "total_facilities": len(facilities),
        "total_capacity": total_capacity,
        "total_occupied": total_occupied,
        "overall_occupancy_percent": (
            round((total_occupied / total_capacity) * 100, 2) if total_capacity else 0.0
        ),
        "underutilized_count": sum(
            1 for f in facilities if f.occupancy_percent < UNDERUTILIZED_THRESHOLD
        ),
        "overcrowded_count": sum(
            1 for f in facilities if f.occupancy_percent >= OVERCROWDED_THRESHOLD
        ),
        "by_type": utilization_by_type(db),
    }
