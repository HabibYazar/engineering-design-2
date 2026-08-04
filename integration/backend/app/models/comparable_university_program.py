"""Karşılaştırma için diğer üniversitelerin program verileri."""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.decimal_types import MoneyType
from app.database import Base


class ComparableUniversityProgram(Base):
    """Başka üniversitelerdeki benzer programların kontenjan ve puan verileri.

    Kendi programımızı sektörle kıyaslayabilmek için tutulur. Bu tablo kendi
    veritabanımızdaki AcademicProgram ile foreign key ile bağlı değildir; çünkü
    dış üniversitelerin programları bizim yapımızda yer almaz. Eşleştirme
    program adı üzerinden yapılır.
    """

    __tablename__ = "comparable_university_programs"

    # Aynı üniversite + program + yıl kombinasyonu tekrar girilmesin.
    __table_args__ = (
        UniqueConstraint(
            "university_name",
            "program_name",
            "academic_year",
            name="uq_comparable_university_program_year",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    university_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    program_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    academic_year: Mapped[str] = mapped_column(String(9), nullable=False, index=True)

    quota: Mapped[int] = mapped_column(Integer, nullable=False)
    enrolled_student_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Doluluk oranı dışarıdan geldiği gibi saklanır; verilmezse hesaplanarak doldurulur.
    occupancy_rate: Mapped[Optional[Decimal]] = mapped_column(MoneyType, nullable=True)
    minimum_admission_score: Mapped[Optional[Decimal]] = mapped_column(MoneyType, nullable=True)

    # Sadece "benzer" değil, doğrudan rakip olarak izlenen üniversiteler işaretlenir.
    is_competitor: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        """Nesnenin okunabilir metin gösterimini döndürür."""
        return (
            f"<ComparableUniversityProgram(id={self.id}, "
            f"university='{self.university_name}', program='{self.program_name}')>"
        )
