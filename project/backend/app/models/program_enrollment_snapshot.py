"""Program bazlı yıllık kayıt fotoğrafı (ProgramEnrollmentSnapshot) modeli."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.decimal_types import MoneyType
from app.database import Base

if TYPE_CHECKING:
    from app.models.academic_program import AcademicProgram


class ProgramEnrollmentSnapshot(Base):
    """Bir programın belirli bir akademik yıldaki kontenjan ve yerleşme verilerini tutar.

    Öğrenci tablosu "kim, hangi durumda" sorusunu; bu tablo ise "o yıl kontenjan kaçtı,
    kaç kişi yerleşti, taban puan neydi" sorusunu cevaplar. Talep trendi ve doluluk
    analizleri bu tablodan üretilir.
    """

    __tablename__ = "program_enrollment_snapshots"

    # Aynı program için aynı yıl iki snapshot olamaz.
    # Composite index aynı zamanda program+yıl sorgularını hızlandırır.
    __table_args__ = (
        UniqueConstraint(
            "academic_program_id", "academic_year", name="uq_program_academic_year"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    academic_program_id: Mapped[int] = mapped_column(
        ForeignKey("academic_programs.id"), nullable=False, index=True
    )
    academic_year: Mapped[str] = mapped_column(String(9), nullable=False, index=True)

    quota: Mapped[int] = mapped_column(Integer, nullable=False)
    enrolled_student_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Taban puanlar: kendi programımız, Türkiye ve Ankara ortalamaları.
    # Karşılaştırmalı analiz için üçü birlikte saklanıyor.
    minimum_admission_score: Mapped[Optional[Decimal]] = mapped_column(MoneyType, nullable=True)
    national_average_minimum_score: Mapped[Optional[Decimal]] = mapped_column(
        MoneyType, nullable=True
    )
    ankara_average_minimum_score: Mapped[Optional[Decimal]] = mapped_column(
        MoneyType, nullable=True
    )

    # Tam burslu kontenjanın taban puanı. Ücretli taban puandan belirgin biçimde
    # yüksektir; Modül 3 burs politikası analizinde ayrı gösterge olarak kullanılıyor.
    full_scholarship_minimum_admission_score: Mapped[Optional[Decimal]] = mapped_column(
        MoneyType, nullable=True
    )

    graduated_student_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    dropped_out_student_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    non_renewed_student_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    academic_program: Mapped["AcademicProgram"] = relationship(
        "AcademicProgram", back_populates="enrollment_snapshots"
    )

    def __repr__(self) -> str:
        """Nesnenin okunabilir metin gösterimini döndürür."""
        return (
            f"<ProgramEnrollmentSnapshot(id={self.id}, "
            f"program_id={self.academic_program_id}, year='{self.academic_year}')>"
        )
