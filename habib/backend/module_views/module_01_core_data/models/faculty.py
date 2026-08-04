"""Fakülte (Faculty) veritabanı modeli."""

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, DateTime, String, Text, func
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

    # Kayıtları veritabanından silmek yerine pasifleştiriyoruz (soft delete).
    # Geçmiş veriler ve raporlar bozulmasın diye bu yöntem tercih edildi.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Oluşturulma zamanı veritabanı tarafından otomatik atanır.
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
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
