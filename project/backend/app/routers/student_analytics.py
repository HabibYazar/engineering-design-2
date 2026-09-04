"""Öğrenci analitiği endpoint'leri.

Router hiçbir hesaplama yapmaz; tüm analizler app/services altındaki
student_analytics_service, student_trend_service ve student_alert_service
modüllerinde yapılır.

NOT: Sabit yollar ("/overview", "/program-snapshots" vb.) parametreli
yollardan önce tanımlanmıştır.
"""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    AcademicProgram,
    ComparableUniversityProgram,
    ProgramEnrollmentSnapshot,
)
from app.schemas.student_analytics import (
    AlertSeverity,
    AlertsResponse,
    DepartmentAnalytics,
    FacultyAnalytics,
    ProgramAnalytics,
    ProgramComparisonResponse,
    ProgramDemandResponse,
    StudentOverview,
    TrendMetric,
    TrendResponse,
)
from app.schemas.students import (
    ComparableProgramCreate,
    ComparableProgramResponse,
    ComparableProgramUpdate,
    ProgramSnapshotCreate,
    ProgramSnapshotResponse,
    ProgramSnapshotUpdate,
)
from app.services.crud_helpers import apply_updates, get_object_or_404
from app.services.student_alert_service import build_alerts
from app.services.student_analytics_service import (
    build_department_analytics,
    build_faculty_analytics,
    build_overview,
    build_program_analytics,
    build_program_comparison,
    build_program_demand,
)
from app.services.scope import resolve, scope_params
from app.services.student_trend_service import build_trend

router = APIRouter(prefix="/api/student-analytics", tags=["Student Analytics"])

SNAPSHOT_LABEL: str = "Program snapshot"
COMPARISON_LABEL: str = "Karşılaştırma kaydı"

# Trend sorgularında varsayılan pencere: son 5 yıl.
DEFAULT_TREND_WINDOW: int = 5


def _ensure_program_exists(db: Session, program_id: int) -> AcademicProgram:
    """Akademik programın var olduğunu doğrular."""
    program: Optional[AcademicProgram] = db.get(AcademicProgram, program_id)
    if program is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Akademik program bulunamadı (id={program_id}).",
        )
    return program


def _ensure_snapshot_unique(
    db: Session,
    program_id: int,
    academic_year: str,
    exclude_id: Optional[int] = None,
) -> None:
    """Aynı program + akademik yıl snapshot'ı varsa 409 fırlatır."""
    statement = (
        select(ProgramEnrollmentSnapshot)
        .where(ProgramEnrollmentSnapshot.academic_program_id == program_id)
        .where(ProgramEnrollmentSnapshot.academic_year == academic_year)
    )
    if exclude_id is not None:
        statement = statement.where(ProgramEnrollmentSnapshot.id != exclude_id)

    if db.execute(statement).scalars().first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Bu program için {academic_year} akademik yılına ait snapshot zaten mevcut."
            ),
        )


# ===========================================================================
# ANALİTİK ENDPOINT'LERİ
# ===========================================================================


@router.get("/overview", response_model=StudentOverview, summary="Genel öğrenci özeti")
def get_overview(
    faculty_id: Optional[int] = Query(default=None, gt=0),
    department_id: Optional[int] = Query(default=None, gt=0),
    academic_program_id: Optional[int] = Query(default=None, gt=0),
    academic_year: Optional[str] = Query(default=None, description="YYYY-YYYY"),
    db: Session = Depends(get_db),
) -> StudentOverview:
    """Öğrenci sayıları, oranlar ve akademik başarı özetini döndürür."""
    return build_overview(
        db, faculty_id, department_id, academic_program_id, academic_year,
        resolve(db, faculty_id, department_id, academic_program_id),
    )


@router.get(
    "/by-program",
    response_model=List[ProgramAnalytics],
    summary="Program bazlı analitik",
)
def get_by_program(
    faculty_id: Optional[int] = Query(default=None, gt=0),
    department_id: Optional[int] = Query(default=None, gt=0),
    academic_program_id: Optional[int] = Query(default=None, gt=0),
    academic_year: Optional[str] = Query(default=None, description="YYYY-YYYY"),
    db: Session = Depends(get_db),
) -> List[ProgramAnalytics]:
    """Her akademik program için doluluk, mezuniyet, kayıp ve başarı metriklerini döndürür."""
    return build_program_analytics(
        db, faculty_id, department_id, academic_program_id, academic_year,
        resolve(db, faculty_id, department_id, academic_program_id),
    )


