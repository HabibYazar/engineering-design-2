"""What-if senaryo analizi için Pydantic v2 şemaları."""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

# Yüzde alanları için ortak sınırlar.
# Alt sınır -100: bir değerin tamamen sıfırlanması (%-100) mantıklı en düşük değişimdir.
# Üst sınır 1000: 11 katına çıkmak gerçekçi bir senaryo üst sınırı olarak seçildi.
PERCENT_MIN: Decimal = Decimal("-100")
PERCENT_MAX: Decimal = Decimal("1000")


class ScenarioType(str, Enum):
    """Desteklenen senaryo türleri."""

    STUDENT_ENROLLMENT = "student-enrollment"
    TUITION_SCHOLARSHIP = "tuition-scholarship"
    ACADEMIC_STAFFING = "academic-staffing"
    INVESTMENT = "investment"
    RESEARCH_STRATEGY = "research-strategy"
    ECONOMIC_RISK = "economic-risk"
    COMBINED = "combined"


class ScenarioStatus(str, Enum):
    """Senaryonun yaşam döngüsündeki durumu."""

    DRAFT = "draft"  # oluşturuldu ama henüz simüle edilmedi
    SIMULATED = "simulated"  # en az bir kez hesaplandı
    ARCHIVED = "archived"  # pasifleştirildi


class RiskLevel(str, Enum):
    """Senaryonun genel risk seviyesi."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CapacityStatus(str, Enum):
    """Fiziksel kapasitenin yeterlilik durumu."""

    SUFFICIENT = "sufficient"  # kapasite rahat
    TIGHT = "tight"  # %90'ın üzerinde doluluk, sınırda
    INSUFFICIENT = "insufficient"  # kapasite aşıldı


# ---------------------------------------------------------------------------
# Baseline şemaları
# ---------------------------------------------------------------------------


class ScenarioBaselineBase(BaseModel):
    """Baseline'ın ortak alanları ve doğrulama kuralları."""

    name: str = Field(..., min_length=2, max_length=255)

    # gt=0: Öğrenci ve personel sayısı sıfır olamaz, aksi halde
    # oran ve öğrenci başına maliyet hesaplarında sıfıra bölme oluşur.
    student_count: int = Field(..., gt=0, description="Mevcut toplam öğrenci sayısı")
    academic_staff_count: int = Field(..., gt=0, description="Mevcut akademik personel sayısı")
    classroom_capacity: int = Field(..., gt=0, description="Toplam derslik kapasitesi")
    laboratory_capacity: int = Field(..., gt=0, description="Toplam laboratuvar kapasitesi")

    # ge=0: Para alanları negatif olamaz.
    #
    # examples=[...]: Decimal alanlar OpenAPI'de "anyOf: [number, string(pattern)]" olarak
    # üretilir. Swagger arayüzü örnek değer bulamadığında bu desene uyan rastgele ve çok uzun
    # sayılar gösterir. Her alana anlamına uygun bir örnek vererek dokümantasyonun okunabilir
    # olmasını sağlıyoruz. Bu değerler yalnızca dokümantasyonu etkiler; doğrulama kuralları
    # ve gerçek cevaplar değişmez.
    annual_tuition_per_student: Decimal = Field(
        ..., ge=0, description="Öğrenci başına yıllık ücret", examples=[180000.00]
    )
    scholarship_rate_percent: Decimal = Field(
        ..., ge=0, le=100, description="Mevcut burs oranı (%)", examples=[35.00]
    )
    annual_research_revenue: Decimal = Field(..., ge=0, examples=[50000000.00])
    annual_other_revenue: Decimal = Field(..., ge=0, examples=[25000000.00])
    annual_personnel_expense: Decimal = Field(..., ge=0, examples=[320000000.00])
    annual_education_expense: Decimal = Field(..., ge=0, examples=[70000000.00])
    annual_rd_expense: Decimal = Field(..., ge=0, examples=[45000000.00])
    annual_building_energy_expense: Decimal = Field(..., ge=0, examples=[30000000.00])
    annual_technology_expense: Decimal = Field(..., ge=0, examples=[25000000.00])


