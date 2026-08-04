"""İdari Birim (AdministrativeUnit) veritabanı modeli."""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AdministrativeUnit(Base):
    """Erasmus Ofisi, Öğrenci İşleri gibi idari birimleri temsil eder."""

    # İdari birimler akademik hiyerarşiye (fakülte-bölüm) bağlı olmadığı için
    # bu modelde foreign key bulunmaz; bağımsız bir tablodur.
    __tablename__ = "administrative_units"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        """Nesnenin okunabilir metin gösterimini döndürür."""
        return f"<AdministrativeUnit(id={self.id}, code='{self.code}')>"
