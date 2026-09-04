"""KAPSAMLI ÖĞRENCİ DEMOGRAFİ SAYIMLARI — normalize, dönemli, kaynaklı.

NEDEN YENİ BİR MODEL
--------------------
Mevcut modellerin hiçbiri bu veriyi taşıyamıyordu:

  · `Student.is_international` BİREYSEL öğrenci satırı ister; kurumun
    gerçek verisinde bireysel öğrenci kaydı YOKTUR (yalnızca toplamlar).
  · `UniversityStudentHeadcount` yalnızca ÜNİVERSİTE düzeyindedir ve
    cinsiyet/öğrenim düzeyi kırılımı taşır; fakülte/program kırılımı yok.
  · `YksPlacementRecord` yerleştirme kaydıdır, mevcut öğrenci gövdesinin
    demografisini anlatmaz.

Bu tablo, "bir KAPSAMDA, bir DÖNEMDE, bir DEMOGRAFİ BOYUTUNDA kaç
öğrenci var" sorusunun genel cevabıdır. Bugün yalnızca `foreign`
(yabancı uyruklu) boyutu doludur; cinsiyet, burs türü, uyruk kırılımı
gibi yeni boyutlar aynı tabloya `dimension` değeriyle eklenebilir —
her demografi için ayrı tablo açmak, aynı kuralı tekrar tekrar yazmak
demek olurdu.

KAYNAK NE DERSE O
-----------------
`source_faculty_label` / `source_program_label` alanları kaynak
dosyadaki metni AYNEN saklar. Çözümlenen kimlikler (`faculty_id`,
`department_id`, `academic_program_id`) bunun YANINDA durur, yerine
geçmez. Böylece:

  · kaynak toplamları her zaman yeniden üretilebilir,
  · eşleştirme kararları denetlenebilir (`resolution`, `resolution_note`),
  · eşleşmeyen satır SESSİZCE DÜŞMEZ; kaynak etiketiyle saklanır.

FAKÜLTE ATIFI KAYNAĞINDIR
-------------------------
Bir program, kurumun hiyerarşisinde kaynak dosyanın söylediğinden
BAŞKA bir fakültenin altında olabilir (gözlenen: "İç Mimarlık ve Çevre
Tasarımı" kaynakta Mühendislik ve Mimarlık'ta, hiyerarşide Güzel
Sanatlar'da). Böyle bir durumda satır KAYNAĞIN fakültesine yazılır ve
program kimliği BOŞ bırakılıp çelişki `resolution_note` içinde
kaydedilir. Programı sessizce başka fakülteye taşımak da, fakülte
toplamını kaynağa aykırı hâle getirmek de veri uydurmak olurdu.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

#: Demografi boyutları. Yeni boyut eklerken tablo değil bu liste büyür.
DIMENSION_FOREIGN = "foreign"

#: Eşleştirmenin hangi düzeyde tutunduğu.
RESOLUTION_PROGRAM = "program"
RESOLUTION_DEPARTMENT = "department"
RESOLUTION_FACULTY = "faculty"


class StudentDemographicCount(Base):
    """Kapsam + dönem + boyut başına öğrenci sayısı."""

    __tablename__ = "student_demographic_counts"
    __table_args__ = (
        # İDEMPOTENSİN OMURGASI: aynı kaynak satırı ikinci kez
        # aktarıldığında yeni satır açılmaz, mevcut satır güncellenir.
        UniqueConstraint(
            "academic_year", "dimension",
            "source_faculty_label", "source_program_label",
            name="uq_demografi_kaynak_satiri",
        ),
        Index("ix_demografi_kapsam", "academic_year", "dimension", "faculty_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    #: Bu sayının ait olduğu akademik yıl. Veri kümesi TEK yıla aittir;
    #: başka bir dönem seçildiğinde bu satırlar KULLANILMAZ.
    academic_year: Mapped[str] = mapped_column(String(20), nullable=False)
    dimension: Mapped[str] = mapped_column(String(40), nullable=False,
                                           default=DIMENSION_FOREIGN)

    # --- çözümlenen hiyerarşi (kimlikle) ---
    faculty_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("faculties.id"), nullable=True)
    department_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("departments.id"), nullable=True)
    academic_program_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("academic_programs.id"), nullable=True)

    # --- kaynağın kendi metni (izlenebilirlik) ---
    source_faculty_label: Mapped[str] = mapped_column(String(255), nullable=False)
    source_program_label: Mapped[str] = mapped_column(String(255), nullable=False)
    education_language: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True)

    student_count: Mapped[int] = mapped_column(Integer, nullable=False)

    #: "program" | "department" | "faculty" — sayının hangi düzeye
    #: güvenle bağlandığı. Arayüz, program düzeyinde çözülmemiş satırı
    #: fakülte toplamına dâhil eder ama program kırılımında göstermez.
    resolution: Mapped[str] = mapped_column(String(20), nullable=False)
    resolution_note: Mapped[Optional[str]] = mapped_column(String(400),
                                                           nullable=True)

    source_dataset: Mapped[str] = mapped_column(String(120), nullable=False)
    source_file: Mapped[str] = mapped_column(String(255), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, onupdate=func.current_timestamp(), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - hata ayıklama kolaylığı
        return (f"<StudentDemographicCount {self.academic_year} "
                f"{self.dimension} {self.source_program_label}="
                f"{self.student_count}>")
