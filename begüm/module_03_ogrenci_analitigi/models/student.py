"""Öğrenci (Student) veritabanı modeli — PDF Bölüm 3'ün ana varlığı."""

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

if TYPE_CHECKING:
    from .academic_program import AcademicProgram
    from .student_academic_record import StudentAcademicRecord


class Student(Base):
    """Bir öğrencinin künye bilgilerini ve güncel öğrencilik durumunu tutar."""

    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    student_number: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, nullable=False
    )
    first_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    gender: Mapped[str] = mapped_column(String(20), default="unspecified", nullable=False)
    nationality: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Uluslararası öğrenci oranı (PDF 3. bölüm) bu alandan hesaplanır.
    is_international: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Burs oranı yüzde olarak tutulur: 0 = burssuz, 100 = tam burslu.
    # Burslu öğrenci yüzdesi bu alanın > 0 olmasına göre hesaplanır.
    scholarship_rate_percent: Mapped[float] = mapped_column(
        Numeric(6, 2), default=0, nullable=False
    )

    enrollment_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # current_status öğrencinin yaşam döngüsündeki yerini belirtir:
    # newly-enrolled | active | graduated | dropped-out | non-renewed
    # PDF'in "yeni kayıt / aktif / mezun" sayıları bu alandan üretilir.
    current_status: Mapped[str] = mapped_column(String(30), default="active", nullable=False)

    # Öğrencinin okuldan ayrıldığı yıl (terk / kayıt sildirme). Modül 1'in yer tutucu
    # tanımında bulunmayan, Modül 3'ün eklediği alandır: yıl bazlı öğrenci kaybı ve
    # kayıt yenilememe oranlarının doğru paydayla hesaplanabilmesi için gereklidir.
    # Mezunlarda bu alan boştur; onların ayrılış yılı actual_graduation_year'dır.
    status_change_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    preparatory_school: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    academic_program_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("academic_programs.id"), nullable=True, index=True
    )

    current_gpa: Mapped[Optional[float]] = mapped_column(Numeric(4, 2), nullable=True)

    # Ortalama mezuniyet süresi = actual_graduation_year - enrollment_year
    expected_graduation_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    actual_graduation_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Yalnızca mezun öğrenciler için anlamlıdır (PDF: "Graduate employment rate").
    # Hâlâ okuyan/terk eden öğrencilerde None kalır — istihdam oranı yalnızca
    # mezunlar üzerinden hesaplanır.
    is_employed: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    academic_program: Mapped[Optional["AcademicProgram"]] = relationship(
        "AcademicProgram", back_populates="students"
    )
    academic_records: Mapped[List["StudentAcademicRecord"]] = relationship(
        "StudentAcademicRecord", back_populates="student", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        """Nesnenin okunabilir metin gösterimini döndürür."""
        return f"<Student(id={self.id}, number='{self.student_number}')>"
