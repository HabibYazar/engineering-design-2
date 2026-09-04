"""Modül 8 — Kurumsal performans (KPI) izleme endpoint'leri."""

from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.kpi import (
    KpiFacultyComparisonItem,
    KpiMeasurement,
    KpiScorecard,
    StrategicKpiCreate,
    StrategicKpiResponse,
    StrategicKpiUpdate,
)
from app.services import kpi_service as service
from app.services.scope import resolve, scope_params

router = APIRouter(prefix="/api/kpi", tags=["Modül 8 — Performans Yönetimi"])


# Sabit yollar parametreli yoldan önce tanımlandı.


@router.get(
    "/scorecard",
    response_model=KpiScorecard,
    summary="Kurumsal KPI karnesi",
)
def get_scorecard(
    academic_year: Optional[str] = Query(default=None, examples=["2025-2026"]),
    kapsam: dict = Depends(scope_params),
    db: Session = Depends(get_db),
) -> KpiScorecard:
    """Genel başarı oranı ve stratejik boyut bazlı dağılım.

    KPI'lar en fazla fakülte seviyesinde ölçülür; bölüm/program kapsamında
    "bu seviyede KPI ölçülmüyor" anlamına gelen 404 döner.
    """
    return KpiScorecard(**service.scorecard(db, academic_year, resolve(db, **kapsam)))


@router.get(
    "/dimensions",
    response_model=List[str],
    summary="Tanımlı stratejik boyutlar",
)
def list_dimensions(db: Session = Depends(get_db)) -> List[str]:
    """Filtre açılır listesini besler."""
    return service.list_dimensions(db)


@router.get(
    "/faculty-comparison",
    response_model=List[KpiFacultyComparisonItem],
    summary="Fakülte bazlı KPI karşılaştırması",
)
def faculty_comparison(
    academic_year: Optional[str] = Query(default=None, examples=["2025-2026"]),
    kapsam: dict = Depends(scope_params),
    db: Session = Depends(get_db),
) -> List[KpiFacultyComparisonItem]:
    """Yalnızca ölçüm girilmiş KPI'lar hesaba katılır.

    Fakülteler arası karşılaştırma ÜNİVERSİTE kapsamının işidir; fakülte
    kapsamında yalnızca o fakültenin satırı kalır.
    """
    return [
        KpiFacultyComparisonItem(**row)
        for row in service.faculty_comparison(db, academic_year, resolve(db, **kapsam))
    ]


@router.get(
    "/attention",
    response_model=List[StrategicKpiResponse],
    summary="Müdahale gerektiren KPI'lar",
)
def attention_list(
    academic_year: Optional[str] = Query(default=None, examples=["2025-2026"]),
    kapsam: dict = Depends(scope_params),
    db: Session = Depends(get_db),
) -> List[StrategicKpiResponse]:
    """Riskli ve gecikmeli KPI'ları en düşük başarıdan sıralar."""
    return [
        StrategicKpiResponse(**row)
        for row in service.attention_list(db, academic_year, resolve(db, **kapsam))
    ]


@router.get(
    "/missing-data",
    response_model=List[StrategicKpiResponse],
    summary="Ölçümü bulunmayan göstergeler",
)
def missing_data_list(
    academic_year: Optional[str] = Query(default=None, examples=["2025-2026"]),
    kapsam: dict = Depends(scope_params),
    db: Session = Depends(get_db),
) -> List[StrategicKpiResponse]:
    """Veri eksikliği bir performans sorunu değil, ölçüm eksiğidir.

    Bu göstergeler müdahale listesine girmez ve kurum ortalamasına dahil
    edilmez; ayrı olarak burada raporlanır.
    """
    return [
        StrategicKpiResponse(**row)
        for row in service.missing_data_list(db, academic_year, resolve(db, **kapsam))
    ]


