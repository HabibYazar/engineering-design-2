"""Bağımsız demo giriş noktası — Modül 1 (Temel Veri) + Modül 13 (Veri Entegrasyonu).

Bu dosya YALNIZCA module_views klasörü içindeki modül kopyalarını kullanır.
backend/app altındaki orijinal dosyalardan hiçbir şey import edilmez; ana backend'e
hiçbir bağımlılık yoktur. GitHub'dan sadece module_views klasörü indirilse bile demo
çalışır.

Çalıştırma:
    python main.py
    uvicorn main:app --reload

Adres:
    http://127.0.0.1:8000/docs

--------------------------------------------------------------------------------
NEDEN BİR UYUMLULUK KATMANI GEREKİYOR?
--------------------------------------------------------------------------------
module_views içindeki dosyalar ana projeden birebir kopyalandığı için import yolları
hâlâ "app.database", "app.models", "app.schemas", "app.services" biçimindedir. Bu
dosyaların İÇERİĞİNİ değiştirmek yasak olduğundan, burada sys.modules üzerinde SANAL
bir "app" paketi kuruyoruz ve alt modüllerini module_views içindeki kopyalara
yönlendiriyoruz. Böylece kaynak kodların iş mantığına dokunmadan çalışmaları sağlanıyor.

--------------------------------------------------------------------------------
BU DOSYADA ÜRETİLEN EKSİK ORTAK BİLEŞENLER
--------------------------------------------------------------------------------
1) app.database eşdeğeri  : Base, engine, SessionLocal, get_db, init_db
                            (module_views içinde bir database.py kopyası bulunmuyor)
2) Health endpoint         : module_views içinde health.py kopyası bulunmuyor,
                            bu yüzden /health burada tanımlandı
3) validate_academic_year  : Modül 13'ün doğrulayıcısı bu yardımcıyı
                            app.schemas.students'tan istiyor; Modül 2'ye bağımlılık
                            oluşturmamak için burada yeniden üretildi
4) Yer tutucu tablolar     : Modül 13'ün import_validators.py dosyası 12 model sınıfı
                            import ediyor ve Modül 1'in academic_program.py kopyası
                            Student / ProgramEnrollmentSnapshot ilişkileri tanımlıyor.
                            Bu 8 sınıf yalnızca TABLO TANIMI olarak üretildi; hiçbir
                            iş mantığı, şema, servis veya endpoint içermezler ve
                            demoda hiçbir endpoint tarafından kullanılmazlar.
"""

import sys
import types
from decimal import Decimal
from importlib import util as importlib_util
from pathlib import Path
from typing import Any, Dict, Generator, List, Tuple

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    func,
    inspect,
)
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker

# ===========================================================================
# 0) YOLLAR
# ===========================================================================

BASE_DIR: Path = Path(__file__).resolve().parent
MODULE_01_DIR: Path = BASE_DIR / "module_01_core_data"
MODULE_13_DIR: Path = BASE_DIR / "module_13_data_integration"
SAMPLE_DATA_DIR: Path = MODULE_13_DIR / "sample_data"

# Veritabanı module_views klasörünün içinde oluşturulur.
DB_PATH: Path = BASE_DIR / "demo_module_views.db"
DATABASE_URL: str = f"sqlite:///{DB_PATH}"


def _require_dir(path: Path, label: str) -> None:
    """Gerekli klasörün varlığını kontrol eder, yoksa anlaşılır hata verir."""
    if not path.is_dir():
        raise RuntimeError(
            f"{label} klasörü bulunamadı: {path}\n"
            "Bu demo module_views klasörünün içinden çalıştırılmalıdır."
        )


_require_dir(MODULE_01_DIR, "Modül 1")
_require_dir(MODULE_13_DIR, "Modül 13")


# ===========================================================================
# 1) ORTAK VERİTABANI ALTYAPISI  (app.database eşdeğeri)
# ===========================================================================

