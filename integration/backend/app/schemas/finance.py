"""Modül 6 — Stratejik finansal analiz şemaları.

Tüm tutarlar milyon USD cinsindendir ve Decimal olarak taşınır.
"""

from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class FinancialPeriodCreate(BaseModel):
    """Yeni mali dönem açar."""

    academic_year: str = Field(pattern=r"^\d{4}-\d{4}$", examples=["2026-2027"])
    total_students: int = Field(default=0, ge=0, examples=[2700])
    total_graduates: int = Field(default=0, ge=0, examples=[540])
    copy_categories_from: Optional[str] = Field(
        default=None,
        description=(
            "Verilirse bu yılın gelir/gider kalem yapısı sıfır tutarla kopyalanır."
        ),
        examples=["2025-2026"],
    )


class FinancialPeriodUpdate(BaseModel):
    """Öğrenci ve mezun sayılarını günceller."""

    total_students: Optional[int] = Field(default=None, ge=0, examples=[2750])
    total_graduates: Optional[int] = Field(default=None, ge=0, examples=[560])


class FinancialPeriodResponse(BaseModel):
    """Mali dönem bilgisi."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    academic_year: str
    total_students: int
    total_graduates: int
    is_active: bool


class FinancialEntryCreate(BaseModel):
    """Gelir veya gider kalemi kaydeder."""

    kind: str = Field(description="revenue veya expenditure", examples=["revenue"])
    category: str = Field(min_length=2, max_length=120, examples=["Öğrenim ücretleri"])
    amount: Decimal = Field(
        description="Milyon USD. Negatif değer düzeltme olarak mevcut tutardan düşer.",
        examples=[Decimal("486.00")],
    )


class FinancialEntryResponse(BaseModel):
    """Kalem bilgisi."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str = Field(examples=["revenue"])
    category: str = Field(examples=["Öğrenim ücretleri"])
    amount: Decimal = Field(examples=[Decimal("486.00")])
    share_percent: Optional[Decimal] = Field(
        default=None,
        description="Kendi türü içindeki payı.",
        examples=[Decimal("78.13")],
    )


class DepartmentBudgetUpsert(BaseModel):
    """Bölüm bütçesini ekler veya günceller."""

    department_id: int = Field(ge=1, examples=[1])
    student_count: int = Field(ge=0, examples=[620])
    revenue: Decimal = Field(ge=0, examples=[Decimal("152.00")])
    expenditure: Decimal = Field(ge=0, examples=[Decimal("128.00")])
    allocated_budget: Decimal = Field(ge=0, examples=[Decimal("125.00")])


class DepartmentBudgetResponse(BaseModel):
    """Bölüm bütçesi ve türetilmiş göstergeler."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    department_id: int
    department_name: str = Field(examples=["Bilgisayar Mühendisliği"])
    faculty_name: str = Field(examples=["Mühendislik Fakültesi"])
    student_count: int = Field(examples=[620])
    revenue: Decimal = Field(examples=[Decimal("152.00")])
    expenditure: Decimal = Field(examples=[Decimal("128.00")])
    allocated_budget: Decimal = Field(examples=[Decimal("125.00")])
    balance: Decimal = Field(
        description="Gelir eksi gider.", examples=[Decimal("24.00")]
    )
    cost_per_student_thousand_usd: Optional[Decimal] = Field(
        default=None,
        description="Öğrenci sayısı sıfırsa hesaplanmaz.",
        examples=[Decimal("206.45")],
    )
    budget_realization_percent: Optional[Decimal] = Field(
        default=None,
        description="Bütçe tahsis edilmemişse hesaplanmaz.",
        examples=[Decimal("102.40")],
    )
    budget_status: str = Field(
        description="bütçe içinde / hafif aşım / bütçe aşımı / bütçe tanımsız",
        examples=["hafif aşım"],
    )


class FinancialSummary(BaseModel):
    """Mali dönem özeti ve oran göstergeleri."""

    academic_year: str = Field(examples=["2025-2026"])
    total_revenue: Decimal = Field(examples=[Decimal("622.00")])
    total_expenditure: Decimal = Field(examples=[Decimal("601.00")])
    balance: Decimal = Field(examples=[Decimal("21.00")])
    balance_status: str = Field(examples=["fazla"])
    total_students: int = Field(examples=[2700])
    total_graduates: int = Field(examples=[540])
    # Bin USD cinsinden gösterim özet kartlar için pratiktir ancak iki ondalıkla
    # yuvarlandığı için 10 USD çözünürlük kaybı olur. Hassas karşılaştırma ve
    # test gereken yerlerde tam USD alanları kullanılır.
    revenue_per_student_usd: Optional[Decimal] = Field(
        default=None, description="Öğrenci başına gelir (tam USD)", examples=[Decimal("12600.00")]
    )
    cost_per_student_usd: Optional[Decimal] = Field(
        default=None, description="Öğrenci başına maliyet (tam USD)", examples=[Decimal("11875.00")]
    )
    revenue_per_student_thousand_usd: Optional[Decimal] = Field(
        default=None, examples=[Decimal("230.37")]
    )
    cost_per_student_thousand_usd: Optional[Decimal] = Field(
        default=None, examples=[Decimal("222.59")]
    )
    cost_per_graduate_million_usd: Optional[Decimal] = Field(
        default=None, examples=[Decimal("1.11")]
    )
    personnel_expense_share_percent: Optional[Decimal] = Field(
        default=None, examples=[Decimal("46.92")]
    )
    research_revenue_share_percent: Optional[Decimal] = Field(
        default=None, examples=[Decimal("9.97")]
    )
    scholarship_impact_percent: Optional[Decimal] = Field(
        default=None, examples=[Decimal("14.15")]
    )
    revenue_breakdown: List[FinancialEntryResponse]
    expenditure_breakdown: List[FinancialEntryResponse]


class FinancialTrendItem(BaseModel):
    """Yıllar arası mali karşılaştırma satırı."""

    academic_year: str = Field(examples=["2025-2026"])
    total_revenue: Decimal = Field(examples=[Decimal("622.00")])
    total_expenditure: Decimal = Field(examples=[Decimal("601.00")])
    balance: Decimal = Field(examples=[Decimal("21.00")])
    revenue_change_percent: Optional[Decimal] = Field(
        default=None,
        description="Bir önceki yıla göre değişim. İlk yıl için hesaplanmaz.",
        examples=[Decimal("11.83")],
    )
    expenditure_change_percent: Optional[Decimal] = Field(
        default=None, examples=[Decimal("9.85")]
    )
