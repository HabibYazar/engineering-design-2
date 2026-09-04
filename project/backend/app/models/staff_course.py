"""Akademisyenin verdiği dersler — YÖK Akademik'ten, yıl bazında.

KAYNAK
------
Toplayıcının `courses` tablosu. Ankara Bilim Üniversitesi'nin 164
akademisyeni için 1860 satır; her satır bir akademisyenin bir akademik
yılda verdiği bir derstir:

    {"Dönem": "2025-2026", "Ders Adı": "Atık Yönetimi",
     "Dili": "Türkçe", "Saat": "2"}

NEDEN AYRI TABLO
----------------
`academic_staff.teaching_load_hours` yalnızca EN GÜNCEL yılın toplam
saatini tutuyor — tek bir sayı. Oysa kaynak 1992'ye kadar uzanan yıl
bazlı bir geçmiş taşıyor. Bu geçmişi tek sayıya indirgemek:

  * "bu akademisyen hangi dersleri veriyor?" sorusunu cevaplanamaz kılar,
  * ders yükünün yıllar içindeki değişimini görünmez yapar.

Ham satırlar burada durur; `teaching_load_hours` bu tablodan TÜRETİLİR
ve türetme kuralı (yalnızca en güncel yıl) değişmez.

KAYNAKTA OLMAYAN
----------------
Ders KODU yoktur — YÖK Akademik yalnızca ders adını yayımlar. Müfredat
dosyasındaki (`curriculum_courses`) kodlarla eşleştirme YAPILMAZ: aynı
adın iki farklı ders olması mümkündür ve yanlış eşleştirme, bir
akademisyene vermediği dersi atfetmek olurdu.
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
    from app.models.academic_staff import AcademicStaff


class AcademicStaffCourse(Base):
    """Bir akademisyenin bir akademik yılda verdiği tek bir ders."""

    __tablename__ = "academic_staff_courses"

    __table_args__ = (
        # Kaynağın doğal anahtarı. Aynı akademisyen aynı yıl aynı dersi
        # aynı dilde iki kez veremez; aktarım bu sayede idempotenttir.
        UniqueConstraint(
            "academic_staff_id",
            "academic_year",
            "course_name",
            "language",
            name="uq_staff_course",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    academic_staff_id: Mapped[int] = mapped_column(
        ForeignKey("academic_staff.id"), nullable=False, index=True
    )

    #: "2025-2026". Kaynak bu biçimde veriyor; normalize edilemeyen
    #: satırlar aktarılmaz (rapora yazılır).
    academic_year: Mapped[str] = mapped_column(String(9), nullable=False, index=True)

    course_name: Mapped[str] = mapped_column(String(300), nullable=False)
    #: "Türkçe" / "İngilizce" …
    language: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)

    #: Haftalık ders saati. Kaynakta okunamayan değer 0 DEĞİL, NULL olur.
    weekly_hours: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # --- köken ---
    source_dataset: Mapped[str] = mapped_column(String(120), nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    academic_staff: Mapped["AcademicStaff"] = relationship("AcademicStaff")

    def __repr__(self) -> str:
        return (
            f"<AcademicStaffCourse({self.academic_year} "
            f"{self.course_name!r} staff={self.academic_staff_id})>"
        )
