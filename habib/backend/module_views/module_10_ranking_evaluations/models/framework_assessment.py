"""Çerçeve değerlendirmesi (FrameworkAssessment) veritabanı modeli."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.decimal_types import MoneyType
from app.database import Base

if TYPE_CHECKING:
    from app.models.dimension_assessment import DimensionAssessment
    from app.models.evaluation_framework import EvaluationFramework


class FrameworkAssessment(Base):
    """Bir çerçevenin belirli yıl/dönemdeki hesaplanmış değerlendirme özeti.

    Bu tablo hesaplanmış sonuçları saklar; servis katmanı gerektiğinde aynı
    hesaplamayı yeniden çalıştırıp kaydı günceller. Böylece geçmiş
    değerlendirmeler tarihsel olarak izlenebilir, hesaplama her istekte
    baştan yapılmak zorunda kalmaz.

    NOT: Bu skorlar gerçek THE/QS/YÖK sıralaması DEĞİLDİR. Kurumun kendi
    verisine dayanan iç performans izleme ve veri hazırlık göstergeleridir.
    """

    __tablename__ = "framework_assessments"

    __table_args__ = (
        UniqueConstraint(
            "framework_id", "academic_year", "period", name="uq_assessment_framework_year_period"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    framework_id: Mapped[int] = mapped_column(
        ForeignKey("evaluation_frameworks.id"), nullable=False, index=True
    )

    academic_year: Mapped[str] = mapped_column(String(9), nullable=False, index=True)
    period: Mapped[str] = mapped_column(String(10), default="annual", nullable=False)

    # Üç skor da 0-100 aralığında tutulur.
    readiness_score: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)
    performance_score: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)
    compliance_score: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)

    missing_indicator_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    partial_indicator_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    available_indicator_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # risk_level: low | medium | high | critical
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    # Hesaplama sırasında uygulanan fallback ve varsayımların kaydı.
    calculation_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    calculated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    framework: Mapped["EvaluationFramework"] = relationship(
        "EvaluationFramework", back_populates="assessments"
    )
    dimension_assessments: Mapped[List["DimensionAssessment"]] = relationship(
        "DimensionAssessment",
        back_populates="framework_assessment",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        """Nesnenin okunabilir metin gösterimini döndürür."""
        return (
            f"<FrameworkAssessment(id={self.id}, framework_id={self.framework_id}, "
            f"year='{self.academic_year}', risk='{self.risk_level}')>"
        )
