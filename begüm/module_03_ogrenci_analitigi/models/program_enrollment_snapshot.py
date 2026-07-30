"""Program yıllık kayıt fotoğrafı (snapshot) modeli.

Her satır bir akademik programın bir akademik yıldaki kontenjan, kayıt, taban puan
ve öğrenci kaybı verilerini tutar. PDF Bölüm 3'teki doluluk oranı, taban puan
analizi ve öğrenci kaybı göstergelerinin ana kaynağıdır; Bölüm 7 (sürdürülebilirlik)
ve Bölüm 11 (erken uyarı) de bu tabloyu kullanır.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

if TYPE_CHECKING:
    from .academic_program import AcademicProgram


class ProgramEnrollmentSnapshot(Base):
    """Bir akademik programın tek bir akademik yıldaki kayıt fotoğrafı."""

    __tablename__ = "program_enrollment_snapshots"
    __table_args__ = (
        UniqueConstraint("academic_program_id", "academic_year", name="uq_program_year"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    academic_program_id: Mapped[int] = mapped_column(
        ForeignKey("academic_programs.id"), nullable=False, index=True
    )
    academic_year: Mapped[str] = mapped_column(String(9), nullable=False, index=True)

    # Doluluk oranı = enrolled_student_count / quota
    quota: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    enrolled_student_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Taban puan analizi: programın puanı Ankara ve Türkiye ortalamasıyla karşılaştırılır.
    minimum_admission_score: Mapped[Optional[float]] = mapped_column(
        Numeric(8, 2), nullable=True
    )
    national_average_minimum_score: Mapped[Optional[float]] = mapped_column(
        Numeric(8, 2), nullable=True
    )
    ankara_average_minimum_score: Mapped[Optional[float]] = mapped_column(
        Numeric(8, 2), nullable=True
    )

    graduated_student_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    dropped_out_student_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    non_renewed_student_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    academic_program: Mapped["AcademicProgram"] = relationship(
        "AcademicProgram", back_populates="enrollment_snapshots"
    )

    def __repr__(self) -> str:
        """Nesnenin okunabilir metin gösterimini döndürür."""
        return (
            f"<ProgramEnrollmentSnapshot(program_id={self.academic_program_id}, "
            f"year='{self.academic_year}')>"
        )
