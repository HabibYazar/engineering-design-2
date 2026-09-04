"""Kanonik müfredat dersi — uygulamanın okuduğu temiz katman.

`curriculum_courses` HAM aktarımdır ve asla silinmez; bu tablo ondan
TÜRETİLİR. Türetme kuralı tek yerdedir: `services/curriculum_canonical.py`.

Aktarım sonunda tamamen yeniden kurulur, bu yüzden idempotenttir.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.academic_program import AcademicProgram
    from app.models.department import Department


class CurriculumCanonicalCourse(Base):
    """Birleştirilmiş, tekilleştirilmiş gerçek ders."""

    __tablename__ = "curriculum_canonical_courses"

    __table_args__ = (
        # Bir bölümde bir kanonik anahtar bir kez bulunur. Anahtar,
        # normalize edilmiş ders kodudur; kod yoksa normalize edilmiş ad.
        UniqueConstraint("department_id", "canonical_key",
                         name="uq_canonical_course"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    department_id: Mapped[int] = mapped_column(
        ForeignKey("departments.id"), nullable=False, index=True
    )
    academic_program_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("academic_programs.id"), nullable=True, index=True
    )

    #: Birleştirme anahtarı — normalize kod ("ATA101") veya normalize ad.
    canonical_key: Mapped[str] = mapped_column(String(120), nullable=False,
                                               index=True)
    course_code: Mapped[Optional[str]] = mapped_column(String(40), nullable=True,
                                                       index=True)
    #: Temizlenmiş ders adı. Kaynakta okunabilir ad yoksa NULL kalır —
    #: uydurma ad üretilmez.
    course_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    #: Arayüzde gösterilecek etiket: ad yoksa kod.
    display_name: Mapped[str] = mapped_column(Text, nullable=False)

    #: Ders kodunun ilk basamağından çıkarılan sınıf (1-5). Kod kalıba
    #: uymuyorsa NULL — zorlanmaz, ders "Diğer / Seçmeli" grubuna düşer.
    class_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True,
                                                      index=True)

    #: Bu kanonik dersin kaç ham satırdan geldiği — izlenebilirlik.
    source_row_count: Mapped[int] = mapped_column(Integer, default=1,
                                                  nullable=False)
    source_types: Mapped[Optional[str]] = mapped_column(String(400),
                                                        nullable=True)

    rebuilt_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    department: Mapped["Department"] = relationship("Department")
    academic_program: Mapped[Optional["AcademicProgram"]] = relationship(
        "AcademicProgram"
    )

    def __repr__(self) -> str:
        return f"<CurriculumCanonicalCourse({self.course_code!r} {self.class_year})>"
