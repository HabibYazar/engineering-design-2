"""Modül 11 — Risk ve erken uyarı endpoint'leri."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import education_analytics_service as analytics
from app.schemas.early_warning import (
    AlertResponse,
    AlertSummaryResponse,
    RuleCatalogResponse,
)
from app.services import early_warning_rule_engine as rule_engine
from app.services.scope import resolve, scope_params

router = APIRouter(prefix="/api/early-warning", tags=["Modül 11 — Erken Uyarı"])

DEFAULT_ACADEMIC_YEAR = "2026-2027"


def _validate_academic_year(db: Session, academic_year: str) -> None:
    """Akademik yılın veride bulunduğunu doğrular."""
    available = analytics.get_available_academic_years(db)
    if academic_year not in available:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"'{academic_year}' için veri yok. Mevcut yıllar: {', '.join(available)}",
        )


@router.get("/alerts", response_model=List[AlertResponse])
def get_alerts(
    academic_year: str = Query(default=DEFAULT_ACADEMIC_YEAR, description="Örn. 2026-2027"),
    severity: Optional[str] = Query(
        default=None, description="kritik | yuksek | orta | dusuk"
    ),
    program_code: Optional[str] = Query(default=None, description="Örn. CENG-BSC"),
    kapsam: dict = Depends(scope_params),
    db: Session = Depends(get_db),
):
    """Seçili kapsamdaki erken uyarı alarmlarını önem sırasına göre döndürür."""
    _validate_academic_year(db, academic_year)
    return rule_engine.evaluate(
        db, academic_year, severity, program_code, resolve(db, **kapsam)
    )


@router.get("/summary", response_model=AlertSummaryResponse)
def get_summary(
    academic_year: str = Query(default=DEFAULT_ACADEMIC_YEAR, description="Örn. 2026-2027"),
    kapsam: dict = Depends(scope_params),
    db: Session = Depends(get_db),
):
    """Seçili kapsamdaki alarmların önem/kapsam özetini döndürür.

    Program sayfasındaki risk kartı yalnızca o programın uyarılarını sayar.
    """
    _validate_academic_year(db, academic_year)
    return rule_engine.summarize(
        rule_engine.evaluate(db, academic_year, scope=resolve(db, **kapsam))
    )


@router.get("/rules", response_model=List[RuleCatalogResponse])
def get_rules():
    """Tanımlı tüm kuralları listeler (uygulanmış ve veri bekleyenler birlikte)."""
    return rule_engine.get_rule_catalog()


@router.get("/rules/pending", response_model=List[RuleCatalogResponse])
def get_pending_rules():
    """Diğer modüllerin verisini bekleyen kuralları listeler."""
    return rule_engine.get_pending_rules()
