"""Modül 7 istek ve yanıt şemaları."""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class CriterionScore(BaseModel):
    """Tek bir sürdürülebilirlik kriterinin puan ve ağırlık bilgisi."""

    name: str
    source: str = Field(description="Kriterin verisinin hangi modülden geldiği")
    weight: float = Field(description="Yapılandırmadaki ham ağırlık")
    effective_weight: float = Field(
        description="Eksik kriterler çıkarıldıktan sonra yeniden normalize edilmiş ağırlık"
    )
    score: Optional[float] = Field(default=None, description="0-100 arası kriter puanı")
    available: bool = Field(description="Kriterin verisi mevcut mu")


class SupportingMetrics(BaseModel):
    """Puanı açıklayan Modül 3 göstergeleri."""

    quota: int
    enrolled_student_count: int
    occupancy_rate: float
    graduation_rate: float
    attrition_rate: float
    total_students: int
    minimum_admission_score: Optional[float] = None
    national_score_gap: Optional[float] = None


class SustainabilityResponse(BaseModel):
    """Bir programın sürdürülebilirlik değerlendirmesi."""

    program_code: str
    program_name: str
    academic_year: str
    sustainability_score: float = Field(description="0-100 arası ağırlıklı puan")
    data_completeness_percent: float = Field(
        description="Puanın kaç yüzdelik ağırlıkla hesaplandığı (veri tamlığı)"
    )
    category: str
    category_reason: str
    criteria: List[CriterionScore]
    missing_criteria: List[str]
    supporting_metrics: SupportingMetrics


class CategorySummaryResponse(BaseModel):
    """Kategori bazlı program dağılımı."""

    category: str
    program_count: int
    program_codes: List[str]


class SustainabilityRequest(BaseModel):
    """Diğer modüllerden gelen kriter puanlarıyla yeniden değerlendirme isteği."""

    academic_year: str = Field(default="2026-2027")
    external_inputs: Dict[str, Dict[str, float]] = Field(
        default_factory=dict,
        description=(
            "Program kodu -> kriter adı -> 0-100 puan. "
            'Örnek: {"CENG-BSC": {"research_performance": 72, "strategic_contribution": 85}}'
        ),
    )
    weight_overrides: Dict[str, float] = Field(
        default_factory=dict,
        description="Yapılandırmadaki ağırlıkları geçici olarak değiştirir",
    )


class WeightConfigResponse(BaseModel):
    """Aktif ağırlık yapılandırması."""

    weights: Dict[str, float]
    criterion_sources: Dict[str, str]
    classification_thresholds: Dict[str, float]
    total_weight: float
    computed_criteria: List[str]
