"""Modül 3 yanıt şemaları (Pydantic).

Şemalar hem /docs sayfasındaki dokümantasyonu üretir hem de servis çıktısının
sözleşmeye uygunluğunu doğrular.
"""

from typing import List, Optional

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
