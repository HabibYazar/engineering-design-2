"""Karşılaştırma kurumu (BenchmarkInstitution) veritabanı modeli."""

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.benchmark_metric_value import BenchmarkMetricValue


class BenchmarkInstitution(Base):
    """Karşılaştırma yapılacak diğer yükseköğretim kurumları.

    Kendi veritabanımızdaki Faculty/Department yapısıyla ilişkilendirilmez;
    dış kurumların iç yapısını tutmuyoruz. Eşleştirme gösterge bazında,
    BenchmarkMetricValue üzerinden yapılır.

    institution_type alanı karşılaştırma kapsamını belirlemede kullanılır
    (national-average, similar, competitor gibi).
    """

    __tablename__ = "benchmark_institutions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # İsim benzersizdir; içe aktarımda eşleştirme anahtarı olarak kullanılır.
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)

    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)

    # institution_type: national-average | similar | competitor | international | other
    institution_type: Mapped[str] = mapped_column(
        String(30), default="similar", nullable=False, index=True
    )

    # Doğrudan rakip olarak izlenen kurumlar ayrıca işaretlenir.
    is_competitor: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    metric_values: Mapped[List["BenchmarkMetricValue"]] = relationship(
        "BenchmarkMetricValue",
        back_populates="institution",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        """Nesnenin okunabilir metin gösterimini döndürür."""
        return f"<BenchmarkInstitution(id={self.id}, name='{self.name}')>"
