"""Akademik Program modeli — Modül 1'in (Temel Veri) sahibi olduğu tablonun yerel kopyası.

Bu tablo Modül 1'e aittir; burada yalnızca demo bağımsız çalışabilsin diye
tanımlanmıştır. Kolon adları Modül 1'deki tanımla birebir aynıdır. Entegrasyonda
bu dosya silinip Modül 1'in modeli import edilecektir.
"""

from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

if TYPE_CHECKING:
    from .program_enrollment_snapshot import ProgramEnrollmentSnapshot
    from .student import Student


class AcademicProgram(Base):
    """Bölümlere bağlı lisans/yüksek lisans gibi akademik programları temsil eder."""

    __tablename__ = "academic_programs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Modül 1'de bu alan zorunludur. Bağımsız demoda bölüm tablosu bulunmadığı için
    # nullable bırakıldı; entegrasyonda Modül 1'in tanımı geçerli olacak.
    department_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    degree_level: Mapped[str] = mapped_column(String(50), nullable=False, default="Bachelor")
    duration_years: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    quota: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Modül 3 (Öğrenci Analitiği) ilişkileri.
    students: Mapped[List["Student"]] = relationship(
        "Student", back_populates="academic_program", cascade="all, delete-orphan"
    )
    enrollment_snapshots: Mapped[List["ProgramEnrollmentSnapshot"]] = relationship(
        "ProgramEnrollmentSnapshot",
        back_populates="academic_program",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        """Nesnenin okunabilir metin gösterimini döndürür."""
        return f"<AcademicProgram(id={self.id}, code='{self.code}')>"
