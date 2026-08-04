"""Değerlendirme göstergesi (EvaluationIndicator) veritabanı modeli."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    Boolean,
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
    from app.models.benchmark_metric_value import BenchmarkMetricValue
    from app.models.evaluation_dimension import EvaluationDimension
    from app.models.institutional_metric_value import InstitutionalMetricValue


class EvaluationIndicator(Base):
    """Bir boyut altındaki ölçülebilir gösterge.

    code alanı yalnızca boyut içinde değil, TÜM sistemde benzersizdir. Bunun sebebi:
    CSV/Excel içe aktarımında ve otomatik eşleştirmede göstergeye tek bir metinle
    (örn. "the-international-student-ratio") referans verebilmek. Bu, istenen
    "aynı dimension içinde benzersiz" kuralını da kapsayan daha güçlü bir kısıttır.
    Seed verisinde kodlar çerçeve ön ekiyle üretilir (the-, qs-, yok-).
    """

    __tablename__ = "evaluation_indicators"

    __table_args__ = (
        UniqueConstraint("dimension_id", "code", name="uq_indicator_dimension_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    dimension_id: Mapped[int] = mapped_column(
        ForeignKey("evaluation_dimensions.id"), nullable=False, index=True
    )

    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Ölçü birimi (ratio, %, adet, TL vb.). Boş bırakılabilir; doluysa cevapta gösterilir.
    unit: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # calculation_type: raw | percentage | ratio | score | boolean | manual
    calculation_type: Mapped[str] = mapped_column(String(20), nullable=False)

    # Göstergenin boyut içindeki yüzdesel ağırlığı (0-100).
    weight: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)

    # direction: higher_is_better | lower_is_better | target_is_best
    # Normalizasyonun yönünü belirler; örneğin öğrenci/öğretim üyesi oranında
    # düşük değer iyidir, yayın sayısında yüksek değer iyidir.
    direction: Mapped[str] = mapped_column(String(20), nullable=False)

    # Normalizasyon sınırları. Eksik olduklarında hesaplama motoru açıklanabilir
    # bir fallback uygular ve calculation_notes'a not düşer.
    minimum_value: Mapped[Optional[Decimal]] = mapped_column(MoneyType, nullable=True)
    target_value: Mapped[Optional[Decimal]] = mapped_column(MoneyType, nullable=True)
    maximum_value: Mapped[Optional[Decimal]] = mapped_column(MoneyType, nullable=True)

    # Verinin nereden geleceğini açıklayan serbest metin (eksik veri raporunda gösterilir).
    data_source: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Hazırlık (readiness) skoruna dahil edilecek mi?
    required_for_readiness: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=True
    )

    # --- Projeye özel genişletmeler ---
    # auto_source_key: Modül 1/2 verisinden otomatik doldurulacak göstergeleri
    # işaretler. Aynı anahtar birden fazla çerçevede kullanılabilir; böylece bir
    # senkronizasyon THE, QS ve YÖK göstergelerini aynı anda besler.
    auto_source_key: Mapped[Optional[str]] = mapped_column(String(80), nullable=True, index=True)

    # What-if etki analizinde hangi değişkenin pay ve paydayı etkilediğini bildirir.
    # Örn. "yayın / akademik personel" göstergesi için
    # impact_numerator_variable="publication_count", impact_denominator_variable="academic_staff_count".
    impact_numerator_variable: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    impact_denominator_variable: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    dimension: Mapped["EvaluationDimension"] = relationship(
        "EvaluationDimension", back_populates="indicators"
    )
    metric_values: Mapped[List["InstitutionalMetricValue"]] = relationship(
        "InstitutionalMetricValue",
        back_populates="indicator",
        cascade="all, delete-orphan",
    )
    benchmark_values: Mapped[List["BenchmarkMetricValue"]] = relationship(
        "BenchmarkMetricValue",
        back_populates="indicator",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        """Nesnenin okunabilir metin gösterimini döndürür."""
        return f"<EvaluationIndicator(id={self.id}, code='{self.code}')>"
