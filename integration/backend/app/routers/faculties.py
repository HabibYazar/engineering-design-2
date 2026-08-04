"""Fakülte kaynağının CRUD endpoint'leri."""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Faculty
from app.schemas import FacultyCreate, FacultyResponse, FacultyUpdate
from app.services import (
    apply_updates,
    ensure_code_is_unique,
    get_object_or_404,
)

# prefix sayesinde bu dosyadaki tüm yollar /api/faculties ile başlar.
router = APIRouter(prefix="/api/faculties", tags=["Faculties"])

LABEL: str = "Fakülte"


@router.get("", response_model=List[FacultyResponse])
def list_faculties(
    skip: int = Query(default=0, ge=0, description="Atlanacak kayıt sayısı"),
    limit: int = Query(default=100, ge=1, le=500, description="Getirilecek kayıt sayısı"),
    is_active: Optional[bool] = Query(default=None, description="Aktiflik durumuna göre filtre"),
    db: Session = Depends(get_db),
) -> List[Faculty]:
    """Fakülteleri sayfalama (skip/limit) ile listeler."""
    # Kayıt sayısı büyüdüğünde tüm veriyi tek seferde döndürmek sunucuyu yorar.
    # Bu yüzden sayfalama zorunlu tutuldu.
    statement = select(Faculty)
    if is_active is not None:
        statement = statement.where(Faculty.is_active == is_active)

    statement = statement.order_by(Faculty.id).offset(skip).limit(limit)
    return list(db.execute(statement).scalars().all())


@router.get("/{faculty_id}", response_model=FacultyResponse)
def get_faculty(faculty_id: int, db: Session = Depends(get_db)) -> Faculty:
    """Tek bir fakülteyi id ile getirir."""
    return get_object_or_404(db, Faculty, faculty_id, LABEL)


@router.post("", response_model=FacultyResponse, status_code=status.HTTP_201_CREATED)
def create_faculty(payload: FacultyCreate, db: Session = Depends(get_db)) -> Faculty:
    """Yeni bir fakülte kaydı oluşturur."""
    # Kod tekrarını veritabanı hatasına bırakmak yerine önce kontrol ediyoruz;
    # böylece istemciye anlamlı bir 409 mesajı dönebiliyoruz.
    ensure_code_is_unique(db, Faculty, payload.code, LABEL)

    faculty = Faculty(**payload.model_dump())
    db.add(faculty)
    db.commit()
    # refresh, veritabanının atadığı id ve created_at değerlerini nesneye yükler.
    db.refresh(faculty)
    return faculty


@router.put("/{faculty_id}", response_model=FacultyResponse)
def update_faculty(
    faculty_id: int,
    payload: FacultyUpdate,
    db: Session = Depends(get_db),
) -> Faculty:
    """Var olan bir fakülteyi kısmi olarak günceller."""
    faculty = get_object_or_404(db, Faculty, faculty_id, LABEL)

    # exclude_unset=True: istemcinin göndermediği alanlar güncellemeye dahil edilmez.
    update_data = payload.model_dump(exclude_unset=True)

    if "code" in update_data:
        ensure_code_is_unique(db, Faculty, update_data["code"], LABEL, exclude_id=faculty_id)

    apply_updates(faculty, update_data)
    db.commit()
    db.refresh(faculty)
    return faculty


@router.delete("/{faculty_id}", response_model=FacultyResponse)
def deactivate_faculty(faculty_id: int, db: Session = Depends(get_db)) -> Faculty:
    """Fakülteyi veritabanından silmez, is_active=False yaparak pasifleştirir."""
    # Fakülteye bağlı bölüm ve programlar olabileceği için gerçek silme yapmıyoruz.
    # Bu yaklaşım geçmiş verinin ve raporların korunmasını sağlar.
    faculty = get_object_or_404(db, Faculty, faculty_id, LABEL)
    faculty.is_active = False
    db.commit()
    db.refresh(faculty)
    return faculty
