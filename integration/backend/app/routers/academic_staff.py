"""Modül 4 — Akademik personel ve performans endpoint'leri."""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.academic_staff import (
    AcademicStaffCreate,
    AcademicStaffResponse,
    AcademicStaffUpdate,
    StaffComparisonItem,
    StaffOverview,
    StaffScoreItem,
    StaffTrendItem,
)
from app.services import academic_staff_service as service

router = APIRouter(prefix="/api/academic-staff", tags=["Modül 4 — Akademik Personel"])


# NOT: Sabit yollar parametreli yoldan (/{staff_id}) önce tanımlanmalı.
# Aksi halde FastAPI "/overview" isteğini staff_id="overview" sanıp 422 döner.


@router.get(
    "/overview",
    response_model=StaffOverview,
    summary="Akademik personel özet göstergeleri",
)
def get_overview(
    academic_year: Optional[str] = Query(default=None, examples=["2025-2026"]),
    db: Session = Depends(get_db),
) -> StaffOverview:
    """Personel sayısı, toplam üretim ve unvan dağılımını özetler."""
    return StaffOverview(**service.staff_overview(db, academic_year))


@router.get(
    "/ranking",
    response_model=List[StaffScoreItem],
    summary="Ağırlıklı performans sıralaması",
)
def get_ranking(
    academic_year: Optional[str] = Query(default=None, examples=["2025-2026"]),
    department_id: Optional[int] = Query(default=None, ge=1),
    faculty_id: Optional[int] = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> List[StaffScoreItem]:
    """Personeli toplam puana göre sıralar; puan kırılımını da döndürür."""
    return [
        StaffScoreItem(**row)
        for row in service.rank_staff(db, academic_year, department_id, faculty_id)
    ]


@router.get(
    "/compare/{group_by}",
    response_model=List[StaffComparisonItem],
    summary="Bölüm / fakülte / unvan karşılaştırması",
)
def compare(
    group_by: str,
    academic_year: Optional[str] = Query(default=None, examples=["2025-2026"]),
    db: Session = Depends(get_db),
) -> List[StaffComparisonItem]:
    """`group_by` değeri department, faculty veya title olabilir."""
    return [
        StaffComparisonItem(**row) for row in service.compare_staff(db, group_by, academic_year)
    ]


@router.get(
    "/trend",
    response_model=List[StaffTrendItem],
    summary="Yıllara göre yayın ve atıf trendi",
)
def get_trend(db: Session = Depends(get_db)) -> List[StaffTrendItem]:
    """Akademik yıl bazında toplam üretimi döndürür."""
    return [StaffTrendItem(**row) for row in service.staff_trend(db)]


@router.get(
    "",
    response_model=List[AcademicStaffResponse],
    summary="Akademik personel listesi",
)
def list_staff(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    department_id: Optional[int] = Query(default=None, ge=1),
    faculty_id: Optional[int] = Query(default=None, ge=1),
    academic_year: Optional[str] = Query(default=None, examples=["2025-2026"]),
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> List[AcademicStaffResponse]:
    """Filtrelenebilir ve sayfalanabilir personel listesi."""
    return [
        AcademicStaffResponse(**service.to_response_dict(staff))
        for staff in service.list_staff(
            db, skip, limit, department_id, faculty_id, academic_year, include_inactive
        )
    ]


@router.post(
    "",
    response_model=AcademicStaffResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Yeni akademik personel ekle",
)
def create_staff(
    payload: AcademicStaffCreate, db: Session = Depends(get_db)
) -> AcademicStaffResponse:
    """Sicil numarası tekrar ederse 409, bölüm bulunamazsa 404 döner."""
    staff = service.create_staff(db, payload)
    return AcademicStaffResponse(**service.to_response_dict(service.get_staff(db, staff.id)))


@router.get(
    "/{staff_id}",
    response_model=AcademicStaffResponse,
    summary="Tek personel bilgisi",
)
def get_staff(staff_id: int, db: Session = Depends(get_db)) -> AcademicStaffResponse:
    """Personel bulunamazsa 404 döner."""
    return AcademicStaffResponse(**service.to_response_dict(service.get_staff(db, staff_id)))


@router.patch(
    "/{staff_id}",
    response_model=AcademicStaffResponse,
    summary="Personel bilgilerini güncelle",
)
def update_staff(
    staff_id: int, payload: AcademicStaffUpdate, db: Session = Depends(get_db)
) -> AcademicStaffResponse:
    """Yalnızca gönderilen alanlar güncellenir."""
    service.update_staff(db, staff_id, payload)
    return AcademicStaffResponse(**service.to_response_dict(service.get_staff(db, staff_id)))


@router.delete(
    "/{staff_id}",
    response_model=AcademicStaffResponse,
    summary="Personeli pasifleştir",
)
def deactivate_staff(staff_id: int, db: Session = Depends(get_db)) -> AcademicStaffResponse:
    """Kayıt silinmez; geçmiş raporlar bozulmasın diye is_active=False yapılır."""
    service.deactivate_staff(db, staff_id)
    return AcademicStaffResponse(**service.to_response_dict(service.get_staff(db, staff_id)))
