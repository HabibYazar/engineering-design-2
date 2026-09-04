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

from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:  # yalnızca tip ipucu; döngüsel import olmasın
    from app.services.scope import Scope

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models import AcademicStaff, Department, PhysicalFacility, Student
from app.services import staff_scope
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
        selectinload(PhysicalFacility.department).selectinload(Department.faculty),
        selectinload(PhysicalFacility.faculty),
    )


def _department_name(facility: PhysicalFacility) -> Optional[str]:
    return facility.department.name if facility.department else None


def _faculty_name(facility: PhysicalFacility) -> Optional[str]:
    # Derslikler doğrudan fakülteye bağlıdır (part3); diğer mekânlar
    # bölüm üzerinden fakülteye ulaşır.
    if facility.faculty is not None:
        return facility.faculty.name
    if facility.department and facility.department.faculty:
        return facility.department.faculty.name
    return None


def occupancy_status(percent: Optional[float]) -> str:
    """Doluluk oranını üç bantta sınıflandırır.

    Ölçüm yoksa "az kullanılıyor" DEMEZ: envanterden gelen bir derslik
    kullanım verisi olmadığı için boş görünürdü ve kapasite fazlası
    sanılırdı.
    """
    if percent is None:
        return "ölçülmedi"
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
        "faculty_id": facility.faculty_id,
        "capacity": facility.capacity,
        # Ders planlamasında kullanılabilir kapasite (part3 envanteri).
        "student_capacity": facility.student_capacity,
        "floor": facility.floor,
        "owner_label": facility.owner_label,
        "room_label": facility.room_label,
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
    scope: Optional["Scope"] = None,
) -> List[PhysicalFacility]:
    """Filtrelenebilir mekân listesi; analiz çağrısında kapsam zorunlu.

    Program düzeyinde mekân tahsisi kaynakta bulunmadığı için bölümün
    mekânına düşülmez ve boş liste döner. Bu, program ekranında ebeveyn
    kapasitesinin program kapasitesi gibi sunulmasını engeller.
    """
    if scope is not None and scope.level == "program":
        return []
    query = _base_query()
    if not include_inactive:
        query = query.where(PhysicalFacility.is_active.is_(True))
    if facility_type:
        _validate_type(facility_type)
        query = query.where(PhysicalFacility.facility_type == facility_type)
    if department_id is not None:
        query = query.where(PhysicalFacility.department_id == department_id)
    if scope is not None and scope.department_ids is not None:
        bolumler = tuple(scope.department_ids)
        if scope.level == "faculty":
            fakulteler = tuple(scope.faculty_ids or ())
            query = query.where(or_(
                PhysicalFacility.department_id.in_(bolumler or (-1,)),
                PhysicalFacility.faculty_id.in_(fakulteler or (-1,)),
            ))
        else:
            # Bölüm düzeyinde yalnızca doğrudan o bölüme tahsisli mekân.
            # Fakülteye tahsisli derslikler bütün bölümlere kopyalanmaz.
            query = query.where(
                PhysicalFacility.department_id.in_(bolumler or (-1,)))
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


def _active_facilities(
    db: Session, scope: Optional["Scope"] = None
) -> List[PhysicalFacility]:
    """Aktif mekânlar — kapsam verilmişse yalnızca o kapsamdakiler.

    KAPSAM KURALI
    -------------
    Süzme `PhysicalFacility.department_id` ÜZERİNDEN yapılır; bölüm adı
    eşleştirilmez. Bölümü olmayan ("Ortak kullanım") mekânlar dar kapsamda
    DIŞARIDA kalır: ortak bir amfiyi bir fakültenin kapasitesi gibi
    saymak, düzeltmeye çalıştığımız sızıntının ta kendisidir.

    Program kapsamında mekân verisi yoktur — mekânlar bölüme bağlanır —
    bu yüzden bölümün mekânı programa kopyalanmaz ve ölçüm açıkça
    kullanılamaz kalır.

    DERSLİK ENVANTERİ FAKÜLTEYE BAĞLIDIR (part3). Kaynak dosya sahipliği
    MMF / İTBF / GSTF gibi FAKÜLTE kısaltmalarıyla verir; bu yüzden
    süzme hem `department_id` hem `faculty_id` üzerinden yürür. İkisi de
    boş olan mekân (Hazırlık Okulu, ortak amfi) yalnızca ÜNİVERSİTE
    kapsamında görünür — bir fakültenin kapasitesi gibi sayılmaz.
    """
    return list_facilities(db, skip=0, limit=100_000, scope=scope)


