"""Öğrenci analitiği cevap şemaları (Pydantic v2)."""

from decimal import Decimal
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class DemandTrend(str, Enum):
    """Programa olan talebin yönü."""

    INCREASING = "increasing"
    STABLE = "stable"
    DECREASING = "decreasing"


class TrendMetric(str, Enum):
    """Yıllara göre izlenebilen analitik metrikler."""

    TOTAL_STUDENTS = "total-students"
    NEWLY_ENROLLED = "newly-enrolled"
    GRADUATES = "graduates"
    OCCUPANCY_RATE = "occupancy-rate"
    GRADUATION_RATE = "graduation-rate"
    ATTRITION_RATE = "attrition-rate"
    NON_RENEWAL_RATE = "non-renewal-rate"
    SCHOLARSHIP_PERCENTAGE = "scholarship-percentage"
    INTERNATIONAL_PERCENTAGE = "international-percentage"
    AVERAGE_GPA = "average-gpa"
    MINIMUM_ADMISSION_SCORE = "minimum-admission-score"


class AlertSeverity(str, Enum):
    """Erken uyarı şiddet seviyeleri."""

    INFO = "info"
    WARNING = "warning"
    HIGH = "high"
    CRITICAL = "critical"


# ---------------------------------------------------------------------------
# Genel bakış
# ---------------------------------------------------------------------------


class StudentOverview(BaseModel):
    """Üniversite/fakülte/bölüm düzeyinde öğrenci özeti."""

    # examples=[...]: Decimal alanlar OpenAPI'de "anyOf: [number, string(pattern)]" olarak
    # üretildiği için Swagger, örnek verilmediğinde desene uyan rastgele ve çok uzun sayılar
    # gösteriyordu. Her alana anlamına uygun örnek vererek dokümantasyonu okunabilir yapıyoruz.
    # Bu ekleme yalnızca şemayı etkiler; hesaplama ve gerçek cevaplar aynı kalır.
    total_students: int = Field(default=0, examples=[120])
    newly_enrolled_students: int = Field(default=0, examples=[8])
    active_students: int = Field(default=0, examples=[75])
    graduated_students: int = Field(default=0, examples=[17])
    preparatory_school_students: int = Field(default=0, examples=[6])
    dropped_out_students: int = Field(default=0, examples=[5])
    non_renewed_students: int = Field(default=0, examples=[12])

    # Yüzdeler iki ondalık basamağa yuvarlanır.
    scholarship_student_percentage: Decimal = Field(
        default=Decimal("0.00"), examples=[33.33]
    )
    international_student_percentage: Decimal = Field(
        default=Decimal("0.00"), examples=[16.67]
    )

    average_gpa: Decimal = Field(default=Decimal("0.00"), examples=[2.47])
    average_graduation_duration_years: Decimal = Field(
        default=Decimal("0.00"), examples=[4.35]
    )

    # Akademik başarı göstergeleri (StudentAcademicRecord tablosundan).
    # passed_course_ratio yüzde (0-100), credit_efficiency_ratio ise oran (0-1) olduğu için
    # örnekleri bilinçli olarak farklı ölçekte verildi.
    passed_course_ratio: Decimal = Field(default=Decimal("0.00"), examples=[88.43])
    credit_efficiency_ratio: Decimal = Field(default=Decimal("0.00"), examples=[0.88])

    # Hangi filtrelerle hesaplandığı cevapta görünsün diye eklendi.
    applied_filters: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Program / bölüm / fakülte kırılımları
# ---------------------------------------------------------------------------


