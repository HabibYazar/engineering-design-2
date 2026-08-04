"""İçe aktarılan satırların doğrulama kurallarını içeren modül.

Kaynak tanımları (RESOURCE_SPECS) bildirimsel bir yapıdadır: hangi sütunlar zorunlu,
hangileri sayı/ondalık/boolean/enum olarak yorumlanacak, benzersizlik hangi alanlara
göre kontrol edilecek — hepsi tek bir yerde tanımlanır. Doğrulama fonksiyonu bu tanımı
okuyarak çalıştığı için yeni bir kaynak eklemek yeni kod yazmayı değil, yeni bir
ResourceSpec satırı eklemeyi gerektirir.
"""

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple, Type

from app.database import Base
from app.models import (
    AcademicProgram,
    AdministrativeUnit,
    BenchmarkInstitution,
    BenchmarkMetricValue,
    ComparableUniversityProgram,
    Department,
    EvaluationIndicator,
    Faculty,
    InstitutionalMetricValue,
    ProgramEnrollmentSnapshot,
    Student,
    StudentAcademicRecord,
)
from app.schemas.students import validate_academic_year

# is_active alanı için kabul edilen yazım biçimleri.
# Kullanıcılar Excel'de "Evet", "1", "TRUE" gibi farklı şekillerde yazabildiği için
# hepsini tek bir boolean değere indirgiyoruz.
TRUE_VALUES: set = {"true", "1", "yes", "y", "evet", "e", "aktif", "active"}
FALSE_VALUES: set = {"false", "0", "no", "n", "hayir", "hayır", "h", "pasif", "passive"}

# Öğrenci ve akademik kayıt alanlarında kullanılan sabit değer kümeleri.
GENDER_VALUES: set = {"male", "female", "other", "unspecified"}
STUDENT_STATUS_VALUES: set = {
    "newly-enrolled",
    "active",
    "graduated",
    "suspended",
    "dropped-out",
    "non-renewed",
}
SEMESTER_VALUES: set = {"fall", "spring", "summer"}

# Modül 10 (değerlendirme) alanlarında kullanılan sabit değer kümeleri.
PERIOD_VALUES: set = {"annual", "fall", "spring", "summer"}
DATA_STATUS_VALUES: set = {"available", "partial", "missing", "estimated", "invalid"}
INSTITUTION_TYPE_VALUES: set = {
    "national-average",
    "similar",
    "competitor",
    "international",
    "other",
}


@dataclass
class ParentSpec:
    """Dosyadaki bir kod sütununun hangi üst kayda karşılık geldiğini tanımlar.

    Bir kaynağın birden fazla üst kaydı olabilir (örneğin karşılaştırma gösterge
    değeri hem kuruma hem göstergeye bağlıdır), bu yüzden liste halinde tutulur.
    """

    lookup_column: str  # dosyadaki sütun (örn. faculty_code)
    model: Type[Base]  # üst model (örn. Faculty)
    fk_field: str  # bu modeldeki alan (örn. faculty_id)
    label: str  # hata mesajında kullanılacak Türkçe ad
    key_column: str = "code"  # üst modeldeki eşleşme sütunu


@dataclass
class ResourceSpec:
    """Bir kaynağın içe aktarma kurallarını tanımlayan yapı."""

    model: Type[Base]
    label: str
    columns: List[str]
    required: List[str]

    # Benzersizlik anahtarı. Tek alan ("code",) olabileceği gibi
    # bileşik de olabilir ("student_id", "academic_year", "semester").
    # Değerler doğrulama sonrası temizlenmiş veri üzerinden okunur.
    unique_fields: Tuple[str, ...] = ("code",)

    # Boşluklar kırpılıp büyük harfe çevrilecek alanlar (kodlar, öğrenci numarası).
    upper_fields: Tuple[str, ...] = ()

    # Boş bırakıldığında kaydedilmeyen düz metin alanları.
    text_fields: Tuple[str, ...] = ()

    # Boş bırakıldığında None olarak kaydedilen metin alanları.
    nullable_text_fields: Tuple[str, ...] = ()

    # alan adı -> (en küçük değer, en büyük değer veya None)
    integer_fields: Dict[str, Tuple[int, Optional[int]]] = field(default_factory=dict)

    # alan adı -> (en küçük değer, en büyük değer)
    decimal_fields: Dict[str, Tuple[Decimal, Decimal]] = field(default_factory=dict)

    # alan adı -> varsayılan değer
    boolean_fields: Dict[str, bool] = field(default_factory=dict)

    # alan adı -> (izin verilen değerler, varsayılan)
    enum_fields: Dict[str, Tuple[set, Optional[str]]] = field(default_factory=dict)

    # YYYY-YYYY biçiminde doğrulanacak alanlar.
    academic_year_fields: Tuple[str, ...] = ()

    # Foreign key çözümlemesi: dosyadaki kod sütunlarından üst kayıtların id'lerini bulur.
    # Bir kaynağın birden fazla üst kaydı olabilir.
    parents: Tuple[ParentSpec, ...] = ()

    # Tarih/saat olarak yorumlanacak alanlar (ISO biçimi beklenir).
    datetime_fields: Tuple[str, ...] = ()