# SQLite bağlantısı, FastAPI'nin farklı thread'lerinden kullanılabilsin diye
# check_same_thread kontrolü kapatılıyor (ana projedeki davranışın aynısı).
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    """Tüm demo modellerinin türeyeceği temel sınıf."""

    pass


def get_db() -> Generator[Session, None, None]:
    """İstek başına veritabanı oturumu açar ve iş bitince kapatır."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Tanımlı tüm modellere göre tabloları oluşturur."""
    # create_all var olan tabloları tekrar oluşturmaz; her açılışta güvenle çağrılabilir.
    Base.metadata.create_all(bind=engine)


# ===========================================================================
# 2) EKSİK YARDIMCI: validate_academic_year
# ===========================================================================
# Modül 13'ün import_validators.py dosyası bu fonksiyonu app.schemas.students'tan
# alıyor. Modül 2'ye bağımlılık oluşturmamak için burada üretildi; davranışı
# orijinaliyle aynıdır (YYYY-YYYY biçimi ve ardışık yıl kontrolü).

import re  # noqa: E402  (yardımcı fonksiyonun hemen yanında dursun)

ACADEMIC_YEAR_PATTERN = re.compile(r"^\d{4}-\d{4}$")
MIN_ACADEMIC_YEAR: int = 1950
MAX_ACADEMIC_YEAR: int = 2100


def validate_academic_year(value: str) -> str:
    """Akademik yıl biçimini (YYYY-YYYY) ve yılların ardışıklığını doğrular."""
    text: str = str(value).strip()
    if not ACADEMIC_YEAR_PATTERN.match(text):
        raise ValueError(
            f"Akademik yıl 'YYYY-YYYY' biçiminde olmalıdır (örnek: 2024-2025). "
            f"Gelen değer: '{value}'."
        )

    start_year, end_year = (int(part) for part in text.split("-"))
    if end_year != start_year + 1:
        raise ValueError(
            f"Akademik yılın ikinci kısmı birincisinden bir fazla olmalıdır "
            f"(örnek: 2024-2025). Gelen değer: '{value}'."
        )
    if not (MIN_ACADEMIC_YEAR <= start_year <= MAX_ACADEMIC_YEAR):
        raise ValueError(
            f"Akademik yıl {MIN_ACADEMIC_YEAR}-{MAX_ACADEMIC_YEAR} aralığında olmalıdır."
        )
    return text


# ===========================================================================
# 3) YER TUTUCU TABLOLAR
# ===========================================================================
# Modül 13'ün import_validators.py dosyası 12 model sınıfı import eder ve Modül 1'in
# academic_program.py kopyası "Student" ile "ProgramEnrollmentSnapshot" sınıflarına
# ilişki tanımlar. Kaynak dosyaları değiştirmek yasak olduğu için bu sınıflar burada
# ASGARİ TABLO TANIMI olarak üretiliyor.
#
# ÖNEMLİ: Bunlar Modül 2 / 9 / 10'un iş mantığı DEĞİLDİR. Ne şemaları, ne servisleri,
# ne de endpoint'leri bu demoda yer alır. Yalnızca kopyalanan Modül 13 doğrulayıcısının
# import edilebilmesi ve SQLAlchemy ilişki eşlemesinin tamamlanabilmesi için vardır.


