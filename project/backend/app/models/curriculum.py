"""Müfredat / ders kataloğu — üniversitenin yayımladığı gerçek ders listesi.

KAYNAK
------
`data/ekdata/ankara_bilim_mufredat_data1.xlsx` — 1205 satır; her satır bir
bölüm/programa ait bir ders. Satırlar farklı kaynaklardan derlenmiş ve her
biri kendi `source_type` / `source` bilgisini taşıyor (resmî web sayfası,
müfredat el kitapçığı PDF'i, web arşivi vb.). Bu köken bilgisi KORUNUR:
aynı dersin iki farklı kaynaktan gelmesi mümkündür ve hangisinin nereden
geldiği sorulabilmelidir.

VERİ KALİTESİ DÜRÜSTLÜĞÜ
------------------------
1205 satırın 43'ünde `course_name`, PDF'ten çıkarılırken bütün bir dönem
tablosu tek hücreye yapışmış hâlde geliyor:

    "Occupational Health and Safety IİngilizceZ 1 0 1 1ENG 101 Academic
     English I İngilizceZ 2 0 2 2MATH 101Calculus I …"

Bu metin AYIKLANMAYA ÇALIŞILMAZ — tahminle ders adı üretmek uydurma veri
olurdu. Ham metin olduğu gibi saklanır ve `name_is_reliable = False` ile
işaretlenir; hiçbir analiz bu satırı temiz bir ders adı sanamaz.

KAYNAKTA OLMAYAN
----------------
Kredi (AKTS/teorik/uygulama), dönem/yarıyıl, zorunlu-seçmeli bilgisi
TEMİZ satırlarda yoktur. Bozuk satırların içinde geçiyor olabilir ama
güvenilir biçimde ayrıştırılamaz. Bu yüzden bu alanlar tabloya
EKLENMEMİŞTİR: boş bir sütun, veri varmış izlenimi verir.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
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


class CurriculumCourse(Base):
    """Bir bölüm/programın müfredatındaki tek bir ders kaydı."""

    __tablename__ = "curriculum_courses"

    __table_args__ = (
        # Doğal anahtar: kaynağın kendi satırının parmak izi.
        #
        # NEDEN parmak izi: (bölüm, ders kodu) TEKİL DEĞİL — 1205 satırda
        # 151 tekrar var. Aynı kod farklı dönemlerde ve farklı kaynak
        # belgelerde geçiyor. Kodu tekil varsaymak gerçek satırları
        # sessizce yutardı.
        UniqueConstraint("source_fingerprint", name="uq_curriculum_course_source"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # --- hiyerarşi ---
    # Ders her zaman bir BÖLÜME bağlanır. Kaynak satırı bir programa
    # kadar çözülebiliyorsa `academic_program_id` de doldurulur; yoksa
    # NULL kalır — bölüm düzeyinde bir müfredat kaydıdır.
    department_id: Mapped[int] = mapped_column(
        ForeignKey("departments.id"), nullable=False, index=True
    )
    academic_program_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("academic_programs.id"), nullable=True, index=True
    )

    # --- ders ---
    #: Kaynakta 76/1205 satırda ders kodu boş; NULL kalır.
    course_code: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True, index=True
    )
    course_name: Mapped[str] = mapped_column(Text, nullable=False)

    #: False ise `course_name` PDF ayrıştırma artığıdır (birleşmiş metin).
    #: Analizler bu satırları ders adı olarak KULLANMAMALIDIR.
    name_is_reliable: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", nullable=False, index=True
    )

    #: Kaynakta bölüm adı "(İngilizce)" gibi öğretim dili eki taşıyabilir.
    #: Eşleştirmede atılır ama bilgi kaybolmasın diye burada saklanır.
    source_unit_label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # --- köken ---
    #: "official_university_web_curriculum", "uploaded_curriculum_booklet" …
    source_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    #: Belge adı veya "web". Kaynakta 587/1205 satırda boş.
    source_reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source_dataset: Mapped[str] = mapped_column(String(120), nullable=False)
    source_file: Mapped[str] = mapped_column(String(255), nullable=False)
    #: Satırın içeriğinden türetilen kararlı özet — idempotency anahtarı.
    source_fingerprint: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )

    imported_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    department: Mapped["Department"] = relationship("Department")
    academic_program: Mapped[Optional["AcademicProgram"]] = relationship(
        "AcademicProgram"
    )

    def __repr__(self) -> str:
        return f"<CurriculumCourse({self.course_code!r} dept={self.department_id})>"
