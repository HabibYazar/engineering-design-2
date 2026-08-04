"""Senaryo sonuçları (ScenarioResult) veritabanı modeli."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.decimal_types import MoneyType
from app.database import Base

if TYPE_CHECKING:
    from app.models.scenario import Scenario


class ScenarioResult(Base):
    """Bir simülasyonun mevcut durum (baseline) ve tahmini durum (projected) sonuçlarını tutar.

    Her metrik ikili olarak saklanır: karşılaştırmayı sonradan tekrar hesaplamadan
    gösterebilmek için hem başlangıç hem tahmin değeri kaydedilir.
    """

    __tablename__ = "scenario_results"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    scenario_id: Mapped[int] = mapped_column(
        ForeignKey("scenarios.id"), nullable=False, index=True
    )

    # --- Öğrenci sayısı ---
    baseline_student_count: Mapped[int] = mapped_column(Integer, nullable=False)
    projected_student_count: Mapped[int] = mapped_column(Integer, nullable=False)

    # --- Mali sonuçlar ---
    baseline_revenue: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)
    projected_revenue: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)
    baseline_expenditure: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)
    projected_expenditure: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)

    # --- Personel ---
    baseline_staff_count: Mapped[int] = mapped_column(Integer, nullable=False)
    projected_staff_count: Mapped[int] = mapped_column(Integer, nullable=False)
    baseline_student_staff_ratio: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)
    projected_student_staff_ratio: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)

    # --- Öğrenci başına maliyet ---
    baseline_cost_per_student: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)
    projected_cost_per_student: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)

    # --- Fiziksel kapasite ---
    baseline_classroom_capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    projected_classroom_capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    baseline_laboratory_capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    projected_laboratory_capacity: Mapped[int] = mapped_column(Integer, nullable=False)

    # Kapasite durumu: sufficient | tight | insufficient
    # "tight", kapasitenin %90'ından fazlasının dolduğu, henüz aşılmamış ama riskli durumu ifade eder.
    classroom_capacity_status: Mapped[str] = mapped_column(String(20), nullable=False)
    laboratory_capacity_status: Mapped[str] = mapped_column(String(20), nullable=False)

    # risk_level: low | medium | high | critical
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    # Tespit edilen risklere göre üretilen Türkçe öneri metni.
    recommendation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    calculated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    scenario: Mapped["Scenario"] = relationship("Scenario", back_populates="results")

    def __repr__(self) -> str:
        """Nesnenin okunabilir metin gösterimini döndürür."""
        return f"<ScenarioResult(id={self.id}, scenario_id={self.scenario_id}, risk='{self.risk_level}')>"
