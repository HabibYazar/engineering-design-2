"""Modül 4 — Akademik personel şemaları."""

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class AcademicStaffBase(BaseModel):
    """Personel oluşturma ve güncellemede ortak alanlar."""

    staff_number: str = Field(min_length=1, max_length=50, examples=["AK-0001"])
    first_name: str = Field(min_length=2, max_length=100, examples=["Ayşe"])
    last_name: str = Field(min_length=2, max_length=100, examples=["Yılmaz"])
    title: str = Field(min_length=2, max_length=60, examples=["Dr. Öğr. Üyesi"])
    department_id: int = Field(ge=1, examples=[1])
    academic_year: str = Field(pattern=r"^\d{4}-\d{4}$", examples=["2025-2026"])

    # Sayım alanlarının tamamı negatif olamaz; ge=0 ile veritabanına ulaşmadan
    # engelleniyor, böylece puan hesabı hiçbir zaman negatife düşmez.
    publication_count: int = Field(default=0, ge=0, examples=[12])
    citation_count: int = Field(default=0, ge=0, examples=[30])
    teaching_load_hours: int = Field(default=0, ge=0, le=60, examples=[8])
    advising_count: int = Field(default=0, ge=0, examples=[3])
    project_count: int = Field(default=0, ge=0, examples=[2])
    patent_count: int = Field(default=0, ge=0, examples=[0])
    community_engagement_score: int = Field(default=0, ge=0, le=10, examples=[6])

    has_administrative_duty: bool = Field(default=False)
    has_industry_collaboration: bool = Field(default=False)


class AcademicStaffCreate(AcademicStaffBase):
    """Yeni personel kaydı."""


class AcademicStaffUpdate(BaseModel):
    """Kısmi güncelleme; yalnızca gönderilen alanlar değiştirilir."""

    first_name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    last_name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    title: Optional[str] = Field(default=None, min_length=2, max_length=60)
    department_id: Optional[int] = Field(default=None, ge=1)
    academic_year: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{4}$")
    publication_count: Optional[int] = Field(default=None, ge=0)
    citation_count: Optional[int] = Field(default=None, ge=0)
    teaching_load_hours: Optional[int] = Field(default=None, ge=0, le=60)
    advising_count: Optional[int] = Field(default=None, ge=0)
    project_count: Optional[int] = Field(default=None, ge=0)
    patent_count: Optional[int] = Field(default=None, ge=0)
    community_engagement_score: Optional[int] = Field(default=None, ge=0, le=10)
    has_administrative_duty: Optional[bool] = None
    has_industry_collaboration: Optional[bool] = None


class AcademicStaffResponse(AcademicStaffBase):
    """Personel kaydının API cevabı."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    department_name: Optional[str] = None
    faculty_name: Optional[str] = None
    is_active: bool


class StaffScoreItem(BaseModel):
    """Performans sıralamasındaki tek satır."""

    rank: int = Field(examples=[1])
    staff_id: int = Field(examples=[3])
    staff_number: str = Field(examples=["AK-0003"])
    full_name: str = Field(examples=["Fatma Demir"])
    title: str = Field(examples=["Prof. Dr."])
    department_name: str = Field(examples=["Makine Mühendisliği"])
    faculty_name: str = Field(examples=["Mühendislik Fakültesi"])
    academic_year: str = Field(examples=["2025-2026"])
    total_score: float = Field(examples=[236.0])
    performance_band: str = Field(
        description="Puanın eşiklere göre sınıfı.",
        examples=["yüksek performans"],
    )
    # Hangi bileşenin puana ne kadar katkı yaptığı; "kara kutu puan" olmaması için
    # ayrıntı birlikte dönülüyor.
    score_breakdown: dict = Field(
        examples=[{"publication_count": 100.0, "citation_count": 130.0}]
    )


class StaffComparisonItem(BaseModel):
    """Bölüm/fakülte/unvan bazlı karşılaştırma satırı."""

    group_key: str = Field(examples=["Bilgisayar Mühendisliği"])
    staff_count: int = Field(examples=[4])
    average_publication: float = Field(examples=[8.5])
    average_citation: float = Field(examples=[21.0])
    average_score: float = Field(examples=[112.4])
    total_publication: int = Field(examples=[34])
    total_citation: int = Field(examples=[84])


class StaffTrendItem(BaseModel):
    """Akademik yıla göre toplam üretim trendi."""

    academic_year: str = Field(examples=["2025-2026"])
    staff_count: int = Field(examples=[12])
    total_publication: int = Field(examples=[96])
    total_citation: int = Field(examples=[240])
    average_publication_per_staff: float = Field(examples=[8.0])


class StaffOverview(BaseModel):
    """Modül 4 özet göstergeleri."""

    academic_year: str = Field(examples=["2025-2026"])
    total_staff: int = Field(examples=[12])
    total_publication: int = Field(examples=[96])
    total_citation: int = Field(examples=[240])
    average_teaching_load_hours: float = Field(examples=[9.2])
    staff_with_administrative_duty: int = Field(examples=[4])
    staff_with_industry_collaboration: int = Field(examples=[5])
    average_score: float = Field(examples=[112.4])
    title_distribution: List[dict] = Field(
        examples=[[{"title": "Prof. Dr.", "count": 3}]]
    )
