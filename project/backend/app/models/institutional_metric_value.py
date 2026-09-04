"""Kurumun gösterge verisi (InstitutionalMetricValue) veritabanı modeli."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.decimal_types import MoneyType
from app.database import Base

if TYPE_CHECKING:
    from app.models.evaluation_indicator import EvaluationIndicator


class InstitutionalMetricValue(Base):
    """Bir göstergenin belirli bir akademik yıl ve dönemdeki gerçek değeri.

    Aynı gösterge + yıl + dönem için tek kayıt bulunur; bu kısıt hem veritabanı
    seviyesinde hem de API katmanında uygulanır.

    origin alanı verinin kaynağını ayırt eder. Modül 1/2'den otomatik üretilen
    kayıtlar "automatic" olarak işaretlenir; senkronizasyon servisi yalnızca bu
    kayıtların üzerine yazar. Elle girilen (manual) ve içe aktarılan (imported)
    veriler otomatik senkronizasyonla EZİLMEZ — doğrulanmış insan verisi önceliklidir.
    """

    __tablename__ = "institutional_metric_values"

    __table_args__ = (
        UniqueConstraint(
            "indicator_id", "academic_year", "period", name="uq_metric_indicator_year_period"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    indicator_id: Mapped[int] = mapped_column(
        ForeignKey("evaluation_indicators.id"), nullable=False, index=True
    )

    academic_year: Mapped[str] = mapped_column(String(9), nullable=False, index=True)

    # period: annual | fall | spring | summer
    period: Mapped[str] = mapped_column(String(10), default="annual", nullable=False, index=True)

    # Değer, pay ve payda Decimal olarak saklanır; oran hesaplarında float
    # sapması bütçe ve skor sonuçlarını bozmasın diye.
    value: Mapped[Optional[Decimal]] = mapped_column(MoneyType, nullable=True)
    numerator: Mapped[Optional[Decimal]] = mapped_column(MoneyType, nullable=True)
    denominator: Mapped[Optional[Decimal]] = mapped_column(MoneyType, nullable=True)

    # data_status: available | partial | missing | estimated | invalid
    data_status: Mapped[str] = mapped_column(
        String(20), default="available", nullable=False, index=True
    )

    # origin: automatic | manual | imported
    origin: Mapped[str] = mapped_column(
        String(20), default="manual", nullable=False, index=True
    )

    source_reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Verinin hangi tarihte ölçüldüğü; kayıt tarihinden farklı olabilir.
    measured_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    indicator: Mapped["EvaluationIndicator"] = relationship(
        "EvaluationIndicator", back_populates="metric_values"
    )

    def __repr__(self) -> str:
        """Nesnenin okunabilir metin gösterimini döndürür."""
        return (
            f"<InstitutionalMetricValue(id={self.id}, indicator_id={self.indicator_id}, "
            f"year='{self.academic_year}', status='{self.data_status}')>"
        )
