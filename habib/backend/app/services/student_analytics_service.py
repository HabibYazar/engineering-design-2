"""Öğrenci analitiği hesaplamaları.

Router bu dosyadaki fonksiyonları çağırır; hiçbir hesaplama endpoint içinde yapılmaz.

PERFORMANS NOTU:
Tüm sayımlar SQL tarafında `func.count` + `case` ile tek sorguda yapılır. Öğrenci
kayıtlarını Python belleğine çekip döngüyle saymak, 100.000 öğrencide hem belleği
hem de süreyi gereksiz yere büyütürdü. Program/bölüm/fakülte kırılımları da tek bir
`group_by` sorgusuyla alınır; her program için ayrı sorgu atmak (N+1) bilinçli olarak
önlenmiştir.
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import Select, case, func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    AcademicProgram,
    ComparableUniversityProgram,
    Department,
    Faculty,
    ProgramEnrollmentSnapshot,
    Student,
    StudentAcademicRecord,
)
from app.schemas.student_analytics import (
    ComparisonRow,
    DemandTrend,
    DemandYearPoint,
    DepartmentAnalytics,
    FacultyAnalytics,
    ProgramAnalytics,
    ProgramComparisonResponse,
    ProgramDemandResponse,
    StudentOverview,
)

TWO_PLACES: Decimal = Decimal("0.01")
ZERO: Decimal = Decimal("0.00")

# Talep trendi hesabında bakılacak yıl sayısı.
TREND_WINDOW: int = 3


# ===========================================================================
# Ortak yardımcılar
# ===========================================================================


def to_decimal(value: Any) -> Decimal:
    """Herhangi bir sayıyı iki ondalık basamaklı Decimal'e çevirir."""
    # str() üzerinden geçmemizin sebebi: SQL AVG float döndürür ve float doğrudan
    # Decimal'e verilirse ikili gösterimden gelen sapma da taşınır.
    if value is None:
        return ZERO
    return Decimal(str(value)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def percentage(numerator: Any, denominator: Any) -> Decimal:
    """Yüzde hesaplar; payda sıfırsa 0.00 döner."""
    # Sıfıra bölme, öğrencisi olmayan yeni programlarda sık karşılaşılan bir durum.
    # Hata fırlatmak yerine 0 döndürüp raporun bütünlüğünü koruyoruz.
    denominator_value: Decimal = Decimal(str(denominator or 0))
    if denominator_value == 0:
        return ZERO
    return (Decimal(str(numerator or 0)) / denominator_value * Decimal("100")).quantize(
        TWO_PLACES, rounding=ROUND_HALF_UP
    )


def ratio(numerator: Any, denominator: Any) -> Decimal:
    """Oran hesaplar (yüzdeye çevirmeden); payda sıfırsa 0.00 döner."""
    denominator_value: Decimal = Decimal(str(denominator or 0))
    if denominator_value == 0:
        return ZERO
    return (Decimal(str(numerator or 0)) / denominator_value).quantize(
        TWO_PLACES, rounding=ROUND_HALF_UP
    )


def change_percent(current: Any, previous: Any) -> Optional[Decimal]:
    """İki değer arasındaki yüzdesel değişimi hesaplar."""
    # Önceki değer yoksa ya da sıfırsa yüzdesel değişim tanımsızdır.
    if previous is None:
        return None
    previous_value: Decimal = Decimal(str(previous))
    if previous_value == 0:
        return None
    return ((Decimal(str(current)) - previous_value) / previous_value * Decimal("100")).quantize(
        TWO_PLACES, rounding=ROUND_HALF_UP
    )


def academic_year_to_start(academic_year: str) -> int:
    """'2024-2025' biçimindeki yılın başlangıç yılını verir."""
    return int(str(academic_year).split("-")[0])


def year_to_academic_year(year: int) -> str:
    """2024 -> '2024-2025' dönüşümü yapar."""
    return f"{year}-{year + 1}"


def _count_if(condition) -> Any:
    """Koşulu sağlayan satırları SQL tarafında sayan ifade üretir."""
    # SUM(CASE WHEN ... THEN 1 ELSE 0 END) kalıbı, tek sorguda birden fazla
    # farklı sayımı almamızı sağlar. Aksi halde her sayım için ayrı sorgu gerekirdi.
    return func.coalesce(func.sum(case((condition, 1), else_=0)), 0)


def apply_student_scope(
    statement: Select,
    faculty_id: Optional[int] = None,
    department_id: Optional[int] = None,
    academic_program_id: Optional[int] = None,
    enrollment_year: Optional[int] = None,
    only_active_records: bool = True,
) -> Select:
    """Öğrenci sorgusuna fakülte/bölüm/program filtrelerini uygular."""
    # Fakülte veya bölüm filtresi verildiğinde program tablosu üzerinden join gerekir.
    # Join'i yalnızca gerektiğinde eklemek gereksiz maliyeti önler.
    if faculty_id is not None or department_id is not None:
        statement = statement.join(
            AcademicProgram, Student.academic_program_id == AcademicProgram.id
        ).join(Department, AcademicProgram.department_id == Department.id)
        if department_id is not None:
            statement = statement.where(AcademicProgram.department_id == department_id)
        if faculty_id is not None:
            statement = statement.where(Department.faculty_id == faculty_id)

    if academic_program_id is not None:
        statement = statement.where(Student.academic_program_id == academic_program_id)
    if enrollment_year is not None:
        statement = statement.where(Student.enrollment_year == enrollment_year)
    if only_active_records:
        # Pasifleştirilmiş (silinmiş sayılan) kayıtlar istatistiklere girmez.
        statement = statement.where(Student.is_active.is_(True))

    return statement


# ===========================================================================
# 1) Genel bakış
# ===========================================================================


def build_overview(
    db: Session,
    faculty_id: Optional[int] = None,
    department_id: Optional[int] = None,
    academic_program_id: Optional[int] = None,
    academic_year: Optional[str] = None,
) -> StudentOverview:
    """Öğrenci sayıları, oranlar ve akademik başarı özetini hesaplar."""
    # academic_year verilirse kayıt yılı olarak yorumlanır (2024-2025 -> 2024).
    enrollment_year: Optional[int] = (
        academic_year_to_start(academic_year) if academic_year else None
    )

    # Tek sorguda tüm sayımlar: 11 ayrı COUNT sorgusu yerine 1 sorgu.
    statement = select(
        func.count(Student.id).label("total"),
        _count_if(Student.current_status == "newly-enrolled").label("newly_enrolled"),
        _count_if(Student.current_status == "active").label("active"),
        _count_if(Student.current_status == "graduated").label("graduated"),
        _count_if(Student.current_status == "dropped-out").label("dropped_out"),
        _count_if(Student.current_status == "non-renewed").label("non_renewed"),
        _count_if(Student.preparatory_school.is_(True)).label("preparatory"),
        _count_if(Student.scholarship_rate_percent > 0).label("scholarship"),
        _count_if(Student.is_international.is_(True)).label("international"),
        func.avg(Student.current_gpa).label("avg_gpa"),
        func.avg(
            case(
                (
                    Student.actual_graduation_year.isnot(None),
                    Student.actual_graduation_year - Student.enrollment_year,
                ),
                else_=None,
            )
        ).label("avg_graduation_duration"),
    ).select_from(Student)

    statement = apply_student_scope(
        statement, faculty_id, department_id, academic_program_id, enrollment_year
    )
    row = db.execute(statement).one()

    total: int = int(row.total or 0)

    # Akademik başarı göstergeleri ayrı tablodan, yine tek sorguda toplanır.
    record_statement = select(
        func.coalesce(func.sum(StudentAcademicRecord.passed_course_count), 0),
        func.coalesce(func.sum(StudentAcademicRecord.registered_course_count), 0),
        func.coalesce(func.sum(StudentAcademicRecord.earned_credits), 0),
        func.coalesce(func.sum(StudentAcademicRecord.attempted_credits), 0),
    ).select_from(StudentAcademicRecord).join(
        Student, StudentAcademicRecord.student_id == Student.id
    )
    record_statement = apply_student_scope(
        record_statement, faculty_id, department_id, academic_program_id, enrollment_year
    )
    if academic_year:
        record_statement = record_statement.where(
            StudentAcademicRecord.academic_year == academic_year
        )

    passed, registered, earned, attempted = db.execute(record_statement).one()

    return StudentOverview(
        total_students=total,
        newly_enrolled_students=int(row.newly_enrolled or 0),
        active_students=int(row.active or 0),
        graduated_students=int(row.graduated or 0),
        preparatory_school_students=int(row.preparatory or 0),
        dropped_out_students=int(row.dropped_out or 0),
        non_renewed_students=int(row.non_renewed or 0),
        scholarship_student_percentage=percentage(row.scholarship, total),
        international_student_percentage=percentage(row.international, total),
        average_gpa=to_decimal(row.avg_gpa),
        average_graduation_duration_years=to_decimal(row.avg_graduation_duration),
        passed_course_ratio=percentage(passed, registered),
        credit_efficiency_ratio=ratio(earned, attempted),
        applied_filters={
            "faculty_id": faculty_id,
            "department_id": department_id,
            "academic_program_id": academic_program_id,
            "academic_year": academic_year,
        },
    )


# ===========================================================================
# 2) Program bazlı analitik
# ===========================================================================


def _student_aggregates_by_program(
    db: Session,
    faculty_id: Optional[int] = None,
    department_id: Optional[int] = None,
    academic_program_id: Optional[int] = None,
) -> Dict[int, Any]:
    """Program bazında öğrenci sayımlarını tek sorguda toplar."""
    # group_by kullanarak tüm programların sayımlarını tek seferde alıyoruz.
    statement = (
        select(
            Student.academic_program_id.label("program_id"),
            func.count(Student.id).label("total"),
            _count_if(Student.current_status.in_(["active", "newly-enrolled"])).label("active"),
            _count_if(Student.current_status == "graduated").label("graduated"),
            _count_if(Student.current_status == "dropped-out").label("dropped_out"),
            _count_if(Student.current_status == "non-renewed").label("non_renewed"),
            _count_if(Student.scholarship_rate_percent > 0).label("scholarship"),
            _count_if(Student.is_international.is_(True)).label("international"),
            func.avg(Student.current_gpa).label("avg_gpa"),
            func.avg(
                case(
                    (
                        Student.actual_graduation_year.isnot(None),
                        Student.actual_graduation_year - Student.enrollment_year,
                    ),
                    else_=None,
                )
            ).label("avg_graduation_duration"),
        )
        .select_from(Student)
        .group_by(Student.academic_program_id)
    )
    statement = apply_student_scope(
        statement, faculty_id, department_id, academic_program_id
    )
    return {row.program_id: row for row in db.execute(statement).all()}


def _latest_snapshots_by_program(
    db: Session, academic_year: Optional[str] = None
) -> Dict[int, ProgramEnrollmentSnapshot]:
    """Her program için ilgili yılın (yoksa en yeni) snapshot kaydını getirir."""
    # Tüm snapshotları tek sorguda çekip Python'da en yenisini seçiyoruz.
    # Snapshot sayısı program×yıl kadar olduğu için bu veri seti küçüktür;
    # her program için ayrı "en yeni" sorgusu atmaktan çok daha ucuzdur.
    statement = select(ProgramEnrollmentSnapshot)
    if academic_year:
        statement = statement.where(ProgramEnrollmentSnapshot.academic_year == academic_year)
    statement = statement.order_by(
        ProgramEnrollmentSnapshot.academic_program_id,
        ProgramEnrollmentSnapshot.academic_year,
    )

    latest: Dict[int, ProgramEnrollmentSnapshot] = {}
    for snapshot in db.execute(statement).scalars().all():
        latest[snapshot.academic_program_id] = snapshot
    return latest


def _snapshot_history_by_program(db: Session) -> Dict[int, List[ProgramEnrollmentSnapshot]]:
    """Her program için tüm snapshot geçmişini yıla göre sıralı döndürür."""
    statement = select(ProgramEnrollmentSnapshot).order_by(
        ProgramEnrollmentSnapshot.academic_program_id,
        ProgramEnrollmentSnapshot.academic_year,
    )
    history: Dict[int, List[ProgramEnrollmentSnapshot]] = {}
    for snapshot in db.execute(statement).scalars().all():
        history.setdefault(snapshot.academic_program_id, []).append(snapshot)
    return history


def calculate_demand_trend(
    snapshots: Sequence[ProgramEnrollmentSnapshot],
) -> Tuple[DemandTrend, str]:
    """Son üç yılın doluluk oranı ve taban puanına bakarak talep trendini belirler."""
    # Kural: iki ölçüt de yükseliyorsa increasing, ikisi de düşüyorsa decreasing,
    # diğer bütün durumlarda stable. Tek ölçüte bakmak yanıltıcı olurdu; örneğin
    # kontenjan artırılınca doluluk düşebilir ama puan yükselmeye devam edebilir.
    window = list(snapshots)[-TREND_WINDOW:]
    if len(window) < 2:
        return DemandTrend.STABLE, "Trend hesaplamak için en az iki yıllık veri gerekiyor."

    occupancies: List[Decimal] = [
        percentage(item.enrolled_student_count, item.quota) for item in window
    ]
    scores: List[Optional[Decimal]] = [item.minimum_admission_score for item in window]

    occupancy_rising: bool = all(
        occupancies[i] > occupancies[i - 1] for i in range(1, len(occupancies))
    )
    occupancy_falling: bool = all(
        occupancies[i] < occupancies[i - 1] for i in range(1, len(occupancies))
    )

    # Puan verisi eksikse puan ölçütü kararsız kabul edilir.
    has_scores: bool = all(score is not None for score in scores)
    score_rising: bool = has_scores and all(
        scores[i] > scores[i - 1] for i in range(1, len(scores))
    )
    score_falling: bool = has_scores and all(
        scores[i] < scores[i - 1] for i in range(1, len(scores))
    )

    if occupancy_rising and score_rising:
        return (
            DemandTrend.INCREASING,
            "Son yıllarda hem doluluk oranı hem de taban puan sürekli yükseliyor.",
        )
    if occupancy_falling and score_falling:
        return (
            DemandTrend.DECREASING,
            "Son yıllarda hem doluluk oranı hem de taban puan sürekli düşüyor.",
        )
    return (
        DemandTrend.STABLE,
        "Doluluk oranı ve taban puan aynı yönde sürekli hareket etmiyor; talep dengeli görünüyor.",
    )


def build_program_analytics(
    db: Session,
    faculty_id: Optional[int] = None,
    department_id: Optional[int] = None,
    academic_program_id: Optional[int] = None,
    academic_year: Optional[str] = None,
) -> List[ProgramAnalytics]:
    """Her akademik program için analitik özet üretir."""
    # Program + bölüm + fakülte adlarını tek join'li sorguda alıyoruz (N+1 yok).
    program_statement = (
        select(
            AcademicProgram.id,
            AcademicProgram.name,
            AcademicProgram.code,
            Department.id,
            Department.name,
            Faculty.id,
            Faculty.name,
        )
        .join(Department, AcademicProgram.department_id == Department.id)
        .join(Faculty, Department.faculty_id == Faculty.id)
        .order_by(AcademicProgram.id)
    )
    if academic_program_id is not None:
        program_statement = program_statement.where(AcademicProgram.id == academic_program_id)
    if department_id is not None:
        program_statement = program_statement.where(
            AcademicProgram.department_id == department_id
        )
    if faculty_id is not None:
        program_statement = program_statement.where(Department.faculty_id == faculty_id)

    programs = db.execute(program_statement).all()

    aggregates = _student_aggregates_by_program(
        db, faculty_id, department_id, academic_program_id
    )
    snapshots = _latest_snapshots_by_program(db, academic_year)
    history = _snapshot_history_by_program(db)

    results: List[ProgramAnalytics] = []
    for prog_id, prog_name, prog_code, dept_id, dept_name, fac_id, fac_name in programs:
        agg = aggregates.get(prog_id)
        snapshot = snapshots.get(prog_id)

        total: int = int(agg.total) if agg else 0
        active: int = int(agg.active) if agg else 0
        graduated: int = int(agg.graduated) if agg else 0
        dropped: int = int(agg.dropped_out) if agg else 0
        non_renewed: int = int(agg.non_renewed) if agg else 0

        # Mezuniyet oranının paydası: mezun + aktif + bırakan.
        # Kaydını yenilemeyenler henüz kesin ayrılmış sayılmadığı için paydaya dahil edilmez.
        graduation_base: int = graduated + active + dropped

        quota: int = snapshot.quota if snapshot else 0
        enrolled: int = snapshot.enrolled_student_count if snapshot else 0

        trend, _ = calculate_demand_trend(history.get(prog_id, []))

        results.append(
            ProgramAnalytics(
                program_id=prog_id,
                program_name=prog_name,
                program_code=prog_code,
                department_id=dept_id,
                department_name=dept_name,
                faculty_id=fac_id,
                faculty_name=fac_name,
                quota=quota,
                enrolled_student_count=enrolled,
                occupancy_rate=percentage(enrolled, quota),
                active_student_count=active,
                graduate_count=graduated,
                graduation_rate=percentage(graduated, graduation_base),
                dropped_out_count=dropped,
                attrition_rate=percentage(dropped, total),
                non_renewed_count=non_renewed,
                non_renewal_rate=percentage(non_renewed, total),
                scholarship_student_percentage=percentage(
                    agg.scholarship if agg else 0, total
                ),
                international_student_percentage=percentage(
                    agg.international if agg else 0, total
                ),
                average_gpa=to_decimal(agg.avg_gpa if agg else None),
                average_graduation_duration_years=to_decimal(
                    agg.avg_graduation_duration if agg else None
                ),
                minimum_admission_score=snapshot.minimum_admission_score if snapshot else None,
                demand_trend=trend,
                total_students=total,
            )
        )

    return results


# ===========================================================================
# 3) Bölüm ve fakülte kırılımları
# ===========================================================================


def build_department_analytics(
    db: Session,
    faculty_id: Optional[int] = None,
    department_id: Optional[int] = None,
    academic_year: Optional[str] = None,
) -> List[DepartmentAnalytics]:
    """Program sonuçlarını bölüm düzeyinde birleştirir."""
    # Program analizini yeniden hesaplamak yerine üzerine toplama yapıyoruz;
    # böylece aynı SQL sorguları ikinci kez çalıştırılmıyor.
    programs = build_program_analytics(
        db, faculty_id=faculty_id, department_id=department_id, academic_year=academic_year
    )

    grouped: Dict[int, List[ProgramAnalytics]] = {}
    for program in programs:
        grouped.setdefault(program.department_id, []).append(program)

    results: List[DepartmentAnalytics] = []
    for dept_id, items in sorted(grouped.items()):
        first = items[0]

        total = sum(item.total_students for item in items)
        active = sum(item.active_student_count for item in items)
        graduates = sum(item.graduate_count for item in items)
        dropped = sum(item.dropped_out_count for item in items)
        non_renewed = sum(item.non_renewed_count for item in items)

        # Doluluk oranı ortalaması, kontenjan toplamı üzerinden ağırlıklı hesaplanır.
        # Basit ortalama alsaydık 10 kişilik program ile 200 kişilik program eşit ağırlık alırdı.
        total_quota = sum(item.quota for item in items)
        total_enrolled = sum(item.enrolled_student_count for item in items)

        scholarship_count = sum(
            round(item.scholarship_student_percentage / Decimal("100") * item.total_students)
            for item in items
        )
        international_count = sum(
            round(item.international_student_percentage / Decimal("100") * item.total_students)
            for item in items
        )

        # GPA ortalaması öğrenci sayısıyla ağırlıklandırılır.
        gpa_weighted_sum = sum(item.average_gpa * item.total_students for item in items)

        results.append(
            DepartmentAnalytics(
                department_id=dept_id,
                department_name=first.department_name,
                department_code="",
                faculty_id=first.faculty_id,
                faculty_name=first.faculty_name,
                program_count=len(items),
                total_students=total,
                active_students=active,
                graduates=graduates,
                dropped_out_students=dropped,
                non_renewed_students=non_renewed,
                average_occupancy_rate=percentage(total_enrolled, total_quota),
                graduation_rate=percentage(graduates, graduates + active + dropped),
                attrition_rate=percentage(dropped, total),
                non_renewal_rate=percentage(non_renewed, total),
                international_student_percentage=percentage(international_count, total),
                scholarship_student_percentage=percentage(scholarship_count, total),
                average_gpa=ratio(gpa_weighted_sum, total),
            )
        )

    # Bölüm kodlarını tek sorguda ekliyoruz.
    codes = dict(
        db.execute(select(Department.id, Department.code)).all()
    )
    for item in results:
        item.department_code = codes.get(item.department_id, "")

    return results


def build_faculty_analytics(
    db: Session,
    faculty_id: Optional[int] = None,
    academic_year: Optional[str] = None,
) -> List[FacultyAnalytics]:
    """Bölüm sonuçlarını fakülte düzeyinde birleştirir."""
    departments = build_department_analytics(
        db, faculty_id=faculty_id, academic_year=academic_year
    )

    grouped: Dict[int, List[DepartmentAnalytics]] = {}
    for department in departments:
        grouped.setdefault(department.faculty_id, []).append(department)

    # Doluluk ağırlıklandırması için program düzeyindeki kontenjan toplamları gerekli.
    programs = build_program_analytics(db, faculty_id=faculty_id, academic_year=academic_year)
    quota_by_faculty: Dict[int, Tuple[int, int]] = {}
    for program in programs:
        quota, enrolled = quota_by_faculty.get(program.faculty_id, (0, 0))
        quota_by_faculty[program.faculty_id] = (
            quota + program.quota,
            enrolled + program.enrolled_student_count,
        )

    results: List[FacultyAnalytics] = []
    for fac_id, items in sorted(grouped.items()):
        first = items[0]

        total = sum(item.total_students for item in items)
        active = sum(item.active_students for item in items)
        graduates = sum(item.graduates for item in items)
        dropped = sum(item.dropped_out_students for item in items)
        non_renewed = sum(item.non_renewed_students for item in items)

        scholarship_count = sum(
            round(item.scholarship_student_percentage / Decimal("100") * item.total_students)
            for item in items
        )
        international_count = sum(
            round(item.international_student_percentage / Decimal("100") * item.total_students)
            for item in items
        )
        gpa_weighted_sum = sum(item.average_gpa * item.total_students for item in items)

        total_quota, total_enrolled = quota_by_faculty.get(fac_id, (0, 0))

        results.append(
            FacultyAnalytics(
                faculty_id=fac_id,
                faculty_name=first.faculty_name,
                faculty_code="",
                department_count=len(items),
                program_count=sum(item.program_count for item in items),
                total_students=total,
                active_students=active,
                graduates=graduates,
                dropped_out_students=dropped,
                non_renewed_students=non_renewed,
                average_occupancy_rate=percentage(total_enrolled, total_quota),
                graduation_rate=percentage(graduates, graduates + active + dropped),
                attrition_rate=percentage(dropped, total),
                non_renewal_rate=percentage(non_renewed, total),
                international_student_percentage=percentage(international_count, total),
                scholarship_student_percentage=percentage(scholarship_count, total),
                average_gpa=ratio(gpa_weighted_sum, total),
            )
        )

    codes = dict(db.execute(select(Faculty.id, Faculty.code)).all())
    for item in results:
        item.faculty_code = codes.get(item.faculty_id, "")

    return results


# ===========================================================================
# 4) Program talep analizi
# ===========================================================================


def build_program_demand(db: Session, program_id: int) -> ProgramDemandResponse:
    """Bir programın yıllara göre talep gelişimini ve trendini hesaplar."""
    program_row = db.execute(
        select(
            AcademicProgram.id,
            AcademicProgram.name,
            AcademicProgram.code,
            Department.name,
            Faculty.name,
        )
        .join(Department, AcademicProgram.department_id == Department.id)
        .join(Faculty, Department.faculty_id == Faculty.id)
        .where(AcademicProgram.id == program_id)
    ).first()

    snapshots: List[ProgramEnrollmentSnapshot] = list(
        db.execute(
            select(ProgramEnrollmentSnapshot)
            .where(ProgramEnrollmentSnapshot.academic_program_id == program_id)
            .order_by(ProgramEnrollmentSnapshot.academic_year)
        )
        .scalars()
        .all()
    )

    points: List[DemandYearPoint] = []
    previous_occupancy: Optional[Decimal] = None
    previous_score: Optional[Decimal] = None

    for snapshot in snapshots:
        occupancy: Decimal = percentage(snapshot.enrolled_student_count, snapshot.quota)
        points.append(
            DemandYearPoint(
                academic_year=snapshot.academic_year,
                year=academic_year_to_start(snapshot.academic_year),
                quota=snapshot.quota,
                enrolled_student_count=snapshot.enrolled_student_count,
                occupancy_rate=occupancy,
                minimum_admission_score=snapshot.minimum_admission_score,
                national_average_minimum_score=snapshot.national_average_minimum_score,
                ankara_average_minimum_score=snapshot.ankara_average_minimum_score,
                occupancy_change_percent=change_percent(occupancy, previous_occupancy),
                score_change_percent=(
                    change_percent(snapshot.minimum_admission_score, previous_score)
                    if snapshot.minimum_admission_score is not None
                    else None
                ),
            )
        )
        previous_occupancy = occupancy
        previous_score = snapshot.minimum_admission_score

    trend, explanation = calculate_demand_trend(snapshots)

    return ProgramDemandResponse(
        program_id=program_row[0],
        program_name=program_row[1],
        program_code=program_row[2],
        department_name=program_row[3],
        faculty_name=program_row[4],
        years=points,
        demand_trend=trend,
        trend_explanation=explanation,
    )


# ===========================================================================
# 5) Karşılaştırmalı analiz
# ===========================================================================


def build_program_comparison(
    db: Session,
    program_id: int,
    academic_year: Optional[str] = None,
) -> ProgramComparisonResponse:
    """Programı diğer üniversitelerin benzer programlarıyla karşılaştırır."""
    program_row = db.execute(
        select(AcademicProgram.id, AcademicProgram.name)
        .where(AcademicProgram.id == program_id)
    ).first()

    # Yıl verilmezse programın en yeni snapshot yılı kullanılır.
    snapshot_statement = select(ProgramEnrollmentSnapshot).where(
        ProgramEnrollmentSnapshot.academic_program_id == program_id
    )
    if academic_year:
        snapshot_statement = snapshot_statement.where(
            ProgramEnrollmentSnapshot.academic_year == academic_year
        )
    snapshot_statement = snapshot_statement.order_by(
        ProgramEnrollmentSnapshot.academic_year.desc()
    )
    snapshot: Optional[ProgramEnrollmentSnapshot] = (
        db.execute(snapshot_statement).scalars().first()
    )

    selected_year: str = (
        snapshot.academic_year if snapshot else (academic_year or "")
    )

    own_occupancy: Decimal = (
        percentage(snapshot.enrolled_student_count, snapshot.quota) if snapshot else ZERO
    )
    own_score: Optional[Decimal] = snapshot.minimum_admission_score if snapshot else None

    own_row = ComparisonRow(
        label="Kendi programımız",
        university_name="Kendi Üniversitemiz",
        quota=snapshot.quota if snapshot else None,
        enrolled_student_count=snapshot.enrolled_student_count if snapshot else None,
        occupancy_rate=own_occupancy,
        minimum_admission_score=own_score,
        occupancy_difference=ZERO,
        score_difference=ZERO,
    )

    # Ulusal ve Ankara ortalamaları snapshot içinde saklandığı için ek sorgu gerekmiyor.
    national_row: Optional[ComparisonRow] = None
    ankara_row: Optional[ComparisonRow] = None
    if snapshot and snapshot.national_average_minimum_score is not None:
        national_row = ComparisonRow(
            label="Türkiye ortalaması",
            minimum_admission_score=snapshot.national_average_minimum_score,
            score_difference=(
                (own_score - snapshot.national_average_minimum_score)
                if own_score is not None
                else None
            ),
        )
    if snapshot and snapshot.ankara_average_minimum_score is not None:
        ankara_row = ComparisonRow(
            label="Ankara ortalaması",
            city="Ankara",
            minimum_admission_score=snapshot.ankara_average_minimum_score,
            score_difference=(
                (own_score - snapshot.ankara_average_minimum_score)
                if own_score is not None
                else None
            ),
        )

    # Karşılaştırma kayıtları tek sorguda çekilir.
    comparable_statement = select(ComparableUniversityProgram)
    if selected_year:
        comparable_statement = comparable_statement.where(
            ComparableUniversityProgram.academic_year == selected_year
        )
    comparable_statement = comparable_statement.order_by(
        ComparableUniversityProgram.minimum_admission_score.desc()
    )
    comparables = list(db.execute(comparable_statement).scalars().all())

    similar: List[ComparisonRow] = []
    competitors: List[ComparisonRow] = []

    for item in comparables:
        occupancy: Decimal = (
            item.occupancy_rate
            if item.occupancy_rate is not None
            else percentage(item.enrolled_student_count, item.quota)
        )
        row = ComparisonRow(
            label=f"{item.university_name} — {item.program_name}",
            university_name=item.university_name,
            city=item.city,
            quota=item.quota,
            enrolled_student_count=item.enrolled_student_count,
            occupancy_rate=occupancy,
            minimum_admission_score=item.minimum_admission_score,
            is_competitor=item.is_competitor,
            occupancy_difference=(own_occupancy - occupancy),
            score_difference=(
                (own_score - item.minimum_admission_score)
                if own_score is not None and item.minimum_admission_score is not None
                else None
            ),
        )
        similar.append(row)
        if item.is_competitor:
            competitors.append(row)

    # Sıralama: kendi programımız dahil edilerek kaçıncı sırada olduğumuz bulunur.
    score_rank: Optional[int] = None
    if own_score is not None:
        better_scores = sum(
            1
            for item in comparables
            if item.minimum_admission_score is not None
            and item.minimum_admission_score > own_score
        )
        score_rank = better_scores + 1

    better_occupancy = sum(
        1
        for item in comparables
        if (
            item.occupancy_rate
            if item.occupancy_rate is not None
            else percentage(item.enrolled_student_count, item.quota)
        )
        > own_occupancy
    )
    occupancy_rank: int = better_occupancy + 1

    total_compared: int = len(comparables) + 1
    summary: str = (
        f"{len(comparables)} karşılaştırma kaydı içinde taban puan sıralamasında "
        f"{score_rank if score_rank else '-'}. , doluluk oranı sıralamasında "
        f"{occupancy_rank}. sıradayız (toplam {total_compared} program)."
    )

    return ProgramComparisonResponse(
        program_id=program_row[0],
        program_name=program_row[1],
        academic_year=selected_year,
        own_program=own_row,
        national_average=national_row,
        ankara_average=ankara_row,
        similar_programs=similar,
        competitor_programs=competitors,
        score_rank=score_rank,
        occupancy_rank=occupancy_rank,
        total_compared=total_compared,
        summary=summary,
    )


# ===========================================================================
# 6) Öğrenci listeleme filtreleri (router tarafından kullanılır)
# ===========================================================================


def build_student_filter_statement(
    faculty_id: Optional[int] = None,
    department_id: Optional[int] = None,
    academic_program_id: Optional[int] = None,
    current_status: Optional[str] = None,
    is_international: Optional[bool] = None,
    preparatory_school: Optional[bool] = None,
    enrollment_year: Optional[int] = None,
    is_active: Optional[bool] = None,
    search: Optional[str] = None,
) -> Select:
    """Öğrenci listeleme sorgusunu verilen filtrelere göre oluşturur."""
    statement = select(Student)

    # Fakülte/bölüm filtresi program tablosu üzerinden join gerektirir.
    if faculty_id is not None or department_id is not None:
        statement = statement.join(
            AcademicProgram, Student.academic_program_id == AcademicProgram.id
        ).join(Department, AcademicProgram.department_id == Department.id)
        if department_id is not None:
            statement = statement.where(AcademicProgram.department_id == department_id)
        if faculty_id is not None:
            statement = statement.where(Department.faculty_id == faculty_id)

    if academic_program_id is not None:
        statement = statement.where(Student.academic_program_id == academic_program_id)
    if current_status is not None:
        statement = statement.where(Student.current_status == current_status)
    if is_international is not None:
        statement = statement.where(Student.is_international.is_(is_international))
    if preparatory_school is not None:
        statement = statement.where(Student.preparatory_school.is_(preparatory_school))
    if enrollment_year is not None:
        statement = statement.where(Student.enrollment_year == enrollment_year)
    if is_active is not None:
        statement = statement.where(Student.is_active.is_(is_active))

    if search:
        # Arama numara, ad ve soyad üzerinde büyük/küçük harf duyarsız yapılır.
        pattern: str = f"%{search.strip()}%"
        statement = statement.where(
            or_(
                Student.student_number.ilike(pattern),
                Student.first_name.ilike(pattern),
                Student.last_name.ilike(pattern),
            )
        )

    return statement
