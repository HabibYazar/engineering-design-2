"""THE / QS / YÖK değerlendirme ve izleme modülü şemaları (Pydantic v2).

ÖNEMLİ UYARI: Bu modül gerçek THE, QS veya YÖK sıralaması ÜRETMEZ ve resmi
sıralama tahmini yapmaz. Üretilen skorlar yalnızca kurumun kendi verisine
dayanan iç performans izleme (performance monitoring), veri hazırlık
(data readiness), iç uyum (compliance) ve iyileştirme takibi amaçlıdır.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.students import validate_academic_year

# Metodoloji yılı için makul aralık.
MIN_METHODOLOGY_YEAR: int = 2000
MAX_METHODOLOGY_YEAR: int = 2100


# ---------------------------------------------------------------------------
# Enum tanımları
# ---------------------------------------------------------------------------


class FrameworkCode(str, Enum):
    """Desteklenen değerlendirme çerçeveleri."""

    THE = "THE"
    QS = "QS"
    YOK = "YOK"


class CalculationType(str, Enum):
    """Gösterge değerinin nasıl hesaplanacağını belirler."""

    RAW = "raw"  # doğrudan girilen ham değer
    PERCENTAGE = "percentage"  # pay / payda × 100
    RATIO = "ratio"  # pay / payda
    SCORE = "score"  # zaten 0-100 aralığında bir skor
    BOOLEAN = "boolean"  # var/yok (100 / 0)
    MANUAL = "manual"  # elle girilen, hesaplanmayan değer


class IndicatorDirection(str, Enum):
    """Göstergenin hangi yönde iyileştiğini belirtir."""

    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"
    TARGET_IS_BEST = "target_is_best"


class DataStatus(str, Enum):
    """Gösterge verisinin durumu."""

    AVAILABLE = "available"
    PARTIAL = "partial"
    MISSING = "missing"
    ESTIMATED = "estimated"
    INVALID = "invalid"


class MetricOrigin(str, Enum):
    """Verinin nereden geldiğini gösterir."""

    AUTOMATIC = "automatic"  # Modül 1/2 verisinden otomatik üretildi
    MANUAL = "manual"  # kullanıcı elle girdi
    IMPORTED = "imported"  # CSV/XLSX/JSON ile içe aktarıldı


class MetricPeriod(str, Enum):
    """Ölçüm dönemi."""

    ANNUAL = "annual"
    FALL = "fall"
    SPRING = "spring"
    SUMMER = "summer"


class EvaluationRiskLevel(str, Enum):
    """Değerlendirme risk seviyesi."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class BenchmarkScope(str, Enum):
    """Karşılaştırma kapsamı."""

    PREVIOUS_YEARS = "previous-years"
    NATIONAL = "national"
    SIMILAR = "similar"
    COMPETITORS = "competitors"
    ALL = "all"


class PerformanceStatus(str, Enum):
    """Karşılaştırma sonucundaki konum."""

    ABOVE = "above"
    NEAR = "near"
    BELOW = "below"
    UNKNOWN = "unknown"  # yeterli karşılaştırma verisi yok


class RecommendationUrgency(str, Enum):
    """Önerinin aciliyeti."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ImpactVariable(str, Enum):
    """What-if etki analizinde değiştirilebilen temel büyüklükler."""

    CITATION_COUNT = "citation_count"
    PUBLICATION_COUNT = "publication_count"
    ACADEMIC_STAFF_COUNT = "academic_staff_count"
    INTERNATIONAL_STUDENT_COUNT = "international_student_count"
    INTERNATIONAL_ACADEMIC_STAFF_COUNT = "international_academic_staff_count"
    DOCTORAL_GRADUATE_COUNT = "doctoral_graduate_count"
    RESEARCH_INCOME = "research_income"
    INDUSTRY_INCOME = "industry_income"
    PATENT_COUNT = "patent_count"
    TOTAL_STUDENT_COUNT = "total_student_count"


# ---------------------------------------------------------------------------
# EvaluationFramework
# ---------------------------------------------------------------------------


class FrameworkBase(BaseModel):
    """Çerçevenin ortak alanları."""

    code: FrameworkCode = Field(..., description="THE, QS veya YOK")
    name: str = Field(..., min_length=2, max_length=255, examples=["THE World University Rankings"])
    methodology_year: int = Field(
        ..., ge=MIN_METHODOLOGY_YEAR, le=MAX_METHODOLOGY_YEAR, examples=[2026]
    )
    description: Optional[str] = Field(
        default=None, examples=["Times Higher Education 2026 metodolojisi (iç izleme amaçlı)."]
    )


class FrameworkCreate(FrameworkBase):
    """Yeni çerçeve oluştururken kullanılan şema."""

    is_active: bool = True


class FrameworkUpdate(BaseModel):
    """Çerçeve güncellerken kullanılan şema; tüm alanlar isteğe bağlıdır."""

    code: Optional[FrameworkCode] = None
    name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    methodology_year: Optional[int] = Field(
        default=None, ge=MIN_METHODOLOGY_YEAR, le=MAX_METHODOLOGY_YEAR, examples=[2026]
    )
    description: Optional[str] = None
    is_active: Optional[bool] = None


class FrameworkResponse(FrameworkBase):
    """Çerçeve kaydının API cevabı."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class FrameworkDetailResponse(FrameworkResponse):
    """Boyut sayısı ve ağırlık toplamı ile birlikte çerçeve detayı."""

    dimension_count: int = Field(default=0, examples=[5])
    indicator_count: int = Field(default=0, examples=[14])

    # Ağırlık toplamı 100 değilse arayüz uyarı gösterebilsin diye açıkça döndürülür.
    total_dimension_weight: Decimal = Field(default=Decimal("0.00"), examples=[100.00])
    weight_is_balanced: bool = Field(default=False, examples=[True])