@router.get(
    "/by-department",
    response_model=List[DepartmentAnalytics],
    summary="Bölüm bazlı analitik",
)
def get_by_department(
    faculty_id: Optional[int] = Query(default=None, gt=0),
    department_id: Optional[int] = Query(default=None, gt=0),
    academic_program_id: Optional[int] = Query(default=None, gt=0),
    academic_year: Optional[str] = Query(default=None, description="YYYY-YYYY"),
    db: Session = Depends(get_db),
) -> List[DepartmentAnalytics]:
    """Program sonuçlarını bölüm düzeyinde birleştirir.

    `academic_program_id` verilirse yalnızca o programın bölümü kalır;
    kardeş bölümler listeye giremez.
    """
    return build_department_analytics(
        db, faculty_id, department_id, academic_year,
        resolve(db, faculty_id, department_id, academic_program_id),
    )


@router.get(
    "/by-faculty",
    response_model=List[FacultyAnalytics],
    summary="Fakülte bazlı analitik",
)
def get_by_faculty(
    faculty_id: Optional[int] = Query(default=None, gt=0),
    department_id: Optional[int] = Query(default=None, gt=0),
    academic_program_id: Optional[int] = Query(default=None, gt=0),
    academic_year: Optional[str] = Query(default=None, description="YYYY-YYYY"),
    db: Session = Depends(get_db),
) -> List[FacultyAnalytics]:
    """Bölüm sonuçlarını fakülte düzeyinde birleştirir.

    Üniversite kapsamında yalnızca AKADEMİK birimler döner; Rektörlük
    gibi idari birimler fakülte karşılaştırmasında yer almaz.
    """
    return build_faculty_analytics(
        db, faculty_id, academic_year,
        resolve(db, faculty_id, department_id, academic_program_id),
    )


@router.get("/trends", response_model=TrendResponse, summary="Yıllara göre trend")
def get_trends(
    metric: TrendMetric = Query(..., description="İzlenecek metrik"),
    start_year: Optional[int] = Query(default=None, ge=1950, le=2100),
    end_year: Optional[int] = Query(default=None, ge=1950, le=2100),
    faculty_id: Optional[int] = Query(default=None, gt=0),
    department_id: Optional[int] = Query(default=None, gt=0),
    academic_program_id: Optional[int] = Query(default=None, gt=0),
    db: Session = Depends(get_db),
) -> TrendResponse:
    """Seçilen metriğin yıllara göre gelişimini ve değişim yüzdelerini döndürür."""
    # Yıl aralığı verilmezse son DEFAULT_TREND_WINDOW yıl kullanılır.
    current_year: int = datetime.now().year
    resolved_end: int = end_year if end_year is not None else current_year
    resolved_start: int = (
        start_year if start_year is not None else resolved_end - DEFAULT_TREND_WINDOW + 1
    )

    if resolved_start > resolved_end:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=[
                {
                    "loc": ["query", "start_year"],
                    "msg": (
                        f"Başlangıç yılı ({resolved_start}) bitiş yılından "
                        f"({resolved_end}) büyük olamaz."
                    ),
                    "type": "value_error",
                }
            ],
        )

    return build_trend(
        db,
        metric,
        resolved_start,
        resolved_end,
        faculty_id,
        department_id,
        academic_program_id,
    )


@router.get("/alerts", response_model=AlertsResponse, summary="Erken uyarılar")
def get_alerts(
    faculty_id: Optional[int] = Query(default=None, gt=0),
    department_id: Optional[int] = Query(default=None, gt=0),
    academic_program_id: Optional[int] = Query(default=None, gt=0),
    severity: Optional[AlertSeverity] = Query(default=None),
    international_target_percent: Decimal = Query(
        default=Decimal("5"),
        ge=0,
        le=100,
        description="Uluslararası öğrenci oranı hedefi (%)",
    ),
    db: Session = Depends(get_db),
) -> AlertsResponse:
    """Eşik değerlerin dışına çıkan metrikler için erken uyarı listesi döndürür."""
    return build_alerts(
        db,
        faculty_id,
        department_id,
        academic_program_id,
        severity,
        international_target_percent,
    )


