"""Fakülte (Faculty) veritabanı modeli."""

from datetime import date, datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, Date, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# TYPE_CHECKING bloğu sadece tip kontrolü sırasında çalışır.
# Böylece Department <-> Faculty arasında karşılıklı import (circular import) hatası oluşmaz.
if TYPE_CHECKING:
    from app.models.department import Department


class Faculty(Base):
    """Üniversite bünyesindeki fakülteleri temsil eden model."""

    __tablename__ = "faculties"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # code alanı fakültenin kısa kodu (örn. FEA). Aynı kodun iki kez girilmemesi için unique.
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # BİRİM TÜRÜ — üniversitenin çocukları hepsi "fakülte" değildir.
    #
    #   FACULTY           akademik fakülte
    #   VOCATIONAL_SCHOOL meslek yüksekokulu
    #   INSTITUTE         enstitü (lisansüstü)
    #   ADMINISTRATIVE    idari birim (Rektörlük, Genel Sekreterlik…)
    #
    # Bu ayrım kozmetik değildir: Rektörlük'ü fakülte saymak, akademik
    # karşılaştırmalara idari personeli katar ve "7 fakültemiz var" gibi
    # yanlış bir kurumsal tabloya yol açar. Yalnızca AKADEMIK_TURLER
    # akademik grafik ve karşılaştırmalara girer; ADMINISTRATIVE sistem/
    # yönetim yapısına aittir.
    #
    # Serbest metin değil, kapalı liste: `UnitType` doğrular.
    # server_default, elindeki eski veritabanı dosyasına bu sütunun
    # ALTER TABLE ile eklenebilmesi için gereklidir (bkz. database.py).
    unit_type: Mapped[str] = mapped_column(
        String(30), default="FACULTY", server_default="'FACULTY'",
        nullable=False, index=True,
    )

    # Kayıtları veritabanından silmek yerine pasifleştiriyoruz (soft delete).
    # Geçmiş veriler ve raporlar bozulmasın diye bu yöntem tercih edildi.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Oluşturulma zamanı veritabanı tarafından otomatik atanır.
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


    # --- YÖK BİRİM KAYIT DEFTERİ ZENGİNLEŞTİRMESİ (data/ekdata/part2) ---
    # Kaynak: YÖK "Fakülteler/Enstitüler/YO/MYO Hakkında Genel Bilgiler" dışa aktarımı.
    # İkisi de NULL OLABİLİR: elimizdeki her birim YÖK dosyasında
    # bulunmayabilir ve bulunmayan bir tarihi uydurmak yerine boş
    # bırakılır. Aktarım yalnızca NULL alanı doldurur; dolu bir alanı
    # ASLA ezmez (bkz. import_yok_registry.py).
    established_on: Mapped[Optional[date]] = mapped_column(
        Date, nullable=True,
        comment="YÖK kayıt defterindeki açılış tarihi",
    )
    #: AKTİF | PASİF | YARI PASİF — YÖK'ün bildirdiği kayıt durumu.
    #: `is_active` ile KARIŞTIRILMAMALIDIR: `is_active` bizim soft-delete
    #: bayrağımız, bu ise dış kaynağın beyanıdır. Aktarım `is_active`
    #: değerine dokunmaz.
    yok_status: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True,
        comment="YÖK kayıt durumu (AKTİF/PASİF/YARI PASİF)",
    )

    # Bir fakültenin birden fazla bölümü olabilir (one-to-many).
    # cascade ayarı, fakülte silinirse bağlı bölümlerin de temizlenmesini sağlar.
    departments: Mapped[List["Department"]] = relationship(
        "Department",
        back_populates="faculty",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        """Nesnenin okunabilir metin gösterimini döndürür."""
        return f"<Faculty(id={self.id}, code='{self.code}')>"
