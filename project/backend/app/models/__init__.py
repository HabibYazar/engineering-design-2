"""Veritabanı modellerinin toplandığı paket."""

# Modelleri burada import etmemizin iki sebebi var:
# 1) Base.metadata tabloları tanısın ve create_all ile oluşturabilsin.
# 2) Diğer dosyalarda "from app.models import Faculty" şeklinde kısa kullanım sağlansın.
from app.models.academic_program import AcademicProgram
from app.models.academic_staff import AcademicStaff
from app.models.academic_success import AcademicSuccessRecord
from app.models.administrative_unit import AdministrativeUnit
from app.models.benchmark_institution import BenchmarkInstitution
from app.models.benchmark_metric_value import BenchmarkMetricValue
from app.models.comparable_university_program import ComparableUniversityProgram
from app.models.department import Department
from app.models.curriculum import CurriculumCourse
from app.models.curriculum_canonical import CurriculumCanonicalCourse
from app.models.university_headcount import UniversityStudentHeadcount
from app.models.university_profile import UniversityProfile
from app.models.tuition_fee import CompetitorTuitionFee, ProgramTuitionFee
from app.models.staff_course import AcademicStaffCourse
from app.models.student_demographic import StudentDemographicCount
from app.models.data_conflict import DataSourceConflict
from app.models.yks_placement import YksPlacementRecord
from app.models.yok_atlas_metric import YokAtlasBenchmarkMetric
from app.models.program_allocation import (
    ProgramAcademicStaffAllocation,
    ProgramFacilityAllocation,
)
from app.models.engagement import (
    IndustryCollaborationRecord,
    RegionalContributionRecord,
)
from app.models.dimension_assessment import DimensionAssessment
from app.models.evaluation_dimension import EvaluationDimension
from app.models.evaluation_framework import EvaluationFramework
from app.models.evaluation_indicator import EvaluationIndicator
from app.models.faculty import Faculty
from app.models.financial_period import (
    DepartmentBudget,
    FinancialEntry,
    FinancialPeriod,
)
from app.models.framework_assessment import FrameworkAssessment
from app.models.import_job import ImportJob
from app.models.institutional_metric_value import InstitutionalMetricValue
from app.models.manual_metric_entry import ManualMetricEntry, ManualMetricEntryAudit
from app.models.uploaded_data_source import UploadedDataSource, UploadedMetricRecord
from app.models.physical_facility import PhysicalFacility
from app.models.program_enrollment_snapshot import ProgramEnrollmentSnapshot
from app.models.scenario import Scenario
from app.models.scenario_baseline import ScenarioBaseline
from app.models.scenario_input import ScenarioInput
from app.models.scenario_result import ScenarioResult
from app.models.student import Student
from app.models.strategic_kpi import KpiFacultyValue, StrategicKpi
from app.models.student_academic_record import StudentAcademicRecord
from app.models.system_user import SystemUser

__all__ = [
    # Modül 1 - Üniversite yapısı
    "Faculty",
    "Department",
    "AcademicProgram",
    "AdministrativeUnit",
    # Modül 13 - Veri entegrasyonu
    "ImportJob",
    # Modül 9 - Senaryo analizi
    "ScenarioBaseline",
    "Scenario",
    "ScenarioInput",
    "ScenarioResult",
    # Modül 2 - Öğrenci analitiği
    "Student",
    "StudentAcademicRecord",
    "ProgramEnrollmentSnapshot",
    "ComparableUniversityProgram",
    # Modül 10 - THE / QS / YÖK değerlendirme ve izleme
    "EvaluationFramework",
    "EvaluationDimension",
    "EvaluationIndicator",
    "InstitutionalMetricValue",
    "ManualMetricEntry",
    "ManualMetricEntryAudit",
    "UploadedDataSource",
    "UploadedMetricRecord",
    "FrameworkAssessment",
    "DimensionAssessment",
    "BenchmarkInstitution",
    "BenchmarkMetricValue",
    # Modül 4 - Akademik personel (Eda)
    "AcademicStaff",
    # Modül 5 - Fiziksel kaynaklar (Eda)
    "PhysicalFacility",
    # Modül 14 - Kullanıcı ve yetkilendirme (Eda)
    "SystemUser",
    # Modül 6 - Finansal analiz (Halil)
    "FinancialPeriod",
    "FinancialEntry",
    "DepartmentBudget",
    # Modül 8 - Performans yönetimi (Halil)
    "StrategicKpi",
    "KpiFacultyValue",
    # Akademik başarı analizi
    "AcademicSuccessRecord",
    # Sanayi iş birliği ve bölgesel katkı
    "IndustryCollaborationRecord",
    "RegionalContributionRecord",
    # Program düzeyinde kaynak tahsisi
    "ProgramAcademicStaffAllocation",
    "ProgramFacilityAllocation",
    # Ek gerçek veri kümeleri (data/ekdata)
    "YksPlacementRecord",       # ÖSYM yerleştirme, kaynak granülerliğinde
    "YokAtlasBenchmarkMetric",  # Ankara YÖK Atlas ikincil karşılaştırma metrikleri
    "CurriculumCourse",         # müfredat / ders kataloğu
    "DataSourceConflict",       # kaynaklar arası çakışma kaydı
    "AcademicStaffCourse",      # akademisyenin verdiği dersler (yıl bazında)
    "StudentDemographicCount",  # kapsam+dönem bazlı öğrenci demografisi
    "CurriculumCanonicalCourse",  # temizlenmiş/tekilleştirilmiş müfredat
    "UniversityStudentHeadcount",  # YÖK kayıtlı öğrenci sayıları (üniversite düzeyi)
    "UniversityProfile",  # rakip analizi için kurum başına yapısal büyüklükler
    "ProgramTuitionFee",  # kendi programlarımızın eğitim ücreti
    "CompetitorTuitionFee",  # rakip kurumların eğitim ücretleri
]
