"""EĞİTİM ÜCRETLERİ — kendi programlarımız ve rakip kurumlar.

İKİ AYRI TABLO, İKİ AYRI TANE
-----------------------------
`ProgramTuitionFee`      kendi programlarımızın ücreti; GERÇEK program
                         kimliğine bağlanır, hiyerarşi/kapsam süzmesine girer
`CompetitorTuitionFee`   rakip üniversitelerin ücretleri; dış kurumların iç
                         hiyerarşisini modellemediğimiz için yalnızca METİN
                         alanları taşır ve üniversite düzeyinde karşılaştırılır

Bunları tek tabloda birleştirmek, dış kurumların bölümlerini bizim
`departments` tablomuza yazmayı gerektirirdi; bu da kapsam çözümlemesini
bozardı (bkz. `benchmark_institution.py`).

NEDEN YENİ TABLO
----------------
Şemada program düzeyinde ücret yoktu. `financial_periods.
list_tuition_per_student_usd` üniversite geneli TEK bir sayıdır ve
senaryo motorunun girdisidir; program × dil × ücret türü kırılımını
taşıyamaz.

GRAİN (tekillik)
----------------
    ProgramTuitionFee     (akademik yıl, program, eğitim dili, ücret türü)
    CompetitorTuitionFee  (üniversite, yıl, seviye, birim, program,
                           ücret türü, ücret metni)

Kaynak aynı programı hem "Ücretli" hem "%50 Burslu" satırıyla yayımlar;
bunlar FARKLI ücretlerdir, tekrar değildir.

PARA BİRİMİ
-----------
Kaynak TL yayımlar. Sayı TL olarak saklanır (`currency = "TRY"`);
dönüştürme YAPILMAZ — kur varsayımı uydurma bir değer üretirdi.
"""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Final, Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
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
    from app.models.faculty import Faculty

#: Ücret türü kapalı listesi. Kaynaktaki yazım varyantları aktarımda
#: buraya indirgenir ("%50 Burslu" ve "%50 İndirimli" AYNI şeydir).
FEE_FULL: Final = "FULL"                 # Ücretli / tam ücret
FEE_HALF_SCHOLARSHIP: Final = "HALF"     # %50 burslu / %50 indirimli
FEE_OTHER_DISCOUNT: Final = "DISCOUNT"   # tercih indirimi, peşin vb.
FEE_FULL_SCHOLARSHIP: Final = "SCHOLARSHIP"   # tam burslu (0 TL)

FEE_TYPES: Final = (FEE_FULL, FEE_HALF_SCHOLARSHIP, FEE_OTHER_DISCOUNT,
                    FEE_FULL_SCHOLARSHIP)

FEE_TYPE_LABELS: Final[dict] = {
    FEE_FULL: "Tam ücret",
    FEE_HALF_SCHOLARSHIP: "%50 burslu",
    FEE_OTHER_DISCOUNT: "Diğer indirim",
    FEE_FULL_SCHOLARSHIP: "Tam burslu",
}

#: Öğrenim düzeyi (rakip dosyasındaki "Seviye" sütunu).
LEVEL_BACHELOR: Final = "LISANS"
LEVEL_ASSOCIATE: Final = "ONLISANS"
LEVEL_PREP: Final = "HAZIRLIK"
LEVEL_HEALTH: Final = "SAGLIK"

LEVEL_LABELS: Final[dict] = {
    LEVEL_BACHELOR: "Lisans",
    LEVEL_ASSOCIATE: "Ön Lisans / MYO",
    LEVEL_PREP: "Hazırlık",
    LEVEL_HEALTH: "Sağlık Bilimleri",
}


