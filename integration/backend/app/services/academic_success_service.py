"""Akademik başarı analizi servisi.

Üniversite → fakülte → bölüm → program kırılımında başarı göstergeleri üretir.

Temel kural: fakülte ve bölüm oranları hiçbir yerde SAKLANMAZ. Program
satırlarından, ölçülen öğrenci sayısına göre AĞIRLIKLI ORTALAMA ile hesaplanır.

Neden ağırlıklı: 40 öğrencili bir programın %95 geçme oranı ile 600 öğrencili
bir programın %70 geçme oranının basit ortalaması %82,5 çıkar. Oysa gerçek
fakülte oranı %71,6'dır. Basit ortalama küçük programları büyükler kadar
etkili sayar ve fakülte performansını olduğundan iyi gösterir.
"""

from decimal import Decimal
from typing import Dict, List, Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.decimal_types import quantize_money
from app.models import (
    AcademicProgram,
    AcademicStaff,
    AcademicSuccessRecord,
    Department,
    Faculty,
)

ZERO = Decimal("0")
HUNDRED = Decimal("100")

# Bir seviyenin "en iyi / en zayıf" listesine girmesi için gereken en az
# öğrenci sayısı. 3 öğrencili bir programın %100 geçme oranı sıralamanın
# başına çıkarsa liste yanıltıcı olur.
MIN_STUDENTS_FOR_RANKING = 30


def _weighted_average(pairs: List[tuple]) -> Optional[Decimal]:
    """(değer, ağırlık) çiftlerinden ağırlıklı ortalama hesaplar.

    Ağırlık toplamı sıfırsa ortalama tanımsızdır ve None döner; sıfır
    döndürmek "başarı oranı %0" anlamına gelirdi.
    """
    total_weight = sum(Decimal(str(w)) for _, w in pairs)
    if total_weight == ZERO:
        return None
    total = sum(Decimal(str(v)) * Decimal(str(w)) for v, w in pairs)
    return quantize_money(total / total_weight)


def _load_records(
    db: Session,
    academic_year: Optional[str] = None,
    faculty_id: Optional[int] = None,
    department_id: Optional[int] = None,
    academic_program_id: Optional[int] = None,
) -> List[AcademicSuccessRecord]:
    """Filtrelenmiş başarı kayıtlarını ilişkileriyle birlikte getirir."""
    query = select(AcademicSuccessRecord).options(
        selectinload(AcademicSuccessRecord.academic_program)
        .selectinload(AcademicProgram.department)
        .selectinload(Department.faculty)
    )
    if academic_year:
        query = query.where(AcademicSuccessRecord.academic_year == academic_year)
    if academic_program_id:
        query = query.where(
            AcademicSuccessRecord.academic_program_id == academic_program_id
        )
    records = list(db.execute(query).scalars().unique())

    # Fakülte/bölüm filtresi program ilişkisi üzerinden uygulanıyor.
    if department_id:
        records = [
            r for r in records if r.academic_program.department_id == department_id
        ]
    if faculty_id:
        records = [
            r
            for r in records
            if r.academic_program.department
            and r.academic_program.department.faculty_id == faculty_id
        ]
    return records


def available_years(db: Session) -> List[str]:
    """Başarı verisi bulunan akademik yıllar."""
    rows = db.execute(
        select(AcademicSuccessRecord.academic_year)
        .distinct()
        .order_by(AcademicSuccessRecord.academic_year)
    ).scalars()
    return list(rows)


def _aggregate(records: List[AcademicSuccessRecord]) -> dict:
    """Kayıt listesinden ağırlıklı özet üretir."""
    if not records:
        return {}

    weights = [(r.course_pass_rate, r.measured_student_count) for r in records]
    pass_rate = _weighted_average(weights)

    return {
        "measured_student_count": sum(r.measured_student_count for r in records),
        "course_pass_rate": pass_rate,
        # Kalma oranı ayrı saklanmaz; geçme oranından türetilir ki
        # ikisinin toplamı her zaman tam 100 etsin.
        "course_fail_rate": (
            quantize_money(HUNDRED - pass_rate) if pass_rate is not None else None
        ),
        "average_success_score": _weighted_average(
            [(r.average_success_score, r.measured_student_count) for r in records]
        ),
        "dropout_rate": _weighted_average(
            [(r.dropout_rate, r.measured_student_count) for r in records]
        ),
        "graduation_rate": _weighted_average(
            [(r.graduation_rate, r.measured_student_count) for r in records]
        ),
        "graduate_count": sum(r.graduate_count for r in records),
        "program_count": len({r.academic_program_id for r in records}),
    }


