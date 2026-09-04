"""Manuel girişe açık metriklerin kontrollü kayıt defteri.

İstemci serbest metrik adı veya doğrulama kuralı gönderemez. Yeni bir metrik
bu dosyaya eklendiğinde API tanımı, form davranışı ve sunucu doğrulaması aynı
kaynaktan beslenir.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Final, Optional


@dataclass(frozen=True)
class ManualMetricDefinition:
    key: str
    label: str
    screen_key: str
    value_type: str
    unit: str
    allowed_scopes: tuple[str, ...]
    academic_year_required: bool = True
    chartable: bool = True
    minimum: Optional[Decimal] = Decimal("0")
    maximum: Optional[Decimal] = None
    integer_only: bool = False
    source_label: str = "Manuel veri"

    def public_dict(self) -> dict:
        data = asdict(self)
        data["allowed_scopes"] = list(self.allowed_scopes)
        data["minimum"] = str(self.minimum) if self.minimum is not None else None
        data["maximum"] = str(self.maximum) if self.maximum is not None else None
        return data


ALL_SCOPES: Final = ("university", "faculty", "department", "program")
UNIVERSITY_ONLY: Final = ("university",)
UNIVERSITY_FACULTY: Final = ("university", "faculty")
PROGRAM_ONLY: Final = ("program",)

MANUAL_METRIC_REGISTRY: Final[dict[str, ManualMetricDefinition]] = {
    "citation_count": ManualMetricDefinition(
        key="citation_count", label="Atıf Sayısı", screen_key="academic",
        value_type="number", unit="adet", allowed_scopes=ALL_SCOPES,
        integer_only=True,
    ),
    "project_count": ManualMetricDefinition(
        key="project_count", label="Proje Sayısı", screen_key="academic",
        value_type="number", unit="adet", allowed_scopes=ALL_SCOPES,
        integer_only=True,
    ),
    "patent_count": ManualMetricDefinition(
        key="patent_count", label="Patent Sayısı", screen_key="academic",
        value_type="number", unit="adet", allowed_scopes=ALL_SCOPES,
        integer_only=True,
    ),
    "classroom_utilization_rate": ManualMetricDefinition(
        key="classroom_utilization_rate", label="Derslik Kullanım Oranı",
        screen_key="infrastructure", value_type="number", unit="%",
        allowed_scopes=ALL_SCOPES, maximum=Decimal("100"),
    ),
    "laboratory_utilization_rate": ManualMetricDefinition(
        key="laboratory_utilization_rate", label="Laboratuvar Kullanım Oranı",
        screen_key="infrastructure", value_type="number", unit="%",
        allowed_scopes=ALL_SCOPES, maximum=Decimal("100"),
    ),
    "total_income": ManualMetricDefinition(
        key="total_income", label="Toplam Gelir", screen_key="finance",
        value_type="number", unit="milyon USD", allowed_scopes=ALL_SCOPES,
    ),
    "total_expense": ManualMetricDefinition(
        key="total_expense", label="Toplam Gider", screen_key="finance",
        value_type="number", unit="milyon USD", allowed_scopes=ALL_SCOPES,
    ),
    "personnel_cost": ManualMetricDefinition(
        key="personnel_cost", label="Personel Gideri", screen_key="finance",
        value_type="number", unit="milyon USD", allowed_scopes=ALL_SCOPES,
    ),
    # Program bazlı akademik başarı. Üst kapsamlar bu satırlardan
    # ağırlıklı olarak türetilir; ayrı bir sentetik fakülte toplamı yoktur.
    "measured_student_count": ManualMetricDefinition(
        key="measured_student_count", label="Ölçülen Öğrenci",
        screen_key="academic_success", value_type="number", unit="öğrenci",
        allowed_scopes=PROGRAM_ONLY, integer_only=True,
    ),
    "course_pass_rate": ManualMetricDefinition(
        key="course_pass_rate", label="Ders Geçme Oranı",
        screen_key="academic_success", value_type="number", unit="%",
        allowed_scopes=PROGRAM_ONLY, maximum=Decimal("100"),
    ),
    "average_success_score": ManualMetricDefinition(
        key="average_success_score", label="Ortalama Başarı Puanı",
        screen_key="academic_success", value_type="number", unit="puan",
        allowed_scopes=PROGRAM_ONLY, maximum=Decimal("100"),
    ),
    "dropout_rate": ManualMetricDefinition(
        key="dropout_rate", label="Öğrenci Kaybı Oranı",
        screen_key="academic_success", value_type="number", unit="%",
        allowed_scopes=PROGRAM_ONLY, maximum=Decimal("100"),
    ),
    "graduation_rate": ManualMetricDefinition(
        key="graduation_rate", label="Mezuniyet Oranı",
        screen_key="academic_success", value_type="number", unit="%",
        allowed_scopes=PROGRAM_ONLY, maximum=Decimal("100"),
    ),
    "graduate_count": ManualMetricDefinition(
        key="graduate_count", label="Mezun Sayısı",
        screen_key="academic_success", value_type="number", unit="adet",
        allowed_scopes=PROGRAM_ONLY, integer_only=True,
    ),
    # Personel kimliği uploaded_metric_records.academic_staff_id alanında
    # korunur. Kapsam alanı yalnızca personelin gerçek bölümünü taşır.
    "community_engagement_score": ManualMetricDefinition(
        key="community_engagement_score", label="Toplumsal Katkı Puanı",
        screen_key="academic", value_type="number", unit="puan",
        allowed_scopes=ALL_SCOPES, maximum=Decimal("10"),
    ),
    # Sanayi iş birliği fakülte seviyesinde ölçülür; kurum endeksi
    # mevcut fakülte satırlarından toplanır.
    "industry_active_partnerships": ManualMetricDefinition(
        key="industry_active_partnerships", label="Aktif Sanayi İş Birliği",
        screen_key="engagement", value_type="number", unit="adet",
        allowed_scopes=("faculty",), integer_only=True,
    ),
    "industry_joint_projects": ManualMetricDefinition(
        key="industry_joint_projects", label="Sanayi Ortak Projesi",
        screen_key="engagement", value_type="number", unit="adet",
        allowed_scopes=("faculty",), integer_only=True,
    ),
    "industry_funded_research_musd": ManualMetricDefinition(
        key="industry_funded_research_musd", label="Sanayi Destekli Araştırma",
        screen_key="engagement", value_type="number", unit="milyon USD",
        allowed_scopes=("faculty",),
    ),
    "industry_intern_students": ManualMetricDefinition(
        key="industry_intern_students", label="Sanayide Staj Yapan Öğrenci",
        screen_key="engagement", value_type="number", unit="kişi",
        allowed_scopes=("faculty",), integer_only=True,
    ),
    "industry_signed_protocols": ManualMetricDefinition(
        key="industry_signed_protocols", label="İmzalanan Sanayi Protokolü",
        screen_key="engagement", value_type="number", unit="adet",
        allowed_scopes=("faculty",), integer_only=True,
    ),
    # Bölgesel katkı kurum geneli bir göstergedir; alt kapsama devredilmez.
    "regional_graduates_employed": ManualMetricDefinition(
        key="regional_graduates_employed", label="Bölgede İstihdam Edilen Mezun",
        screen_key="engagement", value_type="number", unit="kişi",
        allowed_scopes=UNIVERSITY_ONLY, integer_only=True,
    ),
    "regional_public_projects": ManualMetricDefinition(
        key="regional_public_projects", label="Yerel Kamu Projesi",
        screen_key="engagement", value_type="number", unit="adet",
        allowed_scopes=UNIVERSITY_ONLY, integer_only=True,
    ),
    "municipality_partnerships": ManualMetricDefinition(
        key="municipality_partnerships", label="Belediye İş Birliği",
        screen_key="engagement", value_type="number", unit="adet",
        allowed_scopes=UNIVERSITY_ONLY, integer_only=True,
    ),
    "community_service_hours": ManualMetricDefinition(
        key="community_service_hours", label="Toplum Hizmeti Saati",
        screen_key="engagement", value_type="number", unit="saat",
        allowed_scopes=UNIVERSITY_ONLY, integer_only=True,
    ),
    "regional_sme_collaborations": ManualMetricDefinition(
        key="regional_sme_collaborations", label="Bölgesel KOBİ İş Birliği",
        screen_key="engagement", value_type="number", unit="adet",
        allowed_scopes=UNIVERSITY_ONLY, integer_only=True,
    ),
    "public_events_hosted": ManualMetricDefinition(
        key="public_events_hosted", label="Halka Açık Etkinlik",
        screen_key="engagement", value_type="number", unit="adet",
        allowed_scopes=UNIVERSITY_ONLY, integer_only=True,
    ),
    "facility_occupancy_rate": ManualMetricDefinition(
        key="facility_occupancy_rate", label="Mekân Doluluk Oranı",
        screen_key="infrastructure", value_type="number", unit="%",
        allowed_scopes=UNIVERSITY_FACULTY, maximum=Decimal("100"),
    ),
    "facility_area_m2": ManualMetricDefinition(
        key="facility_area_m2", label="Toplam Mekân Alanı",
        screen_key="infrastructure", value_type="number", unit="m²",
        allowed_scopes=UNIVERSITY_FACULTY,
    ),
    # Analitik mali kalemler kurum seviyesindedir. Muhasebe kaydı değil,
    # finans ekranındaki yönetimsel dağılımı beslerler.
    "gross_tuition_revenue": ManualMetricDefinition(
        key="gross_tuition_revenue", label="Öğrenim Ücreti Geliri (Brüt)",
        screen_key="finance", value_type="number", unit="milyon USD",
        allowed_scopes=UNIVERSITY_ONLY,
    ),
    "research_revenue": ManualMetricDefinition(
        key="research_revenue", label="Araştırma Geliri",
        screen_key="finance", value_type="number", unit="milyon USD",
        allowed_scopes=UNIVERSITY_ONLY,
    ),
    "other_revenue": ManualMetricDefinition(
        key="other_revenue", label="Diğer Gelirler", screen_key="finance",
        value_type="number", unit="milyon USD", allowed_scopes=UNIVERSITY_ONLY,
    ),
    "scholarship_expense": ManualMetricDefinition(
        key="scholarship_expense", label="Burs Giderleri", screen_key="finance",
        value_type="number", unit="milyon USD", allowed_scopes=UNIVERSITY_ONLY,
    ),
    "academic_personnel_expense": ManualMetricDefinition(
        key="academic_personnel_expense", label="Akademik Personel Giderleri",
        screen_key="finance", value_type="number", unit="milyon USD",
        allowed_scopes=UNIVERSITY_ONLY,
    ),
    "administrative_personnel_expense": ManualMetricDefinition(
        key="administrative_personnel_expense", label="İdari Personel Giderleri",
        screen_key="finance", value_type="number", unit="milyon USD",
        allowed_scopes=UNIVERSITY_ONLY,
    ),
    "education_operating_expense": ManualMetricDefinition(
        key="education_operating_expense", label="Eğitim ve İşletme Giderleri",
        screen_key="finance", value_type="number", unit="milyon USD",
        allowed_scopes=UNIVERSITY_ONLY,
    ),
    "research_laboratory_expense": ManualMetricDefinition(
        key="research_laboratory_expense", label="Araştırma ve Laboratuvar Giderleri",
        screen_key="finance", value_type="number", unit="milyon USD",
        allowed_scopes=UNIVERSITY_ONLY,
    ),
    "facility_infrastructure_expense": ManualMetricDefinition(
        key="facility_infrastructure_expense", label="Tesis ve Altyapı Giderleri",
        screen_key="finance", value_type="number", unit="milyon USD",
        allowed_scopes=UNIVERSITY_ONLY,
    ),
    "technology_expense": ManualMetricDefinition(
        key="technology_expense", label="Teknoloji Giderleri", screen_key="finance",
        value_type="number", unit="milyon USD", allowed_scopes=UNIVERSITY_ONLY,
    ),
    "other_operating_expense": ManualMetricDefinition(
        key="other_operating_expense", label="Diğer İşletme Giderleri",
        screen_key="finance", value_type="number", unit="milyon USD",
        allowed_scopes=UNIVERSITY_ONLY,
    ),
    # Öğrenci düzeyinde yanıt veya kişi kaydı tutulmaz. Ders anketi ve
    # istihdam analitiği program düzeyinde toplulaştırılır; üst kapsamlar
    # bu satırları uygun payda ile yeniden hesaplar.
    "average_course_evaluation_score": ManualMetricDefinition(
        key="average_course_evaluation_score", label="Ortalama Ders Değerlendirme Puanı",
        screen_key="course_survey", value_type="number", unit="/5",
        allowed_scopes=PROGRAM_ONLY, maximum=Decimal("5"),
    ),
    "course_satisfaction_rate": ManualMetricDefinition(
        key="course_satisfaction_rate", label="Ders Memnuniyet Oranı",
        screen_key="course_survey", value_type="number", unit="%",
        allowed_scopes=PROGRAM_ONLY, maximum=Decimal("100"),
    ),
    "instructor_satisfaction_rate": ManualMetricDefinition(
        key="instructor_satisfaction_rate", label="Öğretim Elemanı Memnuniyeti",
        screen_key="course_survey", value_type="number", unit="%",
        allowed_scopes=PROGRAM_ONLY, maximum=Decimal("100"),
    ),
    "course_survey_response_rate": ManualMetricDefinition(
        key="course_survey_response_rate", label="Ders Anketi Yanıt Oranı",
        screen_key="course_survey", value_type="number", unit="%",
        allowed_scopes=PROGRAM_ONLY, maximum=Decimal("100"),
    ),
    "course_evaluation_count": ManualMetricDefinition(
        key="course_evaluation_count", label="Ders Anketi Katılımcısı",
        screen_key="course_survey", value_type="number", unit="kişi",
        allowed_scopes=PROGRAM_ONLY, integer_only=True,
    ),
    "graduate_employment_rate": ManualMetricDefinition(
        key="graduate_employment_rate", label="Mezun İstihdam Oranı",
        screen_key="student_employment", value_type="number", unit="%",
        allowed_scopes=PROGRAM_ONLY, maximum=Decimal("100"),
    ),
    "employment_within_6_months_rate": ManualMetricDefinition(
        key="employment_within_6_months_rate", label="6 Ay İçinde İstihdam",
        screen_key="student_employment", value_type="number", unit="%",
        allowed_scopes=PROGRAM_ONLY, maximum=Decimal("100"),
    ),
    "employment_within_12_months_rate": ManualMetricDefinition(
        key="employment_within_12_months_rate", label="12 Ay İçinde İstihdam",
        screen_key="student_employment", value_type="number", unit="%",
        allowed_scopes=PROGRAM_ONLY, maximum=Decimal("100"),
    ),
    "sector_alignment_rate": ManualMetricDefinition(
        key="sector_alignment_rate", label="Alanıyla Uyumlu İstihdam",
        screen_key="student_employment", value_type="number", unit="%",
        allowed_scopes=PROGRAM_ONLY, maximum=Decimal("100"),
    ),
    # Dergi çeyreklik sınıfı ve yayın-bazlı atıf granülerliği kaynakta yoktur;
    # bu iki alan yalnızca açıkça sentetik analitik tahmin olarak desteklenir.
    "q1_publication_rate": ManualMetricDefinition(
        key="q1_publication_rate", label="Q1 Yayın Oranı (Tahmin)",
        screen_key="publication_quality", value_type="number", unit="%",
        allowed_scopes=UNIVERSITY_FACULTY, maximum=Decimal("100"),
    ),
    "estimated_h_index": ManualMetricDefinition(
        key="estimated_h_index", label="H-indeks (Analitik Tahmin)",
        screen_key="publication_quality", value_type="number", unit="puan",
        allowed_scopes=UNIVERSITY_FACULTY, integer_only=True,
    ),
    # Yetkili 80 derslik/laboratuvar satırına dokunmayan kurum düzeyi
    # tamamlayıcı mekân envanteri.
    "office_count": ManualMetricDefinition(
        key="office_count", label="Ofis Sayısı", screen_key="physical_supplementary",
        value_type="number", unit="adet", allowed_scopes=UNIVERSITY_ONLY,
        integer_only=True,
    ),
    "office_area_m2": ManualMetricDefinition(
        key="office_area_m2", label="Ofis Alanı", screen_key="physical_supplementary",
        value_type="number", unit="m²", allowed_scopes=UNIVERSITY_ONLY,
    ),
    "library_count": ManualMetricDefinition(
        key="library_count", label="Kütüphane Sayısı", screen_key="physical_supplementary",
        value_type="number", unit="adet", allowed_scopes=UNIVERSITY_ONLY,
        integer_only=True,
    ),
    "library_area_m2": ManualMetricDefinition(
        key="library_area_m2", label="Kütüphane Alanı", screen_key="physical_supplementary",
        value_type="number", unit="m²", allowed_scopes=UNIVERSITY_ONLY,
    ),
    "common_area_count": ManualMetricDefinition(
        key="common_area_count", label="Ortak Alan Sayısı", screen_key="physical_supplementary",
        value_type="number", unit="adet", allowed_scopes=UNIVERSITY_ONLY,
        integer_only=True,
    ),
    "common_area_m2": ManualMetricDefinition(
        key="common_area_m2", label="Ortak Alan", screen_key="physical_supplementary",
        value_type="number", unit="m²", allowed_scopes=UNIVERSITY_ONLY,
    ),
    "study_area_capacity": ManualMetricDefinition(
        key="study_area_capacity", label="Çalışma Alanı Kapasitesi",
        screen_key="physical_supplementary", value_type="number", unit="kişi",
        allowed_scopes=UNIVERSITY_ONLY, integer_only=True,
    ),
    # 2025-2026 yetkili tarife ayrı kalır; bu anahtar yalnızca geçmişe
    # dönük %50 burslu program tahminlerini taşır.
    "historical_half_tuition_fee_estimate": ManualMetricDefinition(
        key="historical_half_tuition_fee_estimate",
        label="Geçmiş %50 Burslu Ücret Tahmini", screen_key="tuition",
        value_type="number", unit="TRY", allowed_scopes=PROGRAM_ONLY,
    ),
}


def get_definition(metric_key: str) -> ManualMetricDefinition:
    """Bilinmeyen anahtar için HTTP'ten bağımsız bir KeyError üretir."""
    return MANUAL_METRIC_REGISTRY[metric_key]


def list_definitions(
    *, screen_key: Optional[str] = None, scope_type: Optional[str] = None
) -> list[ManualMetricDefinition]:
    definitions = list(MANUAL_METRIC_REGISTRY.values())
    if screen_key:
        definitions = [d for d in definitions if d.screen_key == screen_key]
    if scope_type:
        definitions = [d for d in definitions if scope_type in d.allowed_scopes]
    return definitions
