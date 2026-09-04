"""İdari birim için Pydantic v2 şemaları."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class AdministrativeUnitBase(BaseModel):
    """İdari birimin ortak alanlarını tanımlayan temel şema."""

    name: str = Field(..., min_length=2, max_length=255)
    code: str = Field(..., min_length=1, max_length=50)
    description: Optional[str] = None


class AdministrativeUnitCreate(AdministrativeUnitBase):
    """Yeni idari birim oluştururken istemciden beklenen veri."""

    is_active: bool = True


class AdministrativeUnitUpdate(BaseModel):
    """İdari birim güncellerken kullanılan şema; tüm alanlar isteğe bağlıdır."""

    name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    code: Optional[str] = Field(default=None, min_length=1, max_length=50)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class AdministrativeUnitResponse(AdministrativeUnitBase):
    """API'nin idari birim kaydını istemciye döndürürken kullandığı şema."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool
    created_at: datetime