def _previous_year(academic_year: str) -> str:
    """'2025-2026' -> '2024-2025'."""
    try:
        start, end = academic_year.split("-")
        return f"{int(start) - 1}-{int(end) - 1}"
    except (ValueError, AttributeError):
        return ""


def _with_change(current: dict, previous: dict) -> dict:
    """Özete önceki döneme göre değişimi ekler.

    Önceki dönem verisi yoksa değişim alanları None kalır; sıfır yazmak
    "değişim olmadı" anlamına gelirdi ve veri eksikliğini gizlerdi.
    """
    result = dict(current)
    for key in ("course_pass_rate", "average_success_score", "dropout_rate", "graduation_rate"):
        current_value = current.get(key)
        previous_value = previous.get(key) if previous else None
        change_key = f"{key}_change"
        if current_value is None or previous_value is None:
            result[change_key] = None
        else:
            result[change_key] = quantize_money(
                Decimal(str(current_value)) - Decimal(str(previous_value))
            )
    result["previous_academic_year"] = previous.get("_year") if previous else None
    return result


# ----------------------------------------------------------------------------
# Üniversite geneli
# ----------------------------------------------------------------------------


def university_overview(db: Session, academic_year: str) -> dict:
    """Üniversite geneli başarı özeti ve önceki döneme göre değişim."""
    records = _load_records(db, academic_year=academic_year)
    if not records:
        years = available_years(db)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"'{academic_year}' için başarı verisi yok. "
                f"Mevcut dönemler: {', '.join(years) if years else 'hiç yok'}."
            ),
        )

    current = _aggregate(records)
    previous_year = _previous_year(academic_year)
    previous_records = _load_records(db, academic_year=previous_year)
    previous = _aggregate(previous_records)
    if previous:
        previous["_year"] = previous_year

    summary = _with_change(current, previous)
    summary["academic_year"] = academic_year
    summary["scope"] = "Üniversite geneli"

    # Öğrenci sayısı ile başarı ilişkisi ve akademisyen başına öğrenci
    # ilişkisi ayrı endpoint'lerde değil burada da özetleniyor ki pano
    # tek çağrıda dolsun.
    summary["faculty_count"] = len(
        {
            r.academic_program.department.faculty_id
            for r in records
            if r.academic_program.department
        }
    )
    summary["department_count"] = len(
        {r.academic_program.department_id for r in records}
    )
    return summary


# ----------------------------------------------------------------------------
# Kırılımlar
# ----------------------------------------------------------------------------


def by_faculty(db: Session, academic_year: str) -> List[dict]:
    """Fakülte bazlı başarı özeti."""
    records = _load_records(db, academic_year=academic_year)
    previous_records = _load_records(db, academic_year=_previous_year(academic_year))

    groups: Dict[int, List[AcademicSuccessRecord]] = {}
    names: Dict[int, str] = {}
    for record in records:
        department = record.academic_program.department
        if not department or not department.faculty:
            continue
        groups.setdefault(department.faculty_id, []).append(record)
        names[department.faculty_id] = department.faculty.name

    previous_groups: Dict[int, List[AcademicSuccessRecord]] = {}
    for record in previous_records:
        department = record.academic_program.department
        if department:
            previous_groups.setdefault(department.faculty_id, []).append(record)

    rows = []
    for faculty_id, items in groups.items():
        summary = _with_change(
            _aggregate(items), _aggregate(previous_groups.get(faculty_id, []))
        )
        summary["faculty_id"] = faculty_id
        summary["faculty_name"] = names[faculty_id]
        summary["academic_year"] = academic_year
        rows.append(summary)

    rows.sort(key=lambda r: r["course_pass_rate"] or ZERO, reverse=True)
    return rows


def by_department(
    db: Session, academic_year: str, faculty_id: Optional[int] = None
) -> List[dict]:
    """Bölüm bazlı başarı özeti. Fakülte verilirse yalnızca o fakültenin bölümleri."""
    records = _load_records(db, academic_year=academic_year, faculty_id=faculty_id)
    previous_records = _load_records(
        db, academic_year=_previous_year(academic_year), faculty_id=faculty_id
    )

    groups: Dict[int, List[AcademicSuccessRecord]] = {}
    meta: Dict[int, dict] = {}
    for record in records:
        department = record.academic_program.department
        if not department:
            continue
        groups.setdefault(department.id, []).append(record)
        meta[department.id] = {
            "department_name": department.name,
            "department_code": department.code,
            "faculty_id": department.faculty_id,
            "faculty_name": department.faculty.name if department.faculty else None,
        }

    previous_groups: Dict[int, List[AcademicSuccessRecord]] = {}
    for record in previous_records:
        if record.academic_program.department:
            previous_groups.setdefault(
                record.academic_program.department_id, []
            ).append(record)

    rows = []
    for department_id, items in groups.items():
        summary = _with_change(
            _aggregate(items), _aggregate(previous_groups.get(department_id, []))
        )
        summary.update(meta[department_id])
        summary["department_id"] = department_id
        summary["academic_year"] = academic_year
        rows.append(summary)

    rows.sort(key=lambda r: r["course_pass_rate"] or ZERO, reverse=True)
    return rows