# ---------------------------------------------------------------------------
# EvaluationDimension
# ---------------------------------------------------------------------------


class DimensionBase(BaseModel):
    """Boyutun ortak alanları."""

    code: str = Field(..., min_length=2, max_length=80, examples=["research-environment"])
    name: str = Field(..., min_length=2, max_length=255, examples=["Research Environment"])
    description: Optional[str] = None

    # Ağırlık 0-100 aralığında olmalı.
    weight: Decimal = Field(..., ge=0, le=100, examples=[29.00])
    display_order: int = Field(default=0, ge=0, examples=[2])

    @field_validator("code")
    @classmethod
    def _normalize_code(cls, value: str) -> str:
        """Boyut kodunu küçük harfe çevirip boşlukları temizler."""
        # Kodları tek biçimde tutmak, aynı boyutun "Research " ve "research"
        # olarak iki kez tanımlanmasını engeller.
        return str(value).strip().lower()


class DimensionCreate(DimensionBase):
    """Yeni boyut oluştururken kullanılan şema."""

    framework_id: int = Field(..., gt=0, examples=[1])
    is_active: bool = True


class DimensionUpdate(BaseModel):
    """Boyut güncellerken kullanılan şema."""

    framework_id: Optional[int] = Field(default=None, gt=0)
    code: Optional[str] = Field(default=None, min_length=2, max_length=80)
    name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    description: Optional[str] = None
    weight: Optional[Decimal] = Field(default=None, ge=0, le=100, examples=[29.00])
    display_order: Optional[int] = Field(default=None, ge=0)
    is_active: Optional[bool] = None

    @field_validator("code")
    @classmethod
    def _normalize_code(cls, value: Optional[str]) -> Optional[str]:
        """Boyut kodunu normalize eder."""
        return None if value is None else str(value).strip().lower()


class DimensionResponse(DimensionBase):
    """Boyut kaydının API cevabı."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    framework_id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class DimensionDetailResponse(DimensionResponse):
    """Gösterge sayısı ve ağırlık toplamı ile birlikte boyut detayı."""

    framework_code: str = Field(default="", examples=["THE"])
    indicator_count: int = Field(default=0, examples=[4])
    total_indicator_weight: Decimal = Field(default=Decimal("0.00"), examples=[100.00])
    weight_is_balanced: bool = Field(default=False, examples=[True])


# ---------------------------------------------------------------------------
# EvaluationIndicator
# ---------------------------------------------------------------------------


class IndicatorBase(BaseModel):
    """Göstergenin ortak alanları ve doğrulama kuralları."""

    code: str = Field(
        ..., min_length=2, max_length=100, examples=["the-international-student-ratio"]
    )
    name: str = Field(..., min_length=2, max_length=255, examples=["International student ratio"])
    description: Optional[str] = None

    unit: Optional[str] = Field(default=None, max_length=50, examples=["%"])
    calculation_type: CalculationType = CalculationType.RAW
    weight: Decimal = Field(..., ge=0, le=100, examples=[25.00])
    direction: IndicatorDirection = IndicatorDirection.HIGHER_IS_BETTER

    # Normalizasyon sınırları.
    minimum_value: Optional[Decimal] = Field(default=None, examples=[0.00])
    target_value: Optional[Decimal] = Field(default=None, examples=[25.00])
    maximum_value: Optional[Decimal] = Field(default=None, examples=[60.00])

    data_source: Optional[str] = Field(
        default=None, max_length=255, examples=["Öğrenci İşleri Daire Başkanlığı"]
    )
    required_for_readiness: bool = True

    # Modül 1/2 verisinden otomatik doldurma anahtarı.
    auto_source_key: Optional[str] = Field(
        default=None, max_length=80, examples=["international_student_ratio"]
    )

    # What-if etki analizi değişken eşleşmesi.
    impact_numerator_variable: Optional[str] = Field(
        default=None, max_length=80, examples=["international_student_count"]
    )
    impact_denominator_variable: Optional[str] = Field(
        default=None, max_length=80, examples=["total_student_count"]
    )

    @field_validator("code")
    @classmethod
    def _normalize_code(cls, value: str) -> str:
        """Gösterge kodunu küçük harfe çevirip boşlukları temizler."""
        return str(value).strip().lower()

    @model_validator(mode="after")
    def _check_bounds(self) -> "IndicatorBase":
        """minimum / target / maximum değerlerinin tutarlılığını doğrular."""
        # Sınırlar birbirini geçerse normalizasyon anlamsız sonuç üretirdi;
        # bu yüzden daha veri girilirken engelliyoruz.
        minimum, target, maximum = self.minimum_value, self.target_value, self.maximum_value

        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError(
                f"minimum_value ({minimum}) maximum_value ({maximum}) değerinden büyük olamaz."
            )
        if minimum is not None and target is not None and target < minimum:
            raise ValueError(
                f"target_value ({target}) minimum_value ({minimum}) değerinden küçük olamaz."
            )
        if maximum is not None and target is not None and target > maximum:
            raise ValueError(
                f"target_value ({target}) maximum_value ({maximum}) değerinden büyük olamaz."
            )

        # target_is_best yönü, hedefin ne olduğunu bilmeden hesaplanamaz.
        if self.direction == IndicatorDirection.TARGET_IS_BEST and target is None:
            raise ValueError(
                "direction 'target_is_best' seçildiğinde target_value alanı zorunludur."
            )
        return self


class IndicatorCreate(IndicatorBase):
    """Yeni gösterge oluştururken kullanılan şema."""

    dimension_id: int = Field(..., gt=0, examples=[1])
    is_active: bool = True


class IndicatorUpdate(BaseModel):
    """Gösterge güncellerken kullanılan şema."""

    dimension_id: Optional[int] = Field(default=None, gt=0)
    code: Optional[str] = Field(default=None, min_length=2, max_length=100)
    name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    description: Optional[str] = None
    unit: Optional[str] = Field(default=None, max_length=50)
    calculation_type: Optional[CalculationType] = None
    weight: Optional[Decimal] = Field(default=None, ge=0, le=100, examples=[25.00])
    direction: Optional[IndicatorDirection] = None
    minimum_value: Optional[Decimal] = Field(default=None, examples=[0.00])
    target_value: Optional[Decimal] = Field(default=None, examples=[25.00])
    maximum_value: Optional[Decimal] = Field(default=None, examples=[60.00])
    data_source: Optional[str] = Field(default=None, max_length=255)
    required_for_readiness: Optional[bool] = None
    auto_source_key: Optional[str] = Field(default=None, max_length=80)
    impact_numerator_variable: Optional[str] = Field(default=None, max_length=80)
    impact_denominator_variable: Optional[str] = Field(default=None, max_length=80)
    is_active: Optional[bool] = None

    @field_validator("code")
    @classmethod
    def _normalize_code(cls, value: Optional[str]) -> Optional[str]:
        """Gösterge kodunu normalize eder."""
        return None if value is None else str(value).strip().lower()


class IndicatorResponse(IndicatorBase):
    """Gösterge kaydının API cevabı."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    dimension_id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class IndicatorDetailResponse(IndicatorResponse):
    """Boyut ve çerçeve bilgisiyle birlikte gösterge detayı."""

    dimension_code: str = Field(default="", examples=["international-outlook"])
    dimension_name: str = Field(default="", examples=["International Outlook"])
    framework_code: str = Field(default="", examples=["THE"])
    framework_id: int = Field(default=0, examples=[1])
    metric_value_count: int = Field(default=0, examples=[3])


