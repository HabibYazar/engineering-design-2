"""Modül 3 — Öğrenci analitiği endpoint'leri."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.education_analytics import (
    AcademicPerformanceTrendResponse,
    AdmissionScoreAnalysisResponse,
    ComparativeAnalysisRequest,
    ComparativeAnalysisResult,
    DemandTrendResponse,
    ProgramMetricsResponse,
    UniversityOverviewResponse,
)
from app.services import education_analytics_service as service

router = APIRouter(prefix="/api/education-analytics", tags=["Modül 3 — Öğrenci Analitiği"])

DEFAULT_ACADEMIC_YEAR = "2026-2027"


def _validate_academic_year(db: Session, academic_year: str) -> str:
    """Akademik yılın veride bulunduğunu doğrular."""
    available = service.get_available_academic_years(db)
    if academic_year not in available:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"'{academic_year}' için veri yok. Mevcut yıllar: {', '.join(available)}",
        )
    return academic_year


@router.get("/academic-years", response_model=List[str])
def list_academic_years(db: Session = Depends(get_db)) -> List[str]:
    """Analiz yapılabilen akademik yılları listeler."""
    return service.get_available_academic_years(db)


@router.get("/overview", response_model=UniversityOverviewResponse)
def get_overview(
    academic_year: str = Query(default=DEFAULT_ACADEMIC_YEAR, description="Örn. 2026-2027"),
    db: Session = Depends(get_db),
):
    """Üniversite geneli öğrenci göstergelerini döndürür (roll-up görünüm)."""
    _validate_academic_year(db, academic_year)
    return service.get_university_overview(db, academic_year)


@router.get("/programs", response_model=List[ProgramMetricsResponse])
def list_program_metrics(
    academic_year: str = Query(default=DEFAULT_ACADEMIC_YEAR, description="Örn. 2026-2027"),
    db: Session = Depends(get_db),
):
    """Tüm programların göstergelerini doluluk oranına göre artan sırada listeler."""
    _validate_academic_year(db, academic_year)
    return service.get_program_metrics(db, academic_year)


@router.get("/programs/{program_code}", response_model=ProgramMetricsResponse)
def get_program(
    program_code: str,
    academic_year: str = Query(default=DEFAULT_ACADEMIC_YEAR, description="Örn. 2026-2027"),
    db: Session = Depends(get_db),
):
    """Tek bir programın göstergelerini getirir (drill-down görünüm)."""
    _validate_academic_year(db, academic_year)
    metrics = service.get_program_detail(db, program_code, academic_year)
    if metrics is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"'{program_code}' kodlu program bulunamadı.",
        )
    return metrics


@router.get("/admission-scores", response_model=List[AdmissionScoreAnalysisResponse])
def get_admission_scores(
    academic_year: str = Query(default=DEFAULT_ACADEMIC_YEAR, description="Örn. 2026-2027"),
    db: Session = Depends(get_db),
):
    """Taban puanları Ankara ve Türkiye ortalamalarıyla karşılaştırır."""
    _validate_academic_year(db, academic_year)
    return service.get_admission_score_analysis(db, academic_year)


@router.get("/demand-trends", response_model=List[DemandTrendResponse])
def get_demand_trends(db: Session = Depends(get_db)):
    """Programların yıllar içindeki talep trendini döndürür."""
    return service.get_demand_trends(db)


@router.get("/performance-trends", response_model=List[AcademicPerformanceTrendResponse])
def get_performance_trends(db: Session = Depends(get_db)):
    """Programların yıllara göre ortalama dönem GNO trendini döndürür."""
    return service.get_academic_performance_trend(db)


@router.post("/comparative", response_model=List[ComparativeAnalysisResult])
def post_comparative_analysis(
    payload: ComparativeAnalysisRequest, db: Session = Depends(get_db)
):
    """Benzer/rakip üniversitelerle program bazlı karşılaştırma yapar.

    Kıyaslama verisi (Modül 13'ün sağlayacağı) istek gövdesiyle verilir; bu
    modül veriyi uydurmaz, yalnızca kendi göstergeleriyle kıyaslar.
    """
    _validate_academic_year(db, payload.academic_year)
    comparators = {
        code: [c.model_dump() for c in items] for code, items in payload.comparators.items()
    }
    return service.get_comparative_analysis(db, payload.academic_year, comparators)