def _require_data(facilities: List[PhysicalFacility]) -> None:
    """Veri yokken sıfır dolu bir rapor üretmemek için 404 döner."""
    if not facilities:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fiziksel mekân verisi girilmemiş. Önce mekân kaydı ekleyin.",
        )


def utilization_by_type(db: Session, scope: Optional["Scope"] = None) -> List[dict]:
    """Tesis türüne göre toplam kapasite ve ortalama kullanım oranı."""
    facilities = _active_facilities(db, scope)
    _require_data(facilities)

    groups: Dict[str, dict] = {}
    for facility in facilities:
        bucket = groups.setdefault(
            facility.facility_type,
            {"capacity": 0, "student_capacity": 0, "occupied": 0,
             "occupied_measured": 0, "count": 0},
        )
        bucket["capacity"] += facility.capacity or 0
        bucket["student_capacity"] += facility.student_capacity or 0
        if facility.occupied is not None:
            bucket["occupied"] += facility.occupied
            bucket["occupied_measured"] += 1
        bucket["count"] += 1

    result = []
    for ftype, data in groups.items():
        # Kullanım ölçülmemişse oran YOK; 0.0 "boş" demek olurdu.
        utilization = (
            round((data["occupied"] / data["capacity"]) * 100, 2)
            if data["capacity"] and data["occupied_measured"]
            else None
        )
        result.append(
            {
                "facility_type": ftype,
                "facility_count": data["count"],
                "total_capacity": data["capacity"] or None,
                "total_student_capacity": data["student_capacity"] or None,
                "total_occupied": (data["occupied"]
                                   if data["occupied_measured"] else None),
                "average_utilization_percent": utilization,
            }
        )
    result.sort(key=lambda row: row["total_capacity"] or 0, reverse=True)
    return result


def allocation_by_department(db: Session, scope: Optional["Scope"] = None) -> List[dict]:
    """Bölüm bazlı alan/kapasite dağılımı."""
    facilities = _active_facilities(db, scope)
    _require_data(facilities)

    groups: Dict[str, dict] = {}
    for facility in facilities:
        # Bölümü olmayan ortak alanlar ayrı bir grupta toplanıyor; başka bir
        # bölüme dağıtmak dağılım raporunu yanıltır.
        # Derslikler FAKÜLTEYE tahsislidir; bölüm adı yoktur. Bu yüzden
        # gruplama bölüm → fakülte → ham sahiplik etiketi sırasıyla en
        # bilinen birime düşer; hepsi boşsa "Ortak kullanım" kalır.
        key = (_department_name(facility) or _faculty_name(facility)
               or facility.owner_label or "Ortak kullanım")
        bucket = groups.setdefault(
            key,
            {
                "faculty": _faculty_name(facility) or "Ortak",
                "count": 0,
                "capacity": 0,
                "capacity_measured": 0,
                "student_capacity": 0,
                "area": 0,
                "has_area": False,
            },
        )
        bucket["count"] += 1
        # Ölçülmemiş kapasite toplama girmez.
        if facility.capacity is not None:
            bucket["capacity"] += facility.capacity
            bucket["capacity_measured"] += 1
        if facility.student_capacity is not None:
            bucket["student_capacity"] += facility.student_capacity
        if facility.area_square_meters:
            bucket["area"] += facility.area_square_meters
            bucket["has_area"] = True

    result = [
        {
            "department_name": key,
            "faculty_name": data["faculty"],
            "facility_count": data["count"],
            "total_capacity": (data["capacity"]
                               if data["capacity_measured"] else None),
            "total_student_capacity": data["student_capacity"] or None,
            # Hiç metrekare girilmemişse 0 yerine None: "ölçüm yok" ile
            # "sıfır metrekare" farklı şeyler.
            "total_area_square_meters": data["area"] if data["has_area"] else None,
        }
        for key, data in groups.items()
    ]
    result.sort(key=lambda row: row["total_capacity"] or 0, reverse=True)
    return result