# ---------------------------------------------------------------------------
# InstitutionalMetricValue
# ---------------------------------------------------------------------------


class MetricValueBase(BaseModel):
    """Gösterge verisinin ortak alanları."""

    academic_year: str = Field(..., description="YYYY-YYYY biçiminde", examples=["2025-2026"])
    period: MetricPeriod = MetricPeriod.ANNUAL

    value: Optional[Decimal] = Field(default=None, examples=[16.67])
    numerator: Optional[Decimal] = Field(default=None, examples=[20.00])
    denominator: Optional[Decimal] = Field(default=None, examples=[120.00])

    data_status: DataStatus = DataStatus.AVAILABLE
    source_reference: Optional[str] = Field(
        default=None, max_length=255, examples=["Öğrenci Bilgi Sistemi raporu 2026-01"]
    )
    notes: Optional[str] = None
    measured_at: Optional[datetime] = None

    @field_validator("academic_year")
    @classmethod
    def _check_academic_year(cls, value: str) -> str:
        """Akademik yıl biçimini doğrular."""
        return validate_academic_year(value)

    @model_validator(mode="after")
    def _check_values(self) -> "MetricValueBase":
        """Pay/payda ve değer alanlarının tutarlılığını doğrular."""
        # Payda sıfır olursa oran hesaplanamaz; bu bir veri giriş hatasıdır.
        if self.denominator is not None and self.denominator == 0:
            raise ValueError(
                "denominator alanı sıfır olamaz; oran ve yüzde hesabı yapılamaz."
            )

        # Yalnızca pay verilip payda verilmemişse oran hesaplanamaz.
        if self.numerator is not None and self.denominator is None and self.value is None:
            raise ValueError(
                "numerator verildiğinde denominator veya value alanlarından biri de gereklidir."
            )

        # Veri "available" işaretlendiyse en az bir sayısal bilgi bulunmalı.
        if self.data_status == DataStatus.AVAILABLE and self.value is None and self.numerator is None:
            raise ValueError(
                "data_status 'available' olduğunda value veya numerator/denominator "
                "alanları doldurulmalıdır."
            )
        return self


class MetricValueCreate(MetricValueBase):
    """Yeni gösterge verisi oluştururken kullanılan şema."""

    indicator_id: int = Field(..., gt=0, examples=[1])
    origin: MetricOrigin = MetricOrigin.MANUAL


class MetricValueUpdate(BaseModel):
    """Gösterge verisi güncellerken kullanılan şema."""

    indicator_id: Optional[int] = Field(default=None, gt=0)
    academic_year: Optional[str] = Field(default=None, examples=["2025-2026"])
    period: Optional[MetricPeriod] = None
    value: Optional[Decimal] = Field(default=None, examples=[16.67])
    numerator: Optional[Decimal] = Field(default=None, examples=[20.00])
    denominator: Optional[Decimal] = Field(default=None, examples=[120.00])
    data_status: Optional[DataStatus] = None
    origin: Optional[MetricOrigin] = None
    source_reference: Optional[str] = Field(default=None, max_length=255)
    notes: Optional[str] = None
    measured_at: Optional[datetime] = None

    @field_validator("academic_year")
    @classmethod
    def _check_academic_year(cls, value: Optional[str]) -> Optional[str]:
        """Akademik yıl biçimini doğrular."""
        return None if value is None else validate_academic_year(value)

    @model_validator(mode="after")
    def _check_denominator(self) -> "MetricValueUpdate":
        """Payda sıfır girilmesini engeller."""
        if self.denominator is not None and self.denominator == 0:
            raise ValueError("denominator alanı sıfır olamaz.")
        return self


