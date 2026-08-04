"""Bölüm kaynağının CRUD endpoint'leri."""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Department, Faculty
from app.schemas import DepartmentCreate, DepartmentResponse, DepartmentUpdate
from app.services import (
    apply_updates,
    ensure_code_is_unique,
    ensure_parent_exists,
    get_object_or_404,
)

router = APIRouter(prefix="/api/departments", tags=["Departments"])

LABEL: str = "Bölüm"


@router.get("", response_model=List[DepartmentResponse])
def list_departments(
    skip: int = Query(default=0, ge=0, description="Atlanacak kayıt sayısı"),
    limit: int = Query(default=100, ge=1, le=500, description="Getirilecek kayıt sayısı"),
    faculty_id: Optional[int] = Query(default=None, gt=0, description="Fakülteye göre filtre"),
    is_active: Optional[bool] = Query(default=None, description="Aktiflik durumuna göre filtre"),
    db: Session = Depends(get_db),
) -> List[Department]:
    """Bölümleri sayfalama ve isteğe bağlı fakülte filtresi ile listeler."""
    # faculty_id filtresi, arayüzde "bir fakültenin bölümleri" ekranı için eklendi.
    statement = select(Department)
    if faculty_id is not None:
        statement = statement.where(Department.faculty_id == faculty_id)
    if is_active is not None:
        statement = statement.where(Department.is_active == is_active)

    statement = statement.order_by(Department.id).offset(skip).limit(limit)
    return list(db.execute(statement).scalars().all())


@router.get("/{department_id}", response_model=DepartmentResponse)
def get_department(department_id: int, db: Session = Depends(get_db)) -> Department:
    """Tek bir bölümü id ile getirir."""
    return get_object_or_404(db, Department, department_id, LABEL)


@router.post("", response_model=DepartmentResponse, status_code=status.HTTP_201_CREATED)
def create_department(payload: DepartmentCreate, db: Session = Depends(get_db)) -> Department:
    """Yeni bir bölüm kaydı oluşturur."""
    # Önce bağlanacağı fakülte gerçekten var mı diye bakıyoruz.
    # Aksi halde veritabanı seviyesinde anlamsız bir hata alınırdı.
    ensure_parent_exists(db, Faculty, payload.faculty_id, "Fakülte")
    ensure_code_is_unique(db, Department, payload.code, LABEL)

    department = Department(**payload.model_dump())
    db.add(department)
    db.commit()
    db.refresh(department)
    return department


@router.put("/{department_id}", response_model=DepartmentResponse)
def update_department(
    department_id: int,
    payload: DepartmentUpdate,
    db: Session = Depends(get_db),
) -> Department:
    """Var olan bir bölümü kısmi olarak günceller."""
    department = get_object_or_404(db, Department, department_id, LABEL)
    update_data = payload.model_dump(exclude_unset=True)

    # Bölüm başka bir fakülteye taşınıyorsa yeni fakültenin geçerliliği kontrol edilir.
    if "faculty_id" in update_data:
        ensure_parent_exists(db, Faculty, update_data["faculty_id"], "Fakülte")

    if "code" in update_data:
        ensure_code_is_unique(db, Department, update_data["code"], LABEL, exclude_id=department_id)

    apply_updates(department, update_data)
    db.commit()
    db.refresh(department)
    return department


@router.delete("/{department_id}", response_model=DepartmentResponse)
def deactivate_department(department_id: int, db: Session = Depends(get_db)) -> Department:
    """Bölümü silmez, is_active=False yaparak pasifleştirir."""
    department = get_object_or_404(db, Department, department_id, LABEL)
    department.is_active = False
    db.commit()
    db.refresh(department)
    return department