# ===========================================================================
# PROGRAM SNAPSHOT CRUD
# ===========================================================================


@router.post(
    "/program-snapshots",
    response_model=ProgramSnapshotResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_snapshot(
    payload: ProgramSnapshotCreate,
    db: Session = Depends(get_db),
) -> ProgramEnrollmentSnapshot:
    """Yeni bir program kayıt fotoğrafı oluşturur."""
    _ensure_program_exists(db, payload.academic_program_id)
    _ensure_snapshot_unique(db, payload.academic_program_id, payload.academic_year)

    snapshot = ProgramEnrollmentSnapshot(**payload.model_dump())
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot


@router.get("/program-snapshots", response_model=List[ProgramSnapshotResponse])
def list_snapshots(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    academic_program_id: Optional[int] = Query(default=None, gt=0),
    academic_year: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
) -> List[ProgramEnrollmentSnapshot]:
    """Program snapshot kayıtlarını listeler."""
    statement = select(ProgramEnrollmentSnapshot)
    if academic_program_id is not None:
        statement = statement.where(
            ProgramEnrollmentSnapshot.academic_program_id == academic_program_id
        )
    if academic_year:
        statement = statement.where(
            ProgramEnrollmentSnapshot.academic_year == academic_year
        )

    statement = (
        statement.order_by(
            ProgramEnrollmentSnapshot.academic_program_id,
            ProgramEnrollmentSnapshot.academic_year,
        )
        .offset(skip)
        .limit(limit)
    )
    return list(db.execute(statement).scalars().all())


@router.get(
    "/program-snapshots/{snapshot_id}", response_model=ProgramSnapshotResponse
)
def get_snapshot(
    snapshot_id: int, db: Session = Depends(get_db)
) -> ProgramEnrollmentSnapshot:
    """Tek bir snapshot kaydını getirir."""
    return get_object_or_404(db, ProgramEnrollmentSnapshot, snapshot_id, SNAPSHOT_LABEL)


@router.put(
    "/program-snapshots/{snapshot_id}", response_model=ProgramSnapshotResponse
)
def update_snapshot(
    snapshot_id: int,
    payload: ProgramSnapshotUpdate,
    db: Session = Depends(get_db),
) -> ProgramEnrollmentSnapshot:
    """Var olan bir snapshot kaydını kısmi olarak günceller."""
    snapshot = get_object_or_404(
        db, ProgramEnrollmentSnapshot, snapshot_id, SNAPSHOT_LABEL
    )
    update_data = payload.model_dump(exclude_unset=True)

    if update_data.get("academic_program_id") is not None:
        _ensure_program_exists(db, update_data["academic_program_id"])

    new_program: int = update_data.get(
        "academic_program_id", snapshot.academic_program_id
    )
    new_year: str = update_data.get("academic_year", snapshot.academic_year)
    if new_program != snapshot.academic_program_id or new_year != snapshot.academic_year:
        _ensure_snapshot_unique(db, new_program, new_year, exclude_id=snapshot_id)

    apply_updates(snapshot, update_data)
    db.commit()
    db.refresh(snapshot)
    return snapshot


@router.delete(
    "/program-snapshots/{snapshot_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_snapshot(snapshot_id: int, db: Session = Depends(get_db)) -> None:
    """Bir snapshot kaydını siler."""
    # Snapshot'ta is_active alanı yok; yanlış girilen bir yıl verisinin
    # tamamen kaldırılabilmesi için fiziksel silme uygulanıyor.
    snapshot = get_object_or_404(
        db, ProgramEnrollmentSnapshot, snapshot_id, SNAPSHOT_LABEL
    )
    db.delete(snapshot)
    db.commit()


# ===========================================================================
# KARŞILAŞTIRMA PROGRAMI CRUD
# ===========================================================================


@router.post(
    "/comparable-programs",
    response_model=ComparableProgramResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_comparable_program(
    payload: ComparableProgramCreate,
    db: Session = Depends(get_db),
) -> ComparableUniversityProgram:
    """Yeni bir karşılaştırma programı kaydı oluşturur."""
    # Aynı üniversite + program + yıl kombinasyonu tekrar eklenemez.
    existing = db.execute(
        select(ComparableUniversityProgram)
        .where(ComparableUniversityProgram.university_name == payload.university_name)
        .where(ComparableUniversityProgram.program_name == payload.program_name)
        .where(ComparableUniversityProgram.academic_year == payload.academic_year)
    ).scalars().first()

    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"'{payload.university_name}' üniversitesinin '{payload.program_name}' "
                f"programı için {payload.academic_year} yılı kaydı zaten mevcut."
            ),
        )

    comparison = ComparableUniversityProgram(**payload.model_dump())
    db.add(comparison)
    db.commit()
    db.refresh(comparison)
    return comparison


@router.get("/comparable-programs", response_model=List[ComparableProgramResponse])
def list_comparable_programs(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    academic_year: Optional[str] = Query(default=None),
    city: Optional[str] = Query(default=None),
    is_competitor: Optional[bool] = Query(default=None),
    db: Session = Depends(get_db),
) -> List[ComparableUniversityProgram]:
    """Karşılaştırma programlarını listeler."""
    statement = select(ComparableUniversityProgram)
    if academic_year:
        statement = statement.where(
            ComparableUniversityProgram.academic_year == academic_year
        )
    if city:
        statement = statement.where(ComparableUniversityProgram.city == city)
    if is_competitor is not None:
        statement = statement.where(
            ComparableUniversityProgram.is_competitor.is_(is_competitor)
        )

    statement = statement.order_by(ComparableUniversityProgram.id).offset(skip).limit(limit)
    return list(db.execute(statement).scalars().all())


@router.get(
    "/comparable-programs/{comparison_id}", response_model=ComparableProgramResponse
)
def get_comparable_program(
    comparison_id: int, db: Session = Depends(get_db)
) -> ComparableUniversityProgram:
    """Tek bir karşılaştırma kaydını getirir."""
    return get_object_or_404(
        db, ComparableUniversityProgram, comparison_id, COMPARISON_LABEL
    )


@router.put(
    "/comparable-programs/{comparison_id}", response_model=ComparableProgramResponse
)
def update_comparable_program(
    comparison_id: int,
    payload: ComparableProgramUpdate,
    db: Session = Depends(get_db),
) -> ComparableUniversityProgram:
    """Var olan bir karşılaştırma kaydını kısmi olarak günceller."""
    comparison = get_object_or_404(
        db, ComparableUniversityProgram, comparison_id, COMPARISON_LABEL
    )
    apply_updates(comparison, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(comparison)
    return comparison


@router.delete(
    "/comparable-programs/{comparison_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_comparable_program(comparison_id: int, db: Session = Depends(get_db)) -> None:
    """Bir karşılaştırma kaydını siler."""
    comparison = get_object_or_404(
        db, ComparableUniversityProgram, comparison_id, COMPARISON_LABEL
    )
    db.delete(comparison)
    db.commit()


# ===========================================================================
# PROGRAM BAZLI TALEP VE KARŞILAŞTIRMA (parametreli yollar en sonda)
# ===========================================================================


@router.get(
    "/programs/{program_id}/demand",
    response_model=ProgramDemandResponse,
    summary="Programın yıllara göre talep analizi",
)
def get_program_demand(
    program_id: int, db: Session = Depends(get_db)
) -> ProgramDemandResponse:
    """Programın kontenjan, doluluk ve taban puan gelişimini döndürür."""
    _ensure_program_exists(db, program_id)
    return build_program_demand(db, program_id)


@router.get(
    "/programs/{program_id}/comparisons",
    response_model=ProgramComparisonResponse,
    summary="Programın diğer üniversitelerle karşılaştırması",
)
def get_program_comparisons(
    program_id: int,
    academic_year: Optional[str] = Query(default=None, description="YYYY-YYYY"),
    db: Session = Depends(get_db),
) -> ProgramComparisonResponse:
    """Programı ulusal, Ankara ve rakip üniversite verileriyle karşılaştırır."""
    _ensure_program_exists(db, program_id)
    return build_program_comparison(db, program_id, academic_year)