class ScenarioBaselineCreate(ScenarioBaselineBase):
    """Yeni baseline oluştururken kullanılan şema."""

    # Varsayılan olarak aktif; aktif yapılırsa önceki aktif baseline otomatik pasifleşir.
    is_active: bool = True


class ScenarioBaselineUpdate(BaseModel):
    """Baseline güncellerken kullanılan şema; tüm alanlar isteğe bağlıdır."""

    name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    student_count: Optional[int] = Field(default=None, gt=0)
    academic_staff_count: Optional[int] = Field(default=None, gt=0)
    classroom_capacity: Optional[int] = Field(default=None, gt=0)
    laboratory_capacity: Optional[int] = Field(default=None, gt=0)
    # Güncelleme şemasında da aynı örnekler kullanılıyor; Swagger'da her iki
    # gövde de tutarlı görünsün diye tekrarlandı.
    annual_tuition_per_student: Optional[Decimal] = Field(
        default=None, ge=0, examples=[180000.00]
    )
    scholarship_rate_percent: Optional[Decimal] = Field(
        default=None, ge=0, le=100, examples=[35.00]
    )
    annual_research_revenue: Optional[Decimal] = Field(default=None, ge=0, examples=[50000000.00])
    annual_other_revenue: Optional[Decimal] = Field(default=None, ge=0, examples=[25000000.00])
    annual_personnel_expense: Optional[Decimal] = Field(
        default=None, ge=0, examples=[320000000.00]
    )
    annual_education_expense: Optional[Decimal] = Field(
        default=None, ge=0, examples=[70000000.00]
    )
    annual_rd_expense: Optional[Decimal] = Field(default=None, ge=0, examples=[45000000.00])
    annual_building_energy_expense: Optional[Decimal] = Field(
        default=None, ge=0, examples=[30000000.00]
    )
    annual_technology_expense: Optional[Decimal] = Field(
        default=None, ge=0, examples=[25000000.00]
    )
    is_active: Optional[bool] = None


class ScenarioBaselineResponse(ScenarioBaselineBase):
    """Baseline kaydının API cevabı."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Scenario şemaları
# ---------------------------------------------------------------------------


class ScenarioBase(BaseModel):
    """Senaryonun ortak alanları."""

    name: str = Field(..., min_length=2, max_length=255)
    description: Optional[str] = None
    scenario_type: ScenarioType


class ScenarioCreate(ScenarioBase):
    """Yeni senaryo oluştururken kullanılan şema."""

    status: ScenarioStatus = ScenarioStatus.DRAFT


class ScenarioUpdate(BaseModel):
    """Senaryo güncellerken kullanılan şema; tüm alanlar isteğe bağlıdır."""

    name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    description: Optional[str] = None
    scenario_type: Optional[ScenarioType] = None
    status: Optional[ScenarioStatus] = None


class ScenarioResponse(ScenarioBase):
    """Senaryo kaydının API cevabı."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# ScenarioInput şemaları
# ---------------------------------------------------------------------------