# Ondalık alanlar için sık kullanılan sınırlar.
GPA_RANGE: Tuple[Decimal, Decimal] = (Decimal("0"), Decimal("4"))
PERCENT_RANGE: Tuple[Decimal, Decimal] = (Decimal("0"), Decimal("100"))
SCORE_RANGE: Tuple[Decimal, Decimal] = (Decimal("0"), Decimal("1000"))

# Gösterge değerleri para (araştırma geliri) veya adet (atıf sayısı) olabildiği
# için üst sınır geniş tutuldu. Negatif değer kabul edilmez.
METRIC_VALUE_RANGE: Tuple[Decimal, Decimal] = (Decimal("0"), Decimal("1000000000000"))


# Kaynak tanımları. Yeni bir kaynak eklenmesi gerekirse sadece buraya satır eklemek yeterli.
RESOURCE_SPECS: Dict[str, ResourceSpec] = {
    # ------------------------------------------------------------------
    # Modül 1 kaynakları (mevcut davranış birebir korundu)
    # ------------------------------------------------------------------
    "faculties": ResourceSpec(
        model=Faculty,
        label="Fakülte",
        columns=["name", "code", "description", "is_active"],
        required=["name", "code"],
        unique_fields=("code",),
        upper_fields=("code",),
        text_fields=("name",),
        nullable_text_fields=("description",),
        boolean_fields={"is_active": True},
    ),
    "departments": ResourceSpec(
        model=Department,
        label="Bölüm",
        columns=["faculty_code", "name", "code", "description", "is_active"],
        required=["name", "code", "faculty_code"],
        unique_fields=("code",),
        upper_fields=("code",),
        text_fields=("name",),
        nullable_text_fields=("description",),
        boolean_fields={"is_active": True},
        parents=(
            ParentSpec(
                lookup_column="faculty_code",
                model=Faculty,
                fk_field="faculty_id",
                label="Fakülte",
            ),
        ),
    ),
    "programs": ResourceSpec(
        model=AcademicProgram,
        label="Akademik program",
        columns=[
            "department_code",
            "name",
            "code",
            "degree_level",
            "duration_years",
            "quota",
            "description",
            "is_active",
        ],
        required=["name", "code", "department_code", "degree_level"],
        unique_fields=("code",),
        upper_fields=("code",),
        text_fields=("name", "degree_level"),
        nullable_text_fields=("description",),
        # duration_years en az 1, quota en az 0 olmalı.
        integer_fields={"duration_years": (1, None), "quota": (0, None)},
        boolean_fields={"is_active": True},
        parents=(
            ParentSpec(
                lookup_column="department_code",
                model=Department,
                fk_field="department_id",
                label="Bölüm",
            ),
        ),
    ),
    "administrative-units": ResourceSpec(
        model=AdministrativeUnit,
        label="İdari birim",
        columns=["name", "code", "description", "is_active"],
        required=["name", "code"],
        unique_fields=("code",),
        upper_fields=("code",),
        text_fields=("name",),
        nullable_text_fields=("description",),
        boolean_fields={"is_active": True},
    ),
    # ------------------------------------------------------------------
    # Modül 2 kaynakları (öğrenci analitiği)
    # ------------------------------------------------------------------
    "students": ResourceSpec(
        model=Student,
        label="Öğrenci",
        columns=[
            "student_number",
            "first_name",
            "last_name",
            "gender",
            "nationality",
            "is_international",
            "scholarship_rate_percent",
            "enrollment_year",
            "current_status",
            "preparatory_school",
            "academic_program_code",
            "current_gpa",
            "expected_graduation_year",
            "actual_graduation_year",
            "is_active",
        ],
        required=["student_number", "first_name", "last_name", "enrollment_year",
                  "academic_program_code"],
        unique_fields=("student_number",),
        upper_fields=("student_number",),
        text_fields=("first_name", "last_name"),
        nullable_text_fields=("nationality",),
        integer_fields={
            "enrollment_year": (1950, 2100),
            "expected_graduation_year": (1950, 2100),
            "actual_graduation_year": (1950, 2100),
        },
        decimal_fields={
            "scholarship_rate_percent": PERCENT_RANGE,
            "current_gpa": GPA_RANGE,
        },
        boolean_fields={
            "is_active": True,
            "is_international": False,
            "preparatory_school": False,
        },
        enum_fields={
            "gender": (GENDER_VALUES, "unspecified"),
            "current_status": (STUDENT_STATUS_VALUES, "active"),
        },
        parents=(
            ParentSpec(
                lookup_column="academic_program_code",
                model=AcademicProgram,
                fk_field="academic_program_id",
                label="Akademik program",
            ),
        ),
    ),
    "student-academic-records": ResourceSpec(
        model=StudentAcademicRecord,
        label="Öğrenci akademik kaydı",
        columns=[
            "student_number",
            "academic_year",
            "semester",
            "registered_course_count",
            "passed_course_count",
            "failed_course_count",
            "earned_credits",
            "attempted_credits",
            "semester_gpa",
            "cumulative_gpa",
            "registration_renewed",
        ],
        required=["student_number", "academic_year", "semester"],
        # Aynı öğrencinin aynı yıl ve dönemi iki kez girilemez.
        unique_fields=("student_id", "academic_year", "semester"),
        integer_fields={
            "registered_course_count": (0, None),
            "passed_course_count": (0, None),
            "failed_course_count": (0, None),
            "earned_credits": (0, None),
            "attempted_credits": (0, None),
        },
        decimal_fields={"semester_gpa": GPA_RANGE, "cumulative_gpa": GPA_RANGE},
        boolean_fields={"registration_renewed": True},
        enum_fields={"semester": (SEMESTER_VALUES, None)},
        academic_year_fields=("academic_year",),
        parents=(
            ParentSpec(
                lookup_column="student_number",
                model=Student,
                key_column="student_number",
                fk_field="student_id",
                label="Öğrenci",
            ),
        ),
    ),
    "program-enrollment-snapshots": ResourceSpec(
        model=ProgramEnrollmentSnapshot,
        label="Program kayıt fotoğrafı",
        columns=[
            "academic_program_code",
            "academic_year",
            "quota",
            "enrolled_student_count",
            "minimum_admission_score",
            "national_average_minimum_score",
            "ankara_average_minimum_score",
            "graduated_student_count",
            "dropped_out_student_count",
            "non_renewed_student_count",
        ],
        required=["academic_program_code", "academic_year", "quota"],
        # Aynı program için aynı yıl iki snapshot olamaz.
        unique_fields=("academic_program_id", "academic_year"),
        integer_fields={
            "quota": (1, None),
            "enrolled_student_count": (0, None),
            "graduated_student_count": (0, None),
            "dropped_out_student_count": (0, None),
            "non_renewed_student_count": (0, None),
        },
        decimal_fields={
            "minimum_admission_score": SCORE_RANGE,
            "national_average_minimum_score": SCORE_RANGE,
            "ankara_average_minimum_score": SCORE_RANGE,
        },
        academic_year_fields=("academic_year",),
        parents=(
            ParentSpec(
                lookup_column="academic_program_code",
                model=AcademicProgram,
                fk_field="academic_program_id",
                label="Akademik program",
            ),
        ),
    ),
    "comparable-university-programs": ResourceSpec(
        model=ComparableUniversityProgram,
        label="Karşılaştırma programı",
        columns=[
            "university_name",
            "program_name",
            "city",
            "academic_year",
            "quota",
            "enrolled_student_count",
            "occupancy_rate",
            "minimum_admission_score",
            "is_competitor",
        ],
        required=["university_name", "program_name", "academic_year", "quota"],
        unique_fields=("university_name", "program_name", "academic_year"),
        text_fields=("university_name", "program_name"),
        nullable_text_fields=("city",),
        integer_fields={"quota": (1, None), "enrolled_student_count": (0, None)},
        decimal_fields={
            "occupancy_rate": (Decimal("0"), Decimal("1000")),
            "minimum_admission_score": SCORE_RANGE,
        },
        boolean_fields={"is_competitor": False},
        academic_year_fields=("academic_year",),
    ),
    # ------------------------------------------------------------------
    # Modül 10 kaynakları (THE / QS / YÖK değerlendirme)
    # ------------------------------------------------------------------
    "institutional-metric-values": ResourceSpec(
        model=InstitutionalMetricValue,
        label="Kurumsal gösterge verisi",
        columns=[
            "indicator_code",
            "academic_year",
            "period",
            "value",
            "numerator",
            "denominator",
            "data_status",
            "source_reference",
            "notes",
        ],
        required=["indicator_code", "academic_year"],
        # Aynı gösterge için aynı yıl ve dönem iki kez girilemez.
        unique_fields=("indicator_id", "academic_year", "period"),
        nullable_text_fields=("source_reference", "notes"),
        decimal_fields={
            "value": METRIC_VALUE_RANGE,
            "numerator": METRIC_VALUE_RANGE,
            "denominator": METRIC_VALUE_RANGE,
        },
        enum_fields={
            "period": (PERIOD_VALUES, "annual"),
            "data_status": (DATA_STATUS_VALUES, "available"),
        },
        academic_year_fields=("academic_year",),
        parents=(
            ParentSpec(
                lookup_column="indicator_code",
                model=EvaluationIndicator,
                fk_field="indicator_id",
                label="Gösterge",
            ),
        ),
    ),
    "benchmark-institutions": ResourceSpec(
        model=BenchmarkInstitution,
        label="Karşılaştırma kurumu",
        columns=[
            "name",
            "country",
            "city",
            "institution_type",
            "is_competitor",
            "notes",
            "is_active",
        ],
        required=["name"],
        unique_fields=("name",),
        text_fields=("name",),
        nullable_text_fields=("country", "city", "notes"),
        enum_fields={"institution_type": (INSTITUTION_TYPE_VALUES, "similar")},
        boolean_fields={"is_competitor": False, "is_active": True},
    ),
    "benchmark-metric-values": ResourceSpec(
        model=BenchmarkMetricValue,
        label="Karşılaştırma gösterge değeri",
        columns=[
            "benchmark_institution_name",
            "indicator_code",
            "academic_year",
            "period",
            "value",
            "source_reference",
        ],
        required=["benchmark_institution_name", "indicator_code", "academic_year", "value"],
        unique_fields=(
            "benchmark_institution_id",
            "indicator_id",
            "academic_year",
            "period",
        ),
        nullable_text_fields=("source_reference",),
        decimal_fields={"value": METRIC_VALUE_RANGE},
        enum_fields={"period": (PERIOD_VALUES, "annual")},
        academic_year_fields=("academic_year",),
        # İki üst kayıt: hem kurum hem gösterge çözümlenmelidir.
        parents=(
            ParentSpec(
                lookup_column="benchmark_institution_name",
                model=BenchmarkInstitution,
                key_column="name",
                fk_field="benchmark_institution_id",
                label="Karşılaştırma kurumu",
            ),
            ParentSpec(
                lookup_column="indicator_code",
                model=EvaluationIndicator,
                fk_field="indicator_id",
                label="Gösterge",
            ),
        ),
    ),
}