class MetricValueResponse(MetricValueBase):
    """Gösterge verisinin API cevabı."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    indicator_id: int
    origin: MetricOrigin
    created_at: datetime
    updated_at: datetime


class MetricValueDetailResponse(MetricValueResponse):
    """Gösterge ve çerçeve bilgisiyle birlikte veri detayı."""

    indicator_code: str = Field(default="", examples=["the-international-student-ratio"])
    indicator_name: str = Field(default="", examples=["International student ratio"])
    indicator_unit: Optional[str] = Field(default=None, examples=["%"])
    dimension_code: str = Field(default="", examples=["international-outlook"])
    framework_code: str = Field(default="", examples=["THE"])

    # Hesaplama motorunun ürettiği değerler: ham değerden türetilen etkin değer
    # ve 0-100 aralığına normalize edilmiş performans skoru.
    effective_value: Optional[Decimal] = Field(default=None, examples=[16.67])
    performance_score: Optional[Decimal] = Field(default=None, examples=[66.68])
    calculation_notes: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Değerlendirme sonuçları
# ---------------------------------------------------------------------------


class IndicatorAssessmentDetail(BaseModel):
    """Değerlendirme içindeki tek bir göstergenin sonucu."""

    indicator_id: int = Field(..., examples=[1])
    indicator_code: str = Field(..., examples=["the-international-student-ratio"])
    indicator_name: str = Field(..., examples=["International student ratio"])
    unit: Optional[str] = Field(default=None, examples=["%"])
    weight: Decimal = Field(..., examples=[25.00])
    direction: IndicatorDirection = IndicatorDirection.HIGHER_IS_BETTER
    calculation_type: CalculationType = CalculationType.RATIO

    data_status: DataStatus = DataStatus.MISSING
    origin: Optional[MetricOrigin] = Field(default=None, examples=["automatic"])

    raw_value: Optional[Decimal] = Field(default=None, examples=[16.67])
    effective_value: Optional[Decimal] = Field(default=None, examples=[16.67])
    performance_score: Optional[Decimal] = Field(default=None, examples=[66.68])
    readiness_factor: Decimal = Field(default=Decimal("0.00"), examples=[1.00])

    target_value: Optional[Decimal] = Field(default=None, examples=[25.00])
    data_source: Optional[str] = Field(default=None, examples=["Öğrenci İşleri Daire Başkanlığı"])
    calculation_notes: List[str] = Field(default_factory=list)


class DimensionAssessmentResponse(BaseModel):
    """Boyut değerlendirmesinin API cevabı."""

    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    dimension_id: int = Field(..., examples=[1])
    dimension_code: str = Field(default="", examples=["international-outlook"])
    dimension_name: str = Field(default="", examples=["International Outlook"])
    dimension_weight: Decimal = Field(default=Decimal("0.00"), examples=[7.50])

    readiness_score: Decimal = Field(default=Decimal("0.00"), examples=[83.33])
    performance_score: Decimal = Field(default=Decimal("0.00"), examples=[61.25])
    weighted_score: Decimal = Field(default=Decimal("0.00"), examples=[4.59])

    missing_indicator_count: int = Field(default=0, examples=[1])
    available_indicator_count: int = Field(default=0, examples=[2])
    total_indicator_count: int = Field(default=0, examples=[3])

    risk_level: EvaluationRiskLevel = EvaluationRiskLevel.MEDIUM
    indicators: List[IndicatorAssessmentDetail] = Field(default_factory=list)


class MissingDataItem(BaseModel):
    """Eksik veya sorunlu tek bir gösterge verisi."""

    indicator_id: int = Field(..., examples=[7])
    indicator_code: str = Field(..., examples=["the-citation-impact"])
    indicator_name: str = Field(..., examples=["Citation impact"])
    dimension_code: str = Field(..., examples=["research-quality"])
    dimension_name: str = Field(..., examples=["Research Quality"])
    framework_code: str = Field(..., examples=["THE"])

    data_status: DataStatus = DataStatus.MISSING
    expected_data_source: Optional[str] = Field(
        default=None, examples=["Scopus / WoS atıf raporu"]
    )

    # Bu verinin eksikliğinin readiness skorunda yol açtığı tahmini puan kaybı.
    estimated_readiness_loss: Decimal = Field(default=Decimal("0.00"), examples=[7.25])
    message: str = Field(
        ..., examples=["'Citation impact' göstergesi için veri girilmemiş."]
    )


class MissingDataSummary(BaseModel):
    """Eksik veri analizinin özeti."""

    missing_count: int = Field(default=0, examples=[2])
    partial_count: int = Field(default=0, examples=[1])
    invalid_count: int = Field(default=0, examples=[0])
    estimated_count: int = Field(default=0, examples=[1])
    total_readiness_loss: Decimal = Field(default=Decimal("0.00"), examples=[18.50])
    items: List[MissingDataItem] = Field(default_factory=list)


class RecommendationItem(BaseModel):
    """Tek bir stratejik öneri."""

    framework: str = Field(..., examples=["THE"])
    dimension: str = Field(..., examples=["International Outlook"])
    indicator: str = Field(..., examples=["International student ratio"])
    indicator_code: str = Field(..., examples=["the-international-student-ratio"])

    current_value: Optional[Decimal] = Field(default=None, examples=[16.67])
    target_value: Optional[Decimal] = Field(default=None, examples=[25.00])
    gap: Optional[Decimal] = Field(default=None, examples=[8.33])

    urgency: RecommendationUrgency = RecommendationUrgency.MEDIUM

    # Hedefe ulaşılırsa çerçeve performans skorunda beklenen artış (puan).
    expected_score_gain: Decimal = Field(default=Decimal("0.00"), examples=[2.50])

    recommendation: str = Field(
        ...,
        examples=[
            "Uluslararası öğrenci oranı %16.67 seviyesinde; hedef %25.00. "
            "Aradaki 8.33 puanlık fark için uluslararası tanıtım ve değişim "
            "programları güçlendirilmelidir."
        ],
    )
    required_data_or_action: str = Field(
        ..., examples=["Uluslararası öğrenci kayıt verilerinin dönemsel olarak güncellenmesi"]
    )


class AssessmentResponse(BaseModel):
    """Kaydedilmiş değerlendirmenin özet cevabı."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    framework_id: int
    academic_year: str = Field(..., examples=["2025-2026"])
    period: MetricPeriod = MetricPeriod.ANNUAL

    readiness_score: Decimal = Field(..., examples=[72.50])
    performance_score: Decimal = Field(..., examples=[58.40])
    compliance_score: Decimal = Field(..., examples=[42.34])

    missing_indicator_count: int = Field(default=0, examples=[2])
    partial_indicator_count: int = Field(default=0, examples=[1])
    available_indicator_count: int = Field(default=0, examples=[11])

    risk_level: EvaluationRiskLevel = EvaluationRiskLevel.HIGH
    calculation_notes: Optional[str] = None
    calculated_at: datetime
    created_at: datetime
    updated_at: datetime