class ScenarioInputCreate(BaseModel):
    """Simülasyonda kullanılacak değişiklik parametreleri.

    Tüm alanların varsayılanı 0'dır; yönetici sadece değiştirmek istediği
    parametreyi göndererek "diğer her şey sabitken ne olur" sorusunu sorabilir.
    """

    # Yüzdesel değişimler
    # Her alana kendi anlamına uygun gerçekçi bir örnek verildi; böylece Swagger'daki
    # "Try it out" gövdesi doğrudan denenebilir bir senaryo üretiyor.
    student_change_percent: Decimal = Field(
        default=Decimal("0"), ge=PERCENT_MIN, le=PERCENT_MAX,
        description="Öğrenci sayısındaki yüzdesel değişim",
        examples=[10.00],
    )
    tuition_change_percent: Decimal = Field(
        default=Decimal("0"), ge=PERCENT_MIN, le=PERCENT_MAX,
        description="Öğrenim ücretindeki yüzdesel değişim",
        examples=[25.00],
    )
    scholarship_change_percent: Decimal = Field(
        default=Decimal("0"), ge=PERCENT_MIN, le=PERCENT_MAX,
        description="Burs oranına eklenecek yüzde puanı (mevcut orana eklenir)",
        examples=[-5.00],
    )
    inflation_percent: Decimal = Field(
        default=Decimal("0"), ge=PERCENT_MIN, le=PERCENT_MAX,
        description="Beklenen yıllık enflasyon",
        examples=[35.00],
    )
    exchange_rate_change_percent: Decimal = Field(
        default=Decimal("0"), ge=PERCENT_MIN, le=PERCENT_MAX,
        description="Döviz kurundaki yüzdesel değişim",
        examples=[20.00],
    )
    research_funding_change_percent: Decimal = Field(
        default=Decimal("0"), ge=PERCENT_MIN, le=PERCENT_MAX,
        description="Araştırma fonlarındaki yüzdesel değişim",
        examples=[10.00],
    )

    # Mutlak değişimler (negatif olabilir)
    academic_staff_change: int = Field(
        default=0, description="Akademik personel sayısındaki artış/azalış (adet)"
    )
    classroom_capacity_change: int = Field(
        default=0, description="Derslik kapasitesindeki artış/azalış (kişi)"
    )
    laboratory_capacity_change: int = Field(
        default=0, description="Laboratuvar kapasitesindeki artış/azalış (kişi)"
    )


class ScenarioInputResponse(ScenarioInputCreate):
    """Kaydedilmiş senaryo girdisinin API cevabı."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    scenario_id: int
    created_at: datetime


# ---------------------------------------------------------------------------
# Sonuç ve simülasyon şemaları
# ---------------------------------------------------------------------------


class ScenarioResultResponse(BaseModel):
    """Kaydedilmiş simülasyon sonucunun API cevabı."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    scenario_id: int

    baseline_student_count: int = Field(..., examples=[5000])
    projected_student_count: int = Field(..., examples=[5500])

    # Örnek değerler tutarlı bir senaryodan alındı (%10 öğrenci artışı):
    # aynı satırda okunduğunda mevcut durum ile tahmin arasındaki fark anlaşılıyor.
    baseline_revenue: Decimal = Field(..., examples=[660000000.00])
    projected_revenue: Decimal = Field(..., examples=[718500000.00])
    baseline_expenditure: Decimal = Field(..., examples=[490000000.00])
    projected_expenditure: Decimal = Field(..., examples=[497000000.00])

    baseline_staff_count: int = Field(..., examples=[220])
    projected_staff_count: int = Field(..., examples=[220])
    baseline_student_staff_ratio: Decimal = Field(..., examples=[22.73])
    projected_student_staff_ratio: Decimal = Field(..., examples=[25.00])

    baseline_cost_per_student: Decimal = Field(..., examples=[98000.00])
    projected_cost_per_student: Decimal = Field(..., examples=[90363.64])

    baseline_classroom_capacity: int = Field(..., examples=[5500])
    projected_classroom_capacity: int = Field(..., examples=[5500])
    baseline_laboratory_capacity: int = Field(..., examples=[5200])
    projected_laboratory_capacity: int = Field(..., examples=[5200])

    classroom_capacity_status: str = Field(..., examples=["tight"])
    laboratory_capacity_status: str = Field(..., examples=["insufficient"])

    risk_level: str = Field(..., examples=["medium"])
    recommendation: Optional[str] = Field(
        default=None,
        examples=["Senaryo uygulanabilir ancak izlenmesi gereken riskler var."],
    )
    calculated_at: datetime


class RiskItem(BaseModel):
    """Tespit edilen tek bir riskin açıklaması."""

    code: str = Field(..., description="Riskin teknik kodu")
    message: str = Field(..., description="Türkçe risk açıklaması")
    severity: str = Field(..., description="warning | critical")


