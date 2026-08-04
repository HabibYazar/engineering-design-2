"""Modül 3 — Stratejik Eğitim ve Öğrenci Analitiği hesaplama servisi.

PDF Bölüm 3'te sayılan göstergelerin tamamı burada üretilir:
toplam/aktif/yeni kayıt/mezun sayıları, kontenjan doluluk oranı, mezuniyet oranı,
hazırlık öğrenci sayısı, ortalama mezuniyet süresi, öğrenci kaybı ve kayıt
yenilememe oranları, burslu ve uluslararası öğrenci yüzdeleri, taban puan analizi
ve program talep trendi.

Hesaplamalar veritabanından okunan satırlar üzerinde Python'da yapılır; veri hacmi
küçük olduğu için bu tercih okunabilirliği artırır ve her formülün demoda satır
satır gösterilmesini kolaylaştırır.
"""

from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    AcademicProgram,
    ProgramEnrollmentSnapshot,
    Student,
    StudentAcademicRecord,
)

# Aktif öğrencilik sayılan durumlar.
ACTIVE_STATUSES = {"active", "newly-enrolled"}


def _to_float(value) -> Optional[float]:
    """Numeric kolonlardan gelen Decimal değerleri float'a çevirir."""
    return None if value is None else float(value)


def _rate(numerator: float, denominator: float) -> float:
    """Yüzde hesaplar; payda sıfırsa 0.0 döndürür."""
    if not denominator:
        return 0.0
    return round(numerator / denominator * 100, 2)


def _left_year(student: Student) -> Optional[int]:
    """Öğrencinin okuldan ayrıldığı yılı döndürür; hâlâ kayıtlıysa None."""
    if student.actual_graduation_year is not None:
        return student.actual_graduation_year
    return student.status_change_year


def _is_enrolled_in_year(student: Student, year: int) -> bool:
    """Öğrencinin verilen takvim yılında programa kayıtlı olup olmadığını söyler."""
    if student.enrollment_year is None or student.enrollment_year > year:
        return False
    left = _left_year(student)
    return left is None or left > year


def _start_year(academic_year: str) -> int:
    """'2026-2027' -> 2026."""
    return int(academic_year.split("-")[0])


def get_available_academic_years(db: Session) -> List[str]:
    """Veride bulunan akademik yılları eskiden yeniye sıralı döndürür."""
    rows = db.execute(
        select(ProgramEnrollmentSnapshot.academic_year).distinct()
    ).scalars().all()
    return sorted(rows)


def _load_programs(db: Session) -> List[AcademicProgram]:
    """Programları öğrenci ve snapshot ilişkileriyle birlikte yükler."""
    statement = (
        select(AcademicProgram)
        .options(
            selectinload(AcademicProgram.students),
            selectinload(AcademicProgram.enrollment_snapshots),
        )
        .order_by(AcademicProgram.code)
    )
    return list(db.execute(statement).scalars().all())


def _snapshot_for(program: AcademicProgram, academic_year: str):
    """Programın verilen akademik yıla ait kayıt fotoğrafını döndürür."""
    for snapshot in program.enrollment_snapshots:
        if snapshot.academic_year == academic_year:
            return snapshot
    return None


def _graduation_stats(students: List[Student], current_year: int) -> Dict[str, float]:
    """Mezuniyet oranını ve ortalama mezuniyet süresini hesaplar.

    Mezuniyet oranı, yalnızca beklenen mezuniyet yılı geçmiş kohortlar üzerinden
    hesaplanır; hâlâ okuyan öğrenciler paydayı bozmasın diye dışarıda tutulur.
    """
    finished_cohort = [
        s
        for s in students
        if s.expected_graduation_year is not None
        and s.expected_graduation_year <= current_year
    ]
    graduated = [s for s in finished_cohort if s.current_status == "graduated"]

    durations = [
        s.actual_graduation_year - s.enrollment_year
        for s in students
        if s.actual_graduation_year is not None and s.enrollment_year is not None
    ]

    return {
        "graduation_rate": _rate(len(graduated), len(finished_cohort)),
        "graduation_cohort_size": len(finished_cohort),
        "average_time_to_graduation": (
            round(sum(durations) / len(durations), 2) if durations else 0.0
        ),
    }


def _employment_stats(students: List[Student]) -> Dict[str, float]:
    """Mezun istihdam oranını hesaplar (PDF: "Graduate employment rate").

    Yalnızca mezun öğrenciler paydadır; hâlâ okuyanlar veya terk edenler
    istihdam durumuyla ilgisiz olduğundan dışarıda tutulur.
    """
    graduates = [s for s in students if s.current_status == "graduated"]
    employed = [s for s in graduates if s.is_employed]
    return {
        "employment_rate": _rate(len(employed), len(graduates)),
        "employed_graduate_count": len(employed),
    }


