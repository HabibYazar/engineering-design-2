"""Öğrenci dönemlik akademik kayıt modeli.

Her satır bir öğrencinin bir akademik yıl/dönemdeki başarı fotoğrafıdır.
Akademik performans trendi ve kayıt yenileme oranları buradan hesaplanır.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
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
    from .student import Student


class StudentAcademicRecord(Base):
    """Bir öğrencinin tek bir dönemdeki ders yükü ve başarı bilgisi."""

    __tablename__ = "student_academic_records"
    __table_args__ = (
        UniqueConstraint(
            "student_id", "academic_year", "semester", name="uq_student_year_semester"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id"), nullable=False, index=True
    )

    # Biçim: "2026-2027"
    academic_year: Mapped[str] = mapped_column(String(9), nullable=False, index=True)
    # fall | spring | summer
    semester: Mapped[str] = mapped_column(String(10), nullable=False)

    registered_course_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    passed_course_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_course_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    earned_credits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    attempted_credits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    semester_gpa: Mapped[Optional[float]] = mapped_column(Numeric(4, 2), nullable=True)
    cumulative_gpa: Mapped[Optional[float]] = mapped_column(Numeric(4, 2), nullable=True)

    # Kayıt yenilememe, PDF'in "student non-renewal rate" göstergesinin kaynağıdır.
    registration_renewed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    student: Mapped["Student"] = relationship("Student", back_populates="academic_records")

    def __repr__(self) -> str:
        """Nesnenin okunabilir metin gösterimini döndürür."""
        return (
            f"<StudentAcademicRecord(student_id={self.student_id}, "
            f"year='{self.academic_year}', semester='{self.semester}')>"
        )