class ProgramAnalytics(BaseModel):
    """Tek bir akademik programın analitik özeti."""

    program_id: int = Field(..., examples=[1])
    program_name: str = Field(..., examples=["Software Engineering Bachelor's Program"])
    program_code: str = Field(..., examples=["SWE-BSC"])
    department_id: int = Field(..., examples=[1])
    department_name: str = Field(..., examples=["Software Engineering"])
    faculty_id: int = Field(..., examples=[1])
    faculty_name: str = Field(..., examples=["Faculty of Engineering and Architecture"])

    quota: int = Field(default=0, examples=[80])
    enrolled_student_count: int = Field(default=0, examples=[79])
    occupancy_rate: Decimal = Field(default=Decimal("0.00"), examples=[98.75])

    # Oran alanlarının her birine farklı örnek verildi; böylece Swagger'da
    # hangi metriğin hangi büyüklükte olduğu tek bakışta anlaşılıyor.
    active_student_count: int = Field(default=0, examples=[43])
    graduate_count: int = Field(default=0, examples=[7])
    graduation_rate: Decimal = Field(default=Decimal("0.00"), examples=[13.21])
    dropped_out_count: int = Field(default=0, examples=[3])
    attrition_rate: Decimal = Field(default=Decimal("0.00"), examples=[5.00])
    non_renewed_count: int = Field(default=0, examples=[6])
    non_renewal_rate: Decimal = Field(default=Decimal("0.00"), examples=[10.00])

    scholarship_student_percentage: Decimal = Field(
        default=Decimal("0.00"), examples=[33.33]
    )
    international_student_percentage: Decimal = Field(
        default=Decimal("0.00"), examples=[16.67]
    )
    average_gpa: Decimal = Field(default=Decimal("0.00"), examples=[2.43])
    average_graduation_duration_years: Decimal = Field(
        default=Decimal("0.00"), examples=[4.29]
    )

    minimum_admission_score: Optional[Decimal] = Field(default=None, examples=[441.90])
    demand_trend: DemandTrend = DemandTrend.STABLE

    total_students: int = Field(default=0, examples=[60])


class DepartmentAnalytics(BaseModel):
    """Bölüm düzeyinde birleştirilmiş analitik özet."""

    department_id: int = Field(..., examples=[1])
    department_name: str = Field(..., examples=["Software Engineering"])
    department_code: str = Field(..., examples=["SWE"])
    faculty_id: int = Field(..., examples=[1])
    faculty_name: str = Field(..., examples=["Faculty of Engineering and Architecture"])

    program_count: int = Field(default=0, examples=[1])
    total_students: int = Field(default=0, examples=[60])
    active_students: int = Field(default=0, examples=[43])
    graduates: int = Field(default=0, examples=[7])
    dropped_out_students: int = Field(default=0, examples=[3])
    non_renewed_students: int = Field(default=0, examples=[6])

    average_occupancy_rate: Decimal = Field(default=Decimal("0.00"), examples=[98.75])
    graduation_rate: Decimal = Field(default=Decimal("0.00"), examples=[13.21])
    attrition_rate: Decimal = Field(default=Decimal("0.00"), examples=[5.00])
    non_renewal_rate: Decimal = Field(default=Decimal("0.00"), examples=[10.00])
    international_student_percentage: Decimal = Field(
        default=Decimal("0.00"), examples=[16.67]
    )
    scholarship_student_percentage: Decimal = Field(
        default=Decimal("0.00"), examples=[33.33]
    )
    average_gpa: Decimal = Field(default=Decimal("0.00"), examples=[2.43])


class FacultyAnalytics(BaseModel):
    """Fakülte düzeyinde birleştirilmiş analitik özet."""

    faculty_id: int = Field(..., examples=[1])
    faculty_name: str = Field(..., examples=["Faculty of Engineering and Architecture"])
    faculty_code: str = Field(..., examples=["FEA"])

    department_count: int = Field(default=0, examples=[2])
    program_count: int = Field(default=0, examples=[2])
    total_students: int = Field(default=0, examples=[120])
    active_students: int = Field(default=0, examples=[83])
    graduates: int = Field(default=0, examples=[17])
    dropped_out_students: int = Field(default=0, examples=[5])
    non_renewed_students: int = Field(default=0, examples=[12])

    # Fakülte düzeyinde doluluk, kontenjan toplamı üzerinden ağırlıklı hesaplandığı için
    # örnek değer program örneklerinden farklı (68.33 = 123/180).
    average_occupancy_rate: Decimal = Field(default=Decimal("0.00"), examples=[68.33])
    graduation_rate: Decimal = Field(default=Decimal("0.00"), examples=[16.19])
    attrition_rate: Decimal = Field(default=Decimal("0.00"), examples=[4.17])
    non_renewal_rate: Decimal = Field(default=Decimal("0.00"), examples=[10.00])
    international_student_percentage: Decimal = Field(
        default=Decimal("0.00"), examples=[16.67]
    )
    scholarship_student_percentage: Decimal = Field(
        default=Decimal("0.00"), examples=[33.33]
    )
    average_gpa: Decimal = Field(default=Decimal("0.00"), examples=[2.47])