def by_program(
    db: Session,
    academic_year: str,
    faculty_id: Optional[int] = None,
    department_id: Optional[int] = None,
) -> List[dict]:
    """Program bazlı başarı listesi — en alt kırılım."""
    records = _load_records(
        db,
        academic_year=academic_year,
        faculty_id=faculty_id,
        department_id=department_id,
    )
    previous_records = {
        r.academic_program_id: r
        for r in _load_records(db, academic_year=_previous_year(academic_year))
    }

    # Akademisyen başına öğrenci sayısı ile başarı ilişkisini gösterebilmek
    # için bölüm bazlı personel sayısı gerekiyor.
    staff_counts: Dict[int, int] = {}
    for staff in db.execute(
        select(AcademicStaff).where(AcademicStaff.is_active.is_(True))
    ).scalars():
        staff_counts[staff.department_id] = staff_counts.get(staff.department_id, 0) + 1

    rows = []
    for record in records:
        program = record.academic_program
        department = program.department
        previous = previous_records.get(record.academic_program_id)

        current = {
            "measured_student_count": record.measured_student_count,
            "course_pass_rate": record.course_pass_rate,
            "course_fail_rate": record.course_fail_rate,
            "average_success_score": record.average_success_score,
            "dropout_rate": record.dropout_rate,
            "graduation_rate": record.graduation_rate,
            "graduate_count": record.graduate_count,
        }
        previous_summary = (
            {
                "course_pass_rate": previous.course_pass_rate,
                "average_success_score": previous.average_success_score,
                "dropout_rate": previous.dropout_rate,
                "graduation_rate": previous.graduation_rate,
                "_year": previous.academic_year,
            }
            if previous
            else {}
        )

        summary = _with_change(current, previous_summary)
        summary.update(
            {
                "academic_year": academic_year,
                "program_id": program.id,
                "program_code": program.code,
                "program_name": program.name,
                "department_id": program.department_id,
                "department_name": department.name if department else None,
                "faculty_id": department.faculty_id if department else None,
                "faculty_name": (
                    department.faculty.name if department and department.faculty else None
                ),
                "quota": program.quota,
            }
        )

        # Akademisyen başına öğrenci: bölümün öğrenci sayısı bilinmediği için
        # program ölçüm sayısı kullanılıyor; bölümdeki program sayısına bölünmüyor
        # çünkü personel bölüm genelinde ortak.
        staff = staff_counts.get(program.department_id, 0)
        summary["department_staff_count"] = staff
        summary["students_per_staff"] = (
            quantize_money(Decimal(record.measured_student_count) / Decimal(staff))
            if staff
            else None
        )
        rows.append(summary)

    rows.sort(key=lambda r: r["course_pass_rate"] or ZERO, reverse=True)
    return rows


# ----------------------------------------------------------------------------
# Trend ve sıralamalar
# ----------------------------------------------------------------------------


def trend(
    db: Session,
    faculty_id: Optional[int] = None,
    department_id: Optional[int] = None,
    academic_program_id: Optional[int] = None,
) -> List[dict]:
    """Akademik dönemlere göre başarı trendi."""
    rows = []
    for year in available_years(db):
        records = _load_records(
            db,
            academic_year=year,
            faculty_id=faculty_id,
            department_id=department_id,
            academic_program_id=academic_program_id,
        )
        if not records:
            continue
        summary = _aggregate(records)
        summary["academic_year"] = year
        rows.append(summary)
    return rows


