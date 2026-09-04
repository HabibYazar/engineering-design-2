"""ÖSYM / YKS yerleştirme kaydı — kaynak granülerliğinde.

NEDEN AYRI TABLO
----------------
`program_enrollment_snapshots` (program, akademik_yıl) çiftinde TEKİLDİR.
ÖSYM verisi ise bir programın aynı yıl içinde birden çok YERLEŞTİRME
PROGRAMI olarak yayımlandığını gösteriyor:

    Bilgisayar Mühendisliği · 2025
      ├─ (İngilizce) (Burslu)         kontenjan 10, yerleşen 11, taban 439,52
      ├─ (Burslu)                     kontenjan 10, yerleşen 11, taban 431,91
      ├─ (İngilizce) (%50 İndirimli)  kontenjan 68, yerleşen  4
      ├─ (%50 İndirimli)              kontenjan 66, yerleşen 23
      └─ (Ücretli)                    kontenjan  2, yerleşen  —

Bu satırları snapshot'a sıkıştırmak burslu/ücretli ayrımını ve puan
türü bilgisini YOK EDERDİ. Kaynak granülerliği burada korunur; özet
snapshot'a TOPLANARAK yazılır (bkz. import_ekdata.py). Böylece hem
mevcut API sözleşmeleri çalışmaya devam eder hem de gerçek veri
kaybolmaz.

KAYNAKTA OLMAYAN ALAN UYDURULMAZ
--------------------------------
`program_code`, `vacant_quota`, `highest_score` kaynak dosyada 212/212
satırda boştur; NULL kalırlar.
"""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

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

#: ÖSYM puan türleri. Kapalı liste değil — yeni tür çıkarsa kayıt
#: reddedilmemeli — ama beklenenler belgelenmiştir.
KNOWN_SCORE_TYPES = ("SAY", "EA", "SÖZ", "DİL", "TYT")

#: Kaynakta görülen burs türleri.
KNOWN_SCHOLARSHIP_TYPES = ("Burslu", "%50 İndirimli", "Ücretli")


class YksPlacementRecord(Base):
    """Bir YERLEŞTİRME PROGRAMININ tek bir yıla ait ÖSYM sonucu."""

    __tablename__ = "yks_placement_records"

    __table_args__ = (
        # Kaynağın doğal anahtarı: yıl + yerleştirme programı adı + puan
        # türü + burs türü. Aktarımın idempotent olmasını bu sağlar.
        UniqueConstraint(
            "placement_year",
            "placement_program_name",
            "score_type",
            "scholarship_type",
            name="uq_yks_placement",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # --- hiyerarşi bağlantısı ---
    # Kaydın bağlandığı KURUMSAL program. Kaynaktaki "department" alanı
    # bazen bölüm bazen program adıdır; çözümleme import katmanında
    # ID ilişkileriyle yapılır, burada sonucu saklanır.
    academic_program_id: Mapped[int] = mapped_column(
        ForeignKey("academic_programs.id"), nullable=False, index=True
    )

    # --- zaman ---
    # ÖSYM yerleştirmesi takvim yılıyla yayımlanır (2025). Akademik yıl
    # karşılığı "2025-2026"dır ve ikisi de saklanır: biri kaynağın
    # granülerliği, diğeri sistemin ortak dili.
    placement_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    academic_year: Mapped[str] = mapped_column(String(9), nullable=False, index=True)

    # --- kaynağın kendi kimliği ---
    placement_program_name: Mapped[str] = mapped_column(String(300), nullable=False)
    #: ÖSYM program kodu. Kaynak dosyada 212/212 satırda BOŞ.
    placement_program_code: Mapped[Optional[str]] = mapped_column(
        String(30), nullable=True
    )
    score_type: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    scholarship_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)

    # --- ölçülen değerler ---
    # Hepsi Optional: kaynakta boş olan hücre 0 değil NULL'dır.
    # "Kontenjan sıfır" ile "kontenjan bilinmiyor" farklı şeylerdir.
    quota: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    placed_students: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    vacant_quota: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    #: Kaynakta oran olarak verilir (1.1 = %110). Ölçek DEĞİŞTİRİLMEZ;
    #: sunum katmanı yüzdeye çevirir.
    occupancy_rate: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 4), nullable=True
    )
    #: Taban puan — 5 ondalık basamağa kadar (kaynakta 439.51791 gibi).
    base_score: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 5), nullable=True
    )
    highest_score: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 5), nullable=True
    )
    success_rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # --- köken (provenance) ---
    source_dataset: Mapped[str] = mapped_column(String(120), nullable=False)
    source_file: Mapped[str] = mapped_column(String(255), nullable=False)
    #: Kaynağın kendi satır adı/anahtarı — geri izleme için.
    source_row_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    academic_program: Mapped["AcademicProgram"] = relationship("AcademicProgram")

    def __repr__(self) -> str:
        return (
            f"<YksPlacementRecord({self.placement_year} "
            f"{self.placement_program_name!r} {self.scholarship_type})>"
        )