def _student_composition(students: List[Student]) -> Dict[str, float]:
    """Uluslararası, burslu ve hazırlık öğrenci göstergelerini hesaplar."""
    total = len(students)
    international = sum(1 for s in students if s.is_international)
    scholarship = sum(1 for s in students if float(s.scholarship_rate_percent or 0) > 0)
    preparatory = sum(1 for s in students if s.preparatory_school)

    gpas = [float(s.current_gpa) for s in students if s.current_gpa is not None]

    return {
        "international_student_percentage": _rate(international, total),
        "scholarship_student_percentage": _rate(scholarship, total),
        "preparatory_student_count": preparatory,
        "average_gpa": round(sum(gpas) / len(gpas), 2) if gpas else 0.0,
    }


def build_program_metrics(
    program: AcademicProgram, academic_year: str
) -> Optional[Dict]:
    """Tek bir program için verilen akademik yılın tüm göstergelerini üretir."""
    snapshot = _snapshot_for(program, academic_year)
    if snapshot is None:
        return None

    year = _start_year(academic_year)
    students = list(program.students)

    # O yıl fiilen kayıtlı olan öğrenci gövdesi — kayıp oranlarının paydası budur.
    enrolled_body = [s for s in students if _is_enrolled_in_year(s, year)]

    active = [s for s in students if s.current_status in ACTIVE_STATUSES]
    newly_enrolled = [s for s in students if s.current_status == "newly-enrolled"]
    graduated_total = [s for s in students if s.current_status == "graduated"]

    occupancy_rate = _rate(snapshot.enrolled_student_count, snapshot.quota)

    metrics: Dict = {
        "program_code": program.code,
        "program_name": program.name,
        "academic_year": academic_year,
        # --- Kontenjan ve doluluk ---
        "quota": snapshot.quota,
        "enrolled_student_count": snapshot.enrolled_student_count,
        "occupancy_rate": occupancy_rate,
        # --- Öğrenci sayıları ---
        "total_students": len(students),
        "active_student_count": len(active),
        "newly_enrolled_student_count": len(newly_enrolled),
        "graduated_student_count_total": len(graduated_total),
        "graduated_student_count_in_year": snapshot.graduated_student_count,
        "student_body_in_year": len(enrolled_body),
        # --- Öğrenci kaybı (PDF: attrition & non-renewal) ---
        "dropped_out_student_count": snapshot.dropped_out_student_count,
        "non_renewed_student_count": snapshot.non_renewed_student_count,
        "attrition_rate": _rate(snapshot.dropped_out_student_count, len(enrolled_body)),
        "non_renewal_rate": _rate(snapshot.non_renewed_student_count, len(enrolled_body)),
        # --- Taban puan ---
        "minimum_admission_score": _to_float(snapshot.minimum_admission_score),
        "national_average_minimum_score": _to_float(snapshot.national_average_minimum_score),
        "ankara_average_minimum_score": _to_float(snapshot.ankara_average_minimum_score),
        "full_scholarship_minimum_admission_score": _to_float(
            snapshot.full_scholarship_minimum_admission_score
        ),
    }

    metrics.update(_graduation_stats(students, year))
    metrics.update(_student_composition(students))
    metrics.update(_employment_stats(students))

    # Taban puanın Ankara ve Türkiye ortalamasına göre farkı (PDF: taban puan analizi).
    score = metrics["minimum_admission_score"]
    national = metrics["national_average_minimum_score"]
    ankara = metrics["ankara_average_minimum_score"]
    metrics["national_score_gap"] = (
        round(score - national, 2) if score is not None and national is not None else None
    )
    metrics["ankara_score_gap"] = (
        round(score - ankara, 2) if score is not None and ankara is not None else None
    )

    return metrics


def get_program_metrics(db: Session, academic_year: str) -> List[Dict]:
    """Tüm programların göstergelerini doluluk oranına göre artan sırada döndürür."""
    programs = _load_programs(db)
    metrics = [
        m
        for m in (build_program_metrics(p, academic_year) for p in programs)
        if m is not None
    ]
    return sorted(metrics, key=lambda m: m["occupancy_rate"])


def get_program_detail(db: Session, program_code: str, academic_year: str) -> Optional[Dict]:
    """Tek bir programın göstergelerini kod ile getirir."""
    programs = _load_programs(db)
    for program in programs:
        if program.code.upper() == program_code.upper():
            return build_program_metrics(program, academic_year)
    return None