class FinancialBreakdown(BaseModel):
    """Gelir ve gider kalemlerinin ayrıntılı dökümü.

    Toplam rakamın nereden geldiğini göstermek için eklendi; yönetici
    "gider neden arttı" sorusunu tek bakışta cevaplayabilsin.
    """

    projected_tuition_revenue: Decimal = Field(..., examples=[643500000.00])
    projected_research_revenue: Decimal = Field(..., examples=[50000000.00])
    projected_other_revenue: Decimal = Field(..., examples=[25000000.00])

    projected_personnel_expense: Decimal = Field(..., examples=[320000000.00])
    projected_education_expense: Decimal = Field(..., examples=[77000000.00])
    projected_rd_expense: Decimal = Field(..., examples=[45000000.00])
    projected_building_energy_expense: Decimal = Field(..., examples=[30000000.00])
    projected_technology_expense: Decimal = Field(..., examples=[25000000.00])

    effective_scholarship_rate_percent: Decimal = Field(..., examples=[35.00])
    scholarship_deduction: Decimal = Field(..., examples=[346500000.00])

    # Bütçe dengesi: pozitifse fazla, negatifse açık.
    baseline_balance: Decimal = Field(..., examples=[170000000.00])
    projected_balance: Decimal = Field(..., examples=[221500000.00])


class SimulationResponse(BaseModel):
    """Simülasyon veya ön izleme sonucunda dönen tam rapor."""

    scenario_id: Optional[int] = Field(
        default=None, description="preview modunda None döner"
    )
    scenario_name: Optional[str] = None
    scenario_type: Optional[str] = None
    baseline_id: int
    baseline_name: str
    preview: bool = False

    # Kullanılan girdiler; raporun hangi varsayımlarla üretildiği görünsün diye eklendi.
    inputs: ScenarioInputCreate

    # Ana sonuç tablosu (preview modunda id ve tarih alanları doldurulmaz).
    result: "SimulationMetrics"
    breakdown: FinancialBreakdown

    risks: List[RiskItem] = Field(default_factory=list)
    risk_level: RiskLevel
    recommendation: str

    result_id: Optional[int] = Field(
        default=None, description="Veritabanına kaydedilen sonucun id'si (preview'da None)"
    )
    calculated_at: datetime

    # Öğrenci sayısının nereden alındığını belirtir:
    #   "baseline"            -> ScenarioBaseline.student_count kullanıldı (varsayılan)
    #   "live-student-module" -> Modül 2'deki aktif öğrenci sayısı kullanıldı
    student_data_source: str = Field(
        default="baseline", description="baseline | live-student-module"
    )
    live_active_student_count: Optional[int] = Field(
        default=None, description="Canlı veri kullanıldıysa Student tablosundaki aktif sayı"
    )


class SimulationMetrics(BaseModel):
    """Simülasyonun sayısal sonuçları (veritabanına kaydedilenlerle aynı alanlar)."""

    baseline_student_count: int = Field(..., examples=[5000])
    projected_student_count: int = Field(..., examples=[5500])

    baseline_revenue: Decimal = Field(..., examples=[660000000.00])
    projected_revenue: Decimal = Field(..., examples=[718500000.00])
    baseline_expenditure: Decimal = Field(..., examples=[490000000.00])
    projected_expenditure: Decimal = Field(..., examples=[497000000.00])

    baseline_staff_count: int = Field(..., examples=[220])
    projected_staff_count: int = Field(..., examples=[220])
    baseline_student_staff_ratio: Decimal = Field(..., examples=[22.73])
    projected_student_staff_ratio: Decimal = Field(..., examples=[25.00])

    baseline_cost_per_student: Decimal = Field(..., examples=[98000.00])
    projected_cost_per_student: Decimal = Field(..., examples=[90363.64])

    baseline_classroom_capacity: int = Field(..., examples=[5500])
    projected_classroom_capacity: int = Field(..., examples=[5500])
    baseline_laboratory_capacity: int = Field(..., examples=[5200])
    projected_laboratory_capacity: int = Field(..., examples=[5200])

    classroom_capacity_status: CapacityStatus
    laboratory_capacity_status: CapacityStatus


# SimulationResponse içinde SimulationMetrics'e isimle referans verdiğimiz için
# modeli sonradan tanımlayıp burada bağlıyoruz.
SimulationResponse.model_rebuild()
