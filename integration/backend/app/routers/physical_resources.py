"""Modül 5 — Fiziksel kaynak ve kapasite endpoint'leri.

Entegrasyon notu: Eda'nın orijinal kodunda `/capacity` yolu hem
`classroom_routes.py` hem `capacity_routes.py` içinde tanımlıydı ve iki router
aynı uygulamaya eklendiği için ikincisi sessizce gölgede kalıyordu. Burada tek
router kullanılarak bu belirsizlik ortadan kaldırıldı.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.physical_resources import (
    AllocationByDepartmentItem,
    CapacityForecastResponse,
    CapacityOverview,
    FacilityFlagItem,
    PhysicalFacilityCreate,
    PhysicalFacilityResponse,
    PhysicalFacilityUpdate,
    SpacePerPersonResponse,
    UtilizationByTypeItem,
)
from app.services import physical_resources_service as service

router = APIRouter(
    prefix="/api/physical-resources", tags=["Modül 5 — Fiziksel Kaynaklar"]
)


# Sabit yollar parametreli yoldan önce tanımlandı.


@router.get(
    "/capacity/overview",
    response_model=CapacityOverview,
    summary="Kapasite özet göstergeleri",
)
def capacity_overview(db: Session = Depends(get_db)) -> CapacityOverview:
    """Toplam kapasite, doluluk ve tür bazlı dağılımı özetler."""
    return CapacityOverview(**service.capacity_overview(db))


@router.get(
    "/capacity/by-type",
    response_model=List[UtilizationByTypeItem],
    summary="Tesis türüne göre kullanım oranı",
)
def by_type(db: Session = Depends(get_db)) -> List[UtilizationByTypeItem]:
    """Derslik, laboratuvar, ofis gibi türlerin kullanım oranını verir."""
    return [UtilizationByTypeItem(**row) for row in service.utilization_by_type(db)]


@router.get(
    "/capacity/by-department",
    response_model=List[AllocationByDepartmentItem],
    summary="Bölüm bazlı alan dağılımı",
)
def by_department(db: Session = Depends(get_db)) -> List[AllocationByDepartmentItem]:
    """Hangi bölüme ne kadar kapasite ayrıldığını gösterir."""
    return [
        AllocationByDepartmentItem(**row) for row in service.allocation_by_department(db)
    ]


@router.get(
    "/capacity/per-person",
    response_model=SpacePerPersonResponse,
    summary="Kişi başına düşen kapasite",
)
def per_person(db: Session = Depends(get_db)) -> SpacePerPersonResponse:
    """Öğrenci ve personel sayıları veritabanından sayılarak hesaplanır."""
    return SpacePerPersonResponse(**service.space_per_person(db))


@router.get(
    "/capacity/underutilized",
    response_model=List[FacilityFlagItem],
    summary="Az kullanılan mekânlar (%50 altı)",
)
def underutilized(db: Session = Depends(get_db)) -> List[FacilityFlagItem]:
    """Doluluk oranı eşiğin altında kalan mekânları listeler."""
    return [FacilityFlagItem(**row) for row in service.underutilized_facilities(db)]


@router.get(
    "/capacity/overcrowded",
    response_model=List[FacilityFlagItem],
    summary="Aşırı dolu mekânlar (%90 üstü)",
)
def overcrowded(db: Session = Depends(get_db)) -> List[FacilityFlagItem]:
    """Doluluk oranı kritik eşiği aşan mekânları listeler."""
    return [FacilityFlagItem(**row) for row in service.overcrowded_facilities(db)]


@router.get(
    "/capacity/forecast",
    response_model=CapacityForecastResponse,
    summary="Büyüme senaryosunda kapasite projeksiyonu",
)
def forecast(
    growth_percent: float = Query(
        default=10.0,
        ge=-50.0,
        le=200.0,
        description="Beklenen öğrenci artış yüzdesi. Negatif değer küçülmeyi ifade eder.",
    ),
    db: Session = Depends(get_db),
) -> CapacityForecastResponse:
    """Verilen büyüme oranında kapasitenin yetip yetmeyeceğini hesaplar."""
    return CapacityForecastResponse(**service.forecast_capacity_need(db, growth_percent))


@router.get(
    "/facilities",
    response_model=List[PhysicalFacilityResponse],
    summary="Mekân listesi",
)
def list_facilities(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    facility_type: Optional[str] = Query(default=None, examples=["classroom"]),
    department_id: Optional[int] = Query(default=None, ge=1),
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> List[PhysicalFacilityResponse]:
    """Filtrelenebilir ve sayfalanabilir mekân listesi."""
    return [
        PhysicalFacilityResponse(**service.to_response_dict(facility))
        for facility in service.list_facilities(
            db, skip, limit, facility_type, department_id, include_inactive
        )
    ]


@router.post(
    "/facilities",
    response_model=PhysicalFacilityResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Yeni mekân ekle",
)
def create_facility(
    payload: PhysicalFacilityCreate, db: Session = Depends(get_db)
) -> PhysicalFacilityResponse:
    """Mekân kodu tekrar ederse 409, bölüm bulunamazsa 404 döner."""
    facility = service.create_facility(db, payload)
    return PhysicalFacilityResponse(
        **service.to_response_dict(service.get_facility(db, facility.id))
    )


@router.get(
    "/facilities/{facility_id}",
    response_model=PhysicalFacilityResponse,
    summary="Tek mekân bilgisi",
)
def get_facility(facility_id: int, db: Session = Depends(get_db)) -> PhysicalFacilityResponse:
    """Mekân bulunamazsa 404 döner."""
    return PhysicalFacilityResponse(
        **service.to_response_dict(service.get_facility(db, facility_id))
    )


@router.patch(
    "/facilities/{facility_id}",
    response_model=PhysicalFacilityResponse,
    summary="Mekân bilgilerini güncelle",
)
def update_facility(
    facility_id: int, payload: PhysicalFacilityUpdate, db: Session = Depends(get_db)
) -> PhysicalFacilityResponse:
    """Doluluk kapasiteyi aşarsa 422 döner."""
    service.update_facility(db, facility_id, payload)
    return PhysicalFacilityResponse(
        **service.to_response_dict(service.get_facility(db, facility_id))
    )


@router.delete(
    "/facilities/{facility_id}",
    response_model=PhysicalFacilityResponse,
    summary="Mekânı pasifleştir",
)
def deactivate_facility(
    facility_id: int, db: Session = Depends(get_db)
) -> PhysicalFacilityResponse:
    """Kayıt silinmez; kapasite geçmişi korunsun diye pasifleştirilir."""
    service.deactivate_facility(db, facility_id)
    return PhysicalFacilityResponse(
        **service.to_response_dict(service.get_facility(db, facility_id))
    )
