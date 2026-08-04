"""Bölüm için Pydantic v2 şemaları."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class DepartmentBase(BaseModel):
    """Bölümün ortak alanlarını tanımlayan temel şema."""

    name: str = Field(..., min_length=2, max_length=255)
    code: str = Field(..., min_length=1, max_length=50)
    description: Optional[str] = None


class DepartmentCreate(DepartmentBase):
    """Yeni bölüm oluştururken istemciden beklenen veri."""

    # Bölüm mutlaka bir fakülteye bağlanmalı; bu yüzden faculty_id zorunlu.
    # gt=0 ile 0 veya negatif id gönderilmesi baştan engellenir.
    faculty_id: int = Field(..., gt=0)
    is_active: bool = True


class DepartmentUpdate(BaseModel):
    """Bölüm güncellerken kullanılan şema; tüm alanlar isteğe bağlıdır."""

    faculty_id: Optional[int] = Field(default=None, gt=0)
    name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    code: Optional[str] = Field(default=None, min_length=1, max_length=50)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class DepartmentResponse(DepartmentBase):
    """API'nin bölüm kaydını istemciye döndürürken kullandığı şema."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    faculty_id: int
    is_active: bool
    created_at: datetime
