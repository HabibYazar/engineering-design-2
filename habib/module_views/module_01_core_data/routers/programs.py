"""Akademik program kaynağının CRUD endpoint'leri."""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AcademicProgram, Department
from app.schemas import (
    AcademicProgramCreate,
    AcademicProgramResponse,
    AcademicProgramUpdate,
)
from app.services import (
    apply_updates,
    ensure_code_is_unique,
    ensure_parent_exists,
    get_object_or_404,
)

router = APIRouter(prefix="/api/programs", tags=["Academic Programs"])

LABEL: str = "Akademik program"


@router.get("", response_model=List[AcademicProgramResponse])
def list_programs(
    skip: int = Query(default=0, ge=0, description="Atlanacak kayıt sayısı"),
    limit: int = Query(default=100, ge=1, le=500, description="Getirilecek kayıt sayısı"),
    department_id: Optional[int] = Query(default=None, gt=0, description="Bölüme göre filtre"),
    is_active: Optional[bool] = Query(default=None, description="Aktiflik durumuna göre filtre"),
    db: Session = Depends(get_db),
) -> List[AcademicProgram]:
    """Akademik programları sayfalama ve isteğe bağlı bölüm filtresi ile listeler."""
    statement = select(AcademicProgram)
    if department_id is not None:
        statement = statement.where(AcademicProgram.department_id == department_id)
    if is_active is not None:
        statement = statement.where(AcademicProgram.is_active == is_active)

    statement = statement.order_by(AcademicProgram.id).offset(skip).limit(limit)
    return list(db.execute(statement).scalars().all())


@router.get("/{program_id}", response_model=AcademicProgramResponse)
def get_program(program_id: int, db: Session = Depends(get_db)) -> AcademicProgram:
    """Tek bir akademik programı id ile getirir."""
    return get_object_or_404(db, AcademicProgram, program_id, LABEL)


@router.post("", response_model=AcademicProgramResponse, status_code=status.HTTP_201_CREATED)
def create_program(
    payload: AcademicProgramCreate,
    db: Session = Depends(get_db),
) -> AcademicProgram:
    """Yeni bir akademik program kaydı oluşturur."""
    # Program eklenmeden önce bağlanacağı bölümün varlığı doğrulanır.
    ensure_parent_exists(db, Department, payload.department_id, "Bölüm")
    ensure_code_is_unique(db, AcademicProgram, payload.code, LABEL)

    program = AcademicProgram(**payload.model_dump())
    db.add(program)
    db.commit()
    db.refresh(program)
    return program


@router.put("/{program_id}", response_model=AcademicProgramResponse)
def update_program(
    program_id: int,
    payload: AcademicProgramUpdate,
    db: Session = Depends(get_db),
) -> AcademicProgram:
    """Var olan bir akademik programı kısmi olarak günceller."""
    program = get_object_or_404(db, AcademicProgram, program_id, LABEL)
    update_data = payload.model_dump(exclude_unset=True)

    if "department_id" in update_data:
        ensure_parent_exists(db, Department, update_data["department_id"], "Bölüm")

    if "code" in update_data:
        ensure_code_is_unique(
            db, AcademicProgram, update_data["code"], LABEL, exclude_id=program_id
        )

    apply_updates(program, update_data)
    db.commit()
    db.refresh(program)
    return program


@router.delete("/{program_id}", response_model=AcademicProgramResponse)
def deactivate_program(program_id: int, db: Session = Depends(get_db)) -> AcademicProgram:
    """Programı silmez, is_active=False yaparak pasifleştirir."""
    program = get_object_or_404(db, AcademicProgram, program_id, LABEL)
    program.is_active = False
    db.commit()
    db.refresh(program)
    return program
