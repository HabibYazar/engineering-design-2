"""Akademik başarı analizi şemaları.

Tüm oranlar yüzde (%) cinsindendir ve 0-100 aralığındadır.
"""

from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


class SuccessMetricsBase(BaseModel):
    """Her seviyede tekrar eden başarı göstergeleri."""

    academic_year: str = Field(examples=["2025-2026"])
    source_type: Optional[str] = None
    source_label: Optional[str] = None
    provenance: Optional[str] = None
    is_synthetic: bool = False
    uploaded_source_id: Optional[int] = None
    filename: Optional[str] = None

    measured_student_count: int = Field(
        description="Ölçüme dahil öğrenci sayısı. Ağırlıklı ortalamanın ağırlığıdır.",
        examples=[3820],
    )
    course_pass_rate: Optional[Decimal] = Field(
        default=None, description="Ders geçme oranı (%)", examples=[Decimal("82.40")]
    )
    course_fail_rate: Optional[Decimal] = Field(
        default=None,
        description="Ders başarısızlık oranı (%). 100 − geçme oranı olarak türetilir.",
        examples=[Decimal("17.60")],
    )
    average_success_score: Optional[Decimal] = Field(
        default=None, description="Ortalama başarı puanı (0-100)", examples=[Decimal("72.10")]
    )
    dropout_rate: Optional[Decimal] = Field(
        default=None, description="Öğrenci kaybı / bırakma oranı (%)", examples=[Decimal("7.30")]
    )
    graduation_rate: Optional[Decimal] = Field(
        default=None, description="Mezuniyet oranı (%)", examples=[Decimal("76.80")]
    )
    graduate_count: int = Field(default=0, description="Mezun sayısı", examples=[748])

    # Önceki döneme göre değişim (yüzde PUANI). Önceki dönem verisi yoksa null.
    course_pass_rate_change: Optional[Decimal] = Field(
        default=None,
        description="Ders geçme oranındaki değişim (yüzde puanı). Önceki dönem verisi yoksa null.",
        examples=[Decimal("1.20")],
    )
    average_success_score_change: Optional[Decimal] = Field(default=None)
    dropout_rate_change: Optional[Decimal] = Field(default=None)
    graduation_rate_change: Optional[Decimal] = Field(default=None)
    previous_academic_year: Optional[str] = Field(
        default=None, description="Karşılaştırmada kullanılan önceki dönem", examples=["2024-2025"]
    )


class UniversitySuccessOverview(SuccessMetricsBase):
    """Üniversite geneli başarı özeti."""

    scope: str = Field(default="Üniversite geneli")
    program_count: int = Field(examples=[14])
    department_count: int = Field(examples=[12])
    faculty_count: int = Field(examples=[4])


class FacultySuccessRow(SuccessMetricsBase):
    """Fakülte bazlı başarı satırı."""

    faculty_id: int
    faculty_name: str = Field(examples=["Mühendislik ve Mimarlık Fakültesi"])
    program_count: int


class DepartmentSuccessRow(SuccessMetricsBase):
    """Bölüm bazlı başarı satırı."""

    department_id: int
    department_name: str = Field(examples=["Bilgisayar Mühendisliği"])
    department_code: str = Field(examples=["CENG"])
    faculty_id: Optional[int] = None
    faculty_name: Optional[str] = None
    program_count: int


class ProgramSuccessRow(SuccessMetricsBase):
    """Program bazlı başarı satırı — en alt kırılım."""

    program_id: int
    program_code: str = Field(examples=["CENG-BSC"])
    program_name: str
    department_id: int
    department_name: Optional[str] = None
    faculty_id: Optional[int] = None
    faculty_name: Optional[str] = None
    # Kontenjan kaynakta yoksa null döner; 0 yazmak "kontenjan sıfır" demek
    # olurdu ve doluluk oranını yanlış hesaplatırdı.
    quota: Optional[int] = Field(default=None, examples=[100])
    department_staff_count: int = Field(
        description="Bölümdeki aktif akademik personel sayısı", examples=[20]
    )
    students_per_staff: Optional[Decimal] = Field(
        default=None,
        description="Akademisyen başına öğrenci. Personel yoksa hesaplanmaz.",
        examples=[Decimal("26.00")],
    )


class SuccessTrendPoint(BaseModel):
    """Trend grafiğindeki tek nokta."""

    academic_year: str = Field(examples=["2025-2026"])
    measured_student_count: int
    course_pass_rate: Optional[Decimal] = None
    course_fail_rate: Optional[Decimal] = None
    average_success_score: Optional[Decimal] = None
    dropout_rate: Optional[Decimal] = None
    graduation_rate: Optional[Decimal] = None
    graduate_count: int = 0
    program_count: int = 0
    source_type: Optional[str] = None
    source_label: Optional[str] = None
    provenance: Optional[str] = None
    is_synthetic: bool = False
    uploaded_source_id: Optional[int] = None
    filename: Optional[str] = None


class RankingEntry(BaseModel):
    """Sıralama listesindeki tek birim."""

    name: str = Field(examples=["Hemşirelik"])
    course_pass_rate: Optional[Decimal] = Field(examples=[Decimal("90.20")])
    average_success_score: Optional[Decimal] = Field(examples=[Decimal("79.10")])
    measured_student_count: int = Field(examples=[442])


class SuccessRankings(BaseModel):
    """En başarılı ve en düşük başarılı birimler."""

    academic_year: str
    level: str = Field(description="faculty | department | program", examples=["department"])
    top: List[RankingEntry]
    bottom: List[RankingEntry]
    excluded_small_units: int = Field(
        description="Öğrenci eşiğinin altında kaldığı için listelenmeyen birim sayısı",
        examples=[2],
    )
    minimum_student_threshold: int = Field(examples=[30])
    note: str
    source_type: Optional[str] = None
    source_label: Optional[str] = None
    provenance: Optional[str] = None
    is_synthetic: bool = False
    uploaded_source_id: Optional[int] = None
    filename: Optional[str] = None


class SuccessCorrelations(BaseModel):
    """Öğrenci sayısı ve akademisyen yükü ile başarı arasındaki ilişki."""

    academic_year: str
    program_count: int
    student_count_vs_pass_rate: Optional[Decimal] = Field(
        default=None,
        description="Pearson korelasyon katsayısı (-1 ile +1 arası)",
        examples=[Decimal("-0.34")],
    )
    students_per_staff_vs_pass_rate: Optional[Decimal] = Field(
        default=None, examples=[Decimal("-0.41")]
    )
    interpretation: List[str] = Field(
        description="Katsayıların sade dille yorumu"
    )
    caveat: str = Field(
        description="Korelasyonun nedensellik olmadığına dair uyarı"
    )
    source_type: Optional[str] = None
    source_label: Optional[str] = None
    provenance: Optional[str] = None
    is_synthetic: bool = False
    uploaded_source_id: Optional[int] = None
    filename: Optional[str] = None