@router.get(
    "",
    response_model=List[StrategicKpiResponse],
    summary="KPI listesi",
)
def list_kpis(
    academic_year: Optional[str] = Query(default=None, examples=["2025-2026"]),
    dimension: Optional[str] = Query(default=None),
    kpi_status: Optional[str] = Query(
        default=None, description="hedefte / gecikmeli / riskli / veri eksik"
    ),
    include_inactive: bool = Query(default=False),
    kapsam: dict = Depends(scope_params),
    db: Session = Depends(get_db),
) -> List[StrategicKpiResponse]:
    """Başarı oranı ve durum her istekte yeniden hesaplanır."""
    return [
        StrategicKpiResponse(**row)
        for row in service.list_kpis(
            db, academic_year, dimension, kpi_status, include_inactive,
            resolve(db, **kapsam),
        )
    ]


@router.post(
    "",
    response_model=StrategicKpiResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Yeni KPI tanımla",
)
def create_kpi(
    payload: StrategicKpiCreate, db: Session = Depends(get_db)
) -> StrategicKpiResponse:
    """Aynı yıl aynı isim varsa 409, eşikler ters girilmişse 422 döner."""
    kpi = service.create_kpi(db, payload)
    return StrategicKpiResponse(**service.evaluate(service.get_kpi(db, kpi.id), db))


@router.get(
    "/{kpi_id}",
    response_model=StrategicKpiResponse,
    summary="Tek KPI bilgisi",
)
def get_kpi(kpi_id: int, db: Session = Depends(get_db)) -> StrategicKpiResponse:
    """KPI bulunamazsa 404 döner."""
    return StrategicKpiResponse(**service.evaluate(service.get_kpi(db, kpi_id), db))


@router.patch(
    "/{kpi_id}",
    response_model=StrategicKpiResponse,
    summary="KPI tanımını veya eşiklerini güncelle",
)
def update_kpi(
    kpi_id: int, payload: StrategicKpiUpdate, db: Session = Depends(get_db)
) -> StrategicKpiResponse:
    """Eşikler yönetim tarafından yapılandırılabilir olduğu için burada değişir."""
    service.update_kpi(db, kpi_id, payload)
    return StrategicKpiResponse(**service.evaluate(service.get_kpi(db, kpi_id), db))


@router.post(
    "/{kpi_id}/measurements",
    response_model=StrategicKpiResponse,
    summary="Yeni ölçüm değeri kaydet",
)
def record_measurement(
    kpi_id: int, payload: KpiMeasurement, db: Session = Depends(get_db)
) -> StrategicKpiResponse:
    """Durum otomatik olarak yeniden hesaplanır."""
    service.record_measurement(db, kpi_id, payload)
    return StrategicKpiResponse(**service.evaluate(service.get_kpi(db, kpi_id), db))


@router.put(
    "/{kpi_id}/faculty-values/{faculty_id}",
    response_model=StrategicKpiResponse,
    summary="Fakülte kırılım değeri gir",
)
def set_faculty_value(
    kpi_id: int,
    faculty_id: int,
    value: Decimal = Body(embed=True, examples=[Decimal("4.20")]),
    db: Session = Depends(get_db),
) -> StrategicKpiResponse:
    """Fakülte bulunamazsa 404 döner."""
    service.set_faculty_value(db, kpi_id, faculty_id, value)
    return StrategicKpiResponse(**service.evaluate(service.get_kpi(db, kpi_id), db))


@router.delete(
    "/{kpi_id}",
    response_model=StrategicKpiResponse,
    summary="KPI'yı izlemeden çıkar",
)
def deactivate_kpi(kpi_id: int, db: Session = Depends(get_db)) -> StrategicKpiResponse:
    """Kayıt silinmez; ölçüm geçmişi korunsun diye pasifleştirilir."""
    service.deactivate_kpi(db, kpi_id)
    return StrategicKpiResponse(**service.evaluate(service.get_kpi(db, kpi_id), db))
