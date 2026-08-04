"""Senaryo girdileri (ScenarioInput) veritabanı modeli."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.decimal_types import MoneyType
from app.database import Base

if TYPE_CHECKING:
    from app.models.scenario import Scenario


class ScenarioInput(Base):
    """Bir simülasyonda kullanılan değişiklik parametrelerini saklar.

    Her simülasyon çalıştırmasında yeni bir kayıt oluşur. Böylece "geçen ay hangi
    varsayımlarla bu sonucu bulmuştuk" sorusu sonradan cevaplanabilir.
    """

    __tablename__ = "scenario_inputs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    scenario_id: Mapped[int] = mapped_column(
        ForeignKey("scenarios.id"), nullable=False, index=True
    )

    # --- Yüzdesel değişimler ---
    # Hepsi Decimal; yüzde hesapları da para hesaplarını etkilediği için
    # burada float kullanmak sonuçlara sapma taşırdı.
    student_change_percent: Mapped[Decimal] = mapped_column(MoneyType, default=Decimal("0"), nullable=False)
    tuition_change_percent: Mapped[Decimal] = mapped_column(MoneyType, default=Decimal("0"), nullable=False)
    scholarship_change_percent: Mapped[Decimal] = mapped_column(MoneyType, default=Decimal("0"), nullable=False)
    inflation_percent: Mapped[Decimal] = mapped_column(MoneyType, default=Decimal("0"), nullable=False)
    exchange_rate_change_percent: Mapped[Decimal] = mapped_column(MoneyType, default=Decimal("0"), nullable=False)
    research_funding_change_percent: Mapped[Decimal] = mapped_column(MoneyType, default=Decimal("0"), nullable=False)

    # --- Mutlak (adet bazlı) değişimler ---
    # Bunlar yüzde değil, doğrudan sayı olarak girilir ve negatif olabilir.
    academic_staff_change: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    classroom_capacity_change: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    laboratory_capacity_change: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    scenario: Mapped["Scenario"] = relationship("Scenario", back_populates="inputs")

    def __repr__(self) -> str:
        """Nesnenin okunabilir metin gösterimini döndürür."""
        return f"<ScenarioInput(id={self.id}, scenario_id={self.scenario_id})>"