# Kullanıcı dokümantasyonunda alt çizgili yazımlar da geçtiği için, aynı
# tanımlara alt çizgili takma adlarla da erişilebiliyor. Böylece hem proje
# stiliyle tutarlı tireli isimler hem de alt çizgili isimler çalışır.
RESOURCE_TYPE_ALIASES: Dict[str, str] = {
    "institutional_metric_values": "institutional-metric-values",
    "benchmark_institutions": "benchmark-institutions",
    "benchmark_metric_values": "benchmark-metric-values",
}

for alias, canonical in RESOURCE_TYPE_ALIASES.items():
    RESOURCE_SPECS[alias] = RESOURCE_SPECS[canonical]


def get_resource_spec(resource_type: str) -> ResourceSpec:
    """Kaynak türüne ait doğrulama tanımını döndürür."""
    return RESOURCE_SPECS[resource_type]


def normalize_code(value: Any) -> str:
    """Kod değerini boşluklardan temizler ve büyük harfe çevirir."""
    # Kodların tek biçimde saklanması, "swe" ile "SWE " gibi değerlerin
    # farklı kayıtlar olarak görünmesini engeller.
    return str(value or "").strip().upper()


def parse_boolean(value: Any, default: bool = True) -> Tuple[Optional[bool], bool]:
    """Metin biçimindeki boolean değerini çevirir.

    Dönüş: (değer, gecerli_mi). Değer boşsa varsayılan kullanılır.
    """
    text: str = str(value if value is not None else "").strip().lower()

    # Alan hiç doldurulmamışsa varsayılanı kullanıyoruz; bu, kullanıcıyı
    # her satırda tüm boolean alanları yazmak zorunda bırakmamak için tercih edildi.
    if text == "":
        return default, True

    if text in TRUE_VALUES:
        return True, True
    if text in FALSE_VALUES:
        return False, True

    return None, False


