"""Modül 6 — Stratejik finansal analiz endpoint'leri."""

from typing import List

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.finance import (
    DepartmentBudgetResponse,
    DepartmentBudgetUpsert,
    FinancialEntryCreate,
    FinancialEntryResponse,
    FinancialPeriodCreate,
    FinancialPeriodResponse,
    FinancialPeriodUpdate,
    FinancialSummary,
    FinancialTrendItem,
)
from app.services import finance_service as service

router = APIRouter(prefix="/api/finance", tags=["Modül 6 — Finansal Analiz"])


# Sabit yollar parametreli yoldan önce tanımlandı.


@router.get(
    "/periods",
    response_model=List[FinancialPeriodResponse],
    summary="Mali dönem listesi",
)
def list_periods(db: Session = Depends(get_db)) -> List[FinancialPeriodResponse]:
    """Tanımlı tüm mali dönemleri yeni yıldan eskiye döndürür."""
    return [FinancialPeriodResponse.model_validate(p) for p in service.list_periods(db)]


@router.post(
    "/periods",
    response_model=FinancialPeriodResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Yeni mali dönem aç",
)
def create_period(
    payload: FinancialPeriodCreate, db: Session = Depends(get_db)
) -> FinancialPeriodResponse:
    """Aynı yıl zaten açılmışsa 409 döner."""
    return FinancialPeriodResponse.model_validate(service.create_period(db, payload))


@router.get(
    "/trend",
    response_model=List[FinancialTrendItem],
    summary="Yıllar arası mali karşılaştırma",
)
def get_trend(db: Session = Depends(get_db)) -> List[FinancialTrendItem]:
    """Gelir/gider toplamlarını ve yıllık değişim oranlarını verir."""
    return [FinancialTrendItem(**row) for row in service.financial_trend(db)]


@router.get(
    "/{academic_year}/summary",
    response_model=FinancialSummary,
    summary="Mali dönem özeti ve oran göstergeleri",
)
def get_summary(academic_year: str, db: Session = Depends(get_db)) -> FinancialSummary:
    """Dönem bulunamazsa mevcut dönemleri de listeleyen 404 döner."""
    return FinancialSummary(**service.financial_summary(db, academic_year))


@router.patch(
    "/{academic_year}",
    response_model=FinancialPeriodResponse,
    summary="Dönem öğrenci/mezun sayılarını güncelle",
)
def update_period(
    academic_year: str, payload: FinancialPeriodUpdate, db: Session = Depends(get_db)
) -> FinancialPeriodResponse:
    """Oran hesaplarının paydası olan sayıları günceller."""
    return FinancialPeriodResponse.model_validate(
        service.update_period(db, academic_year, payload)
    )


@router.post(
    "/{academic_year}/entries",
    response_model=FinancialEntryResponse,
    summary="Gelir/gider kalemi işle",
)
def book_entry(
    academic_year: str, payload: FinancialEntryCreate, db: Session = Depends(get_db)
) -> FinancialEntryResponse:
    """Kalem yoksa oluşturulur; varsa tutar üzerine eklenir.

    Negatif tutar düzeltme anlamına gelir ve sonuç sıfırın altına inmez.
    """
    entry = service.book_entry(db, academic_year, payload)
    return FinancialEntryResponse(
        id=entry.id, kind=entry.kind, category=entry.category, amount=entry.amount
    )


@router.delete(
    "/{academic_year}/entries/{entry_id}",
    summary="Kalemi sil",
)
def delete_entry(
    academic_year: str, entry_id: int, db: Session = Depends(get_db)
) -> dict:
    """Yanlış açılmış kalemi tamamen kaldırır."""
    return service.delete_entry(db, academic_year, entry_id)


@router.get(
    "/{academic_year}/departments",
    response_model=List[DepartmentBudgetResponse],
    summary="Bölüm bütçeleri ve gerçekleşme durumu",
)
def list_department_budgets(
    academic_year: str, db: Session = Depends(get_db)
) -> List[DepartmentBudgetResponse]:
    """Bütçe tanımsız bölümler için gerçekleşme oranı hesaplanmaz."""
    return [
        DepartmentBudgetResponse(**service.budget_to_dict(budget))
        for budget in service.list_department_budgets(db, academic_year)
    ]


@router.put(
    "/{academic_year}/departments",
    response_model=DepartmentBudgetResponse,
    summary="Bölüm bütçesi ekle veya güncelle",
)
def upsert_department_budget(
    academic_year: str, payload: DepartmentBudgetUpsert, db: Session = Depends(get_db)
) -> DepartmentBudgetResponse:
    """Bölüm bulunamazsa 404 döner."""
    budget = service.upsert_department_budget(db, academic_year, payload)
    # Bölüm ve fakülte adlarının dolu gelmesi için ilişkiler yüklenmiş
    # listeden yeniden okunuyor.
    for row in service.list_department_budgets(db, academic_year):
        if row.id == budget.id:
            return DepartmentBudgetResponse(**service.budget_to_dict(row))
    return DepartmentBudgetResponse(**service.budget_to_dict(budget))
