"""Öğrencinin dönemlik akademik kaydı (StudentAcademicRecord) modeli."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.decimal_types import MoneyType
from app.database import Base

if TYPE_CHECKING:
    from app.models.student import Student


class StudentAcademicRecord(Base):
    """Bir öğrencinin tek bir akademik dönemdeki performansını tutar.

    Akademik başarı analizleri (ders geçme oranı, kredi verimliliği, GPA gelişimi)
    bu tablodan üretilir.
    """

    __tablename__ = "student_academic_records"

    # Aynı öğrenci için aynı yıl ve dönem iki kez girilemez.
    # Bu kısıt veritabanı seviyesinde de garanti altına alındı; API katmanı 409 döndürür.
    __table_args__ = (
        UniqueConstraint(
            "student_id", "academic_year", "semester", name="uq_student_year_semester"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id"), nullable=False, index=True
    )

    # academic_year "2024-2025" biçimindedir; yıl bazlı trend sorgularında filtrelendiği için index var.
    academic_year: Mapped[str] = mapped_column(String(9), nullable=False, index=True)

    # semester: fall | spring | summer
    semester: Mapped[str] = mapped_column(String(10), nullable=False)

    registered_course_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    passed_course_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_course_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Kredi verimliliği (earned / attempted) akademik başarı göstergelerinden biridir.
    earned_credits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    attempted_credits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    semester_gpa: Mapped[Optional[Decimal]] = mapped_column(MoneyType, nullable=True)
    cumulative_gpa: Mapped[Optional[Decimal]] = mapped_column(MoneyType, nullable=True)

    # Kayıt yenilenmediyse öğrenci "non-renewed" riskindedir; yenilememe oranı buradan da izlenebilir.
    registration_renewed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    student: Mapped["Student"] = relationship("Student", back_populates="academic_records")

    def __repr__(self) -> str:
        """Nesnenin okunabilir metin gösterimini döndürür."""
        return (
            f"<StudentAcademicRecord(id={self.id}, student_id={self.student_id}, "
            f"year='{self.academic_year}', semester='{self.semester}')>"
        )
