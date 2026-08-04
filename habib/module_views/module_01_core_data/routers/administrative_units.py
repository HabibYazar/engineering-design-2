"""İdari birim kaynağının CRUD endpoint'leri."""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AdministrativeUnit
from app.schemas import (
    AdministrativeUnitCreate,
    AdministrativeUnitResponse,
    AdministrativeUnitUpdate,
)
from app.services import (
    apply_updates,
    ensure_code_is_unique,
    get_object_or_404,
)

router = APIRouter(prefix="/api/administrative-units", tags=["Administrative Units"])

LABEL: str = "İdari birim"


@router.get("", response_model=List[AdministrativeUnitResponse])
def list_administrative_units(
    skip: int = Query(default=0, ge=0, description="Atlanacak kayıt sayısı"),
    limit: int = Query(default=100, ge=1, le=500, description="Getirilecek kayıt sayısı"),
    is_active: Optional[bool] = Query(default=None, description="Aktiflik durumuna göre filtre"),
    db: Session = Depends(get_db),
) -> List[AdministrativeUnit]:
    """İdari birimleri sayfalama ile listeler."""
    statement = select(AdministrativeUnit)
    if is_active is not None:
        statement = statement.where(AdministrativeUnit.is_active == is_active)

    statement = statement.order_by(AdministrativeUnit.id).offset(skip).limit(limit)
    return list(db.execute(statement).scalars().all())


@router.get("/{unit_id}", response_model=AdministrativeUnitResponse)
def get_administrative_unit(unit_id: int, db: Session = Depends(get_db)) -> AdministrativeUnit:
    """Tek bir idari birimi id ile getirir."""
    return get_object_or_404(db, AdministrativeUnit, unit_id, LABEL)


@router.post("", response_model=AdministrativeUnitResponse, status_code=status.HTTP_201_CREATED)
def create_administrative_unit(
    payload: AdministrativeUnitCreate,
    db: Session = Depends(get_db),
) -> AdministrativeUnit:
    """Yeni bir idari birim kaydı oluşturur."""
    # İdari birimler bağımsız olduğu için sadece kod çakışması kontrol edilir.
    ensure_code_is_unique(db, AdministrativeUnit, payload.code, LABEL)

    unit = AdministrativeUnit(**payload.model_dump())
    db.add(unit)
    db.commit()
    db.refresh(unit)
    return unit


@router.put("/{unit_id}", response_model=AdministrativeUnitResponse)
def update_administrative_unit(
    unit_id: int,
    payload: AdministrativeUnitUpdate,
    db: Session = Depends(get_db),
) -> AdministrativeUnit:
    """Var olan bir idari birimi kısmi olarak günceller."""
    unit = get_object_or_404(db, AdministrativeUnit, unit_id, LABEL)
    update_data = payload.model_dump(exclude_unset=True)

    if "code" in update_data:
        ensure_code_is_unique(
            db, AdministrativeUnit, update_data["code"], LABEL, exclude_id=unit_id
        )

    apply_updates(unit, update_data)
    db.commit()
    db.refresh(unit)
    return unit


@router.delete("/{unit_id}", response_model=AdministrativeUnitResponse)
def deactivate_administrative_unit(
    unit_id: int,
    db: Session = Depends(get_db),
) -> AdministrativeUnit:
    """İdari birimi silmez, is_active=False yaparak pasifleştirir."""
    unit = get_object_or_404(db, AdministrativeUnit, unit_id, LABEL)
    unit.is_active = False
    db.commit()
    db.refresh(unit)
    return unit
