"""Eğitim ücreti uç noktaları (part3).

Kendi programlarımızın ücretleri KAPSAM DUYARLIDIR; rakip kıyası
tanımı gereği üniversite düzeyindedir ve kapsam parametresi almaz.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.tuition_fee import FEE_HALF_SCHOLARSHIP
from app.services import tuition_service as service
from app.services.scope import resolve, scope_params

router = APIRouter(prefix="/api/tuition", tags=["Eğitim Ücretleri"])


@router.get("/program-fees", summary="Kapsamdaki programların eğitim ücretleri")
def program_fees(
    academic_year: Optional[str] = Query(
        default=None, description="Boş bırakılırsa en güncel yıl."),
    kapsam: dict = Depends(scope_params),
    db: Session = Depends(get_db),
) -> dict:
    """Program/bölüm/fakülte/üniversite kapsamına göre ücret listesi."""
    return service.program_fees(db, resolve(db, **kapsam), academic_year)


@router.get("/trend", summary="Kapsamın yıllara göre ücret seyri")
def fee_trend(
    academic_year: Optional[str] = Query(
        default=None,
        description="Trend bu dönemde biter; boşsa bütün mevcut yıllar."),
    fee_type: str = Query(default=FEE_HALF_SCHOLARSHIP,
                          description="FULL | HALF | DISCOUNT | SCHOLARSHIP"),
    kapsam: dict = Depends(scope_params),
    db: Session = Depends(get_db),
) -> dict:
    return service.fee_trend(
        db, resolve(db, **kapsam), fee_type, academic_year)


@router.get("/competitors", summary="Rakip kurumlarla ücret kıyası")
def competitor_fees(
    academic_year: Optional[str] = Query(default=None),
    fee_type: str = Query(default=FEE_HALF_SCHOLARSHIP),
    level: Optional[str] = Query(
        default=None, description="LISANS | ONLISANS | HAZIRLIK | SAGLIK"),
    kapsam: dict = Depends(scope_params),
    db: Session = Depends(get_db),
) -> dict:
    """Kıyas KAPSAMI TAKİP EDER.

    Üniversite kapsamında kurum medyanları karşılaştırılır. Fakülte,
    bölüm ya da program seçiliyse yalnızca EŞDEĞER PROGRAMLAR
    karşılaştırılır; eşdeğeri olmayan kurum sonuca girmez ve yerine
    kurum geneli medyanı KONMAZ.
    """
    return service.scoped_competitor_comparison(
        db, resolve(db, **kapsam), academic_year, fee_type, level)