class Student(Base):
    """Yer tutucu tablo — demo endpoint'lerinde kullanılmaz."""

    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)
    student_number = Column(String(50), unique=True, index=True, nullable=False)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    gender = Column(String(20), default="unspecified")
    nationality = Column(String(100), nullable=True)
    is_international = Column(Boolean, default=False)
    scholarship_rate_percent = Column(Numeric(6, 2), default=0)
    enrollment_year = Column(Integer, nullable=True)
    current_status = Column(String(30), default="active")
    preparatory_school = Column(Boolean, default=False)
    academic_program_id = Column(Integer, ForeignKey("academic_programs.id"), nullable=True)
    current_gpa = Column(Numeric(4, 2), nullable=True)
    expected_graduation_year = Column(Integer, nullable=True)
    actual_graduation_year = Column(Integer, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # academic_program.py kopyası back_populates="academic_program" bekliyor.
    academic_program = relationship("AcademicProgram", back_populates="students")


class StudentAcademicRecord(Base):
    """Yer tutucu tablo — demo endpoint'lerinde kullanılmaz."""

    __tablename__ = "student_academic_records"
    __table_args__ = (
        UniqueConstraint(
            "student_id", "academic_year", "semester", name="uq_demo_student_year_semester"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    academic_year = Column(String(9), nullable=False)
    semester = Column(String(10), nullable=False)
    registered_course_count = Column(Integer, default=0)
    passed_course_count = Column(Integer, default=0)
    failed_course_count = Column(Integer, default=0)
    earned_credits = Column(Integer, default=0)
    attempted_credits = Column(Integer, default=0)
    semester_gpa = Column(Numeric(4, 2), nullable=True)
    cumulative_gpa = Column(Numeric(4, 2), nullable=True)
    registration_renewed = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())


class ProgramEnrollmentSnapshot(Base):
    """Yer tutucu tablo — demo endpoint'lerinde kullanılmaz."""

    __tablename__ = "program_enrollment_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "academic_program_id", "academic_year", name="uq_demo_program_year"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    academic_program_id = Column(
        Integer, ForeignKey("academic_programs.id"), nullable=False
    )
    academic_year = Column(String(9), nullable=False)
    quota = Column(Integer, nullable=False, default=0)
    enrolled_student_count = Column(Integer, default=0)
    minimum_admission_score = Column(Numeric(8, 2), nullable=True)
    national_average_minimum_score = Column(Numeric(8, 2), nullable=True)
    ankara_average_minimum_score = Column(Numeric(8, 2), nullable=True)
    graduated_student_count = Column(Integer, default=0)
    dropped_out_student_count = Column(Integer, default=0)
    non_renewed_student_count = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # academic_program.py kopyası back_populates="academic_program" bekliyor.
    academic_program = relationship("AcademicProgram", back_populates="enrollment_snapshots")


class ComparableUniversityProgram(Base):
    """Yer tutucu tablo — demo endpoint'lerinde kullanılmaz."""

    __tablename__ = "comparable_university_programs"
    __table_args__ = (
        UniqueConstraint(
            "university_name", "program_name", "academic_year", name="uq_demo_comparable"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    university_name = Column(String(255), nullable=False)
    program_name = Column(String(255), nullable=False)
    city = Column(String(100), nullable=True)
    academic_year = Column(String(9), nullable=False)
    quota = Column(Integer, nullable=False, default=0)
    enrolled_student_count = Column(Integer, default=0)
    occupancy_rate = Column(Numeric(8, 2), nullable=True)
    minimum_admission_score = Column(Numeric(8, 2), nullable=True)
    is_competitor = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())


class EvaluationIndicator(Base):
    """Yer tutucu tablo — demo endpoint'lerinde kullanılmaz."""

    __tablename__ = "evaluation_indicators"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(100), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class InstitutionalMetricValue(Base):
    """Yer tutucu tablo — demo endpoint'lerinde kullanılmaz."""

    __tablename__ = "institutional_metric_values"
    __table_args__ = (
        UniqueConstraint(
            "indicator_id", "academic_year", "period", name="uq_demo_metric_key"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    indicator_id = Column(Integer, ForeignKey("evaluation_indicators.id"), nullable=False)
    academic_year = Column(String(9), nullable=False)
    period = Column(String(10), default="annual", nullable=False)
    value = Column(Numeric(20, 2), nullable=True)
    numerator = Column(Numeric(20, 2), nullable=True)
    denominator = Column(Numeric(20, 2), nullable=True)
    data_status = Column(String(20), default="available")
    origin = Column(String(20), default="imported")
    source_reference = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class BenchmarkInstitution(Base):
    """Yer tutucu tablo — demo endpoint'lerinde kullanılmaz."""

    __tablename__ = "benchmark_institutions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, index=True, nullable=False)
    country = Column(String(100), nullable=True)
    city = Column(String(100), nullable=True)
    institution_type = Column(String(30), default="similar")
    is_competitor = Column(Boolean, default=False)
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class BenchmarkMetricValue(Base):
    """Yer tutucu tablo — demo endpoint'lerinde kullanılmaz."""

    __tablename__ = "benchmark_metric_values"
    __table_args__ = (
        UniqueConstraint(
            "benchmark_institution_id",
            "indicator_id",
            "academic_year",
            "period",
            name="uq_demo_benchmark_value",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    benchmark_institution_id = Column(
        Integer, ForeignKey("benchmark_institutions.id"), nullable=False
    )
    indicator_id = Column(Integer, ForeignKey("evaluation_indicators.id"), nullable=False)
    academic_year = Column(String(9), nullable=False)
    period = Column(String(10), default="annual", nullable=False)
    value = Column(Numeric(20, 2), nullable=False)
    source_reference = Column(String(255), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ===========================================================================
# 4) UYUMLULUK KATMANI — sanal "app" paketi
# ===========================================================================

# Yüklenen her dosyanın gerçek yolu raporlanmak üzere biriktirilir.
LOADED_FILES: List[Tuple[str, Path]] = []


def _new_package(name: str) -> types.ModuleType:
    """sys.modules'a paket gibi davranan boş bir modül kaydeder."""
    module = types.ModuleType(name)
    # __path__ tanımlamak, Python'un bu modülü paket olarak görmesini sağlar.
    module.__path__ = []  # type: ignore[attr-defined]
    sys.modules[name] = module
    return module


def _load_file(module_name: str, file_path: Path) -> types.ModuleType:
    """Bir dosyayı verilen sanal modül adıyla yükler ve sys.modules'a kaydeder."""
    if not file_path.is_file():
        raise RuntimeError(f"Gerekli dosya bulunamadı: {file_path}")

    spec = importlib_util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Modül yüklenemedi: {file_path}")

    module = importlib_util.module_from_spec(spec)
    # exec_module'dan ÖNCE kaydetmek, dosyaların birbirine referans verebilmesi
    # ve döngüsel import'ların çözülebilmesi için gereklidir.
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    LOADED_FILES.append((module_name, file_path))
    return module


def _export(target: types.ModuleType, source: types.ModuleType, names: List[str]) -> None:
    """Kaynak modüldeki isimleri hedef paketin ad alanına taşır."""
    for name in names:
        setattr(target, name, getattr(source, name))


def install_compatibility_layer() -> None:
    """module_views kopyalarını sanal "app" paketi olarak sys.modules'a kurar."""
    # --- app ve app.database ---
    _new_package("app")

    database_module = types.ModuleType("app.database")
    database_module.Base = Base
    database_module.engine = engine
    database_module.SessionLocal = SessionLocal
    database_module.get_db = get_db
    database_module.init_db = init_db
    sys.modules["app.database"] = database_module

    # --- app.models ---
    models_package = _new_package("app.models")

    faculty_mod = _load_file("app.models.faculty", MODULE_01_DIR / "models" / "faculty.py")
    department_mod = _load_file(
        "app.models.department", MODULE_01_DIR / "models" / "department.py"
    )
    program_mod = _load_file(
        "app.models.academic_program", MODULE_01_DIR / "models" / "academic_program.py"
    )
    unit_mod = _load_file(
        "app.models.administrative_unit",
        MODULE_01_DIR / "models" / "administrative_unit.py",
    )
    import_job_mod = _load_file(
        "app.models.import_job", MODULE_13_DIR / "models" / "import_job.py"
    )

    models_package.Faculty = faculty_mod.Faculty
    models_package.Department = department_mod.Department
    models_package.AcademicProgram = program_mod.AcademicProgram
    models_package.AdministrativeUnit = unit_mod.AdministrativeUnit
    models_package.ImportJob = import_job_mod.ImportJob

    # Yer tutucu sınıflar aynı ad alanına eklenir.
    models_package.Student = Student
    models_package.StudentAcademicRecord = StudentAcademicRecord
    models_package.ProgramEnrollmentSnapshot = ProgramEnrollmentSnapshot
    models_package.ComparableUniversityProgram = ComparableUniversityProgram
    models_package.EvaluationIndicator = EvaluationIndicator
    models_package.InstitutionalMetricValue = InstitutionalMetricValue
    models_package.BenchmarkInstitution = BenchmarkInstitution
    models_package.BenchmarkMetricValue = BenchmarkMetricValue

    # academic_program.py, TYPE_CHECKING altında bu iki alt modülü referans ediyor.
    # Çalışma zamanında import edilmese de, tutarlılık için kaydediyoruz.
    student_stub = types.ModuleType("app.models.student")
    student_stub.Student = Student
    sys.modules["app.models.student"] = student_stub

    snapshot_stub = types.ModuleType("app.models.program_enrollment_snapshot")
    snapshot_stub.ProgramEnrollmentSnapshot = ProgramEnrollmentSnapshot
    sys.modules["app.models.program_enrollment_snapshot"] = snapshot_stub

    # --- app.schemas ---
    schemas_package = _new_package("app.schemas")

    faculty_schema = _load_file(
        "app.schemas.faculty", MODULE_01_DIR / "schemas" / "faculty.py"
    )
    department_schema = _load_file(
        "app.schemas.department", MODULE_01_DIR / "schemas" / "department.py"
    )
    program_schema = _load_file(
        "app.schemas.academic_program", MODULE_01_DIR / "schemas" / "academic_program.py"
    )
    unit_schema = _load_file(
        "app.schemas.administrative_unit",
        MODULE_01_DIR / "schemas" / "administrative_unit.py",
    )
    integration_schema = _load_file(
        "app.schemas.data_integration", MODULE_13_DIR / "schemas" / "data_integration.py"
    )

    _export(
        schemas_package,
        faculty_schema,
        ["FacultyCreate", "FacultyUpdate", "FacultyResponse"],
    )
    _export(
        schemas_package,
        department_schema,
        ["DepartmentCreate", "DepartmentUpdate", "DepartmentResponse"],
    )
    _export(
        schemas_package,
        program_schema,
        [
            "AcademicProgramCreate",
            "AcademicProgramUpdate",
            "AcademicProgramResponse",
        ],
    )
    _export(
        schemas_package,
        unit_schema,
        [
            "AdministrativeUnitCreate",
            "AdministrativeUnitUpdate",
            "AdministrativeUnitResponse",
        ],
    )
    _export(
        schemas_package,
        integration_schema,
        ["ResourceType", "RowIssue", "ImportResult", "ImportJobResponse"],
    )

    # app.schemas.students: yalnızca Modül 13'ün ihtiyaç duyduğu yardımcıyı sunar.
    students_schema_stub = types.ModuleType("app.schemas.students")
    students_schema_stub.validate_academic_year = validate_academic_year
    sys.modules["app.schemas.students"] = students_schema_stub

    # --- app.services ---
    services_package = _new_package("app.services")

    crud_helpers = _load_file(
        "app.services.crud_helpers", MODULE_01_DIR / "services" / "crud_helpers.py"
    )
    file_parser = _load_file(
        "app.services.file_parser", MODULE_13_DIR / "services" / "file_parser.py"
    )
    import_validators = _load_file(
        "app.services.import_validators",
        MODULE_13_DIR / "services" / "import_validators.py",
    )
    import_service = _load_file(
        "app.services.import_service", MODULE_13_DIR / "services" / "import_service.py"
    )

    _export(
        services_package,
        crud_helpers,
        [
            "get_object_or_404",
            "ensure_code_is_unique",
            "ensure_parent_exists",
            "apply_updates",
        ],
    )
    _export(services_package, file_parser, ["FileParseError", "parse_file", "detect_file_type"])
    _export(
        services_package,
        import_service,
        [
            "run_import",
            "build_csv_template",
            "get_supported_resources",
            "get_resource_aliases",
        ],
    )
    services_package.import_validators = import_validators

    # --- app.routers ---
    routers_package = _new_package("app.routers")

    routers_package.faculties = _load_file(
        "app.routers.faculties", MODULE_01_DIR / "routers" / "faculties.py"
    )
    routers_package.departments = _load_file(
        "app.routers.departments", MODULE_01_DIR / "routers" / "departments.py"
    )
    routers_package.programs = _load_file(
        "app.routers.programs", MODULE_01_DIR / "routers" / "programs.py"
    )
    routers_package.administrative_units = _load_file(
        "app.routers.administrative_units",
        MODULE_01_DIR / "routers" / "administrative_units.py",
    )
    routers_package.data_integration = _load_file(
        "app.routers.data_integration", MODULE_13_DIR / "routers" / "data_integration.py"
    )


install_compatibility_layer()


# ===========================================================================
# 5) ROUTER'LARI AL  (uyumluluk katmanı kurulduktan SONRA)
# ===========================================================================

from app.routers import (  # noqa: E402
    administrative_units,
    data_integration,
    departments,
    faculties,
    programs,
)

# ===========================================================================
# 6) FASTAPI UYGULAMASI
# ===========================================================================

from fastapi import FastAPI  # noqa: E402

# Demo akışının çalışması için hazır olması gereken tablolar.
REQUIRED_TABLES: List[str] = [
    "faculties",
    "departments",
    "academic_programs",
    "administrative_units",
    "import_jobs",
]

APP_NAME: str = "Week 1 Demo - Core Data and Data Integration"
APP_VERSION: str = "1.0.0"


def verify_required_tables() -> Dict[str, bool]:
    """Demo için gereken tabloların oluştuğunu doğrular."""
    existing = set(inspect(engine).get_table_names())
    return {table: table in existing for table in REQUIRED_TABLES}


from contextlib import asynccontextmanager  # noqa: E402
from typing import AsyncIterator  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Uygulama açılırken veritabanını hazırlar ve tabloları doğrular."""
    init_db()

    status = verify_required_tables()
    missing = [table for table, exists in status.items() if not exists]
    if missing:
        raise RuntimeError(
            "Demo için gereken tablolar oluşturulamadı: " + ", ".join(missing)
        )

    print(f"[module_views-demo] Veritabani: {DB_PATH}")
    print("[module_views-demo] Gerekli tablolar dogrulandi:")
    for table in REQUIRED_TABLES:
        print(f"[module_views-demo]   - {table}: OK")

    yield


app = FastAPI(
    title=APP_NAME,
    description=(
        "Standalone demonstration served entirely from the module_views folder. "
        "Covers Module 1 (University Structure and Core Data Management) and "
        "Module 13 (Data Integration). No dependency on the main backend."
    ),
    version=APP_VERSION,
    lifespan=lifespan,
)

# --- Modül 1 ---
app.include_router(faculties.router)
app.include_router(departments.router)
app.include_router(programs.router)
app.include_router(administrative_units.router)

# --- Modül 13 ---
app.include_router(data_integration.router)

# NOT: Modül 2, 9 ve 10 router'ları bu demoda YOKTUR (kopyaları bile yüklenmez).


# ===========================================================================
# 7) HEALTH ENDPOINT'LERİ
# ===========================================================================
# module_views içinde health.py kopyası bulunmadığı için burada tanımlandı.


@app.get("/health", tags=["Health"])
def health_check() -> Dict[str, Any]:
    """Demo'nun ayakta olduğunu bildiren sağlık durumu bilgisi döndürür."""
    return {
        "status": "healthy",
        "application": APP_NAME,
        "version": APP_VERSION,
        "database": "sqlite",
        "database_file": DB_PATH.name,
        "required_tables": verify_required_tables(),
    }


@app.get("/", tags=["Health"])
def read_root() -> Dict[str, Any]:
    """Demo kapsamını ve bağımsızlığını bildiren karşılama mesajı döndürür."""
    return {
        "message": "module_views standalone demo is running",
        "application": APP_NAME,
        "version": APP_VERSION,
        "standalone": True,
        "source_folder": str(BASE_DIR.name),
        "enabled_modules": [
            "Module 1 - University Structure and Core Data Management",
            "Module 13 - Data Integration",
        ],
        "excluded_modules": [
            "Module 2 - Student Analytics",
            "Module 9 - Scenario Analysis",
            "Module 10 - Ranking Evaluations",
        ],
        "docs_url": "/docs",
        "openapi_url": "/openapi.json",
    }


@app.get("/demo-info", tags=["Health"])
def demo_info() -> Dict[str, Any]:
    """Yüklenen dosyaları ve kullanılabilir örnek verileri listeler."""
    # Demoda hangi dosyaların gerçekten kullanıldığını şeffaf biçimde gösterir.
    csv_files = sorted(p.name for p in SAMPLE_DATA_DIR.glob("*.csv"))
    xlsx_files = sorted(p.name for p in SAMPLE_DATA_DIR.glob("*.xlsx"))
    json_files = sorted(p.name for p in SAMPLE_DATA_DIR.glob("*.json"))

    return {
        "database_path": str(DB_PATH),
        "loaded_python_files": [
            {"module": name, "path": str(path.relative_to(BASE_DIR))}
            for name, path in LOADED_FILES
        ],
        "loaded_file_count": len(LOADED_FILES),
        "module_1_endpoints": [
            "/api/faculties",
            "/api/departments",
            "/api/programs",
            "/api/administrative-units",
        ],
        "module_13_endpoints": [
            "/api/data-integration/import/{resource_type}",
            "/api/data-integration/templates/{resource_type}",
            "/api/data-integration/jobs",
            "/api/data-integration/resources",
        ],
        "demo_resource_types": [
            "faculties",
            "departments",
            "programs",
            "administrative-units",
        ],
        "sample_data_dir": str(SAMPLE_DATA_DIR.relative_to(BASE_DIR)),
        "sample_files": {"csv": csv_files, "xlsx": xlsx_files, "json": json_files},
    }


# ===========================================================================
# 8) ÖRNEK VERİ YÜKLEME  (Modül 1 kopyasındaki seed_data.py)
# ===========================================================================


def load_seed_data() -> bool:
    """Modül 1 kopyasındaki seed_data.py dosyasını çalıştırır.

    Dosya bulunamazsa demo yine açılır; yalnızca örnek kayıtlar olmaz.
    """
    seed_path = MODULE_01_DIR / "seed_data.py"
    if not seed_path.is_file():
        print(f"[module_views-demo] UYARI: {seed_path.name} bulunamadi, seed atlandi.")
        return False

    seed_module = _load_file("module_views_seed_data", seed_path)
    seed_module.seed()
    return True


# ===========================================================================
# 9) DOĞRUDAN ÇALIŞTIRMA:  python main.py
# ===========================================================================

if __name__ == "__main__":
    import uvicorn

    print("=" * 66)
    print(" module_views bagimsiz demo")
    print(" Modul 1 (Temel Veri) + Modul 13 (Veri Entegrasyonu)")
    print("=" * 66)

    # 1) Veritabanı ve tablolar
    init_db()
    print(f"[module_views-demo] Veritabani hazir: {DB_PATH}")

    # 2) Örnek veriler (seed_data.py idempotenttir, tekrar çalıştırılabilir)
    load_seed_data()

    # 3) Yüklenen dosya özeti
    print(f"[module_views-demo] Yuklenen Python dosyasi: {len(LOADED_FILES)}")

    print()
    print("  Swagger UI : http://127.0.0.1:8000/docs")
    print("  OpenAPI    : http://127.0.0.1:8000/openapi.json")
    print("  Health     : http://127.0.0.1:8000/health")
    print("  Demo info  : http://127.0.0.1:8000/demo-info")
    print()
    print("  Durdurmak icin CTRL+C")
    print()

    # reload=False: "python main.py" ile öngörülebilir davranış sağlar.
    # Otomatik yeniden yukleme icin: uvicorn main:app --reload
    uvicorn.run(app, host="127.0.0.1", port=8000)
