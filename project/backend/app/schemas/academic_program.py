"""Akademik program için Pydantic v2 şemaları."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class AcademicProgramBase(BaseModel):
    """Akademik programın ortak alanlarını tanımlayan temel şema."""

    name: str = Field(..., min_length=2, max_length=255)
    code: str = Field(..., min_length=1, max_length=50)
    degree_level: str = Field(..., min_length=2, max_length=50)

    # Eğitim süresi ve kontenjan için mantıklı sınırlar koyduk;
    # böylece hatalı veri veritabanına hiç ulaşmadan engelleniyor.
    duration_years: int = Field(default=4, ge=1, le=10)
    quota: int = Field(default=0, ge=0)
    description: Optional[str] = None


class AcademicProgramCreate(AcademicProgramBase):
    """Yeni akademik program oluştururken istemciden beklenen veri."""

    # Program mutlaka bir bölüme bağlanmalı.
    department_id: int = Field(..., gt=0)
    is_active: bool = True


class AcademicProgramUpdate(BaseModel):
    """Program güncellerken kullanılan şema; tüm alanlar isteğe bağlıdır."""

    department_id: Optional[int] = Field(default=None, gt=0)
    name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    code: Optional[str] = Field(default=None, min_length=1, max_length=50)
    degree_level: Optional[str] = Field(default=None, min_length=2, max_length=50)
    duration_years: Optional[int] = Field(default=None, ge=1, le=10)
    quota: Optional[int] = Field(default=None, ge=0)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class AcademicProgramResponse(AcademicProgramBase):
    """API'nin program kaydını istemciye döndürürken kullandığı şema.

    YAZMA ile OKUMA kısıtları bilerek ayrıldı: kullanıcı yeni program
    girerken süre/kontenjan hâlâ geçerli aralıkta olmak zorundadır
    (`AcademicProgramCreate`), ancak dış kaynaktan (YÖK Akademik) gelen
    kayıtlarda bu alanlar bulunmayabilir. O durumda `null` döneriz —
    varsayılan bir sayı uydurmak, arayüzde "4 yıl" veya "%0 doluluk"
    gibi gerçek olmayan bilgiler üretirdi.
    """

    model_config = ConfigDict(from_attributes=True)

    duration_years: Optional[int] = Field(default=None, ge=1, le=10)
    quota: Optional[int] = Field(default=None, ge=0)

    # Programın öğrenci sayısı. Arayüzde sadece "Öğrenci Sayısı" olarak
    # görünür; "tahmini/yaklaşık" gibi bir ibare EKLENMEZ.
    # NULL = veri yok (0 değil).
    student_count: Optional[int] = Field(
        default=None, ge=0, description="Öğrenci sayısı"
    )
    # İZLENEBİLİRLİK — arayüzde gösterilmez, denetim için döner.
    student_count_source_method: Optional[str] = Field(
        default=None,
        description="İç izlenebilirlik: sayının hangi yöntemle üretildiği.",
    )
    student_count_year_span: Optional[str] = Field(
        default=None,
        description="İç izlenebilirlik: toplamaya giren yerleştirme yılları.",
    )

    id: int
    department_id: int
    is_active: bool
    created_at: datetime
