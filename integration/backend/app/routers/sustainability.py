"""Modül 7 — Akademik program sürdürülebilirlik endpoint'leri."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import education_analytics_service as analytics
from app.schemas.sustainability import (
    CategorySummaryResponse,
    SustainabilityRequest,
    SustainabilityResponse,
    WeightConfigResponse,
)
from app.services import sustainability_service as service

router = APIRouter(
    prefix="/api/program-sustainability",
    tags=["Modül 7 — Program Sürdürülebilirliği"],
)

DEFAULT_ACADEMIC_YEAR = "2026-2027"


def _validate_academic_year(db: Session, academic_year: str) -> None:
    """Akademik yılın veride bulunduğunu doğrular."""
    available = analytics.get_available_academic_years(db)
    if academic_year not in available:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"'{academic_year}' için veri yok. Mevcut yıllar: {', '.join(available)}",
        )


@router.get("/weights", response_model=WeightConfigResponse)
def get_weights():
    """Kriter ağırlıklarını ve sınıflandırma eşiklerini döndürür."""
    config = service.load_config()
    return {
        "weights": config["weights"],
        "criterion_sources": config["criterion_sources"],
        "classification_thresholds": config["classification_thresholds"],
        "total_weight": sum(config["weights"].values()),
        "computed_criteria": sorted(service.COMPUTED_CRITERIA),
    }


@router.get("/scores", response_model=List[SustainabilityResponse])
def get_scores(
    academic_year: str = Query(default=DEFAULT_ACADEMIC_YEAR, description="Örn. 2026-2027"),
    db: Session = Depends(get_db),
):
    """Tüm programları yalnızca Modül 3 verisiyle değerlendirir (puana göre artan)."""
    _validate_academic_year(db, academic_year)
    return service.evaluate_all(db, academic_year)


@router.post("/scores", response_model=List[SustainabilityResponse])
def post_scores(payload: SustainabilityRequest, db: Session = Depends(get_db)):
    """Diğer modüllerden gelen kriter puanlarıyla yeniden değerlendirir.

    Eksik kriterler doldurulduğunda veri tamlığının ve puanın nasıl değiştiğini
    göstermek için kullanılır.
    """
    _validate_academic_year(db, payload.academic_year)
    return service.evaluate_all(
        db,
        payload.academic_year,
        external_inputs=payload.external_inputs,
        weight_overrides=payload.weight_overrides,
    )


@router.get("/categories", response_model=List[CategorySummaryResponse])
def get_categories(
    academic_year: str = Query(default=DEFAULT_ACADEMIC_YEAR, description="Örn. 2026-2027"),
    db: Session = Depends(get_db),
):
    """Programların PDF Bölüm 7 kategorilerine dağılımını özetler."""
    _validate_academic_year(db, academic_year)
    results = service.evaluate_all(db, academic_year)
    return service.summarize_categories(results)


@router.get("/scores/{program_code}", response_model=SustainabilityResponse)
def get_program_score(
    program_code: str,
    academic_year: str = Query(default=DEFAULT_ACADEMIC_YEAR, description="Örn. 2026-2027"),
    db: Session = Depends(get_db),
):
    """Tek bir programın sürdürülebilirlik değerlendirmesini getirir."""
    _validate_academic_year(db, academic_year)
    for result in service.evaluate_all(db, academic_year):
        if result["program_code"].upper() == program_code.upper():
            return result
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"'{program_code}' kodlu program bulunamadı.",
    )
