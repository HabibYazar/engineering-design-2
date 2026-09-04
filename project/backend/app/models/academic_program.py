"""Akademik Program (AcademicProgram) veritabanı modeli."""

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.department import Department
    from app.models.program_enrollment_snapshot import ProgramEnrollmentSnapshot
    from app.models.student import Student


class AcademicProgram(Base):
    """Bölümlere bağlı lisans/yüksek lisans gibi akademik programları temsil eder."""

    __tablename__ = "academic_programs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Her program bir bölüme bağlıdır.
    department_id: Mapped[int] = mapped_column(
        ForeignKey("departments.id"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)

    # degree_level programın derecesini tutar (Bachelor, Master, PhD gibi).
    # Serbest metin bırakıldı; ileride sabit bir listeye (Enum) çevrilebilir.
    degree_level: Mapped[str] = mapped_column(String(50), nullable=False)

    # duration_years ve quota, karar destek analizlerinde (kontenjan doluluk oranı vb.)
    # kullanılacağı için sayısal tutuluyor.
    #
    # NULL ile 0 farklıdır ve bu ayrım bilinçlidir:
    #   NULL → veri kaynağında bu bilgi YOK (ör. YÖK Akademik toplayıcısı
    #          kontenjan/öğrenim süresi yayımlamaz)
    #   0    → bilgi var ve değeri sıfır (ör. kontenjan açılmamış program)
    # Eskiden bu alanlar NOT NULL + varsayılan 4/0 idi; bu, "veri yok"u
    # "süre 4 yıl" ve "doluluk %0" gibi UYDURULMUŞ değerlere çeviriyordu.
    duration_years: Mapped[Optional[int]] = mapped_column(
        Integer, default=None, nullable=True
    )
    quota: Mapped[Optional[int]] = mapped_column(Integer, default=None, nullable=True)

    # ----------------------------------------------------------------------
    # RESMÎ ÖĞRENCİ SAYISI
    # ----------------------------------------------------------------------
    # Programın kabul edilen öğrenci sayısı. Türetme kuralı TEK YERDE
    # tanımlıdır: `app/services/student_count.py`. Bu sütun onun
    # ÖNBELLEĞİDİR; aktarım sonunda `refresh_stored_counts()` yazar.
    #
    # NULL = veri yok. 0 DEĞİL: sıfır öğrencili bir program ile öğrenci
    # verisi bulunmayan bir program aynı şey değildir.
    student_count: Mapped[Optional[int]] = mapped_column(
        Integer, default=None, nullable=True
    )

    # İZLENEBİLİRLİK — kullanıcıya GÖSTERİLMEZ.
    # Sayının hangi yöntemle ve hangi yıllardan üretildiğini saklar ki
    # "bu sayı nereden geliyor?" sorusu veritabanından cevaplanabilsin.
    # Arayüz yalnızca `student_count` alanını "Öğrenci Sayısı" olarak
    # gösterir; burada bir "tahmini" ibaresi ÜRETİLMEZ.
    student_count_source_method: Mapped[Optional[str]] = mapped_column(
        String(60), default=None, nullable=True
    )
    #: Toplamaya giren yerleştirme yılları, ör. "2022-2025".
    student_count_year_span: Mapped[Optional[str]] = mapped_column(
        String(20), default=None, nullable=True
    )

    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Many-to-one: Programdan bağlı olduğu bölüme erişim.
    department: Mapped["Department"] = relationship("Department", back_populates="programs")

    # --- Modül 2 (Student Analytics) ile eklenen ilişkiler ---
    # Mevcut alanlara dokunulmadı; yalnızca yeni ilişkiler eklendi.
    # Bir programa kayıtlı öğrenciler ve programın yıllık kayıt fotoğrafları.
    students: Mapped[List["Student"]] = relationship(
        "Student", back_populates="academic_program", cascade="all, delete-orphan"
    )
    enrollment_snapshots: Mapped[List["ProgramEnrollmentSnapshot"]] = relationship(
        "ProgramEnrollmentSnapshot",
        back_populates="academic_program",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        """Nesnenin okunabilir metin gösterimini döndürür."""
        return f"<AcademicProgram(id={self.id}, code='{self.code}')>"