class AssessmentDetailResponse(BaseModel):
    """Hesaplanmış değerlendirmenin tam raporu."""

    # Bu rapor gerçek sıralama değil, iç izleme sonucudur.
    disclaimer: str = Field(
        default=(
            "Bu sonuç gerçek THE/QS/YÖK sıralaması değildir. Kurumun kendi verisine dayanan "
            "iç performans izleme, veri hazırlık ve uyum göstergesidir."
        )
    )

    assessment_id: Optional[int] = Field(default=None, examples=[1])
    framework_id: int = Field(..., examples=[1])
    framework: str = Field(..., examples=["THE"])
    framework_name: str = Field(default="", examples=["THE World University Rankings"])
    methodology_year: int = Field(..., examples=[2026])

    academic_year: str = Field(..., examples=["2025-2026"])
    period: MetricPeriod = MetricPeriod.ANNUAL

    readiness_score: Decimal = Field(default=Decimal("0.00"), examples=[72.50])
    performance_score: Decimal = Field(default=Decimal("0.00"), examples=[58.40])
    compliance_score: Decimal = Field(default=Decimal("0.00"), examples=[42.34])
    risk_level: EvaluationRiskLevel = EvaluationRiskLevel.HIGH

    total_indicator_count: int = Field(default=0, examples=[14])
    available_indicator_count: int = Field(default=0, examples=[11])
    partial_indicator_count: int = Field(default=0, examples=[1])
    missing_indicator_count: int = Field(default=0, examples=[2])
    invalid_indicator_count: int = Field(default=0, examples=[0])
    estimated_indicator_count: int = Field(default=0, examples=[0])

    dimensions: List[DimensionAssessmentResponse] = Field(default_factory=list)
    missing_data: MissingDataSummary = Field(default_factory=MissingDataSummary)

    strongest_indicators: List[IndicatorAssessmentDetail] = Field(default_factory=list)
    weakest_indicators: List[IndicatorAssessmentDetail] = Field(default_factory=list)
    recommendations: List[RecommendationItem] = Field(default_factory=list)

    calculation_notes: List[str] = Field(default_factory=list)
    calculated_at: datetime
    persisted: bool = Field(
        default=False, description="Sonuç veritabanına kaydedildi mi?"
    )


class AssessmentCalculateRequest(BaseModel):
    """Değerlendirme hesaplama isteği."""

    framework_code: Optional[FrameworkCode] = Field(
        default=None, description="Belirtilmezse tüm aktif çerçeveler hesaplanır"
    )
    framework_id: Optional[int] = Field(default=None, gt=0)
    academic_year: str = Field(..., description="YYYY-YYYY", examples=["2025-2026"])
    period: MetricPeriod = MetricPeriod.ANNUAL

    # false verilirse hesaplama yapılır ama veritabanına yazılmaz (deneme modu).
    persist: bool = Field(default=True, description="Sonuç kaydedilsin mi?")

    @field_validator("academic_year")
    @classmethod
    def _check_academic_year(cls, value: str) -> str:
        """Akademik yıl biçimini doğrular."""
        return validate_academic_year(value)


class AssessmentCalculateResponse(BaseModel):
    """Bir veya birden fazla çerçeve için hesaplama sonucu."""

    academic_year: str = Field(..., examples=["2025-2026"])
    period: MetricPeriod = MetricPeriod.ANNUAL
    persisted: bool = Field(default=True)
    calculated_framework_count: int = Field(default=0, examples=[3])
    assessments: List[AssessmentDetailResponse] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Benchmark