class ProgramTuitionFee(Base):
    """Kendi programlarımızın yıllık eğitim ücreti."""

    __tablename__ = "program_tuition_fees"

    __table_args__ = (
        UniqueConstraint("academic_year", "academic_program_id",
                         "education_language", "fee_type",
                         name="uq_program_tuition_fee"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    academic_year: Mapped[str] = mapped_column(String(20), nullable=False,
                                               index=True)

    # --- HİYERARŞİ BAĞI ---
    # Kaynak satırı bir programa çözülebilirse program kimliği yazılır ve
    # kapsam süzmesi bunun üzerinden yürür. Çözülemeyen satır ATILMAZ:
    # bölüm/fakülte kimliği ve ham etiketler korunur; böylece kayıt
    # üniversite kapsamında yine görünür.
    academic_program_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("academic_programs.id"), nullable=True, index=True)
    department_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("departments.id"), nullable=True, index=True)
    faculty_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("faculties.id"), nullable=True, index=True)

    #: Kaynaktaki ham adlar — izlenebilirlik ve eşleşmeyen satırın gösterimi.
    source_faculty_name: Mapped[str] = mapped_column(String(255),
                                                     nullable=False)
    source_program_name: Mapped[str] = mapped_column(String(255),
                                                     nullable=False)

    #: "Türkçe" | "İngilizce" | None (kaynakta belirtilmemiş)
    education_language: Mapped[Optional[str]] = mapped_column(String(20),
                                                              nullable=True)
    fee_type: Mapped[str] = mapped_column(String(20), nullable=False,
                                          index=True)
    #: Kaynaktaki ham ücret/indirim etiketi.
    source_fee_label: Mapped[Optional[str]] = mapped_column(String(120),
                                                            nullable=True)

    #: Yıllık ücret. 0 GERÇEK bir değerdir (tam burslu).
    annual_fee: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="TRY",
                                          server_default="'TRY'",
                                          nullable=False)

    # --- yalnızca 2026-2027 sayfasında bulunan kampanya sütunları ---
    first_five_choice_fee: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 2), nullable=True)
    upfront_payment_fee: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 2), nullable=True)
    #: "75.000 Euro + KDV" gibi TL'ye çevrilemeyen ek ücret; METİN kalır.
    additional_fee_note: Mapped[Optional[str]] = mapped_column(Text,
                                                               nullable=True)

    source_dataset: Mapped[str] = mapped_column(String(80), nullable=False)
    source_file: Mapped[str] = mapped_column(String(255), nullable=False)
    source_sheet: Mapped[Optional[str]] = mapped_column(String(120),
                                                        nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(),
        nullable=False)

    academic_program: Mapped[Optional["AcademicProgram"]] = relationship(
        "AcademicProgram")
    department: Mapped[Optional["Department"]] = relationship("Department")
    faculty: Mapped[Optional["Faculty"]] = relationship("Faculty")

    def __repr__(self) -> str:
        return (f"<ProgramTuitionFee({self.academic_year} "
                f"{self.source_program_name!r} {self.fee_type} "
                f"{self.annual_fee})>")


class CompetitorTuitionFee(Base):
    """Rakip üniversitelerin yayımladığı eğitim ücretleri.

    Dış kurumların iç yapısı MODELLENMEZ; birim/bölüm adları metin olarak
    saklanır. Karşılaştırma üniversite düzeyinde yapılır.
    """

    __tablename__ = "competitor_tuition_fees"

    __table_args__ = (
        # Aynı kurum aynı programı birden çok ücret türüyle yayımlar;
        # tekillik ücret türünü ve tutarı da kapsar.
        UniqueConstraint("university_name", "academic_year", "level",
                         "unit_name", "program_name", "source_fee_label",
                         "fee_text", name="uq_competitor_tuition_fee"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    university_name: Mapped[str] = mapped_column(String(255), nullable=False,
                                                 index=True)
    #: Eşleşen `benchmark_institutions` kaydı — varsa.
    benchmark_institution_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("benchmark_institutions.id"), nullable=True, index=True)

    academic_year: Mapped[str] = mapped_column(String(20), nullable=False,
                                               index=True)
    level: Mapped[Optional[str]] = mapped_column(String(20), nullable=True,
                                                 index=True)
    unit_name: Mapped[Optional[str]] = mapped_column(String(255),
                                                     nullable=True)
    program_name: Mapped[Optional[str]] = mapped_column(String(255),
                                                        nullable=True)

    fee_type: Mapped[str] = mapped_column(String(20), nullable=False,
                                          index=True)
    source_fee_label: Mapped[Optional[str]] = mapped_column(String(160),
                                                            nullable=True)
    #: Kaynaktaki fiyat kategorisi etiketi (Tam Ucretli / Standart Indirim…).
    source_price_category: Mapped[Optional[str]] = mapped_column(String(60),
                                                                 nullable=True)

    #: Sayısal ücret. Kaynak aralık verdiyse (`"386.000 TL - 410.000 TL"`)
    #: NULL kalır ve ham metin `fee_text` içinde korunur — uydurma bir
    #: orta nokta üretilmez.
    annual_fee: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2),
                                                          nullable=True)
    #: Kaynaktaki HAM ücret hücresi (sayı ya da aralık metni).
    fee_text: Mapped[str] = mapped_column(String(160), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="TRY",
                                          server_default="'TRY'",
                                          nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    source_dataset: Mapped[str] = mapped_column(String(80), nullable=False)
    source_file: Mapped[str] = mapped_column(String(255), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(),
        nullable=False)

    def __repr__(self) -> str:
        return (f"<CompetitorTuitionFee({self.university_name!r} "
                f"{self.academic_year} {self.program_name!r} "
                f"{self.annual_fee})>")