# ---------------------------------------------------------------------------
# Trend
# ---------------------------------------------------------------------------


class TrendPoint(BaseModel):
    """Trend serisindeki tek bir yılın değeri."""

    year: int = Field(..., examples=[2025])
    academic_year: Optional[str] = Field(default=None, examples=["2025-2026"])
    value: Decimal = Field(default=Decimal("0.00"), examples=[44.00])

    # Önceki yıla göre mutlak ve yüzdesel değişim.
    # İlk yılda karşılaştırılacak veri olmadığı için None döner.
    change_absolute: Optional[Decimal] = Field(default=None, examples=[-14.00])
    change_percent: Optional[Decimal] = Field(default=None, examples=[-24.14])


class TrendResponse(BaseModel):
    """Yıllara göre metrik gelişimi."""

    metric: TrendMetric
    start_year: int = Field(..., examples=[2022])
    end_year: int = Field(..., examples=[2025])
    points: List[TrendPoint] = Field(default_factory=list)

    # Serinin genel yönü; ilk ve son değer karşılaştırılarak belirlenir.
    overall_direction: DemandTrend = DemandTrend.STABLE
    applied_filters: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Talep ve karşılaştırma
# ---------------------------------------------------------------------------


class DemandYearPoint(BaseModel):
    """Bir programın tek bir yıldaki talep verileri."""

    academic_year: str = Field(..., examples=["2025-2026"])
    year: int = Field(..., examples=[2025])
    quota: int = Field(..., examples=[80])
    enrolled_student_count: int = Field(..., examples=[79])
    occupancy_rate: Decimal = Field(..., examples=[98.75])
    minimum_admission_score: Optional[Decimal] = Field(default=None, examples=[441.90])
    national_average_minimum_score: Optional[Decimal] = Field(default=None, examples=[389.80])
    ankara_average_minimum_score: Optional[Decimal] = Field(default=None, examples=[406.20])

    occupancy_change_percent: Optional[Decimal] = Field(default=None, examples=[3.95])
    score_change_percent: Optional[Decimal] = Field(default=None, examples=[3.18])


class ProgramDemandResponse(BaseModel):
    """Programın yıllara göre talep gelişimi ve trend yorumu."""

    program_id: int = Field(..., examples=[1])
    program_name: str = Field(..., examples=["Software Engineering Bachelor's Program"])
    program_code: str = Field(..., examples=["SWE-BSC"])
    department_name: str = Field(..., examples=["Software Engineering"])
    faculty_name: str = Field(..., examples=["Faculty of Engineering and Architecture"])

    years: List[DemandYearPoint] = Field(default_factory=list)
    demand_trend: DemandTrend = DemandTrend.STABLE
    trend_explanation: str = ""


class ComparisonRow(BaseModel):
    """Karşılaştırma tablosundaki tek bir satır."""

    label: str = Field(..., examples=["Orta Doğu Teknik Üniversitesi — Computer Engineering"])
    university_name: Optional[str] = Field(
        default=None, examples=["Orta Doğu Teknik Üniversitesi"]
    )
    city: Optional[str] = Field(default=None, examples=["Ankara"])
    quota: Optional[int] = Field(default=None, examples=[130])
    enrolled_student_count: Optional[int] = Field(default=None, examples=[130])
    occupancy_rate: Optional[Decimal] = Field(default=None, examples=[100.00])
    minimum_admission_score: Optional[Decimal] = Field(default=None, examples=[498.40])
    is_competitor: bool = False

    # Kendi programımıza göre farklar (pozitif = biz öndeyiz).
    # Örnek değerler negatif: karşılaştırılan üniversite bizden önde olduğunda
    # farkın nasıl göründüğü dokümantasyondan anlaşılsın.
    occupancy_difference: Optional[Decimal] = Field(default=None, examples=[-1.25])
    score_difference: Optional[Decimal] = Field(default=None, examples=[-56.50])


