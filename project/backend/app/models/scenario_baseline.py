"""Senaryo hesaplamalarının başlangıç noktası olan (ScenarioBaseline) modeli."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.decimal_types import MoneyType
from app.database import Base


class ScenarioBaseline(Base):
    """Üniversitenin mevcut mali, personel ve kapasite durumunu tutan referans kayıt.

    Finans, personel ve fiziksel kapasite modülleri henüz hazır olmadığı için
    bu değerler şimdilik elle girilir. İleride o modüller devreye girdiğinde
    baseline otomatik doldurulacak, hesaplama motoru değişmeyecek.
    """

    __tablename__ = "scenario_baselines"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # --- Öğrenci ve gelir tarafı ---
    student_count: Mapped[int] = mapped_column(Integer, nullable=False)
    annual_tuition_per_student: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)
    scholarship_rate_percent: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)
    annual_research_revenue: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)
    annual_other_revenue: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)

    # --- Gider tarafı ---
    # Giderleri tek bir toplam yerine kalemlere ayırıyoruz; çünkü her kalem
    # farklı bir değişkenden etkileniyor (personel sayısı, enflasyon, kur, öğrenci sayısı).
    # Akademik personel gideri. Senaryo motoru ortalama akademik maaşı bu
    # değeri kadro sayısına bölerek buluyor; idari maaşlar BURAYA GİRMEZ.
    annual_personnel_expense: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)
    # İdari personel gideri ayrı tutulur: akademik maaş zammından etkilenmez
    # ve döviz kuruyla artmaz. Eski kayıtlarda bulunmadığı için varsayılanı 0.
    annual_administrative_personnel_expense: Mapped[Decimal] = mapped_column(
        MoneyType, nullable=False, default=Decimal("0"), server_default="0"
    )
    annual_education_expense: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)
    annual_rd_expense: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)
    annual_building_energy_expense: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)
    annual_technology_expense: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)

    # --- Personel ve fiziksel kapasite ---
    academic_staff_count: Mapped[int] = mapped_column(Integer, nullable=False)
    classroom_capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    laboratory_capacity: Mapped[int] = mapped_column(Integer, nullable=False)

    # Sistemde aynı anda yalnızca bir baseline aktif olabilir.
    # Kural servis katmanında uygulanır: yeni bir kayıt aktif yapılınca eskisi pasifleşir.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    # onupdate: Kayıt her güncellendiğinde tarih otomatik yenilenir.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        """Nesnenin okunabilir metin gösterimini döndürür."""
        return f"<ScenarioBaseline(id={self.id}, name='{self.name}', active={self.is_active})>"
