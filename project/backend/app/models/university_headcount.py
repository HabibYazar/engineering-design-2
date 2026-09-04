"""ÜNİVERSİTE DÜZEYİNDE KAYITLI ÖĞRENCİ SAYISI (YÖK İstatistik).

NE TUTAR
--------
YÖK'ün `istatistik.yok.gov.tr` üzerinden yayımladığı **fiilen kayıtlı
öğrenci** sayıları. Kırılım:

    üniversite × akademik yıl × öğrenim türü × öğrenim düzeyi × cinsiyet

Bu, ÖSYM yerleştirme kayıtlarından TÜRETİLEN `academic_programs.
student_count` ile AYNI ŞEY DEĞİLDİR ve onun yerine geçmez:

    student_count            son ≤4 yerleştirme kohortunun toplamı
                             (yalnızca ÖSYM ile gelenler, lisansüstü hariç)
    university_student_headcounts
                             o yıl kayıtlı OLAN herkes (yatay geçiş, DGS,
                             lisansüstü, tekrar eden öğrenciler dâhil)

İki sayı farklı olmak ZORUNDADIR. Aralarındaki fark bir hata değil,
iki farklı ölçümün doğal sonucudur; bu yüzden biri diğerini ezmez ve
fark `data_source_conflicts` üzerinde kayıt altına alınır.

NEDEN AYRI TABLO
----------------
Şemada üniversite düzeyinde, yıl anahtarlı, cinsiyet/düzey kırılımlı
bir sayım tablosu yoktu:

  * `ProgramEnrollmentSnapshot` PROGRAM anahtarlıdır — bu veri kümesinin
    program bilgisi yoktur; bir programa yazmak uydurma olurdu.
  * `InstitutionalMetricValue` tek değerlidir ve bir göstergeye bağlıdır;
    12 kırılımı yazmak 12 sahte gösterge tanımı gerektirirdi.

ÇİFT SAYMA
----------
Kaynak dosyada her üniversite için hem öğrenim türü satırları hem bir
`TOPLAM` satırı, ayrıca her düzey için E/K/T üçlüsü vardır. Bu tabloya
YALNIZCA ayrıntı satırları ve YALNIZCA E/K hücreleri yazılır; toplamlar
sorgu anında yeniden hesaplanır. Böylece "toplamı toplamak" yapısal
olarak imkânsızdır.
"""

from datetime import datetime
from typing import Final, Optional

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

#: Kendi kurumumuz. Dış kurumlarla aynı tabloda dururlar; ayrım addır.
HOME_UNIVERSITY: Final[str] = "ANKARA BİLİM ÜNİVERSİTESİ"

#: Kapalı listeler — kaynaktaki yazım varyantları aktarımda normalize
#: edilir (bkz. `import_yok_registry.py`). Serbest metin bırakmak,
#: "BIRINCI Ö." ile "BİRİNCİ Ö."yu iki ayrı kategori yapardı.
EDUCATION_MODES: Final[tuple] = (
    "BİRİNCİ", "İKİNCİ", "UZAKTAN", "AÇIK",
)
DEGREE_LEVELS: Final[tuple] = (
    "ONLISANS", "LISANS", "YUKSEKLISANS", "DOKTORA",
)
GENDERS: Final[tuple] = ("E", "K")

DEGREE_LEVEL_LABELS: Final[dict] = {
    "ONLISANS": "Önlisans",
    "LISANS": "Lisans",
    "YUKSEKLISANS": "Yüksek Lisans",
    "DOKTORA": "Doktora",
}
EDUCATION_MODE_LABELS: Final[dict] = {
    "BİRİNCİ": "Birinci Öğretim",
    "İKİNCİ": "İkinci Öğretim",
    "UZAKTAN": "Uzaktan Öğretim",
    "AÇIK": "Açık Öğretim",
}


class UniversityStudentHeadcount(Base):
    """Bir üniversitenin bir yıldaki tek kırılımlı öğrenci sayısı."""

    __tablename__ = "university_student_headcounts"

    __table_args__ = (
        # DOĞAL ANAHTAR. Aktarım bu beşliyi upsert eder; aynı dosyayı
        # ikinci kez yüklemek hiçbir satır eklemez.
        UniqueConstraint(
            "university_name", "academic_year", "education_mode",
            "degree_level", "gender",
            name="uq_university_headcount",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    #: Kaynaktaki resmî ad; kurum eşleştirmesi bunun üzerinden yapılır.
    university_name: Mapped[str] = mapped_column(String(255), nullable=False,
                                                 index=True)
    university_type: Mapped[Optional[str]] = mapped_column(String(20),
                                                           nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    #: "2025-2026". Kaynak dosyada YOKTUR; aktarımda AÇIKÇA verilir.
    academic_year: Mapped[str] = mapped_column(String(20), nullable=False,
                                               index=True)

    education_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    degree_level: Mapped[str] = mapped_column(String(20), nullable=False)
    gender: Mapped[str] = mapped_column(String(1), nullable=False)

    #: Sayı. 0 GERÇEK bir değerdir ("bu kırılımda öğrenci yok").
    student_count: Mapped[int] = mapped_column(Integer, nullable=False)

    # --- izlenebilirlik ---
    source_dataset: Mapped[str] = mapped_column(String(80), nullable=False)
    source_file: Mapped[str] = mapped_column(String(255), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return (f"<UniversityStudentHeadcount({self.university_name!r} "
                f"{self.academic_year} {self.degree_level} {self.gender}="
                f"{self.student_count})>")
