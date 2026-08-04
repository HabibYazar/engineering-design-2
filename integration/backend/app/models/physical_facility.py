"""Fiziksel mekân/tesis (Modül 5) veritabanı modeli.

Entegrasyon notu: Eda'nın orijinal kodunda hem `Facility` hem `Classroom` sınıfı
vardı ve `Classroom` alanları `Facility`'nin alt kümesiydi. İki tablo tutmak aynı
derslik için iki farklı doluluk değeri saklanmasına yol açacağı için tek tabloda
birleştirildi; derslikler `facility_type == "classroom"` ile filtreleniyor.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.department import Department

# Desteklenen tesis türleri. Serbest metin yerine sabit liste kullanılıyor ki
# tür bazlı kullanım oranı raporu her zaman aynı grupları üretsin.
FACILITY_TYPES = ("classroom", "laboratory", "office", "library", "other")


class PhysicalFacility(Base):
    """Derslik, laboratuvar, ofis ve benzeri fiziksel mekânları temsil eder."""

    __tablename__ = "physical_facilities"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Mekân kodu ("A101", "Lab-1"). Kampüs genelinde tekil olduğu için unique.
    code: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    facility_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)

    # Ortak kullanım alanları (kütüphane, konferans salonu) hiçbir bölüme ait
    # olmayabilir; bu yüzden nullable bırakıldı.
    department_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("departments.id"), nullable=True, index=True
    )

    # Kapasite sıfır olamaz: doluluk oranı hesabında paydada yer alıyor.
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    occupied: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Metrekare bilgisi kişi başına düşen alan raporunda kullanılır; her mekân
    # için ölçüm girilmemiş olabileceğinden nullable.
    area_square_meters: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    department: Mapped[Optional["Department"]] = relationship("Department")

    @property
    def occupancy_percent(self) -> float:
        """Doluluk yüzdesi. Kapasite 0 ise bölme hatası yerine 0.0 döner."""
        if not self.capacity:
            return 0.0
        return round((self.occupied / self.capacity) * 100, 2)
