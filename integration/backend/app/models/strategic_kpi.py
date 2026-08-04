"""Stratejik KPI ve fakülte kırılımı (Modül 8) modelleri.

Entegrasyon notu: Halil'in orijinal kodunda fakülte kırılımı `faculties: [4.2,
4.0, 3.8, 4.1]` şeklinde sırasız bir listeydi ve hangi değerin hangi fakülteye
ait olduğu yalnızca dizi sırasına bağlıydı. Fakülte eklenip çıkarıldığında tüm
geçmiş veri kayıyordu; bu yüzden kırılım ayrı bir tabloya ve fakülte foreign
key'ine bağlandı.

Risk eşikleri (on/risk) KPI başına saklanıyor çünkü proje tanımı eşiklerin
yönetim tarafından yapılandırılabilir olmasını istiyor.
"""

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
    from app.models.faculty import Faculty

# Varsayılan eşikler. KPI'da ayrı değer tanımlanmazsa bunlar kullanılır.
DEFAULT_ON_TRACK_THRESHOLD = Decimal("90")
DEFAULT_AT_RISK_THRESHOLD = Decimal("70")


class StrategicKpi(Base):
    """İzlenen tek bir stratejik performans göstergesi."""

    __tablename__ = "strategic_kpis"
    __table_args__ = (
        UniqueConstraint("name", "academic_year", name="uq_strategic_kpi_name_year"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # Stratejik boyut (Eğitim Kalitesi, Ar-Ge vb.). Boyut bazlı özet raporda
    # gruplama anahtarı olduğu için index eklendi.
    dimension: Mapped[str] = mapped_column(String(120), nullable=False, index=True)

    unit: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    academic_year: Mapped[str] = mapped_column(String(9), nullable=False, index=True)

    # Ölçüm değerleri Decimal: oran hesabında float yuvarlaması eşik sınırında
    # KPI'yı yanlış banda düşürebilir.
    current_value: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)
    target_value: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)

    # Geçmiş yıl ve üniversite ortalaması opsiyonel: yeni tanımlanan KPI'da
    # karşılaştırma verisi henüz yoktur, sıfır yazmak yanıltıcı olurdu.
    previous_value: Mapped[Optional[Decimal]] = mapped_column(MoneyType, nullable=True)
    university_average: Mapped[Optional[Decimal]] = mapped_column(
        MoneyType, nullable=True
    )

    on_track_threshold: Mapped[Decimal] = mapped_column(
        MoneyType, default=DEFAULT_ON_TRACK_THRESHOLD, nullable=False
    )
    at_risk_threshold: Mapped[Decimal] = mapped_column(
        MoneyType, default=DEFAULT_AT_RISK_THRESHOLD, nullable=False
    )

    corrective_action: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    faculty_values: Mapped[List["KpiFacultyValue"]] = relationship(
        "KpiFacultyValue", back_populates="kpi", cascade="all, delete-orphan"
    )


class KpiFacultyValue(Base):
    """Bir KPI'nın tek bir fakülteye ait ölçüm değeri."""

    __tablename__ = "kpi_faculty_values"
    __table_args__ = (
        UniqueConstraint("kpi_id", "faculty_id", name="uq_kpi_faculty_value"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    kpi_id: Mapped[int] = mapped_column(
        ForeignKey("strategic_kpis.id"), nullable=False, index=True
    )
    faculty_id: Mapped[int] = mapped_column(
        ForeignKey("faculties.id"), nullable=False, index=True
    )

    value: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    kpi: Mapped["StrategicKpi"] = relationship(
        "StrategicKpi", back_populates="faculty_values"
    )
    faculty: Mapped["Faculty"] = relationship("Faculty")
