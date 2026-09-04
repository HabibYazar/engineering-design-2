"""Fakülte için Pydantic v2 şemaları."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.services.unit_types import UNIT_TYPE_LABELS, is_academic

#: Kapalı liste — serbest metin kabul edilmez, yazım hatası kayıt olmaz.
UnitType = Literal["FACULTY", "VOCATIONAL_SCHOOL", "INSTITUTE", "ADMINISTRATIVE"]


class FacultyBase(BaseModel):
    """Fakültenin ortak alanlarını tanımlayan temel şema."""

    # Ortak alanları tek yerde tutup Create/Update şemalarının bundan türemesi
    # kod tekrarını önlüyor.
    name: str = Field(..., min_length=2, max_length=255)
    code: str = Field(..., min_length=1, max_length=50)
    description: Optional[str] = None

    # Üniversitenin her çocuğu fakülte değildir. Rektörlük idari birimdir ve
    # akademik karşılaştırmalara girmemelidir.
    unit_type: UnitType = "FACULTY"


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
    unit_type: Optional[UnitType] = None
    is_active: Optional[bool] = None


class FacultyResponse(FacultyBase):
    """API'nin fakülte kaydını istemciye döndürürken kullandığı şema.

    `unit_type_label` ve `is_academic` TÜREVDİR: arayüzün tür listesini
    kendi içinde tekrar yazmasını (ve zamanla ayrışmasını) önlemek için
    sunucu tarafında hesaplanır.
    """

    # from_attributes, SQLAlchemy nesnesinin doğrudan şemaya dönüştürülmesini sağlar.
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool
    created_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def unit_type_label(self) -> str:
        """Arayüzde gösterilecek Türkçe tür adı."""
        return UNIT_TYPE_LABELS.get(self.unit_type, self.unit_type)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_academic(self) -> bool:
        """Bu birim akademik grafiğe ve karşılaştırmalara girer mi?"""
        return is_academic(self.unit_type)