# ---------------------------------------------------------------------------


class BenchmarkInstitutionBase(BaseModel):
    """Karşılaştırma kurumunun ortak alanları."""

    name: str = Field(
        ..., min_length=2, max_length=255, examples=["Demo Teknik Üniversitesi (örnek veri)"]
    )
    country: Optional[str] = Field(default=None, max_length=100, examples=["Türkiye"])
    city: Optional[str] = Field(default=None, max_length=100, examples=["Ankara"])
    institution_type: str = Field(
        default="similar",
        max_length=30,
        description="national-average | similar | competitor | international | other",
        examples=["competitor"],
    )
    is_competitor: bool = False
    notes: Optional[str] = Field(
        default=None, examples=["Demo amaçlı örnek kurumdur, gerçek veri değildir."]
    )


class BenchmarkInstitutionCreate(BenchmarkInstitutionBase):
    """Yeni karşılaştırma kurumu oluştururken kullanılan şema."""

    is_active: bool = True


class BenchmarkInstitutionUpdate(BaseModel):
    """Karşılaştırma kurumu güncellerken kullanılan şema."""

    name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    country: Optional[str] = Field(default=None, max_length=100)
    city: Optional[str] = Field(default=None, max_length=100)
    institution_type: Optional[str] = Field(default=None, max_length=30)
    is_competitor: Optional[bool] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class BenchmarkInstitutionResponse(BenchmarkInstitutionBase):
    """Karşılaştırma kurumunun API cevabı."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class BenchmarkValueCreate(BaseModel):
    """Karşılaştırma kurumu gösterge değeri oluşturma şeması."""

    benchmark_institution_id: int = Field(..., gt=0, examples=[1])
    indicator_id: int = Field(..., gt=0, examples=[1])
    academic_year: str = Field(..., examples=["2025-2026"])
    period: MetricPeriod = MetricPeriod.ANNUAL
    value: Decimal = Field(..., examples=[22.40])
    source_reference: Optional[str] = Field(default=None, max_length=255)

    @field_validator("academic_year")
    @classmethod
    def _check_academic_year(cls, value: str) -> str:
        """Akademik yıl biçimini doğrular."""
        return validate_academic_year(value)


class BenchmarkValueResponse(BenchmarkValueCreate):
    """Karşılaştırma gösterge değerinin API cevabı."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class BenchmarkComparisonRow(BaseModel):
    """Tek bir göstergenin karşılaştırma satırı."""

    indicator_id: int = Field(..., examples=[1])
    indicator_code: str = Field(..., examples=["the-international-student-ratio"])
    indicator_name: str = Field(..., examples=["International student ratio"])
    unit: Optional[str] = Field(default=None, examples=["%"])
    dimension_name: str = Field(default="", examples=["International Outlook"])
    direction: IndicatorDirection = IndicatorDirection.HIGHER_IS_BETTER

    university_value: Optional[Decimal] = Field(default=None, examples=[16.67])
    benchmark_average: Optional[Decimal] = Field(default=None, examples=[22.40])
    difference: Optional[Decimal] = Field(default=None, examples=[-5.73])
    percentage_difference: Optional[Decimal] = Field(default=None, examples=[-25.58])

    # Sıralama yalnızca yeterli karşılaştırma verisi varsa hesaplanır.
    rank: Optional[int] = Field(default=None, examples=[4])
    percentile: Optional[Decimal] = Field(default=None, examples=[25.00])
    benchmark_count: int = Field(default=0, examples=[4])

    performance_status: PerformanceStatus = PerformanceStatus.UNKNOWN
    warning: Optional[str] = Field(
        default=None, examples=["Yeterli karşılaştırma verisi yok (en az 3 kurum gerekir)."]
    )


class BenchmarkComparisonResponse(BaseModel):
    """Karşılaştırma raporu."""

    framework_code: Optional[str] = Field(default=None, examples=["THE"])
    academic_year: str = Field(..., examples=["2025-2026"])
    period: MetricPeriod = MetricPeriod.ANNUAL
    scope: BenchmarkScope = BenchmarkScope.ALL

    compared_institution_count: int = Field(default=0, examples=[5])
    compared_institutions: List[str] = Field(default_factory=list)

    rows: List[BenchmarkComparisonRow] = Field(default_factory=list)

    above_count: int = Field(default=0, examples=[4])
    near_count: int = Field(default=0, examples=[2])
    below_count: int = Field(default=0, examples=[6])

    warnings: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Trend
# ---------------------------------------------------------------------------


class EvaluationTrendPoint(BaseModel):
    """Trend serisindeki tek bir akademik yıl."""

    academic_year: str = Field(..., examples=["2025-2026"])
    period: MetricPeriod = MetricPeriod.ANNUAL
    readiness_score: Decimal = Field(default=Decimal("0.00"), examples=[72.50])
    performance_score: Decimal = Field(default=Decimal("0.00"), examples=[58.40])
    compliance_score: Decimal = Field(default=Decimal("0.00"), examples=[42.34])
    risk_level: EvaluationRiskLevel = EvaluationRiskLevel.HIGH

    performance_change: Optional[Decimal] = Field(default=None, examples=[4.20])
    readiness_change: Optional[Decimal] = Field(default=None, examples=[6.10])