def get_university_overview(db: Session, academic_year: str) -> Dict:
    """Üniversite geneli konsolide öğrenci göstergelerini üretir."""
    programs = _load_programs(db)
    year = _start_year(academic_year)

    all_students: List[Student] = []
    total_quota = 0
    total_enrolled = 0
    total_dropped = 0
    total_non_renewed = 0
    total_graduated_in_year = 0
    program_count = 0

    for program in programs:
        snapshot = _snapshot_for(program, academic_year)
        if snapshot is None:
            continue
        program_count += 1
        all_students.extend(program.students)
        total_quota += snapshot.quota
        total_enrolled += snapshot.enrolled_student_count
        total_dropped += snapshot.dropped_out_student_count
        total_non_renewed += snapshot.non_renewed_student_count
        total_graduated_in_year += snapshot.graduated_student_count

    enrolled_body = [s for s in all_students if _is_enrolled_in_year(s, year)]

    overview: Dict = {
        "academic_year": academic_year,
        "program_count": program_count,
        "total_students": len(all_students),
        "active_student_count": sum(
            1 for s in all_students if s.current_status in ACTIVE_STATUSES
        ),
        "newly_enrolled_student_count": sum(
            1 for s in all_students if s.current_status == "newly-enrolled"
        ),
        "graduated_student_count_total": sum(
            1 for s in all_students if s.current_status == "graduated"
        ),
        "graduated_student_count_in_year": total_graduated_in_year,
        "student_body_in_year": len(enrolled_body),
        "total_quota": total_quota,
        "total_enrolled_student_count": total_enrolled,
        "overall_occupancy_rate": _rate(total_enrolled, total_quota),
        "dropped_out_student_count": total_dropped,
        "non_renewed_student_count": total_non_renewed,
        "attrition_rate": _rate(total_dropped, len(enrolled_body)),
        "non_renewal_rate": _rate(total_non_renewed, len(enrolled_body)),
    }
    overview.update(_graduation_stats(all_students, year))
    overview.update(_student_composition(all_students))
    overview.update(_employment_stats(all_students))
    return overview


def get_admission_score_analysis(db: Session, academic_year: str) -> List[Dict]:
    """Taban puanları Ankara ve Türkiye ortalamalarıyla karşılaştırır (PDF Bölüm 3)."""
    results = []
    for metrics in get_program_metrics(db, academic_year):
        score = metrics["minimum_admission_score"]
        ankara_gap = metrics["ankara_score_gap"]
        national_gap = metrics["national_score_gap"]

        if ankara_gap is None or national_gap is None:
            position = "veri yok"
        elif ankara_gap >= 0 and national_gap >= 0:
            position = "her iki ortalamanın üzerinde"
        elif national_gap >= 0:
            position = "Türkiye ortalamasının üzerinde, Ankara ortalamasının altında"
        else:
            position = "her iki ortalamanın altında"

        results.append(
            {
                "program_code": metrics["program_code"],
                "program_name": metrics["program_name"],
                "academic_year": academic_year,
                "minimum_admission_score": score,
                "ankara_average_minimum_score": metrics["ankara_average_minimum_score"],
                "national_average_minimum_score": metrics["national_average_minimum_score"],
                "full_scholarship_minimum_admission_score": metrics[
                    "full_scholarship_minimum_admission_score"
                ],
                "ankara_score_gap": ankara_gap,
                "national_score_gap": national_gap,
                "competitive_position": position,
            }
        )
    return sorted(results, key=lambda r: r["minimum_admission_score"] or 0, reverse=True)


def get_demand_trends(db: Session) -> List[Dict]:
    """Programların yıllar içindeki talep trendini üretir (PDF: student demand trends)."""
    programs = _load_programs(db)
    trends = []

    for program in programs:
        snapshots = sorted(program.enrollment_snapshots, key=lambda s: s.academic_year)
        if not snapshots:
            continue

        series = [
            {
                "academic_year": s.academic_year,
                "quota": s.quota,
                "enrolled_student_count": s.enrolled_student_count,
                "occupancy_rate": _rate(s.enrolled_student_count, s.quota),
                "minimum_admission_score": _to_float(s.minimum_admission_score),
                "dropped_out_student_count": s.dropped_out_student_count,
            }
            for s in snapshots
        ]

        first, last = series[0], series[-1]
        occupancy_change = round(last["occupancy_rate"] - first["occupancy_rate"], 2)
        score_change = (
            round(last["minimum_admission_score"] - first["minimum_admission_score"], 2)
            if last["minimum_admission_score"] is not None
            and first["minimum_admission_score"] is not None
            else None
        )

        if occupancy_change <= -10:
            direction = "keskin düşüş"
        elif occupancy_change < -2:
            direction = "düşüş"
        elif occupancy_change <= 2:
            direction = "yatay"
        else:
            direction = "artış"

        trends.append(
            {
                "program_code": program.code,
                "program_name": program.name,
                "series": series,
                "occupancy_change_points": occupancy_change,
                "admission_score_change": score_change,
                "demand_direction": direction,
            }
        )

    return sorted(trends, key=lambda t: t["occupancy_change_points"])


