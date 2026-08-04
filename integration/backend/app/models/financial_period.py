"""Mali dönem, gelir/gider kalemi ve bölüm bütçesi (Modül 6) modelleri.

Entegrasyon notu: Halil'in orijinal kodunda tüm mali veri tek bir JSON dosyasında
iç içe sözlük olarak tutuluyordu (`data.json`). Bu yapıda bölüm adları serbest
metindi ve Modül 1'deki bölüm kayıtlarıyla eşleşmiyordu; aynı bölümün mali
verisi ile öğrenci verisi birbirine bağlanamıyordu. Kanonik modelde bölüm bir
foreign key ile bağlandı.

Para birimi: tüm tutarlar milyon TL cinsinden ve Decimal olarak saklanır.
Float kullanılsaydı toplama sırasında kuruş kayması oluşurdu; bu yüzden projenin
diğer modüllerinde de kullanılan MoneyType tercih edildi.
"""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.decimal_types import MoneyType
from app.database import Base

if TYPE_CHECKING:
    from app.models.department import Department

# Kalem türleri. Serbest metin yerine sabit liste: "revenue"/"Revenue"/"gelir"
# gibi varyasyonlar toplamları böler.
ENTRY_KINDS = ("revenue", "expenditure")


class FinancialPeriod(Base):
    """Bir akademik yılın mali dönemini temsil eder."""

    __tablename__ = "financial_periods"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    academic_year: Mapped[str] = mapped_column(
        String(9), unique=True, index=True, nullable=False
    )

    # Öğrenci ve mezun sayısı; öğrenci/mezun başına maliyet oranlarının paydası.
    # Modül 2'deki öğrenci tablosundan da sayılabilir ancak mali raporlar resmi
    # dönem sonu sayısına göre kapatıldığı için burada ayrıca kaydediliyor.
    total_students: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_graduates: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    entries: Mapped[List["FinancialEntry"]] = relationship(
        "FinancialEntry", back_populates="period", cascade="all, delete-orphan"
    )
    department_budgets: Mapped[List["DepartmentBudget"]] = relationship(
        "DepartmentBudget", back_populates="period", cascade="all, delete-orphan"
    )


class FinancialEntry(Base):
    """Bir mali dönemdeki tek gelir veya gider kalemi."""

    __tablename__ = "financial_entries"
    # Aynı dönemde aynı kalem iki kez açılmasın; ikinci kayıt toplamı bozardı.
    __table_args__ = (
        UniqueConstraint(
            "financial_period_id", "kind", "category", name="uq_financial_entry"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    financial_period_id: Mapped[int] = mapped_column(
        ForeignKey("financial_periods.id"), nullable=False, index=True
    )

    kind: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(120), nullable=False)

    # Milyon TL. Negatif tutar kabul edilmez; düzeltme işlemi servis katmanında
    # mevcut tutarın üzerine eklenerek yapılır ve sonuç sıfırın altına inemez.
    amount: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    period: Mapped["FinancialPeriod"] = relationship(
        "FinancialPeriod", back_populates="entries"
    )


class DepartmentBudget(Base):
    """Bir bölümün belirli bir mali dönemdeki bütçe ve gerçekleşme verisi."""

    __tablename__ = "department_budgets"
    __table_args__ = (
        UniqueConstraint(
            "financial_period_id", "department_id", name="uq_department_budget"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    financial_period_id: Mapped[int] = mapped_column(
        ForeignKey("financial_periods.id"), nullable=False, index=True
    )
    department_id: Mapped[int] = mapped_column(
        ForeignKey("departments.id"), nullable=False, index=True
    )

    student_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    revenue: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)
    expenditure: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)

    # Planlanan bütçe. Sıfır olabilir (bütçe henüz tahsis edilmemiş); bu durumda
    # gerçekleşme oranı hesaplanmaz, uydurma bir yüzde üretilmez.
    allocated_budget: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    period: Mapped["FinancialPeriod"] = relationship(
        "FinancialPeriod", back_populates="department_budgets"
    )
    department: Mapped["Department"] = relationship("Department")
