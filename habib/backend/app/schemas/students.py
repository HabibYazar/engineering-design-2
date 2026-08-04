"""Öğrenci, akademik kayıt, program snapshot ve karşılaştırma şemaları (Pydantic v2)."""

import re
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Kayıt yılı için makul aralık. Üniversitenin kuruluşundan öncesi ya da
# çok uzak bir gelecek yılı veri giriş hatasıdır.
MIN_ENROLLMENT_YEAR: int = 1950
MAX_ENROLLMENT_YEAR: int = 2100

# academic_year "2024-2025" biçiminde olmalıdır.
ACADEMIC_YEAR_PATTERN: re.Pattern = re.compile(r"^\d{4}-\d{4}$")


def validate_academic_year(value: str) -> str:
    """Akademik yıl biçimini (YYYY-YYYY) ve yılların ardışıklığını doğrular."""
    text: str = str(value).strip()
    if not ACADEMIC_YEAR_PATTERN.match(text):
        raise ValueError(
            f"Akademik yıl 'YYYY-YYYY' biçiminde olmalıdır (örnek: 2024-2025). Gelen değer: '{value}'."
        )

    start_year, end_year = (int(part) for part in text.split("-"))
    if end_year != start_year + 1:
        raise ValueError(
            f"Akademik yılın ikinci kısmı birincisinden bir fazla olmalıdır "
            f"(örnek: 2024-2025). Gelen değer: '{value}'."
        )
    if not (MIN_ENROLLMENT_YEAR <= start_year <= MAX_ENROLLMENT_YEAR):
        raise ValueError(
            f"Akademik yıl {MIN_ENROLLMENT_YEAR}-{MAX_ENROLLMENT_YEAR} aralığında olmalıdır."
        )
    return text


class Gender(str, Enum):
    """Öğrencinin cinsiyet bilgisi."""

    MALE = "male"
    FEMALE = "female"
    OTHER = "other"
    UNSPECIFIED = "unspecified"


class StudentStatus(str, Enum):
    """Öğrencinin güncel kayıt durumu."""

    NEWLY_ENROLLED = "newly-enrolled"  # bu yıl kayıt oldu
    ACTIVE = "active"  # öğrenimine devam ediyor
    GRADUATED = "graduated"  # mezun oldu
    SUSPENDED = "suspended"  # kaydı donduruldu
    DROPPED_OUT = "dropped-out"  # öğrenimi bıraktı
    NON_RENEWED = "non-renewed"  # kaydını yenilemedi


class Semester(str, Enum):
    """Akademik dönem."""

    FALL = "fall"
    SPRING = "spring"
    SUMMER = "summer"


# ---------------------------------------------------------------------------
# Student
# ---------------------------------------------------------------------------


class StudentBase(BaseModel):
    """Öğrencinin ortak alanları ve temel doğrulama kuralları."""

    # examples=[...]: Decimal alanlar OpenAPI'de "anyOf: [number, string(pattern)]" olarak
    # üretildiği için Swagger, örnek verilmediğinde desene uyan rastgele ve çok uzun sayılar
    # gösteriyordu. Alanlara anlamına uygun örnek vererek dokümantasyonu okunabilir yapıyoruz.
    # Bu ekleme yalnızca şemayı etkiler; doğrulama ve gerçek cevaplar aynı kalır.
    student_number: str = Field(..., min_length=1, max_length=50, examples=["S2026001"])
    first_name: str = Field(..., min_length=1, max_length=100, examples=["Elif"])
    last_name: str = Field(..., min_length=1, max_length=100, examples=["Yıldız"])

    gender: Gender = Gender.UNSPECIFIED
    nationality: Optional[str] = Field(default=None, max_length=100, examples=["Türkiye"])
    is_international: bool = False

    # Burs oranı yüzde olarak; 0 burssuz demektir.
    scholarship_rate_percent: Decimal = Field(
        default=Decimal("0"), ge=0, le=100, examples=[50.00]
    )

    enrollment_year: int = Field(
        ..., ge=MIN_ENROLLMENT_YEAR, le=MAX_ENROLLMENT_YEAR, examples=[2026]
    )
    current_status: StudentStatus = StudentStatus.ACTIVE
    preparatory_school: bool = False

    academic_program_id: int = Field(..., gt=0, examples=[1])

    # GPA 4'lük sistemde tutuluyor.
    current_gpa: Optional[Decimal] = Field(default=None, ge=0, le=4, examples=[3.20])

    expected_graduation_year: Optional[int] = Field(
        default=None, ge=MIN_ENROLLMENT_YEAR, le=MAX_ENROLLMENT_YEAR, examples=[2030]
    )
    actual_graduation_year: Optional[int] = Field(
        default=None, ge=MIN_ENROLLMENT_YEAR, le=MAX_ENROLLMENT_YEAR, examples=[2030]
    )

    @field_validator("student_number")
    @classmethod
    def _normalize_student_number(cls, value: str) -> str:
        """Öğrenci numarasını boşluklardan temizler ve büyük harfe çevirir."""
        # Aynı numaranın "  2024001 " ve "2024001" olarak iki kez girilmesini engeller.
        return str(value).strip().upper()

    @model_validator(mode="after")
    def _check_graduation_years(self) -> "StudentBase":
        """Mezuniyet yıllarının kayıt yılıyla tutarlı olduğunu doğrular."""
        # Öğrenci kayıt olduğu yıldan önce mezun olamaz.
        if self.actual_graduation_year is not None and self.actual_graduation_year < self.enrollment_year:
            raise ValueError(
                f"Gerçek mezuniyet yılı ({self.actual_graduation_year}) kayıt yılından "
                f"({self.enrollment_year}) küçük olamaz."
            )
        if (
            self.expected_graduation_year is not None
            and self.expected_graduation_year < self.enrollment_year
        ):
            raise ValueError(
                f"Beklenen mezuniyet yılı ({self.expected_graduation_year}) kayıt yılından "
                f"({self.enrollment_year}) küçük olamaz."
            )
        return self


