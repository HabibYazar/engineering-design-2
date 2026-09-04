"""ÜNİVERSİTE KARŞILAŞTIRMA PROFİLİ — kurum başına yapısal büyüklükler.

NE İŞE YARAR
------------
Üniversite seviyesindeki rakip analizi, Ankara'daki bütün kurumlar için
AYNI göstergeleri gerektirir. Öğrenci sayısı `university_student_
headcounts` tablosunda zaten var; bu tablo ona eşlik eden kadro ve
yapı büyüklüklerini tutar:

    academic_staff_count   YÖK Akademik toplayıcısında keşfedilen
                           akademisyen sayısı (21 kurumun hepsinde tam)
    academic_unit_count    fakülte/enstitü/YO/MYO sayısı  (YÖK kayıt defteri)
    department_count       bölüm sayısı                    (YÖK kayıt defteri)
    total_publications     yayın kaydı sayısı — KISMİ (bkz. aşağıda)

HER SÜTUN NULL OLABİLİR
-----------------------
Ve bu bilinçlidir. Karşılaştırma servisi bir göstergeyi ancak
KARŞILAŞTIRILAN BÜTÜN kurumlarda doluysa gösterir. Eksik değeri 0 ile
doldurmak, o kurumu "sıfır kadrolu" göstermek olurdu.

`total_publications` bunun canlı örneğidir: toplayıcı profil ayrıntısını
yalnızca birkaç kurum için indirmiştir. Ankara Bilim'de 164 akademisyen
için 1540 yayın kaydı varken Ankara Üniversitesi'nin 3659
akademisyeninde 175 kayıt vardır. Bu bir ARAŞTIRMA PERFORMANSI farkı
değil, TARAMA KAPSAMI farkıdır. Sayıyı olduğu gibi saklarız —
izlenebilirlik için — ama karşılaştırma servisi kapsama kuralı gereği
göstergeyi kapatır.

BU TABLO HİYERARŞİ DEĞİLDİR
---------------------------
Dış kurumların iç yapısını modellemiyoruz; burada yalnızca SAYILAR var.
`faculties` / `departments` tabloları hâlâ yalnızca kendi kurumumuzu
tutar ve kapsam çözümlemesi onlardan yürür.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UniversityProfile(Base):
    """Bir üniversitenin karşılaştırılabilir yapısal büyüklükleri."""

    __tablename__ = "university_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    #: Doğal anahtar. `university_student_headcounts.university_name` ve
    #: `benchmark_institutions.name` ile AYNI yazımdır; eşleştirme
    #: katlanmış ad üzerinden yapılır ama saklanan ad kaynağınkidir.
    university_name: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True)

    university_type: Mapped[Optional[str]] = mapped_column(String(20),
                                                           nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # --- YÖK Akademik toplayıcısı ---
    academic_staff_count: Mapped[Optional[int]] = mapped_column(Integer,
                                                                nullable=True)
    #: KISMİ VERİ. Karşılaştırmada kapsam kuralına takılır.
    total_publications: Mapped[Optional[int]] = mapped_column(Integer,
                                                              nullable=True)
    academics_with_publications: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True)

    # --- YÖK birim/bölüm kayıt defteri (data/ekdata/part2) ---
    academic_unit_count: Mapped[Optional[int]] = mapped_column(Integer,
                                                               nullable=True)
    department_count: Mapped[Optional[int]] = mapped_column(Integer,
                                                            nullable=True)

    staff_source: Mapped[Optional[str]] = mapped_column(String(120),
                                                        nullable=True)
    structure_source: Mapped[Optional[str]] = mapped_column(String(120),
                                                            nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self) -> str:
        return (f"<UniversityProfile({self.university_name!r} "
                f"kadro={self.academic_staff_count})>")
