"""Veri entegrasyonu (import) işlemleri için Pydantic v2 şemaları."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ResourceType(str, Enum):
    """Toplu aktarım yapılabilen kaynak türleri."""

    # Enum kullanmamızın sebebi: FastAPI bu değerleri path parametresinde otomatik doğrular.
    # Listede olmayan bir değer gelirse endpoint'e hiç girilmeden 422 döner.
    # Modül 1 kaynakları
    FACULTIES = "faculties"
    DEPARTMENTS = "departments"
    PROGRAMS = "programs"
    ADMINISTRATIVE_UNITS = "administrative-units"

    # Modül 2 kaynakları (öğrenci analitiği)
    STUDENTS = "students"
    STUDENT_ACADEMIC_RECORDS = "student-academic-records"
    PROGRAM_ENROLLMENT_SNAPSHOTS = "program-enrollment-snapshots"
    COMPARABLE_UNIVERSITY_PROGRAMS = "comparable-university-programs"

    # Modül 10 kaynakları (THE / QS / YÖK değerlendirme)
    INSTITUTIONAL_METRIC_VALUES = "institutional-metric-values"
    BENCHMARK_INSTITUTIONS = "benchmark-institutions"
    BENCHMARK_METRIC_VALUES = "benchmark-metric-values"

    # Alt çizgili takma adlar: dokümantasyonda bu yazım da geçtiği için
    # her iki biçim de kabul edilir. Kanonik isimler yukarıdaki tireli olanlardır.
    INSTITUTIONAL_METRIC_VALUES_ALIAS = "institutional_metric_values"
    BENCHMARK_INSTITUTIONS_ALIAS = "benchmark_institutions"
    BENCHMARK_METRIC_VALUES_ALIAS = "benchmark_metric_values"


class RowIssue(BaseModel):
    """Tek bir satırda tespit edilen hata veya çakışmayı ifade eder."""

    # Kullanıcının dosyayı düzeltebilmesi için hangi satır, hangi alan ve
    # hangi değerin sorunlu olduğunu tek tek bildiriyoruz.
    row: int = Field(..., description="Dosyadaki satır numarası (başlık satırı hariç, 1'den başlar)")
    field: Optional[str] = Field(default=None, description="Sorunlu alan adı")
    value: Optional[str] = Field(default=None, description="Gönderilen değer")
    message: str = Field(..., description="Türkçe hata açıklaması")
    issue_type: str = Field(default="error", description="error | conflict")


class ImportResult(BaseModel):
    """İçe aktarma veya ön izleme sonucunda dönen özet rapor."""

    resource_type: str
    file_name: str
    file_type: str
    preview: bool

    # Sayısal özet. İlişki şu şekildedir:
    #   total_rows    = valid_rows + error_rows
    #   imported_rows = valid_rows - conflict_rows   (preview modunda her zaman 0)
    total_rows: int = 0
    valid_rows: int = 0
    imported_rows: int = 0
    error_rows: int = 0
    conflict_rows: int = 0

    # preview  -> ön izleme, yazma yapılmadı
    # completed-> tüm satırlar aktarıldı
    # partial  -> bir kısmı aktarıldı, bir kısmı atlandı
    # skipped  -> hiçbir satır aktarılmadı (hata/çakışma), sistemsel sorun yok
    # failed   -> dosya okunamadı veya veritabanı hatası oluştu
    status: str = Field(
        default="completed",
        description="preview | completed | partial | skipped | failed",
    )

    # Ön izlemede kullanıcıya "veri doğru okundu mu" diye göstermek için ilk 10 geçerli kayıt.
    preview_rows: List[Dict[str, Any]] = Field(default_factory=list)

    errors: List[RowIssue] = Field(default_factory=list)

    # Oluşturulan ImportJob kaydının id'si; kullanıcı sonradan bu işi sorgulayabilir.
    job_id: Optional[int] = None
    message: Optional[str] = None


class ImportJobResponse(BaseModel):
    """Geçmiş import işlerinin listelenmesinde kullanılan şema."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    resource_type: str
    file_name: str
    file_type: str
    preview: bool
    total_rows: int
    valid_rows: int
    imported_rows: int
    error_rows: int
    conflict_rows: int
    status: str
    message: Optional[str] = None
    created_at: datetime
