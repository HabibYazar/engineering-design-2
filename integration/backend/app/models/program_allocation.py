"""Program düzeyinde kaynak tahsisi.

NEDEN VAR
---------
Asistan "Bilgisayar Mühendisliği öğrenci sayısı %15 artarsa personel ihtiyacı
ve laboratuvar kapasitesi nasıl etkilenir?" sorusuna cevap verirken, veri
modelinde program–personel ve program–mekân ilişkisi bulunmadığı için
üniversite geneli sayıları (180 öğretim üyesi, 1.020 derslik koltuğu)
kullanmak zorunda kalıyordu. Kurum toplamını program değeri gibi göstermek
bir karar destek sisteminde kabul edilemez.

Bu iki tablo o boşluğu kapatır:

* `ProgramAcademicStaffAllocation` — bir öğretim üyesinin bir programa
  ayırdığı iş yükü. Aynı kişi birden çok programda ders verebilir.
* `ProgramFacilityAllocation` — bir programın bir mekânı haftada kaç saat
  kullandığı. Aynı mekân birden çok program tarafından paylaşılabilir.

BİRİM KARARI
------------
Kapasite "kişi" ile ölçülmez; zaman boyutu taşır. Bir derslik 60 kişilik ve
haftada 40 saat açıksa haftalık kapasitesi 2.400 koltuk-saattir. "60 kişi"
demek, o dersliğin haftada yalnızca bir ders için var olduğunu varsaymak
olurdu.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
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

# Bir mekânın haftalık kullanılabilir ders saati. Kampüs 5 gün × 8 saat
# programlanabilir kabul edilir. Tek yerde tanımlıdır; tahsis doğrulaması ve
# kapasite hesabı aynı sayıyı kullanır.
WEEKLY_AVAILABLE_HOURS: int = 40

# Tahsis türleri. Mekân türüyle uyumu servis katmanında denetlenir; bir
# işletme programına mühendislik laboratuvarı tahsis edilemez.
ALLOCATION_TYPES = ("classroom", "laboratory", "studio", "workshop")

STAFF_ROLES = ("koordinatör", "öğretim üyesi", "yardımcı öğretim elemanı")


class ProgramAcademicStaffAllocation(Base):
    """Bir öğretim üyesinin bir programa ayırdığı iş yükü.

    `allocation_percent` kişinin toplam mesaisinin yüzde kaçını bu programa
    verdiğini söyler. Aynı kişinin aynı akademik yıldaki tahsislerinin toplamı
    %100'ü aşamaz — bu kural servis katmanında doğrulanır ve testlidir.

    KİŞİ SAYISI ile FTE FARKLIDIR. Bir programda 12 öğretim üyesi ders
    veriyor olabilir ama her biri mesaisinin yalnızca bir kısmını ayırıyorsa
    programın gerçek akademik kapasitesi 8,5 FTE'dir. İkisi ayrı ayrı
    raporlanır.
    """

    __tablename__ = "program_academic_staff_allocations"
    __table_args__ = (
        # Aynı kişi aynı yıl aynı programa iki kez tahsis edilemez.
        UniqueConstraint(
            "academic_year",
            "program_id",
            "academic_staff_id",
            name="uq_program_staff_allocation",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    academic_year: Mapped[str] = mapped_column(String(9), nullable=False, index=True)

    program_id: Mapped[int] = mapped_column(
        ForeignKey("academic_programs.id"), nullable=False, index=True
    )
    academic_staff_id: Mapped[int] = mapped_column(
        ForeignKey("academic_staff.id"), nullable=False, index=True
    )

    # Yüzde değerleri MoneyType ile saklanır: float yuvarlaması FTE
    # toplamlarında gözle görülür sapma üretiyordu.
    allocation_percent: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)

    weekly_course_hours: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
        doc="Bu programda haftada verilen ders saati.",
    )

    role: Mapped[str] = mapped_column(
        String(40), default="öğretim üyesi", nullable=False
    )

    # Kişinin ana programı. Rapor ve kadro planlamasında ayırt edicidir.
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    program: Mapped["AcademicProgram"] = relationship("AcademicProgram")  # noqa: F821
    academic_staff: Mapped["AcademicStaff"] = relationship("AcademicStaff")  # noqa: F821

    @property
    def fte(self) -> Decimal:
        """Tam zaman eşdeğeri: tahsis yüzdesinin ondalık karşılığı."""
        return self.allocation_percent / Decimal("100")


class ProgramFacilityAllocation(Base):
    """Bir programın bir mekânı haftada kaç saat kullandığı.

    PAYLAŞIM AÇIKÇA MODELLENİR. `shared_usage_percent`, bu mekânın kapasitesinin
    yüzde kaçının bu programa ait sayılacağını söyler. Bir laboratuvarı üç
    program paylaşıyorsa hiçbiri o laboratuvarın tam kapasitesini kendi
    kapasitesi gibi gösteremez.
    """

    __tablename__ = "program_facility_allocations"
    __table_args__ = (
        UniqueConstraint(
            "academic_year",
            "program_id",
            "facility_id",
            name="uq_program_facility_allocation",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    academic_year: Mapped[str] = mapped_column(String(9), nullable=False, index=True)

    program_id: Mapped[int] = mapped_column(
        ForeignKey("academic_programs.id"), nullable=False, index=True
    )
    facility_id: Mapped[int] = mapped_column(
        ForeignKey("physical_facilities.id"), nullable=False, index=True
    )

    allocation_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    weekly_allocated_hours: Mapped[int] = mapped_column(
        Integer, nullable=False,
        doc="Bu programın mekânı haftada kaç saat kullandığı.",
    )

    shared_usage_percent: Mapped[Decimal] = mapped_column(
        MoneyType, nullable=False,
        doc="Mekân kapasitesinin bu programa düşen payı (0-100).",
    )

    priority_level: Mapped[int] = mapped_column(
        Integer, default=2, nullable=False,
        doc="1 = birincil kullanıcı, 2 = paylaşımlı, 3 = ara sıra.",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    program: Mapped["AcademicProgram"] = relationship("AcademicProgram")  # noqa: F821
    facility: Mapped["PhysicalFacility"] = relationship("PhysicalFacility")  # noqa: F821
