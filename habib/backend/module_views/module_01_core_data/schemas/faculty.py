"""Fakülte için Pydantic v2 şemaları."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class FacultyBase(BaseModel):
    """Fakültenin ortak alanlarını tanımlayan temel şema."""

    # Ortak alanları tek yerde tutup Create/Update şemalarının bundan türemesi
    # kod tekrarını önlüyor.
    name: str = Field(..., min_length=2, max_length=255)
    code: str = Field(..., min_length=1, max_length=50)
    description: Optional[str] = None


class FacultyCreate(FacultyBase):
    """Yeni fakülte oluştururken istemciden beklenen veri."""

    # is_active gönderilmezse kayıt varsayılan olarak aktif kabul edilir.
    is_active: bool = True


class FacultyUpdate(BaseModel):
    """Fakülte güncellerken kullanılan şema; tüm alanlar isteğe bağlıdır."""

    # Kısmi güncelleme (PATCH mantığı) yapabilmek için her alan Optional.
    # Böylece istemci sadece değiştirmek istediği alanı gönderir.
    name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    code: Optional[str] = Field(default=None, min_length=1, max_length=50)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class FacultyResponse(FacultyBase):
    """API'nin fakülte kaydını istemciye döndürürken kullandığı şema."""

    # from_attributes, SQLAlchemy nesnesinin doğrudan şemaya dönüştürülmesini sağlar.
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool
    created_at: datetime
