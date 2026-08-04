"""Sistem kullanıcısı ve rol yetkilendirme (Modül 14) veritabanı modeli.

Entegrasyon notu: Eda'nın orijinal kodunda parolalar düz metin olarak saklanıyordu
("1234"). Demo verisi de olsa düz metin parola bir sistemde örnek teşkil ettiği
için burada PBKDF2 ile saltlanmış özet saklanıyor. Kullanılan `hashlib` Python
standart kütüphanesindedir; projeye yeni bir bağımlılık eklenmedi.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Rol -> yetki eşlemesi. Yetkiler veritabanı yerine kodda tutuluyor çünkü
# demo kapsamında rol seti sabit; ileride tabloya taşınabilir.
ROLE_PERMISSIONS: dict[str, list[str]] = {
    "Admin": ["view_all", "edit_all", "manage_users"],
    "Dekan": ["view_all", "edit_faculty"],
    "Bölüm Başkanı": ["view_department", "edit_department"],
    "Öğretim Üyesi": ["view_own"],
}


class SystemUser(Base):
    """Uygulamaya giriş yapan kullanıcıları ve rollerini temsil eder."""

    __tablename__ = "system_users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    username: Mapped[str] = mapped_column(
        String(80), unique=True, index=True, nullable=False
    )
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)

    # Parolanın kendisi hiçbir zaman saklanmaz; yalnızca salt ve özet tutulur.
    password_salt: Mapped[str] = mapped_column(String(64), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)

    role: Mapped[str] = mapped_column(String(40), nullable=False, index=True)

    # Yetki kapsamı: Dekan bir fakülteye, Bölüm Başkanı bir bölüme bağlıdır.
    # Admin için ikisi de boş kalır çünkü kapsamı tüm kurumdur.
    faculty_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("faculties.id"), nullable=True, index=True
    )
    department_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("departments.id"), nullable=True, index=True
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    @property
    def permissions(self) -> list[str]:
        """Kullanıcının rolüne karşılık gelen yetki listesi."""
        return ROLE_PERMISSIONS.get(self.role, [])