class EvaluationTrendResponse(BaseModel):
    """Bir çerçevenin yıllara göre gelişimi."""

    framework_code: str = Field(..., examples=["THE"])
    framework_name: str = Field(default="", examples=["THE World University Rankings"])
    point_count: int = Field(default=0, examples=[3])
    points: List[EvaluationTrendPoint] = Field(default_factory=list)
    overall_direction: str = Field(
        default="stable", description="increasing | stable | decreasing", examples=["increasing"]
    )
    message: str = Field(default="", examples=["Performans skoru son 3 yılda yükseliyor."])


# ---------------------------------------------------------------------------
# What-if etki analizi
# ---------------------------------------------------------------------------


class ImpactPreviewRequest(BaseModel):
    """Senaryo etkisi ön izleme isteği.

    Değerler MUTLAK DEĞİŞİM olarak girilir (delta). Örneğin publication_count=150
    "yayın sayısı 150 artarsa" anlamına gelir. Negatif değer azalışı ifade eder.
    """

    academic_year: str = Field(..., examples=["2025-2026"])
    period: MetricPeriod = MetricPeriod.ANNUAL
    framework_code: Optional[FrameworkCode] = Field(
        default=None, description="Belirtilmezse tüm aktif çerçeveler değerlendirilir"
    )

    citation_count: Decimal = Field(default=Decimal("0"), examples=[2500.00])
    publication_count: Decimal = Field(default=Decimal("0"), examples=[150.00])
    academic_staff_count: Decimal = Field(default=Decimal("0"), examples=[30.00])
    international_student_count: Decimal = Field(default=Decimal("0"), examples=[40.00])
    international_academic_staff_count: Decimal = Field(default=Decimal("0"), examples=[10.00])
    doctoral_graduate_count: Decimal = Field(default=Decimal("0"), examples=[12.00])
    research_income: Decimal = Field(default=Decimal("0"), examples=[15000000.00])
    industry_income: Decimal = Field(default=Decimal("0"), examples=[5000000.00])
    patent_count: Decimal = Field(default=Decimal("0"), examples=[6.00])
    total_student_count: Decimal = Field(default=Decimal("0"), examples=[0.00])

    @field_validator("academic_year")
    @classmethod
    def _check_academic_year(cls, value: str) -> str:
        """Akademik yıl biçimini doğrular."""
        return validate_academic_year(value)


class ImpactedIndicator(BaseModel):
    """Senaryodan etkilenen tek bir gösterge."""

    indicator_id: int = Field(..., examples=[7])
    indicator_code: str = Field(..., examples=["the-publications-per-staff"])
    indicator_name: str = Field(..., examples=["Publications per academic staff"])
    framework_code: str = Field(..., examples=["THE"])
    dimension_name: str = Field(default="", examples=["Research Environment"])
    unit: Optional[str] = Field(default=None, examples=["adet"])

    before_value: Optional[Decimal] = Field(default=None, examples=[2.45])
    after_value: Optional[Decimal] = Field(default=None, examples=[3.10])
    value_change: Optional[Decimal] = Field(default=None, examples=[0.65])

    before_score: Optional[Decimal] = Field(default=None, examples=[48.00])
    after_score: Optional[Decimal] = Field(default=None, examples=[62.00])
    score_change: Optional[Decimal] = Field(default=None, examples=[14.00])

    applied_variables: List[str] = Field(default_factory=list)


class ImpactedDimension(BaseModel):
    """Senaryodan etkilenen boyut."""

    dimension_id: int = Field(..., examples=[2])
    dimension_code: str = Field(..., examples=["research-environment"])
    dimension_name: str = Field(..., examples=["Research Environment"])
    before_score: Decimal = Field(default=Decimal("0.00"), examples=[48.00])
    after_score: Decimal = Field(default=Decimal("0.00"), examples=[62.00])
    score_change: Decimal = Field(default=Decimal("0.00"), examples=[14.00])


class FrameworkImpact(BaseModel):
    """Bir çerçevenin senaryo öncesi/sonrası durumu."""

    framework_id: int = Field(..., examples=[1])
    framework_code: str = Field(..., examples=["THE"])
    framework_name: str = Field(default="", examples=["THE World University Rankings"])

    before_performance: Decimal = Field(default=Decimal("0.00"), examples=[58.40])
    after_performance: Decimal = Field(default=Decimal("0.00"), examples=[65.20])
    performance_change: Decimal = Field(default=Decimal("0.00"), examples=[6.80])

    before_readiness: Decimal = Field(default=Decimal("0.00"), examples=[72.50])
    after_readiness: Decimal = Field(default=Decimal("0.00"), examples=[72.50])
    readiness_change: Decimal = Field(default=Decimal("0.00"), examples=[0.00])

    before_compliance: Decimal = Field(default=Decimal("0.00"), examples=[42.34])
    after_compliance: Decimal = Field(default=Decimal("0.00"), examples=[47.27])
    compliance_change: Decimal = Field(default=Decimal("0.00"), examples=[4.93])

    before_risk: EvaluationRiskLevel = EvaluationRiskLevel.HIGH
    after_risk: EvaluationRiskLevel = EvaluationRiskLevel.MEDIUM
    risk_changed: bool = Field(default=False, examples=[True])

    impacted_dimensions: List[ImpactedDimension] = Field(default_factory=list)
    impacted_indicators: List[ImpactedIndicator] = Field(default_factory=list)


