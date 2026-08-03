"""Modül 3 yanıt şemaları (Pydantic).

Şemalar hem /docs sayfasındaki dokümantasyonu üretir hem de servis çıktısının
sözleşmeye uygunluğunu doğrular.
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class StudentCompositionMixin(BaseModel):
    """Öğrenci kompozisyonu göstergeleri (üniversite ve program seviyesinde ortak)."""

    international_student_percentage: float = Field(
        description="Uluslararası öğrenci yüzdesi"
    )
    scholarship_student_percentage: float = Field(description="Burslu öğrenci yüzdesi")
    preparatory_student_count: int = Field(description="Hazırlık sınıfı öğrenci sayısı")
    average_gpa: float = Field(description="Ortalama GNO")
    graduation_rate: float = Field(
        description="Beklenen mezuniyet yılı geçmiş kohortlarda mezuniyet oranı (%)"
    )
    graduation_cohort_size: int = Field(
        description="Mezuniyet oranının hesaplandığı kohort büyüklüğü"
    )
    average_time_to_graduation: float = Field(
        description="Ortalama mezuniyet süresi (yıl)"
    )


class UniversityOverviewResponse(StudentCompositionMixin):
    """Üniversite geneli konsolide öğrenci göstergeleri."""

    academic_year: str
    program_count: int
    total_students: int
    active_student_count: int
    newly_enrolled_student_count: int
    graduated_student_count_total: int
    graduated_student_count_in_year: int
    student_body_in_year: int
    total_quota: int
    total_enrolled_student_count: int
    overall_occupancy_rate: float
    dropped_out_student_count: int
    non_renewed_student_count: int
    attrition_rate: float
    non_renewal_rate: float


class ProgramMetricsResponse(StudentCompositionMixin):
    """Tek bir akademik programın öğrenci göstergeleri."""

    program_code: str
    program_name: str
    academic_year: str

    quota: int
    enrolled_student_count: int
    occupancy_rate: float

    total_students: int
    active_student_count: int
    newly_enrolled_student_count: int
    graduated_student_count_total: int
    graduated_student_count_in_year: int
    student_body_in_year: int

    dropped_out_student_count: int
    non_renewed_student_count: int
    attrition_rate: float
    non_renewal_rate: float

    minimum_admission_score: Optional[float] = None
    national_average_minimum_score: Optional[float] = None
    ankara_average_minimum_score: Optional[float] = None
    national_score_gap: Optional[float] = None
    ankara_score_gap: Optional[float] = None


class AdmissionScoreAnalysisResponse(BaseModel):
    """Taban puanın Ankara ve Türkiye ortalamalarına göre konumu."""

    program_code: str
    program_name: str
    academic_year: str
    minimum_admission_score: Optional[float] = None
    ankara_average_minimum_score: Optional[float] = None
    national_average_minimum_score: Optional[float] = None
    ankara_score_gap: Optional[float] = None
    national_score_gap: Optional[float] = None
    competitive_position: str


class DemandTrendPoint(BaseModel):
    """Talep trendinin tek bir yıla ait noktası."""

    academic_year: str
    quota: int
    enrolled_student_count: int
    occupancy_rate: float
    minimum_admission_score: Optional[float] = None
    dropped_out_student_count: int


class DemandTrendResponse(BaseModel):
    """Bir programın yıllar içindeki talep trendi."""

    program_code: str
    program_name: str
    series: List[DemandTrendPoint]
    occupancy_change_points: float = Field(
        description="İlk yıldan son yıla doluluk oranı değişimi (yüzde puan)"
    )
    admission_score_change: Optional[float] = None
    demand_direction: str = Field(description="keskin düşüş | düşüş | yatay | artış")


class AcademicPerformancePoint(BaseModel):
    """Akademik performans trendinin tek bir yıla ait noktası."""

    academic_year: str
    average_semester_gpa: float


class AcademicPerformanceTrendResponse(BaseModel):
    """Bir programın yıllara göre ortalama dönem GNO trendi."""

    program_code: str
    program_name: str
    series: List[AcademicPerformancePoint]
    gpa_change: float


class ComparableUniversityInput(BaseModel):
    """Bir kıyaslama (benzer/rakip) üniversitenin aynı program için verisi.

    Alan adları Modül 13'ün `comparable_university_programs_sample.xlsx` yapısıyla
    birebir aynıdır; entegrasyonda o kaynaktan üretilen veri doğrudan buraya akar.
    """

    university_name: str
    quota: Optional[int] = None
    enrolled_student_count: Optional[int] = None
    occupancy_rate: Optional[float] = None
    minimum_admission_score: Optional[float] = None
    is_competitor: bool = False


class ComparativeAnalysisRequest(BaseModel):
    """PDF Bölüm 3'ün 'benzer üniversiteler ve akademik bölümler arası
    karşılaştırmalı kayıt analizi' maddesi için dış girdi isteği.

    Bu modül kıyaslama verisini uydurmaz (Modül 7'deki external_inputs ile aynı
    ilke): veri Modül 13 (Veri Entegrasyonu) üzerinden sağlanır, burada yalnızca
    kendi göstergelerimizle karşılaştırma hesaplanır.
    """

    academic_year: str = Field(default="2026-2027")
    comparators: Dict[str, List[ComparableUniversityInput]] = Field(
        default_factory=dict,
        description=(
            "program kodu -> kıyaslama üniversiteleri listesi. "
            'Örnek: {"CENG-BSC": [{"university_name": "Boğaziçi Üniversitesi", ...}]}'
        ),
    )


class ComparativeAnalysisResult(BaseModel):
    """Bir programın benzer üniversitelerle karşılaştırma sonucu."""

    program_code: str
    program_name: str
    academic_year: str
    own_occupancy_rate: float
    own_minimum_admission_score: Optional[float] = None
    comparators: List[ComparableUniversityInput]
    average_comparator_occupancy_rate: Optional[float] = None
    average_comparator_admission_score: Optional[float] = None
    occupancy_gap_vs_comparators: Optional[float] = Field(
        default=None, description="Kendi doluluk oranımız - kıyaslama grubu ortalaması (puan)"
    )
    admission_score_gap_vs_comparators: Optional[float] = Field(
        default=None, description="Kendi taban puanımız - kıyaslama grubu ortalaması"
    )
    competitive_position: str = Field(
        description="kıyaslama grubunun üzerinde | kıyaslama grubunun altında | veri yok"
    )