def parse_integer(
    value: Any, minimum: int, maximum: Optional[int] = None
) -> Tuple[Optional[int], bool]:
    """Sayısal alanı tam sayıya çevirir ve sınırları kontrol eder."""
    text: str = str(value if value is not None else "").strip()
    if text == "":
        return None, True  # Boş bırakılırsa modeldeki varsayılan değer kullanılır.

    try:
        # Excel sayıları "4.0" gibi okuyabildiği için önce float'a, sonra int'e çeviriyoruz.
        number = float(text)
    except (TypeError, ValueError):
        return None, False

    if number != int(number):
        return None, False

    number_as_int = int(number)
    if number_as_int < minimum:
        return None, False
    if maximum is not None and number_as_int > maximum:
        return None, False

    return number_as_int, True


def parse_decimal(
    value: Any, minimum: Decimal, maximum: Decimal
) -> Tuple[Optional[Decimal], bool]:
    """Ondalık alanı Decimal'e çevirir ve sınırları kontrol eder."""
    text: str = str(value if value is not None else "").strip()
    if text == "":
        return None, True

    try:
        # Virgüllü yazımı da kabul ediyoruz; Türkçe Excel dosyalarında sık görülür.
        number: Decimal = Decimal(text.replace(",", "."))
    except (InvalidOperation, TypeError, ValueError):
        return None, False

    if number < minimum or number > maximum:
        return None, False
    return number, True