class ImpactPreviewResponse(BaseModel):
    """Senaryo etkisi ön izleme cevabı."""

    disclaimer: str = Field(
        default=(
            "Bu analiz gerçek THE/QS/YÖK sıralamasındaki değişimi TAHMİN ETMEZ. "
            "Yalnızca sistemde tanımlı iç değerlendirme skorlarına etkiyi hesaplar."
        )
    )

    academic_year: str = Field(..., examples=["2025-2026"])
    period: MetricPeriod = MetricPeriod.ANNUAL
    persisted: bool = Field(
        default=False, description="Bu işlem veritabanına hiçbir kayıt yazmaz"
    )

    applied_changes: Dict[str, str] = Field(default_factory=dict)
    frameworks: List[FrameworkImpact] = Field(default_factory=list)
    total_impacted_indicator_count: int = Field(default=0, examples=[6])
    recommendations: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Öğrenci verisi senkronizasyonu
# ---------------------------------------------------------------------------


class StudentMetricSyncRequest(BaseModel):
    """Modül 1/2 verisinden otomatik gösterge üretme isteği."""

    academic_year: str = Field(..., examples=["2025-2026"])
    period: MetricPeriod = MetricPeriod.ANNUAL

    # Manuel/import verinin üzerine yazılsın mı? Varsayılan HAYIR:
    # doğrulanmış insan verisi otomatik veriden önceliklidir.
    overwrite_manual: bool = Field(
        default=False,
        description="true ise elle girilmiş veriler de otomatik değerle güncellenir",
    )

    @field_validator("academic_year")
    @classmethod
    def _check_academic_year(cls, value: str) -> str:
        """Akademik yıl biçimini doğrular."""
        return validate_academic_year(value)


class SyncedMetricItem(BaseModel):
    """Senkronizasyonda işlenen tek bir gösterge."""

    indicator_id: int = Field(..., examples=[1])
    indicator_code: str = Field(..., examples=["the-international-student-ratio"])
    framework_code: str = Field(..., examples=["THE"])
    auto_source_key: str = Field(..., examples=["international_student_ratio"])

    action: str = Field(..., description="created | updated | skipped", examples=["created"])
    previous_value: Optional[Decimal] = Field(default=None, examples=[15.00])
    new_value: Optional[Decimal] = Field(default=None, examples=[16.67])
    reason: Optional[str] = Field(
        default=None, examples=["Kayıt elle girildiği için korundu (origin=manual)."]
    )


class StudentMetricSyncResponse(BaseModel):
    """Otomatik senkronizasyon sonucu."""

    academic_year: str = Field(..., examples=["2025-2026"])
    period: MetricPeriod = MetricPeriod.ANNUAL

    created_count: int = Field(default=0, examples=[6])
    updated_count: int = Field(default=0, examples=[3])
    skipped_count: int = Field(default=0, examples=[1])
    unmatched_source_keys: List[str] = Field(default_factory=list)

    computed_metrics: Dict[str, str] = Field(
        default_factory=dict,
        description="Modül 1/2'den hesaplanan ham değerler (anahtar -> değer)",
    )
    items: List[SyncedMetricItem] = Field(default_factory=list)
    message: str = Field(default="", examples=["9 gösterge senkronize edildi."])


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


class FrameworkSummaryRow(BaseModel):
    """Dashboard'daki tek bir çerçeve satırı."""

    framework_id: int = Field(..., examples=[1])
    framework_code: str = Field(..., examples=["THE"])
    framework_name: str = Field(default="", examples=["THE World University Rankings"])
    methodology_year: int = Field(default=0, examples=[2026])

    academic_year: Optional[str] = Field(default=None, examples=["2025-2026"])
    readiness_score: Optional[Decimal] = Field(default=None, examples=[72.50])
    performance_score: Optional[Decimal] = Field(default=None, examples=[58.40])
    compliance_score: Optional[Decimal] = Field(default=None, examples=[42.34])
    risk_level: Optional[EvaluationRiskLevel] = Field(default=None, examples=["high"])

    missing_indicator_count: int = Field(default=0, examples=[2])
    total_indicator_count: int = Field(default=0, examples=[14])
    has_assessment: bool = Field(default=False, examples=[True])


class DashboardSummaryResponse(BaseModel):
    """Modül 10 genel bakış paneli."""

    disclaimer: str = Field(
        default=(
            "Bu panel gerçek THE/QS/YÖK sıralaması göstermez; iç performans izleme "
            "ve veri hazırlık özetidir."
        )
    )

    academic_year: Optional[str] = Field(default=None, examples=["2025-2026"])
    period: MetricPeriod = MetricPeriod.ANNUAL

    framework_count: int = Field(default=0, examples=[3])
    dimension_count: int = Field(default=0, examples=[19])
    indicator_count: int = Field(default=0, examples=[42])
    metric_value_count: int = Field(default=0, examples=[96])
    benchmark_institution_count: int = Field(default=0, examples=[5])

    average_readiness_score: Decimal = Field(default=Decimal("0.00"), examples=[68.90])
    average_performance_score: Decimal = Field(default=Decimal("0.00"), examples=[55.10])
    average_compliance_score: Decimal = Field(default=Decimal("0.00"), examples=[37.96])
    highest_risk_level: EvaluationRiskLevel = EvaluationRiskLevel.MEDIUM

    frameworks: List[FrameworkSummaryRow] = Field(default_factory=list)
    top_missing_data: List[MissingDataItem] = Field(default_factory=list)
    top_recommendations: List[RecommendationItem] = Field(default_factory=list)
