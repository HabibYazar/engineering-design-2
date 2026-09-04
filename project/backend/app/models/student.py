"""Öğrenci (Student) veritabanı modeli."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.decimal_types import MoneyType
from app.database import Base

if TYPE_CHECKING:
    from app.models.academic_program import AcademicProgram
    from app.models.student_academic_record import StudentAcademicRecord


class Student(Base):
    """Üniversiteye kayıtlı bir öğrenciyi temsil eder.

    Analitik sorguların büyük kısmı bu tablo üzerinde gruplama yaptığı için
    filtrelemede sık kullanılan alanlara (program, durum, kayıt yılı) index eklendi.
    """

    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Öğrenci numarası kurum içinde benzersizdir; hem tekrarı engellemek hem de
    # veri aktarımında eşleştirme anahtarı olarak kullanmak için unique index var.
    student_number: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, nullable=False
    )

    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)

    # gender: male | female | other | unspecified
    gender: Mapped[str] = mapped_column(String(20), default="unspecified", nullable=False)

    nationality: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Uluslararası öğrenci oranı raporlarında doğrudan filtrelendiği için ayrı alan.
    is_international: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )

    # Burs oranı yüzde olarak tutulur; 0 ise öğrenci burssuzdur.
    scholarship_rate_percent: Mapped[Decimal] = mapped_column(
        MoneyType, default=Decimal("0"), nullable=False
    )

    enrollment_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # current_status: newly-enrolled | active | graduated | suspended | dropped-out | non-renewed
    # Mezuniyet, kayıp ve yenilememe oranlarının tamamı bu alandan hesaplandığı için index eklendi.
    current_status: Mapped[str] = mapped_column(
        String(30), default="active", nullable=False, index=True
    )

    # Durum değişikliğinin gerçekleştiği yıl (bırakma/yenilememe/mezuniyet).
    # Modül 3 (Begüm) kohort ve yıllık trend analizlerinde bu alanı kullandığı için
    # entegrasyonda kanonik modele eklendi; boş bırakılabilir, eski kayıtları bozmaz.
    status_change_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Hazırlık okulu öğrencisi mi? Ayrı raporlandığı için boolean tutuluyor.
    preparatory_school: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )

    academic_program_id: Mapped[int] = mapped_column(
        ForeignKey("academic_programs.id"), nullable=False, index=True
    )

    # GPA 0-4 aralığında; ortalama hesaplarında kullanıldığı için Decimal tutuluyor.
    current_gpa: Mapped[Optional[Decimal]] = mapped_column(MoneyType, nullable=True)

    expected_graduation_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    actual_graduation_year: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, index=True
    )

    # Mezunun istihdam durumu. Üçlü mantık gerekli: True/False/bilinmiyor(None).
    # Modül 3 mezun istihdam oranını yalnızca bilgisi girilmiş mezunlar üzerinden
    # hesapladığı için nullable bırakıldı; veri yoksa oran uydurulmaz.
    is_employed: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    # Diğer modüllerle tutarlı olmak için kayıtlar silinmez, pasifleştirilir.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # İlişkiler
    academic_program: Mapped["AcademicProgram"] = relationship(
        "AcademicProgram", back_populates="students"
    )
    academic_records: Mapped[List["StudentAcademicRecord"]] = relationship(
        "StudentAcademicRecord",
        back_populates="student",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        """Nesnenin okunabilir metin gösterimini döndürür."""
        return f"<Student(id={self.id}, number='{self.student_number}', status='{self.current_status}')>"
