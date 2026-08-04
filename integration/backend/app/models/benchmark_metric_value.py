"""Karşılaştırma kurumunun gösterge değeri (BenchmarkMetricValue) modeli."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.decimal_types import MoneyType
from app.database import Base

if TYPE_CHECKING:
    from app.models.benchmark_institution import BenchmarkInstitution
    from app.models.evaluation_indicator import EvaluationIndicator


class BenchmarkMetricValue(Base):
    """Bir karşılaştırma kurumunun belirli göstergedeki yıllık değeri."""

    __tablename__ = "benchmark_metric_values"

    __table_args__ = (
        UniqueConstraint(
            "benchmark_institution_id",
            "indicator_id",
            "academic_year",
            "period",
            name="uq_benchmark_value_key",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    benchmark_institution_id: Mapped[int] = mapped_column(
        ForeignKey("benchmark_institutions.id"), nullable=False, index=True
    )
    indicator_id: Mapped[int] = mapped_column(
        ForeignKey("evaluation_indicators.id"), nullable=False, index=True
    )

    academic_year: Mapped[str] = mapped_column(String(9), nullable=False, index=True)
    period: Mapped[str] = mapped_column(String(10), default="annual", nullable=False)

    # Karşılaştırma değerleri de Decimal tutulur; ortalama hesaplarında
    # float sapması sıralama sonucunu değiştirmesin.
    value: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)

    source_reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    institution: Mapped["BenchmarkInstitution"] = relationship(
        "BenchmarkInstitution", back_populates="metric_values"
    )
    indicator: Mapped["EvaluationIndicator"] = relationship(
        "EvaluationIndicator", back_populates="benchmark_values"
    )

    def __repr__(self) -> str:
        """Nesnenin okunabilir metin gösterimini döndürür."""
        return (
            f"<BenchmarkMetricValue(id={self.id}, institution_id={self.benchmark_institution_id}, "
            f"indicator_id={self.indicator_id}, year='{self.academic_year}')>"
        )
