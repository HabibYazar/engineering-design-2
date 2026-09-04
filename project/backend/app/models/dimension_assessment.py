"""Boyut değerlendirmesi (DimensionAssessment) veritabanı modeli."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
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
    from app.models.evaluation_dimension import EvaluationDimension
    from app.models.framework_assessment import FrameworkAssessment


class DimensionAssessment(Base):
    """Bir değerlendirmenin boyut bazındaki kırılımı.

    weighted_score, boyutun çerçeve toplam skoruna yaptığı katkıyı gösterir
    (performance_score × boyut ağırlığı / 100). Yönetici hangi boyutun toplam
    skoru ne kadar taşıdığını bu alandan görebilir.
    """

    __tablename__ = "dimension_assessments"

    __table_args__ = (
        UniqueConstraint(
            "framework_assessment_id", "dimension_id", name="uq_dimension_assessment"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    framework_assessment_id: Mapped[int] = mapped_column(
        ForeignKey("framework_assessments.id"), nullable=False, index=True
    )
    dimension_id: Mapped[int] = mapped_column(
        ForeignKey("evaluation_dimensions.id"), nullable=False, index=True
    )

    readiness_score: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)
    performance_score: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)
    weighted_score: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)

    missing_indicator_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    framework_assessment: Mapped["FrameworkAssessment"] = relationship(
        "FrameworkAssessment", back_populates="dimension_assessments"
    )
    dimension: Mapped["EvaluationDimension"] = relationship(
        "EvaluationDimension", back_populates="assessments"
    )

    def __repr__(self) -> str:
        """Nesnenin okunabilir metin gösterimini döndürür."""
        return (
            f"<DimensionAssessment(id={self.id}, dimension_id={self.dimension_id}, "
            f"performance={self.performance_score})>"
        )