def validate_row(
    spec: ResourceSpec,
    row: Dict[str, Any],
) -> Tuple[Dict[str, Any], List[Tuple[str, str, str]]]:
    """Tek bir satırı kaynak tanımına göre doğrular.

    Dönüş: (temizlenmiş veri, hata listesi).
    Hata listesi (alan_adi, gonderilen_deger, mesaj) üçlülerinden oluşur.
    """
    cleaned: Dict[str, Any] = {}
    issues: List[Tuple[str, str, str]] = []

    # 1) Zorunlu alan kontrolü
    for column in spec.required:
        raw_value = str(row.get(column, "") or "").strip()
        if raw_value == "":
            issues.append((column, "", f"{column} alanı zorunludur."))

    # 2) Büyük harfe çevrilecek alanlar (kod, öğrenci numarası)
    for field_name in spec.upper_fields:
        value = normalize_code(row.get(field_name))
        if value:
            cleaned[field_name] = value

    # 3) Düz metin alanları
    for field_name in spec.text_fields:
        value = str(row.get(field_name, "") or "").strip()
        if value:
            cleaned[field_name] = value

    # 4) Boş bırakılabilen metin alanları (her zaman kaydedilir, boşsa None)
    for field_name in spec.nullable_text_fields:
        value = str(row.get(field_name, "") or "").strip()
        cleaned[field_name] = value or None

    # 5) Akademik yıl biçimi
    for field_name in spec.academic_year_fields:
        raw_value = str(row.get(field_name, "") or "").strip()
        if raw_value == "":
            continue  # zorunluluk kontrolü yukarıda yapıldı
        try:
            cleaned[field_name] = validate_academic_year(raw_value)
        except ValueError as error:
            issues.append((field_name, raw_value, str(error)))

    # 6) Tam sayı alanları
    for field_name, (minimum, maximum) in spec.integer_fields.items():
        raw_value = row.get(field_name, "")
        parsed_number, is_valid = parse_integer(raw_value, minimum, maximum)
        if not is_valid:
            limit_text: str = (
                f"{minimum} ile {maximum} arasında"
                if maximum is not None
                else f"{minimum} veya daha büyük"
            )
            issues.append(
                (
                    field_name,
                    str(raw_value),
                    f"{field_name} alanı {limit_text} bir tam sayı olmalıdır.",
                )
            )
        elif parsed_number is not None:
            cleaned[field_name] = parsed_number

    # 7) Ondalık alanlar
    for field_name, (minimum_decimal, maximum_decimal) in spec.decimal_fields.items():
        raw_value = row.get(field_name, "")
        parsed_decimal, is_valid = parse_decimal(raw_value, minimum_decimal, maximum_decimal)
        if not is_valid:
            issues.append(
                (
                    field_name,
                    str(raw_value),
                    f"{field_name} alanı {minimum_decimal} ile {maximum_decimal} "
                    "arasında bir sayı olmalıdır.",
                )
            )
        elif parsed_decimal is not None:
            cleaned[field_name] = parsed_decimal

    # 8) Sabit değer (enum) alanları
    for field_name, (allowed_values, default_value) in spec.enum_fields.items():
        raw_value = str(row.get(field_name, "") or "").strip().lower()
        if raw_value == "":
            if default_value is not None:
                cleaned[field_name] = default_value
            continue
        if raw_value not in allowed_values:
            issues.append(
                (
                    field_name,
                    raw_value,
                    f"{field_name} alanı şu değerlerden biri olmalıdır: "
                    f"{', '.join(sorted(allowed_values))}.",
                )
            )
        else:
            cleaned[field_name] = raw_value

    # 9) Boolean alanlar
    for field_name, default_flag in spec.boolean_fields.items():
        raw_value = row.get(field_name, "")
        parsed_flag, is_valid = parse_boolean(raw_value, default_flag)
        if not is_valid:
            issues.append(
                (
                    field_name,
                    str(raw_value),
                    f"{field_name} alanı true/false, 1/0, yes/no veya evet/hayır olmalıdır.",
                )
            )
        else:
            cleaned[field_name] = parsed_flag

    # 10) Üst kayıt kodları (faculty_code, indicator_code, benchmark_institution_name ...)
    # Gerçek id çözümlemesi veritabanı erişimi gerektirdiği için import_service'te yapılır.
    if spec.parents:
        cleaned["_parent_codes"] = {
            parent.lookup_column: normalize_code(row.get(parent.lookup_column))
            for parent in spec.parents
        }

    # 11) Kaynağa özel çapraz alan kontrolleri
    issues.extend(_cross_field_checks(spec, cleaned))

    return cleaned, issues


