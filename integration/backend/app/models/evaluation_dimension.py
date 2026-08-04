"""Değerlendirme boyutu (EvaluationDimension) veritabanı modeli."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    Boolean,
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
    from app.models.evaluation_indicator import EvaluationIndicator


class EvaluationDimension(Base):
    """Bir çerçevenin ana değerlendirme başlığı (örn. Research Environment).

    Ağırlıklar (weight) yapılandırılabilir tutulur; metodoloji değiştiğinde
    kod değişikliği gerekmeden yalnızca veri güncellenir. Toplam ağırlığın
    100 olup olmadığı servis katmanında doğrulanır (bkz. ranking_calculation_service).
    """

    __tablename__ = "evaluation_dimensions"

    __table_args__ = (
        UniqueConstraint("framework_id", "code", name="uq_dimension_framework_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    framework_id: Mapped[int] = mapped_column(
        ForeignKey("evaluation_frameworks.id"), nullable=False, index=True
    )

    code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Boyutun çerçeve içindeki yüzdesel ağırlığı (0-100).
    weight: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)

    # Arayüzde gösterim sırası; metodolojideki sıralamayı korumak için tutulur.
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    framework: Mapped["EvaluationFramework"] = relationship(
        "EvaluationFramework", back_populates="dimensions"
    )
    indicators: Mapped[List["EvaluationIndicator"]] = relationship(
        "EvaluationIndicator",
        back_populates="dimension",
        cascade="all, delete-orphan",
    )
    assessments: Mapped[List["DimensionAssessment"]] = relationship(
        "DimensionAssessment",
        back_populates="dimension",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        """Nesnenin okunabilir metin gösterimini döndürür."""
        return f"<EvaluationDimension(id={self.id}, code='{self.code}', weight={self.weight})>"