def get_academic_performance_trend(db: Session) -> List[Dict]:
    """Program bazında yıllara göre ortalama dönem GNO'sunu döndürür.

    Modül 11'in "akademik göstergeler düşüyor" kuralı bu trendi kullanır.
    """
    statement = (
        select(
            AcademicProgram.code,
            AcademicProgram.name,
            StudentAcademicRecord.academic_year,
            StudentAcademicRecord.semester_gpa,
        )
        .join(Student, Student.academic_program_id == AcademicProgram.id)
        .join(StudentAcademicRecord, StudentAcademicRecord.student_id == Student.id)
    )

    buckets: Dict[str, Dict[str, List[float]]] = {}
    names: Dict[str, str] = {}

    for code, name, academic_year, semester_gpa in db.execute(statement):
        if semester_gpa is None:
            continue
        names[code] = name
        buckets.setdefault(code, {}).setdefault(academic_year, []).append(float(semester_gpa))

    results = []
    for code, per_year in sorted(buckets.items()):
        series = [
            {"academic_year": year, "average_semester_gpa": round(sum(v) / len(v), 3)}
            for year, v in sorted(per_year.items())
        ]
        change = (
            round(series[-1]["average_semester_gpa"] - series[0]["average_semester_gpa"], 3)
            if len(series) > 1
            else 0.0
        )
        results.append(
            {
                "program_code": code,
                "program_name": names[code],
                "series": series,
                "gpa_change": change,
            }
        )
    return results


def get_comparative_analysis(
    db: Session, academic_year: str, comparators: Dict[str, List[Dict]]
) -> List[Dict]:
    """Benzer/rakip üniversitelerle program bazlı karşılaştırma üretir.

    PDF Bölüm 3: "Comparative analyses of student enrollment across similar
    universities and academic departments." Kıyaslama verisi bu modülün
    kapsamı dışındadır (Modül 13 tarafından sağlanır); burada uydurulmaz,
    yalnızca çağıran tarafından verilen veriyle karşılaştırma hesaplanır.
    """
    own_metrics = {m["program_code"]: m for m in get_program_metrics(db, academic_year)}
    results: List[Dict] = []

    for program_code, comparator_list in comparators.items():
        own = own_metrics.get(program_code)
        if own is None:
            continue

        occupancy_values = [
            c["occupancy_rate"] for c in comparator_list if c.get("occupancy_rate") is not None
        ]
        score_values = [
            c["minimum_admission_score"]
            for c in comparator_list
            if c.get("minimum_admission_score") is not None
        ]

        avg_occupancy = (
            round(sum(occupancy_values) / len(occupancy_values), 2) if occupancy_values else None
        )
        avg_score = round(sum(score_values) / len(score_values), 2) if score_values else None

        occupancy_gap = (
            round(own["occupancy_rate"] - avg_occupancy, 2) if avg_occupancy is not None else None
        )
        admission_score = own["minimum_admission_score"]
        score_gap = (
            round(admission_score - avg_score, 2)
            if avg_score is not None and admission_score is not None
            else None
        )

        if occupancy_gap is None:
            position = "veri yok"
        elif occupancy_gap >= 0:
            position = "kıyaslama grubunun üzerinde"
        else:
            position = "kıyaslama grubunun altında"

        results.append(
            {
                "program_code": program_code,
                "program_name": own["program_name"],
                "academic_year": academic_year,
                "own_occupancy_rate": own["occupancy_rate"],
                "own_minimum_admission_score": admission_score,
                "comparators": comparator_list,
                "average_comparator_occupancy_rate": avg_occupancy,
                "average_comparator_admission_score": avg_score,
                "occupancy_gap_vs_comparators": occupancy_gap,
                "admission_score_gap_vs_comparators": score_gap,
                "competitive_position": position,
            }
        )

    return sorted(results, key=lambda r: r["program_code"])