class ProgramComparisonResponse(BaseModel):
    """Programın diğer üniversitelerle karşılaştırması."""

    program_id: int = Field(..., examples=[1])
    program_name: str = Field(..., examples=["Software Engineering Bachelor's Program"])
    academic_year: str = Field(..., examples=["2025-2026"])

    own_program: ComparisonRow
    national_average: Optional[ComparisonRow] = None
    ankara_average: Optional[ComparisonRow] = None

    similar_programs: List[ComparisonRow] = Field(default_factory=list)
    competitor_programs: List[ComparisonRow] = Field(default_factory=list)

    # Sıralama bilgisi: kendi programımız puan ve doluluk sıralamasında kaçıncı.
    score_rank: Optional[int] = Field(default=None, examples=[4])
    occupancy_rank: Optional[int] = Field(default=None, examples=[2])
    total_compared: int = Field(default=0, examples=[8])
    summary: str = Field(
        default="",
        examples=[
            "7 karşılaştırma kaydı içinde taban puan sıralamasında 4. , "
            "doluluk oranı sıralamasında 2. sıradayız (toplam 8 program)."
        ],
    )


# ---------------------------------------------------------------------------
# Erken uyarılar
# ---------------------------------------------------------------------------


class StudentAlert(BaseModel):
    """Tespit edilen tek bir erken uyarı."""

    code: str = Field(..., examples=["low_occupancy_rate"])
    severity: AlertSeverity
    entity_type: str = Field(
        ..., description="program | department | faculty | university", examples=["program"]
    )
    entity_id: Optional[int] = Field(default=None, examples=[2])
    entity_name: str = Field(..., examples=["Computer Engineering Bachelor's Program"])
    metric: str = Field(..., examples=["occupancy_rate"])

    # current_value ve threshold aynı metriğin iki farklı değeridir; örnekleri
    # bilinçli olarak farklı seçildi ki eşiğin altında kalındığı görülsün.
    current_value: Optional[Decimal] = Field(default=None, examples=[44.00])
    threshold: Optional[Decimal] = Field(default=None, examples=[50.00])

    message: str = Field(
        ...,
        examples=[
            "Computer Engineering Bachelor's Program programının doluluk oranı %44.00 ile "
            "hedef alt sınır olan %50 değerinin altında."
        ],
    )
    recommendation: str = Field(
        ...,
        examples=[
            "Kontenjan gözden geçirilmeli, tanıtım faaliyetleri artırılmalı ve programın "
            "tercih edilebilirliğini artıracak müfredat güncellemesi değerlendirilmelidir."
        ],
    )


class AlertsResponse(BaseModel):
    """Uyarı listesi ve özet sayaçlar."""

    total_alerts: int = Field(default=0, examples=[6])
    counts_by_severity: dict = Field(default_factory=dict)
    alerts: List[StudentAlert] = Field(default_factory=list)
    applied_filters: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Senaryo entegrasyonu
# ---------------------------------------------------------------------------


class StudentDataSyncResponse(BaseModel):
    """Aktif baseline'ın öğrenci sayısıyla senkronizasyon sonucu."""

    baseline_id: int = Field(..., examples=[1])
    baseline_name: str = Field(..., examples=["2026 University Baseline"])
    previous_student_count: int = Field(..., examples=[5000])
    new_student_count: int = Field(..., examples=[83])
    difference: int = Field(..., examples=[-4917])
    message: str = Field(
        ...,
        examples=[
            "Aktif baseline'ın öğrenci sayısı 5000 değerinden 83 değerine "
            "güncellendi (fark: -4917)."
        ],
    )
