"""Yıllara göre öğrenci metriklerinin trend analizi.

Her metrik için yıl bazında tek bir toplu sorgu atılır; yıl sayısı kadar döngü içinde
sorgu açmak (N+1) bilinçli olarak önlenmiştir.
"""

from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import (
    AcademicProgram,
    Department,
    ProgramEnrollmentSnapshot,
    Student,
)
from app.schemas.student_analytics import (
    DemandTrend,
    TrendMetric,
    TrendPoint,
    TrendResponse,
)
from app.services.student_analytics_service import (
    ZERO,
    _count_if,
    academic_year_to_start,
    change_percent,
    percentage,
    to_decimal,
    year_to_academic_year,
)

# Trend yönü belirlenirken bu yüzdeden küçük değişimler "sabit" kabul edilir.
# Küçük dalgalanmaların trend olarak yorumlanmasını önler.
STABILITY_THRESHOLD_PERCENT: Decimal = Decimal("5")

# Snapshot tablosundan hesaplanan metrikler (öğrenci tablosundan değil).
SNAPSHOT_METRICS = {
    TrendMetric.OCCUPANCY_RATE,
    TrendMetric.MINIMUM_ADMISSION_SCORE,
}


def _student_metrics_by_year(
    db: Session,
    start_year: int,
    end_year: int,
    faculty_id: Optional[int],
    department_id: Optional[int],
    academic_program_id: Optional[int],
) -> Dict[int, Dict[str, Decimal]]:
    """Öğrenci tablosundan yıl bazında tüm sayımları tek sorguda toplar."""
    # Kayıt yılına göre gruplayıp bütün metrikleri aynı sorguda üretiyoruz.
    statement = (
        select(
            Student.enrollment_year.label("year"),
            func.count(Student.id).label("total"),
            _count_if(Student.current_status == "newly-enrolled").label("newly_enrolled"),
            _count_if(Student.current_status == "graduated").label("graduated"),
            _count_if(Student.current_status.in_(["active", "newly-enrolled"])).label("active"),
            _count_if(Student.current_status == "dropped-out").label("dropped_out"),
            _count_if(Student.current_status == "non-renewed").label("non_renewed"),
            _count_if(Student.scholarship_rate_percent > 0).label("scholarship"),
            _count_if(Student.is_international.is_(True)).label("international"),
            func.avg(Student.current_gpa).label("avg_gpa"),
        )
        .select_from(Student)
        .where(Student.is_active.is_(True))
        .where(Student.enrollment_year >= start_year)
        .where(Student.enrollment_year <= end_year)
        .group_by(Student.enrollment_year)
    )

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

    results: Dict[int, Dict[str, Decimal]] = {}
    for row in db.execute(statement).all():
        total = int(row.total or 0)
        graduated = int(row.graduated or 0)
        active = int(row.active or 0)
        dropped = int(row.dropped_out or 0)
        non_renewed = int(row.non_renewed or 0)

        results[int(row.year)] = {
            TrendMetric.TOTAL_STUDENTS.value: Decimal(total),
            TrendMetric.NEWLY_ENROLLED.value: Decimal(int(row.newly_enrolled or 0)),
            TrendMetric.GRADUATES.value: Decimal(graduated),
            TrendMetric.GRADUATION_RATE.value: percentage(
                graduated, graduated + active + dropped
            ),
            TrendMetric.ATTRITION_RATE.value: percentage(dropped, total),
            TrendMetric.NON_RENEWAL_RATE.value: percentage(non_renewed, total),
            TrendMetric.SCHOLARSHIP_PERCENTAGE.value: percentage(row.scholarship, total),
            TrendMetric.INTERNATIONAL_PERCENTAGE.value: percentage(row.international, total),
            TrendMetric.AVERAGE_GPA.value: to_decimal(row.avg_gpa),
        }
    return results


