"""Akademik Program (AcademicProgram) veritabanı modeli."""

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.department import Department
    from app.models.program_enrollment_snapshot import ProgramEnrollmentSnapshot
    from app.models.student import Student


class AcademicProgram(Base):
    """Bölümlere bağlı lisans/yüksek lisans gibi akademik programları temsil eder."""

    __tablename__ = "academic_programs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Her program bir bölüme bağlıdır.
    department_id: Mapped[int] = mapped_column(
        ForeignKey("departments.id"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)

    # degree_level programın derecesini tutar (Bachelor, Master, PhD gibi).
    # Serbest metin bırakıldı; ileride sabit bir listeye (Enum) çevrilebilir.
    degree_level: Mapped[str] = mapped_column(String(50), nullable=False)

    # duration_years ve quota, karar destek analizlerinde (kontenjan doluluk oranı vb.)
    # kullanılacağı için sayısal tutuluyor.
    duration_years: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    quota: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Many-to-one: Programdan bağlı olduğu bölüme erişim.
    department: Mapped["Department"] = relationship("Department", back_populates="programs")

    # --- Modül 2 (Student Analytics) ile eklenen ilişkiler ---
    # Mevcut alanlara dokunulmadı; yalnızca yeni ilişkiler eklendi.
    # Bir programa kayıtlı öğrenciler ve programın yıllık kayıt fotoğrafları.
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