class StudentCreate(StudentBase):
    """Yeni öğrenci oluştururken kullanılan şema."""

    is_active: bool = True


class StudentUpdate(BaseModel):
    """Öğrenci güncellerken kullanılan şema; tüm alanlar isteğe bağlıdır."""

    student_number: Optional[str] = Field(default=None, min_length=1, max_length=50)
    first_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    gender: Optional[Gender] = None
    nationality: Optional[str] = Field(default=None, max_length=100)
    is_international: Optional[bool] = None
    scholarship_rate_percent: Optional[Decimal] = Field(
        default=None, ge=0, le=100, examples=[50.00]
    )
    enrollment_year: Optional[int] = Field(
        default=None, ge=MIN_ENROLLMENT_YEAR, le=MAX_ENROLLMENT_YEAR, examples=[2026]
    )
    current_status: Optional[StudentStatus] = None
    preparatory_school: Optional[bool] = None
    academic_program_id: Optional[int] = Field(default=None, gt=0, examples=[1])
    current_gpa: Optional[Decimal] = Field(default=None, ge=0, le=4, examples=[3.20])
    expected_graduation_year: Optional[int] = Field(
        default=None, ge=MIN_ENROLLMENT_YEAR, le=MAX_ENROLLMENT_YEAR
    )
    actual_graduation_year: Optional[int] = Field(
        default=None, ge=MIN_ENROLLMENT_YEAR, le=MAX_ENROLLMENT_YEAR
    )
    is_active: Optional[bool] = None

    @field_validator("student_number")
    @classmethod
    def _normalize_student_number(cls, value: Optional[str]) -> Optional[str]:
        """Öğrenci numarasını normalize eder."""
        return None if value is None else str(value).strip().upper()


