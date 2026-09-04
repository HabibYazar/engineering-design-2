"""Fakülte kaynağının CRUD endpoint'leri."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
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
from app.services.unit_types import ACADEMIC_UNIT_TYPES, UNIT_TYPES

# prefix sayesinde bu dosyadaki tüm yollar /api/faculties ile başlar.
router = APIRouter(prefix="/api/faculties", tags=["Faculties"])

LABEL: str = "Fakülte"


@router.get("", response_model=List[FacultyResponse])
def list_faculties(
    skip: int = Query(default=0, ge=0, description="Atlanacak kayıt sayısı"),
    limit: int = Query(default=100, ge=1, le=500, description="Getirilecek kayıt sayısı"),
    is_active: Optional[bool] = Query(default=None, description="Aktiflik durumuna göre filtre"),
    unit_type: Optional[str] = Query(
        default=None,
        description="FACULTY | VOCATIONAL_SCHOOL | INSTITUTE | ADMINISTRATIVE",
    ),
    academic_only: bool = Query(
        default=False,
        description=(
            "true ise yalnızca AKADEMİK birimler döner (Rektörlük gibi idari "
            "birimler hariç). Akademik grafik ve karşılaştırmalar bunu kullanır."
        ),
    ),
    db: Session = Depends(get_db),
) -> List[Faculty]:
    """Üniversitenin alt birimlerini sayfalama (skip/limit) ile listeler.

    Bu tablo yalnızca fakülteleri değil, üniversitenin BÜTÜN üst düzey
    birimlerini tutar: fakülte, meslek yüksekokulu, enstitü ve idari birim
    (Rektörlük). Türü ayırt etmek için `unit_type` alanı döner; akademik
    grafik `academic_only=true` ile idari birimleri dışarıda bırakır.
    """
    # Kayıt sayısı büyüdüğünde tüm veriyi tek seferde döndürmek sunucuyu yorar.
    # Bu yüzden sayfalama zorunlu tutuldu.
    statement = select(Faculty)
    if is_active is not None:
        statement = statement.where(Faculty.is_active == is_active)
    if unit_type is not None:
        if unit_type not in UNIT_TYPES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"unit_type {', '.join(UNIT_TYPES)} değerlerinden biri olmalı.",
            )
        statement = statement.where(Faculty.unit_type == unit_type)
    if academic_only:
        statement = statement.where(Faculty.unit_type.in_(ACADEMIC_UNIT_TYPES))

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
