"""Akademik personel (Modül 4) veritabanı modeli.

Entegrasyon notu: Eda'nın orijinal `Staff` sınıfı düz bir Python nesnesiydi ve
bölüm/fakülte bilgisini serbest metin olarak tutuyordu. Bu yapıda aynı bölüm
farklı yazımlarla ("Bilgisayar Müh." / "Bilgisayar Mühendisliği") ayrı grup gibi
görünüyor ve fakülte karşılaştırmaları bozuluyordu. Bu yüzden kanonik modelde
bölüm bir foreign key'e bağlandı; fakülte bilgisi bölüm üzerinden türetiliyor.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.department import Department


class AcademicStaff(Base):
    """Bir bölüme bağlı akademik personelin performans verilerini tutar."""

    __tablename__ = "academic_staff"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Personel sicil numarası; import ve güncellemelerde tekil anahtar olarak
    # kullanıldığı için unique.
    staff_number: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, nullable=False
    )

    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Unvan karşılaştırma raporlarında gruplama anahtarı olduğu için index eklendi.
    title: Mapped[str] = mapped_column(String(60), nullable=False, index=True)

    department_id: Mapped[int] = mapped_column(
        ForeignKey("departments.id"), nullable=False, index=True
    )

    # Performans verileri yıllık raporlandığı için akademik yıl ile birlikte tutulur.
    academic_year: Mapped[str] = mapped_column(String(9), nullable=False, index=True)

    # Modül 4 puanlama girdileri. Hepsi sayım olduğu için Integer yeterli;
    # ağırlıklandırma app/config/academic_staff_weights.json dosyasından gelir.
    publication_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    citation_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    teaching_load_hours: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    advising_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    project_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    patent_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # 0-10 arası topluma katkı puanı; ölçek dışı değerler servis katmanında reddedilir.
    community_engagement_score: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )

    has_administrative_duty: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    has_industry_collaboration: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    # Diğer modüllerle tutarlı olmak için kayıtlar silinmez, pasifleştirilir.
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    department: Mapped["Department"] = relationship("Department")

    @property
    def full_name(self) -> str:
        """Raporlarda tek alan olarak gösterilen ad soyad."""
        return f"{self.first_name} {self.last_name}"
