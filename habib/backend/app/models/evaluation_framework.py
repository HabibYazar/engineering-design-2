"""Değerlendirme çerçevesi (EvaluationFramework) veritabanı modeli."""

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.evaluation_dimension import EvaluationDimension
    from app.models.framework_assessment import FrameworkAssessment


class EvaluationFramework(Base):
    """THE, QS ve YÖK gibi değerlendirme çerçevelerini temsil eder.

    Sıralama kuruluşları metodolojilerini her yıl güncelleyebildiği için kayıt
    anahtarı yalnızca "code" değil, "code + methodology_year" ikilisidir. Böylece
    THE 2025 ve THE 2026 metodolojileri aynı anda saklanabilir ve geçmiş
    değerlendirmeler hangi metodolojiyle hesaplandıysa o haliyle korunur.
    """

    __tablename__ = "evaluation_frameworks"

    __table_args__ = (
        UniqueConstraint("code", "methodology_year", name="uq_framework_code_year"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # code: THE | QS | YOK (büyük harfe normalize edilir)
    code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Metodolojinin ait olduğu yıl (örn. 2026 sıralaması için yayımlanan metodoloji).
    methodology_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Aynı code için birden fazla yıl olabildiğinden, hesaplamalarda hangi
    # metodolojinin kullanılacağını "aktif" bayrağı belirler.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    dimensions: Mapped[List["EvaluationDimension"]] = relationship(
        "EvaluationDimension",
        back_populates="framework",
        cascade="all, delete-orphan",
    )
    assessments: Mapped[List["FrameworkAssessment"]] = relationship(
        "FrameworkAssessment",
        back_populates="framework",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        """Nesnenin okunabilir metin gösterimini döndürür."""
        return (
            f"<EvaluationFramework(id={self.id}, code='{self.code}', "
            f"year={self.methodology_year})>"
        )