def _cross_field_checks(
    spec: ResourceSpec, cleaned: Dict[str, Any]
) -> List[Tuple[str, str, str]]:
    """Birden fazla alanı birlikte değerlendiren kuralları kontrol eder."""
    issues: List[Tuple[str, str, str]] = []

    if spec.model is StudentAcademicRecord:
        # Geçilen + kalınan ders, alınan dersten fazla olamaz.
        registered = cleaned.get("registered_course_count", 0)
        passed = cleaned.get("passed_course_count", 0)
        failed = cleaned.get("failed_course_count", 0)
        if passed + failed > registered:
            issues.append(
                (
                    "passed_course_count",
                    str(passed),
                    f"Geçilen ({passed}) ve kalınan ({failed}) ders sayısının toplamı, "
                    f"kayıtlı ders sayısını ({registered}) aşamaz.",
                )
            )

        earned = cleaned.get("earned_credits", 0)
        attempted = cleaned.get("attempted_credits", 0)
        if earned > attempted:
            issues.append(
                (
                    "earned_credits",
                    str(earned),
                    f"Kazanılan kredi ({earned}), denenen krediyi ({attempted}) aşamaz.",
                )
            )

    if spec.model is Student:
        # Mezuniyet yılı kayıt yılından küçük olamaz.
        enrollment_year = cleaned.get("enrollment_year")
        graduation_year = cleaned.get("actual_graduation_year")
        if (
            enrollment_year is not None
            and graduation_year is not None
            and graduation_year < enrollment_year
        ):
            issues.append(
                (
                    "actual_graduation_year",
                    str(graduation_year),
                    f"Gerçek mezuniyet yılı ({graduation_year}) kayıt yılından "
                    f"({enrollment_year}) küçük olamaz.",
                )
            )

    return issues