def rankings(db: Session, academic_year: str, level: str = "faculty") -> dict:
    """En başarılı ve en düşük başarılı birimler.

    Küçük birimlerin uç değerleri listeyi yanıltmasın diye en az
    MIN_STUDENTS_FOR_RANKING öğrencisi olan birimler değerlendirilir.
    """
    if level == "faculty":
        rows = by_faculty(db, academic_year)
        name_key = "faculty_name"
    elif level == "department":
        rows = by_department(db, academic_year)
        name_key = "department_name"
    elif level == "program":
        rows = by_program(db, academic_year)
        name_key = "program_name"
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="level alanı faculty, department veya program olmalı.",
        )

    eligible = [
        r for r in rows if r["measured_student_count"] >= MIN_STUDENTS_FOR_RANKING
    ]
    excluded = len(rows) - len(eligible)

    ranked = sorted(eligible, key=lambda r: r["course_pass_rate"] or ZERO, reverse=True)
    return {
        "academic_year": academic_year,
        "level": level,
        "top": [
            {"name": r[name_key], "course_pass_rate": r["course_pass_rate"],
             "average_success_score": r["average_success_score"],
             "measured_student_count": r["measured_student_count"]}
            for r in ranked[:5]
        ],
        "bottom": [
            {"name": r[name_key], "course_pass_rate": r["course_pass_rate"],
             "average_success_score": r["average_success_score"],
             "measured_student_count": r["measured_student_count"]}
            for r in reversed(ranked[-5:])
        ],
        "excluded_small_units": excluded,
        "minimum_student_threshold": MIN_STUDENTS_FOR_RANKING,
        "note": (
            f"Sıralamaya yalnızca en az {MIN_STUDENTS_FOR_RANKING} öğrencisi ölçülen "
            f"birimler alınır. {excluded} birim bu eşiğin altında kaldığı için listelenmedi."
        ),
    }


def correlations(db: Session, academic_year: str) -> dict:
    """Öğrenci sayısı ve akademisyen başına öğrenci ile başarı ilişkisi.

    Pearson korelasyon katsayısı hesaplanır. Katsayı tek başına neden-sonuç
    kanıtlamaz; arayüzde bu uyarı gösterilir.
    """
    programs = by_program(db, academic_year)
    if len(programs) < 3:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"'{academic_year}' için ilişki analizi yapılacak kadar program verisi yok "
                f"(en az 3 gerekli, {len(programs)} bulundu)."
            ),
        )

    def pearson(xs: List[Decimal], ys: List[Decimal]) -> Optional[Decimal]:
        n = Decimal(len(xs))
        if n < 3:
            return None
        mean_x = sum(xs) / n
        mean_y = sum(ys) / n
        cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
        var_x = sum((x - mean_x) ** 2 for x in xs)
        var_y = sum((y - mean_y) ** 2 for y in ys)
        if var_x == ZERO or var_y == ZERO:
            return None
        denominator = (var_x * var_y).sqrt()
        return quantize_money(cov / denominator)

    size_pairs = [
        (Decimal(p["measured_student_count"]), Decimal(str(p["course_pass_rate"])))
        for p in programs
        if p["course_pass_rate"] is not None
    ]
    staff_pairs = [
        (Decimal(str(p["students_per_staff"])), Decimal(str(p["course_pass_rate"])))
        for p in programs
        if p["students_per_staff"] is not None and p["course_pass_rate"] is not None
    ]

    size_corr = pearson([a for a, _ in size_pairs], [b for _, b in size_pairs])
    staff_corr = pearson([a for a, _ in staff_pairs], [b for _, b in staff_pairs])

    def interpret(value: Optional[Decimal], subject: str) -> str:
        if value is None:
            return f"{subject} için ilişki hesaplanamadı (yeterli veri yok)."
        magnitude = abs(value)
        if magnitude < Decimal("0.2"):
            strength = "anlamlı bir ilişki görünmüyor"
        elif magnitude < Decimal("0.5"):
            strength = "zayıf bir ilişki var"
        elif magnitude < Decimal("0.7"):
            strength = "orta düzeyde bir ilişki var"
        else:
            strength = "güçlü bir ilişki var"
        direction = "ters yönlü" if value < ZERO else "aynı yönlü"
        return f"{subject}: {strength} ({direction}, r = {value})."

    return {
        "academic_year": academic_year,
        "program_count": len(programs),
        "student_count_vs_pass_rate": size_corr,
        "students_per_staff_vs_pass_rate": staff_corr,
        "interpretation": [
            interpret(size_corr, "Öğrenci sayısı ile ders geçme oranı"),
            interpret(staff_corr, "Akademisyen başına öğrenci ile ders geçme oranı"),
        ],
        "caveat": (
            "Korelasyon nedensellik değildir. Bu katsayılar yalnızca birlikte "
            "hareket etmeyi gösterir; bir değişkenin diğerine sebep olduğunu kanıtlamaz."
        ),
    }