def space_per_person(db: Session, scope: Optional["Scope"] = None) -> dict:
    """Aktif öğrenci ve personel başına düşen kapasite."""
    facilities = _active_facilities(db, scope)
    _require_data(facilities)

    total_capacity = sum(f.capacity or 0 for f in facilities)
    areas = [f.area_square_meters for f in facilities if f.area_square_meters]
    total_area = sum(areas) if areas else None

    # Sayılar sabit değil, veritabanından geliyor. Kapasite kapsama göre
    # süzüldüyse payda da süzülmelidir; yoksa "fakültenin mekânı / tüm
    # üniversitenin öğrencisi" gibi anlamsız bir oran çıkar.
    # Kadro sayımı TEK kuraldan geçer (aktiflik + kapsam + en güncel yıl);
    # yıl süzgeci olmadan aynı kişi her yıl için tekrar sayılırdı.
    personel_sorgu = staff_scope.apply_staff_filters(
        select(func.count(func.distinct(AcademicStaff.id)))
        .select_from(AcademicStaff), db, scope)

    # ÖĞRENCİ SAYISI resmî kaynaktan gelir (bkz. student_count.py):
    # bireysel öğrenci kaydı olmayan gerçek veride `Student` tablosu
    # boştur ve "kişi başına kapasite" sonsuz/anlamsız çıkardı.
    from app.services import student_count as ogrenci_sayisi_servisi

    student_count = ogrenci_sayisi_servisi.total_for_scope(db, scope) or 0
    staff_count = db.execute(personel_sorgu).scalar_one()

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


def _flagged(db: Session, above: bool, scope: Optional["Scope"] = None) -> List[dict]:
    """Eşiğin altında veya üstünde kalan mekânları listeler."""
    facilities = _active_facilities(db, scope)
    _require_data(facilities)

    rows = []
    for facility in facilities:
        percent = facility.occupancy_percent
        if percent is None:
            continue          # ölçülmemiş mekân "az/aşırı dolu" sayılmaz
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


def underutilized_facilities(db: Session, scope: Optional["Scope"] = None) -> List[dict]:
    """Doluluk oranı %50'nin altındaki mekânlar."""
    return _flagged(db, above=False, scope=scope)


def overcrowded_facilities(db: Session, scope: Optional["Scope"] = None) -> List[dict]:
    """Doluluk oranı %90 ve üzerindeki mekânlar."""
    return _flagged(db, above=True, scope=scope)


def forecast_capacity_need(db: Session, expected_growth_percent: float,
                           scope: Optional["Scope"] = None) -> dict:
    """Öğrenci artışının mevcut kapasiteye etkisini projeksiyonlar."""
    facilities = _active_facilities(db, scope)
    _require_data(facilities)

    total_capacity = sum(f.capacity or 0 for f in facilities)
    # Kullanım ölçülmemişse projeksiyon yapılamaz; 0 varsaymak
    # "kapasite bol" sonucunu uydururdu.
    olculen_kullanim = [f.occupied for f in facilities if f.occupied is not None]
    if not olculen_kullanim:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=("Kapasite projeksiyonu için kullanım (doluluk) ölçümü "
                    "gerekir; envanterde bu ölçüm bulunmuyor."),
        )
    total_occupied = sum(olculen_kullanim)
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


def capacity_overview(db: Session, scope: Optional["Scope"] = None) -> dict:
    """Kapasite özeti.

    ÖLÇÜLMEMİŞ DEĞER TOPLAMA GİRMEZ. part3 derslik envanterinde kullanım
    (doluluk) ölçümü yoktur; `occupied` NULL'dur ve 0 sayılmaz. Aksi
    hâlde 80 derslik "tamamen boş" görünür, kapasite fazlası sanılırdı.
    """
    facilities = _active_facilities(db, scope)
    _require_data(facilities)

    kapasiteler = [f.capacity for f in facilities if f.capacity is not None]
    ogrenci_kap = [f.student_capacity for f in facilities
                   if f.student_capacity is not None]
    kullanim = [f.occupied for f in facilities if f.occupied is not None]
    olculen = [f.occupancy_percent for f in facilities
               if f.occupancy_percent is not None]

    total_capacity = sum(kapasiteler)
    total_occupied = sum(kullanim) if kullanim else None

    return {
        "total_facilities": len(facilities),
        "total_capacity": total_capacity or None,
        "capacity_measured_count": len(kapasiteler),
        #: Ders planlamasında kullanılabilir öğrenci kapasitesi (part3).
        "total_student_capacity": sum(ogrenci_kap) if ogrenci_kap else None,
        "student_capacity_measured_count": len(ogrenci_kap),
        "total_occupied": total_occupied,
        "occupancy_measured_count": len(kullanim),
        "overall_occupancy_percent": (
            round((total_occupied / total_capacity) * 100, 2)
            if total_capacity and total_occupied is not None else None
        ),
        "underutilized_count": (sum(1 for d in olculen
                                    if d < UNDERUTILIZED_THRESHOLD)
                                if olculen else None),
        "overcrowded_count": (sum(1 for d in olculen
                                  if d >= OVERCROWDED_THRESHOLD)
                              if olculen else None),
        # KAPSAM aktarılır: özet ile tür kırılımı aynı kümeyi göstermeli.
        "by_type": utilization_by_type(db, scope),
    }