class StudentResponse(StudentBase):
    """Öğrenci kaydının API cevabı."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# StudentAcademicRecord
# ---------------------------------------------------------------------------


class StudentAcademicRecordBase(BaseModel):
    """Dönemlik akademik kaydın ortak alanları."""

    academic_year: str = Field(
        ..., description="YYYY-YYYY biçiminde akademik yıl", examples=["2026-2027"]
    )
    semester: Semester

    registered_course_count: int = Field(default=0, ge=0, examples=[6])
    passed_course_count: int = Field(default=0, ge=0, examples=[5])
    failed_course_count: int = Field(default=0, ge=0, examples=[1])

    earned_credits: int = Field(default=0, ge=0, examples=[25])
    attempted_credits: int = Field(default=0, ge=0, examples=[30])

    # Dönem ve genel ortalamaya farklı örnekler verildi ki iki alanın
    # ayrı kavramlar olduğu dokümantasyondan anlaşılsın.
    semester_gpa: Optional[Decimal] = Field(default=None, ge=0, le=4, examples=[3.10])
    cumulative_gpa: Optional[Decimal] = Field(default=None, ge=0, le=4, examples=[2.75])

    registration_renewed: bool = True

    @field_validator("academic_year")
    @classmethod
    def _check_academic_year(cls, value: str) -> str:
        """Akademik yıl biçimini doğrular."""
        return validate_academic_year(value)

    @model_validator(mode="after")
    def _check_counts(self) -> "StudentAcademicRecordBase":
        """Ders ve kredi sayılarının mantıksal tutarlılığını doğrular."""
        # Geçilen + kalınan ders, alınan dersten fazla olamaz.
        total_result: int = self.passed_course_count + self.failed_course_count
        if total_result > self.registered_course_count:
            raise ValueError(
                f"Geçilen ({self.passed_course_count}) ve kalınan ({self.failed_course_count}) "
                f"ders sayısının toplamı, kayıtlı ders sayısını ({self.registered_course_count}) "
                "aşamaz."
            )

        # Kazanılan kredi, denenen krediyi aşamaz.
        if self.earned_credits > self.attempted_credits:
            raise ValueError(
                f"Kazanılan kredi ({self.earned_credits}), denenen krediyi "
                f"({self.attempted_credits}) aşamaz."
            )
        return self


class StudentAcademicRecordCreate(StudentAcademicRecordBase):
    """Yeni akademik kayıt oluştururken kullanılan şema."""

    pass


class StudentAcademicRecordUpdate(BaseModel):
    """Akademik kayıt güncellerken kullanılan şema; tüm alanlar isteğe bağlıdır."""

    academic_year: Optional[str] = Field(default=None, examples=["2026-2027"])
    semester: Optional[Semester] = None
    registered_course_count: Optional[int] = Field(default=None, ge=0, examples=[6])
    passed_course_count: Optional[int] = Field(default=None, ge=0, examples=[5])
    failed_course_count: Optional[int] = Field(default=None, ge=0, examples=[1])
    earned_credits: Optional[int] = Field(default=None, ge=0, examples=[25])
    attempted_credits: Optional[int] = Field(default=None, ge=0, examples=[30])
    semester_gpa: Optional[Decimal] = Field(default=None, ge=0, le=4, examples=[3.10])
    cumulative_gpa: Optional[Decimal] = Field(default=None, ge=0, le=4, examples=[2.75])
    registration_renewed: Optional[bool] = None

    @field_validator("academic_year")
    @classmethod
    def _check_academic_year(cls, value: Optional[str]) -> Optional[str]:
        """Akademik yıl biçimini doğrular."""
        return None if value is None else validate_academic_year(value)


class StudentAcademicRecordResponse(StudentAcademicRecordBase):
    """Akademik kaydın API cevabı."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    student_id: int
    created_at: datetime


# ---------------------------------------------------------------------------
# ProgramEnrollmentSnapshot
# ---------------------------------------------------------------------------


class ProgramSnapshotBase(BaseModel):
    """Program kayıt fotoğrafının ortak alanları."""

    academic_program_id: int = Field(..., gt=0, examples=[1])
    academic_year: str = Field(
        ..., description="YYYY-YYYY biçiminde akademik yıl", examples=["2025-2026"]
    )

    # Kontenjan sıfır olamaz; doluluk oranı hesabında payda olarak kullanılıyor.
    quota: int = Field(..., gt=0, examples=[80])
    enrolled_student_count: int = Field(default=0, ge=0, examples=[79])

    # Üç puan alanına da farklı örnek verildi: kendi taban puanımız, Türkiye ve
    # Ankara ortalamaları karşılaştırıldığında aradaki fark Swagger'da görülebilsin.
    minimum_admission_score: Optional[Decimal] = Field(default=None, ge=0, examples=[441.90])
    national_average_minimum_score: Optional[Decimal] = Field(
        default=None, ge=0, examples=[389.80]
    )
    ankara_average_minimum_score: Optional[Decimal] = Field(
        default=None, ge=0, examples=[406.20]
    )

    graduated_student_count: int = Field(default=0, ge=0, examples=[49])
    dropped_out_student_count: int = Field(default=0, ge=0, examples=[3])
    non_renewed_student_count: int = Field(default=0, ge=0, examples=[2])

    @field_validator("academic_year")
    @classmethod
    def _check_academic_year(cls, value: str) -> str:
        """Akademik yıl biçimini doğrular."""
        return validate_academic_year(value)


