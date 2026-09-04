"""Akademik başarı analizi endpoint'leri.

Genelden özele: üniversite → fakülte → bölüm → program.
Bu router hesap yapmaz; academic_success_service'i çağırır.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.academic_success import (
    DepartmentSuccessRow,
    FacultySuccessRow,
    ProgramSuccessRow,
    SuccessCorrelations,
    SuccessRankings,
    SuccessTrendPoint,
    UniversitySuccessOverview,
)
from app.services import academic_success_service as service
from app.services.scope import resolve, scope_params

router = APIRouter(prefix="/api/academic-success", tags=["Akademik Başarı"])

# Sabit yollar parametreli yoldan önce tanımlandı.


@router.get(
    "/academic-years",
    response_model=List[str],
    summary="Başarı verisi bulunan dönemler",
)
def get_academic_years(db: Session = Depends(get_db)) -> List[str]:
    """Dönem seçicinin beslendiği liste."""
    return service.available_years(db)


@router.get(
    "/overview",
    response_model=UniversitySuccessOverview,
    summary="Üniversite geneli başarı özeti",
)
def get_overview(
    academic_year: str = Query(examples=["2025-2026"]),
    kapsam: dict = Depends(scope_params),
    db: Session = Depends(get_db),
) -> UniversitySuccessOverview:
    """Ders geçme, başarısızlık, bırakma ve mezuniyet oranlarının kurum geneli özeti.

    Oranlar fakülte ve bölüm satırlarından değil, en alt kırılım olan program
    satırlarından öğrenci sayısına göre ağırlıklı ortalamayla hesaplanır.
    """
    return UniversitySuccessOverview(**service.university_overview(db, academic_year, resolve(db, **kapsam)))


@router.get(
    "/by-faculty",
    response_model=List[FacultySuccessRow],
    summary="Fakülte bazlı başarı",
)
def get_by_faculty(
    academic_year: str = Query(examples=["2025-2026"]),
    kapsam: dict = Depends(scope_params),
    db: Session = Depends(get_db),
) -> List[FacultySuccessRow]:
    """Fakülteleri ders geçme oranına göre sıralı döndürür."""
    return [FacultySuccessRow(**row) for row in service.by_faculty(db, academic_year, scope=resolve(db, **kapsam))]


@router.get(
    "/by-department",
    response_model=List[DepartmentSuccessRow],
    summary="Bölüm bazlı başarı",
)
def get_by_department(
    academic_year: str = Query(examples=["2025-2026"]),
    faculty_id: Optional[int] = Query(
        default=None, ge=1, description="Verilirse yalnızca o fakültenin bölümleri"
    ),
    kapsam: dict = Depends(scope_params),
    db: Session = Depends(get_db),
) -> List[DepartmentSuccessRow]:
    """Fakülte seçildiğinde o fakültenin bölümlerini gösterir (drill-down)."""
    return [
        DepartmentSuccessRow(**row)
        for row in service.by_department(db, academic_year, faculty_id, scope=resolve(db, **kapsam))
    ]


@router.get(
    "/by-program",
    response_model=List[ProgramSuccessRow],
    summary="Program bazlı başarı",
)
def get_by_program(
    academic_year: str = Query(examples=["2025-2026"]),
    faculty_id: Optional[int] = Query(default=None, ge=1),
    department_id: Optional[int] = Query(
        default=None, ge=1, description="Verilirse yalnızca o bölümün programları"
    ),
    kapsam: dict = Depends(scope_params),
    db: Session = Depends(get_db),
) -> List[ProgramSuccessRow]:
    """Bölüm seçildiğinde o bölümün programlarını gösterir (drill-down)."""
    return [
        ProgramSuccessRow(**row)
        for row in service.by_program(db, academic_year, faculty_id, department_id,
                           scope=resolve(db, **kapsam))
    ]


@router.get(
    "/trend",
    response_model=List[SuccessTrendPoint],
    summary="Akademik dönemlere göre başarı trendi",
)
def get_trend(
    faculty_id: Optional[int] = Query(default=None, ge=1),
    department_id: Optional[int] = Query(default=None, ge=1),
    academic_program_id: Optional[int] = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> List[SuccessTrendPoint]:
    """Filtre verilmezse üniversite geneli trendini döndürür."""
    return [
        SuccessTrendPoint(**row)
        for row in service.trend(db, faculty_id, department_id, academic_program_id,
                          scope=resolve(db, faculty_id, department_id,
                                        academic_program_id))
    ]


@router.get(
    "/rankings",
    response_model=SuccessRankings,
    summary="En başarılı ve en düşük başarılı birimler",
)
def get_rankings(
    academic_year: str = Query(examples=["2025-2026"]),
    level: str = Query(
        default="department", description="faculty | department | program"
    ),
    kapsam: dict = Depends(scope_params),
    db: Session = Depends(get_db),
) -> SuccessRankings:
    """Küçük birimlerin uç değerleri listeyi yanıltmasın diye öğrenci eşiği uygulanır."""
    return SuccessRankings(**service.rankings(db, academic_year, level, resolve(db, **kapsam)))


@router.get(
    "/correlations",
    response_model=SuccessCorrelations,
    summary="Öğrenci sayısı ve akademisyen yükü ile başarı ilişkisi",
)
def get_correlations(
    academic_year: str = Query(examples=["2025-2026"]),
    kapsam: dict = Depends(scope_params),
    db: Session = Depends(get_db),
) -> SuccessCorrelations:
    """Pearson korelasyonu hesaplar. Korelasyon nedensellik değildir; cevapta uyarı vardır."""
    return SuccessCorrelations(**service.correlations(db, academic_year, resolve(db, **kapsam)))