def _snapshot_metrics_by_year(
    db: Session,
    start_year: int,
    end_year: int,
    faculty_id: Optional[int],
    department_id: Optional[int],
    academic_program_id: Optional[int],
) -> Dict[int, Dict[str, Decimal]]:
    """Snapshot tablosundan yıl bazında doluluk ve taban puan ortalamalarını toplar."""
    # Birden fazla program varsa doluluk, kontenjan toplamı üzerinden ağırlıklı hesaplanır.
    statement = (
        select(
            ProgramEnrollmentSnapshot.academic_year.label("academic_year"),
            func.coalesce(func.sum(ProgramEnrollmentSnapshot.quota), 0).label("quota"),
            func.coalesce(
                func.sum(ProgramEnrollmentSnapshot.enrolled_student_count), 0
            ).label("enrolled"),
            func.avg(ProgramEnrollmentSnapshot.minimum_admission_score).label("avg_score"),
        )
        .select_from(ProgramEnrollmentSnapshot)
        .group_by(ProgramEnrollmentSnapshot.academic_year)
    )

    if faculty_id is not None or department_id is not None:
        statement = statement.join(
            AcademicProgram,
            ProgramEnrollmentSnapshot.academic_program_id == AcademicProgram.id,
        ).join(Department, AcademicProgram.department_id == Department.id)
        if department_id is not None:
            statement = statement.where(AcademicProgram.department_id == department_id)
        if faculty_id is not None:
            statement = statement.where(Department.faculty_id == faculty_id)
    if academic_program_id is not None:
        statement = statement.where(
            ProgramEnrollmentSnapshot.academic_program_id == academic_program_id
        )

    results: Dict[int, Dict[str, Decimal]] = {}
    for row in db.execute(statement).all():
        year = academic_year_to_start(row.academic_year)
        if year < start_year or year > end_year:
            continue
        results[year] = {
            TrendMetric.OCCUPANCY_RATE.value: percentage(row.enrolled, row.quota),
            TrendMetric.MINIMUM_ADMISSION_SCORE.value: to_decimal(row.avg_score),
        }
    return results


def build_trend(
    db: Session,
    metric: TrendMetric,
    start_year: int,
    end_year: int,
    faculty_id: Optional[int] = None,
    department_id: Optional[int] = None,
    academic_program_id: Optional[int] = None,
) -> TrendResponse:
    """Seçilen metriğin yıllara göre gelişimini ve değişim yüzdelerini hesaplar."""
    # Metriğin hangi tablodan geleceğine göre uygun toplu sorgu çalıştırılır.
    if metric in SNAPSHOT_METRICS:
        data = _snapshot_metrics_by_year(
            db, start_year, end_year, faculty_id, department_id, academic_program_id
        )
    else:
        data = _student_metrics_by_year(
            db, start_year, end_year, faculty_id, department_id, academic_program_id
        )

    points: List[TrendPoint] = []
    previous_value: Optional[Decimal] = None

    for year in range(start_year, end_year + 1):
        # Veri olmayan yıllar seriden düşürülmez; 0 olarak gösterilir ki
        # grafik üzerinde boşluk görünsün ve düşüş fark edilsin.
        value: Decimal = data.get(year, {}).get(metric.value, ZERO)

        points.append(
            TrendPoint(
                year=year,
                academic_year=year_to_academic_year(year),
                value=value,
                change_absolute=(
                    None if previous_value is None else (value - previous_value)
                ),
                change_percent=change_percent(value, previous_value),
            )
        )
        previous_value = value

    return TrendResponse(
        metric=metric,
        start_year=start_year,
        end_year=end_year,
        points=points,
        overall_direction=_overall_direction(points),
        applied_filters={
            "faculty_id": faculty_id,
            "department_id": department_id,
            "academic_program_id": academic_program_id,
        },
    )


def _overall_direction(points: List[TrendPoint]) -> DemandTrend:
    """Serinin ilk ve son değerini karşılaştırarak genel yönü belirler."""
    if len(points) < 2:
        return DemandTrend.STABLE

    first: Decimal = points[0].value
    last: Decimal = points[-1].value

    if first == 0:
        # Sıfırdan başlayan bir seride yüzdesel değişim tanımsızdır; mutlak farka bakılır.
        if last > 0:
            return DemandTrend.INCREASING
        return DemandTrend.STABLE

    difference: Decimal = (last - first) / first * Decimal("100")
    if difference > STABILITY_THRESHOLD_PERCENT:
        return DemandTrend.INCREASING
    if difference < -STABILITY_THRESHOLD_PERCENT:
        return DemandTrend.DECREASING
    return DemandTrend.STABLE


def detect_consecutive_decline(values: List[Optional[Decimal]], years: int) -> bool:
    """Son N değerin üst üste düşüp düşmediğini kontrol eder."""
    # Erken uyarı servisinde "taban puan iki yıl üst üste düştü" gibi kurallar için kullanılır.
    window = [value for value in values[-(years + 1):] if value is not None]
    if len(window) < years + 1:
        return False
    return all(window[i] < window[i - 1] for i in range(1, len(window)))