class ProgramSnapshotCreate(ProgramSnapshotBase):
    """Yeni snapshot oluştururken kullanılan şema."""

    pass


class ProgramSnapshotUpdate(BaseModel):
    """Snapshot güncellerken kullanılan şema; tüm alanlar isteğe bağlıdır."""

    academic_program_id: Optional[int] = Field(default=None, gt=0, examples=[1])
    academic_year: Optional[str] = Field(default=None, examples=["2025-2026"])
    quota: Optional[int] = Field(default=None, gt=0, examples=[80])
    enrolled_student_count: Optional[int] = Field(default=None, ge=0, examples=[79])
    minimum_admission_score: Optional[Decimal] = Field(default=None, ge=0, examples=[441.90])
    national_average_minimum_score: Optional[Decimal] = Field(
        default=None, ge=0, examples=[389.80]
    )
    ankara_average_minimum_score: Optional[Decimal] = Field(
        default=None, ge=0, examples=[406.20]
    )
    graduated_student_count: Optional[int] = Field(default=None, ge=0, examples=[49])
    dropped_out_student_count: Optional[int] = Field(default=None, ge=0, examples=[3])
    non_renewed_student_count: Optional[int] = Field(default=None, ge=0, examples=[2])

    @field_validator("academic_year")
    @classmethod
    def _check_academic_year(cls, value: Optional[str]) -> Optional[str]:
        """Akademik yıl biçimini doğrular."""
        return None if value is None else validate_academic_year(value)


class ProgramSnapshotResponse(ProgramSnapshotBase):
    """Snapshot kaydının API cevabı."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# ComparableUniversityProgram
# ---------------------------------------------------------------------------


class ComparableProgramBase(BaseModel):
    """Karşılaştırma programının ortak alanları."""

    university_name: str = Field(
        ..., min_length=2, max_length=255, examples=["Orta Doğu Teknik Üniversitesi"]
    )
    program_name: str = Field(
        ..., min_length=2, max_length=255, examples=["Computer Engineering"]
    )
    city: Optional[str] = Field(default=None, max_length=100, examples=["Ankara"])
    academic_year: str = Field(
        ..., description="YYYY-YYYY biçiminde akademik yıl", examples=["2025-2026"]
    )

    quota: int = Field(..., gt=0, examples=[130])
    enrolled_student_count: int = Field(default=0, ge=0, examples=[130])

    # Doluluk oranı %100'ü aşabilir (ek kontenjan), bu yüzden üst sınır geniş tutuldu.
    occupancy_rate: Optional[Decimal] = Field(default=None, ge=0, le=1000, examples=[100.00])
    minimum_admission_score: Optional[Decimal] = Field(default=None, ge=0, examples=[498.40])

    is_competitor: bool = False

    @field_validator("academic_year")
    @classmethod
    def _check_academic_year(cls, value: str) -> str:
        """Akademik yıl biçimini doğrular."""
        return validate_academic_year(value)


class ComparableProgramCreate(ComparableProgramBase):
    """Yeni karşılaştırma kaydı oluştururken kullanılan şema."""

    pass


class ComparableProgramUpdate(BaseModel):
    """Karşılaştırma kaydı güncellerken kullanılan şema."""

    university_name: Optional[str] = Field(
        default=None, min_length=2, max_length=255, examples=["Hacettepe Üniversitesi"]
    )
    program_name: Optional[str] = Field(
        default=None, min_length=2, max_length=255, examples=["Computer Engineering"]
    )
    city: Optional[str] = Field(default=None, max_length=100, examples=["Ankara"])
    academic_year: Optional[str] = Field(default=None, examples=["2025-2026"])
    quota: Optional[int] = Field(default=None, gt=0, examples=[120])
    enrolled_student_count: Optional[int] = Field(default=None, ge=0, examples=[118])
    occupancy_rate: Optional[Decimal] = Field(default=None, ge=0, le=1000, examples=[98.33])
    minimum_admission_score: Optional[Decimal] = Field(default=None, ge=0, examples=[471.25])
    is_competitor: Optional[bool] = None

    @field_validator("academic_year")
    @classmethod
    def _check_academic_year(cls, value: Optional[str]) -> Optional[str]:
        """Akademik yıl biçimini doğrular."""
        return None if value is None else validate_academic_year(value)


class ComparableProgramResponse(ComparableProgramBase):
    """Karşılaştırma kaydının API cevabı."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
