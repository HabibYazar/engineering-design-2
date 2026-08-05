"""Tüm ekip modüllerinin ortak demo verisini tek komutla yükler.

Çalıştırma:
    python seed_all_demo_data.py

Bu script idempotenttir: kaç kez çalıştırılırsa çalıştırılsın aynı veri oluşur,
kayıtlar çoğalmaz. Kod ile birlikte demoya girmeden önce güvenle tekrar
çalıştırılabilir.

Neden ayrı bir script: her modülün kendi seed dosyası vardı ve her biri farklı
sayıda fakülte/bölüm varsayıyordu. Sunumda "Modül 5 bana 9 mekân diyor ama
Modül 2 bana 120 öğrenci diyor" gibi tutarsızlıklar çıkıyordu. Artık ekranda
görünen bütün sayılar integration/shared_demo_data/ altındaki JSON dosyalarından
türetiliyor; tek doğruluk kaynağı orası.

Mevcut modül seed'leri (seed_data, seed_scenario_data, seed_student_data,
seed_ranking_data) DEĞİŞTİRİLMEDİ; bu script onları önce çalıştırır, sonra
ortak veri setini üzerine ekler. Böylece 412 birim testi de bozulmadan kalır.
"""

import json
import random
import sys
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.decimal_types import quantize_money
from app.database import SessionLocal, init_db
from app.models import (
    AcademicProgram,
    AcademicStaff,
    AcademicSuccessRecord,
    AdministrativeUnit,
    Department,
    DepartmentBudget,
    Faculty,
    FinancialEntry,
    FinancialPeriod,
    IndustryCollaborationRecord,
    KpiFacultyValue,
    PhysicalFacility,
    ProgramEnrollmentSnapshot,
    RegionalContributionRecord,
    StrategicKpi,
    Student,
    SystemUser,
)
from app.services.auth_service import hash_password

# Ortak veri klasörü backend'in bir üstünde: integration/shared_demo_data/
DATA_DIR = Path(__file__).resolve().parent.parent / "shared_demo_data"


def load(filename: str) -> dict:
    """Ortak veri dosyasını okur; yoksa ne yapılması gerektiğini söyler."""
    path = DATA_DIR / filename
    if not path.exists():
        raise SystemExit(
            f"Ortak veri dosyasi bulunamadi: {path}\n"
            "integration/shared_demo_data/ klasorunun yerinde oldugundan emin olun."
        )
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


class Counter:
    """Eklenen ve zaten mevcut olan kayıtları modül bazında sayar."""

    def __init__(self) -> None:
        self.rows: List[tuple] = []

    def add(self, label: str, created: int, existing: int) -> None:
        self.rows.append((label, created, existing))

    def report(self) -> None:
        print("\n" + "=" * 68)
        print(f"{'Veri kumesi':<38}{'Eklenen':>12}{'Mevcut':>14}")
        print("-" * 68)
        for label, created, existing in self.rows:
            print(f"{label:<38}{created:>12}{existing:>14}")
        print("=" * 68)
        print(f"{'TOPLAM':<38}"
              f"{sum(r[1] for r in self.rows):>12}"
              f"{sum(r[2] for r in self.rows):>14}")


# ----------------------------------------------------------------------------
# 1) Üniversite yapısı (Modül 1)
# ----------------------------------------------------------------------------


def seed_structure(db: Session, counter: Counter) -> None:
    """Fakülte, bölüm, program ve idari birimleri ekler."""
    data = load("01_university_structure.json")

    created = existing = 0
    faculties: Dict[str, Faculty] = {}
    for row in data["faculties"]:
        obj = db.execute(
            select(Faculty).where(Faculty.code == row["code"])
        ).scalars().first()
        if obj is None:
            obj = Faculty(
                code=row["code"], name=row["name"], description=row["description"]
            )
            db.add(obj)
            db.flush()
            created += 1
        else:
            existing += 1
        faculties[row["code"]] = obj
    counter.add("Fakülteler (Modül 1)", created, existing)

    created = existing = 0
    departments: Dict[str, Department] = {}
    for row in data["departments"]:
        obj = db.execute(
            select(Department).where(Department.code == row["code"])
        ).scalars().first()
        if obj is None:
            obj = Department(
                code=row["code"],
                faculty_id=faculties[row["faculty_code"]].id,
                name=row["name"],
                description=row["description"],
            )
            db.add(obj)
            db.flush()
            created += 1
        else:
            existing += 1
        departments[row["code"]] = obj
    counter.add("Bölümler (Modül 1)", created, existing)

    created = existing = 0
    for row in data["academic_programs"]:
        obj = db.execute(
            select(AcademicProgram).where(AcademicProgram.code == row["code"])
        ).scalars().first()
        if obj is None:
            db.add(
                AcademicProgram(
                    code=row["code"],
                    department_id=departments[row["department_code"]].id,
                    name=row["name"],
                    degree_level=row["degree_level"],
                    duration_years=row["duration_years"],
                    quota=row["quota"],
                    description=row["description"],
                )
            )
            created += 1
        else:
            existing += 1
    counter.add("Akademik programlar (Modül 1)", created, existing)

    created = existing = 0
    for row in data["administrative_units"]:
        obj = db.execute(
            select(AdministrativeUnit).where(AdministrativeUnit.code == row["code"])
        ).scalars().first()
        if obj is None:
            db.add(
                AdministrativeUnit(
                    code=row["code"], name=row["name"], description=row["description"]
                )
            )
            created += 1
        else:
            existing += 1
    counter.add("İdari birimler (Modül 1)", created, existing)

    db.commit()


# ----------------------------------------------------------------------------
# 2) Öğrenciler (Modül 2 / 3)
# ----------------------------------------------------------------------------

FIRST_NAMES = (
    "Ahmet", "Ayşe", "Mehmet", "Zeynep", "Mustafa", "Elif", "Ali", "Fatma",
    "Emre", "Selin", "Burak", "Deniz", "Can", "Ece", "Kaan", "Merve",
    "Omar", "Sara", "İbrahim", "Leyla", "Hasan", "Nur", "Yusuf", "Aylin",
    "Berk", "Cansu", "Doruk", "Esra", "Furkan", "Gizem", "Hakan", "Irmak",
)
LAST_NAMES = (
    "Yılmaz", "Kaya", "Demir", "Çelik", "Şahin", "Yıldız", "Aydın", "Öztürk",
    "Arslan", "Doğan", "Kılıç", "Aslan", "Çetin", "Kara", "Koç", "Kurt",
    "Al-Sayed", "Hassan", "Petrov", "Novak", "Ahmadi", "Khan", "Özkan", "Tekin",
)
INTERNATIONAL_NATIONALITIES = (
    "Azerbaycan", "Suriye", "Irak", "İran", "Pakistan", "Nijerya", "Somali",
    "Almanya", "Kazakistan", "Türkmenistan",
)


def _weighted_choice(rng: random.Random, weights: Dict[str, int]) -> str:
    """Ağırlıklı rastgele seçim."""
    return rng.choices(list(weights), weights=list(weights.values()), k=1)[0]


def seed_students(db: Session, counter: Counter) -> None:
    """Öğrenci kayıtlarını deterministik olarak üretir."""
    spec = load("02_students.json")

    # Zaten hedef sayıya ulaşılmışsa tekrar üretme.
    current = db.execute(select(Student)).scalars().all()
    demo_numbers = {s.student_number for s in current}
    target = spec["total_students"]

    programs = {
        p.code: p
        for p in db.execute(select(AcademicProgram)).scalars()
        if p.code in spec["program_weights"]
    }
    missing = set(spec["program_weights"]) - set(programs)
    if missing:
        raise SystemExit(
            f"Ogrenci uretimi icin gerekli programlar bulunamadi: {sorted(missing)}"
        )

    rng = random.Random(spec["random_seed"])
    years = spec["enrollment_years"]
    scholarship_options = [
        (Decimal(str(item["rate_percent"])), item["weight"])
        for item in spec["scholarship_rate_distribution"]
    ]
    employment = spec["graduate_employment"]

    created = existing = 0
    for index in range(1, target + 1):
        # Öğrenci numarası deterministik: aynı index her zaman aynı numarayı verir.
        student_number = f"DEMO{index:06d}"
        if student_number in demo_numbers:
            existing += 1
            continue

        program_code = _weighted_choice(rng, spec["program_weights"])
        program = programs[program_code]
        enrollment_year = years[index % len(years)]

        status = _weighted_choice(rng, spec["status_weights"])
        # Yeni girişli bir öğrenci mezun veya ayrılmış olamaz; mantıksız veri
        # üretmemek için eski yıla ait olmayan kayıtlar aktife çevrilir.
        years_elapsed = 2026 - enrollment_year
        if status in ("graduated",) and years_elapsed < 4:
            status = "active"
        if status in ("dropped-out", "non-renewed") and years_elapsed < 1:
            status = "newly-enrolled"
        if enrollment_year == max(years) and status == "active":
            status = "newly-enrolled"

        is_international = rng.randint(1, 100) <= spec["international_student_percent"]
        scholarship = rng.choices(
            [o[0] for o in scholarship_options],
            weights=[o[1] for o in scholarship_options],
            k=1,
        )[0]

        gpa_spec = spec["gpa_range"]
        gpa = quantize_money(
            Decimal(str(rng.uniform(gpa_spec["min"], gpa_spec["max"])))
        )

        status_change_year = None
        actual_graduation_year = None
        is_employed = None
        if status in ("graduated", "dropped-out", "non-renewed"):
            status_change_year = min(2026, enrollment_year + rng.randint(1, 5))
            if status == "graduated":
                actual_graduation_year = status_change_year
                # İstihdam bilgisi mezunların yalnızca bir kısmı için biliniyor.
                if rng.randint(1, 100) <= employment["known_information_percent"]:
                    is_employed = (
                        rng.randint(1, 100) <= employment["employed_percent_among_known"]
                    )

        db.add(
            Student(
                student_number=student_number,
                first_name=rng.choice(FIRST_NAMES),
                last_name=rng.choice(LAST_NAMES),
                gender=rng.choice(("female", "male", "unspecified")),
                nationality=(
                    rng.choice(INTERNATIONAL_NATIONALITIES)
                    if is_international
                    else "Türkiye"
                ),
                is_international=is_international,
                scholarship_rate_percent=scholarship,
                enrollment_year=enrollment_year,
                current_status=status,
                status_change_year=status_change_year,
                preparatory_school=(
                    rng.randint(1, 100) <= spec["preparatory_school_percent"]
                ),
                academic_program_id=program.id,
                current_gpa=gpa,
                expected_graduation_year=enrollment_year + program.duration_years,
                actual_graduation_year=actual_graduation_year,
                is_employed=is_employed,
            )
        )
        created += 1

        # Büyük veri setinde belleği şişirmemek için ara ara yazıyoruz.
        if created % 500 == 0:
            db.commit()

    db.commit()
    counter.add("Öğrenciler (Modül 2/3)", created, existing)


def seed_enrollment_snapshots(db: Session, counter: Counter) -> None:
    """Program bazlı yıllık kontenjan/yerleşme görüntülerini üretir."""
    spec = load("02_students.json")
    snap = spec["enrollment_snapshots"]
    rng = random.Random(spec["random_seed"] + 1)

    programs = list(db.execute(select(AcademicProgram)).scalars())
    created = existing = 0

    for academic_year in snap["academic_years"]:
        for program in programs:
            found = db.execute(
                select(ProgramEnrollmentSnapshot).where(
                    ProgramEnrollmentSnapshot.academic_program_id == program.id,
                    ProgramEnrollmentSnapshot.academic_year == academic_year,
                )
            ).scalars().first()
            if found is not None:
                existing += 1
                continue

            fill = snap["fill_rate_percent_range"]
            fill_rate = rng.randint(fill["min"], fill["max"])
            enrolled = round(program.quota * fill_rate / 100)

            score_spec = snap["minimum_admission_score_range"]
            minimum = quantize_money(
                Decimal(str(rng.uniform(score_spec["min"], score_spec["max"])))
            )
            premium = snap["full_scholarship_score_premium_range"]
            national = snap["national_average_offset_range"]
            ankara = snap["ankara_average_offset_range"]

            # Mezun / ayrılan sayıları yerleşen sayısını aşamaz.
            graduated = rng.randint(0, max(0, enrolled // 3))
            dropped = rng.randint(0, max(0, enrolled // 8))
            non_renewed = rng.randint(0, max(0, enrolled // 12))

            db.add(
                ProgramEnrollmentSnapshot(
                    academic_program_id=program.id,
                    academic_year=academic_year,
                    quota=program.quota,
                    enrolled_student_count=enrolled,
                    minimum_admission_score=minimum,
                    full_scholarship_minimum_admission_score=quantize_money(
                        minimum + Decimal(str(rng.uniform(premium["min"], premium["max"])))
                    ),
                    national_average_minimum_score=quantize_money(
                        minimum + Decimal(str(rng.uniform(national["min"], national["max"])))
                    ),
                    ankara_average_minimum_score=quantize_money(
                        minimum + Decimal(str(rng.uniform(ankara["min"], ankara["max"])))
                    ),
                    graduated_student_count=graduated,
                    dropped_out_student_count=dropped,
                    non_renewed_student_count=non_renewed,
                )
            )
            created += 1

    db.commit()
    counter.add("Kayıt görüntüleri (Modül 2/3)", created, existing)


# ----------------------------------------------------------------------------
# 3) Akademik personel (Modül 4)
# ----------------------------------------------------------------------------


# Unvan bazlı maaş bandı (yıllık brüt USD).
# Bantların ağırlıklı ortalaması 05_finance.json içindeki güncel yıl ortalama
# akademik maaşına (34.000 USD) yakın çıkacak şekilde seçildi; böylece
# "personel gideri = sayı × ortalama maaş" eşitliği bozulmuyor.
SALARY_BANDS = {
    "Prof. Dr.":      (52000, 64000),
    "Doç. Dr.":       (41000, 50000),
    "Dr. Öğr. Üyesi": (31000, 39000),
    "Öğr. Gör.":      (23000, 29000),
    "Araş. Gör.":     (16000, 21000),
}


def _salary_for_title(title: str, rng: random.Random) -> Decimal:
    """Unvana göre yıllık brüt maaş üretir."""
    low, high = SALARY_BANDS.get(title, (25000, 32000))
    return quantize_money(Decimal(rng.randint(low, high)))


def seed_academic_staff(db: Session, counter: Counter) -> None:
    """Akademik personel kayıtlarını deterministik olarak üretir."""
    spec = load("03_academic_staff.json")
    rng = random.Random(spec["random_seed"])

    departments = {d.code: d for d in db.execute(select(Department)).scalars()}
    existing_numbers = {
        s.staff_number for s in db.execute(select(AcademicStaff)).scalars()
    }

    titles = spec["title_distribution"]
    title_weights = [t["weight"] for t in titles]
    dept_codes = list(spec["department_weights"])
    dept_weights = [spec["department_weights"][c] for c in dept_codes]

    created = existing = 0
    for index in range(1, spec["total_staff"] + 1):
        staff_number = f"AK{index:04d}"
        if staff_number in existing_numbers:
            existing += 1
            continue

        title_spec = rng.choices(titles, weights=title_weights, k=1)[0]
        dept_code = rng.choices(dept_codes, weights=dept_weights, k=1)[0]
        department = departments.get(dept_code)
        if department is None:
            continue

        pub_lo, pub_hi = title_spec["publication_range"]
        cit_lo, cit_hi = title_spec["citation_range"]
        load_lo, load_hi = title_spec["teaching_load_range"]
        adv_lo, adv_hi = spec["advising_count_range"]
        prj_lo, prj_hi = spec["project_count_range"]
        pat_lo, pat_hi = spec["patent_count_range"]
        com_lo, com_hi = spec["community_engagement_range"]

        db.add(
            AcademicStaff(
                staff_number=staff_number,
                first_name=rng.choice(FIRST_NAMES),
                last_name=rng.choice(LAST_NAMES),
                title=title_spec["title"],
                department_id=department.id,
                academic_year=rng.choice(spec["academic_years"]),
                publication_count=rng.randint(pub_lo, pub_hi),
                citation_count=rng.randint(cit_lo, cit_hi),
                teaching_load_hours=rng.randint(load_lo, load_hi),
                advising_count=rng.randint(adv_lo, adv_hi),
                project_count=rng.randint(prj_lo, prj_hi),
                patent_count=rng.randint(pat_lo, pat_hi),
                community_engagement_score=rng.randint(com_lo, com_hi),
                annual_salary_usd=_salary_for_title(title_spec["title"], rng),
                has_administrative_duty=(
                    rng.randint(1, 100) <= spec["administrative_duty_percent"]
                ),
                has_industry_collaboration=(
                    rng.randint(1, 100) <= spec["industry_collaboration_percent"]
                ),
            )
        )
        created += 1

    db.commit()
    counter.add("Akademik personel (Modül 4)", created, existing)


# ----------------------------------------------------------------------------
# 4) Fiziksel mekânlar (Modül 5)
# ----------------------------------------------------------------------------


def seed_facilities(db: Session, counter: Counter) -> None:
    """Derslik, laboratuvar, ofis ve ortak alanları ekler."""
    data = load("04_physical_facilities.json")
    departments = {d.code: d for d in db.execute(select(Department)).scalars()}

    created = existing = 0
    for row in data["facilities"]:
        found = db.execute(
            select(PhysicalFacility).where(PhysicalFacility.code == row["code"])
        ).scalars().first()
        if found is not None:
            existing += 1
            continue

        dept_code = row.get("department_code")
        department = departments.get(dept_code) if dept_code else None
        db.add(
            PhysicalFacility(
                code=row["code"],
                name=row["name"],
                facility_type=row["facility_type"],
                department_id=department.id if department else None,
                capacity=row["capacity"],
                occupied=row["occupied"],
                area_square_meters=row.get("area_square_meters"),
            )
        )
        created += 1

    db.commit()
    counter.add("Fiziksel mekânlar (Modül 5)", created, existing)


# ----------------------------------------------------------------------------
# 5) Mali veriler (Modül 6)
# ----------------------------------------------------------------------------


def _graduates_for_year(academic_year: str) -> int:
    """Üniversite geneli mezun sayısını başarı veri dosyasından okur.

    Tek kaynak kuralı: bu sayı yalnızca 08_academic_success.json içinde durur.
    """
    spec = load("08_academic_success.json")
    return int(spec["university_graduates_per_year"].get(academic_year, 0))


def seed_finance(db: Session, counter: Counter) -> None:
    """Mali dönemleri, gelir/gider kalemlerini ve bölüm bütçelerini ekler."""
    data = load("05_finance.json")

    created_periods = existing_periods = 0
    created_entries = existing_entries = 0
    periods: Dict[str, FinancialPeriod] = {}

    for row in data["periods"]:
        year = row["academic_year"]
        period = db.execute(
            select(FinancialPeriod).where(FinancialPeriod.academic_year == year)
        ).scalars().first()
        if period is None:
            drivers = row.get("drivers", {})
            # Mezun sayısı mali dosyada tekrar yazılmaz; başarı dosyasından
            # okunur. Aynı sayının iki dosyada durması, birini güncelleyip
            # diğerini unutmaya davetiye çıkarırdı.
            graduates = _graduates_for_year(year)
            period = FinancialPeriod(
                academic_year=year,
                total_students=row.get("total_students", 0),
                total_graduates=(
                    row["total_graduates"]
                    if row.get("total_graduates") is not None
                    else graduates
                ),
                academic_staff_count=drivers.get("academic_staff_count", 0),
                average_academic_salary_usd=quantize_money(
                    Decimal(str(drivers.get("average_academic_salary_usd", 0)))
                ),
                administrative_staff_count=drivers.get("administrative_staff_count", 0),
                average_administrative_salary_usd=quantize_money(
                    Decimal(str(drivers.get("average_administrative_salary_usd", 0)))
                ),
                list_tuition_per_student_usd=quantize_money(
                    Decimal(str(drivers.get("list_tuition_per_student_usd", 0)))
                ),
                average_scholarship_rate_percent=quantize_money(
                    Decimal(str(drivers.get("average_scholarship_rate_percent", 0)))
                ),
            )
            db.add(period)
            db.flush()
            created_periods += 1
        else:
            existing_periods += 1
        periods[year] = period

        # Kalem yapısı ya doğrudan verilir ya da başka bir yıldan sıfırla kopyalanır.
        if "copy_categories_from" in row:
            source = periods.get(row["copy_categories_from"])
            if source is None:
                continue
            source_entries = db.execute(
                select(FinancialEntry).where(
                    FinancialEntry.financial_period_id == source.id
                )
            ).scalars().all()
            category_map = {
                e.kind: [] for e in source_entries
            }
            for entry in source_entries:
                category_map.setdefault(entry.kind, []).append(entry.category)
        else:
            category_map = {
                "revenue": list(row.get("revenue", {})),
                "expenditure": list(row.get("expenditure", {})),
            }

        for kind, categories in category_map.items():
            for category in categories:
                found = db.execute(
                    select(FinancialEntry).where(
                        FinancialEntry.financial_period_id == period.id,
                        FinancialEntry.kind == kind,
                        FinancialEntry.category == category,
                    )
                ).scalars().first()
                if found is not None:
                    existing_entries += 1
                    continue
                amount = Decimal(str(row.get(kind, {}).get(category, 0)))
                db.add(
                    FinancialEntry(
                        financial_period_id=period.id,
                        kind=kind,
                        category=category,
                        amount=quantize_money(amount),
                    )
                )
                created_entries += 1
        db.commit()

    counter.add("Mali dönemler (Modül 6)", created_periods, existing_periods)
    counter.add("Gelir/gider kalemleri (Modül 6)", created_entries, existing_entries)

    # Bölüm bütçeleri
    budget_spec = data["department_budgets"]
    period = periods.get(budget_spec["academic_year"])
    departments = {d.code: d for d in db.execute(select(Department)).scalars()}

    created = existing = 0
    if period is not None:
        for row in budget_spec["rows"]:
            department = departments.get(row["department_code"])
            if department is None:
                continue
            found = db.execute(
                select(DepartmentBudget).where(
                    DepartmentBudget.financial_period_id == period.id,
                    DepartmentBudget.department_id == department.id,
                )
            ).scalars().first()
            if found is not None:
                existing += 1
                continue
            db.add(
                DepartmentBudget(
                    financial_period_id=period.id,
                    department_id=department.id,
                    student_count=row["student_count"],
                    revenue=quantize_money(Decimal(str(row["revenue"]))),
                    expenditure=quantize_money(Decimal(str(row["expenditure"]))),
                    allocated_budget=quantize_money(
                        Decimal(str(row["allocated_budget"]))
                    ),
                )
            )
            created += 1
        db.commit()

    counter.add("Bölüm bütçeleri (Modül 6)", created, existing)


# ----------------------------------------------------------------------------
# 6) KPI'lar (Modül 8)
# ----------------------------------------------------------------------------


def seed_kpis(db: Session, counter: Counter) -> None:
    """Stratejik KPI'ları ve fakülte kırılımlarını ekler."""
    data = load("06_kpis.json")
    academic_year = data["academic_year"]
    faculties = {f.code: f for f in db.execute(select(Faculty)).scalars()}

    created = existing = 0
    created_values = 0
    for row in data["kpis"]:
        kpi = db.execute(
            select(StrategicKpi).where(
                StrategicKpi.name == row["name"],
                StrategicKpi.academic_year == academic_year,
            )
        ).scalars().first()
        if kpi is not None:
            existing += 1
            continue

        kpi = StrategicKpi(
            name=row["name"],
            dimension=row["dimension"],
            unit=row.get("unit"),
            academic_year=academic_year,
            current_value=quantize_money(Decimal(str(row["current_value"]))),
            target_value=quantize_money(Decimal(str(row["target_value"]))),
            previous_value=(
                quantize_money(Decimal(str(row["previous_value"])))
                if row.get("previous_value") is not None
                else None
            ),
            university_average=(
                quantize_money(Decimal(str(row["university_average"])))
                if row.get("university_average") is not None
                else None
            ),
            on_track_threshold=quantize_money(
                Decimal(str(row.get("on_track_threshold", 90)))
            ),
            at_risk_threshold=quantize_money(
                Decimal(str(row.get("at_risk_threshold", 70)))
            ),
            corrective_action=row.get("corrective_action"),
            description=row.get("description"),
            formula=row.get("formula"),
            data_source=row.get("data_source"),
            higher_is_better=row.get("higher_is_better", True),
            value_source=row.get("value_source", "manual"),
        )
        db.add(kpi)
        db.flush()
        created += 1

        for faculty_code, value in (row.get("faculty_values") or {}).items():
            faculty = faculties.get(faculty_code)
            if faculty is None:
                continue
            db.add(
                KpiFacultyValue(
                    kpi_id=kpi.id,
                    faculty_id=faculty.id,
                    value=quantize_money(Decimal(str(value))),
                )
            )
            created_values += 1

    db.commit()
    counter.add("Stratejik KPI'lar (Modül 8)", created, existing)
    counter.add("KPI fakülte kırılımı (Modül 8)", created_values, 0)


# ----------------------------------------------------------------------------
# 7) Kullanıcılar (Modül 14)
# ----------------------------------------------------------------------------


def seed_users(db: Session, counter: Counter) -> None:
    """Demo kullanıcılarını parolaları özetlenmiş biçimde ekler."""
    data = load("07_system_users.json")
    faculties = {f.code: f for f in db.execute(select(Faculty)).scalars()}
    departments = {d.code: d for d in db.execute(select(Department)).scalars()}

    created = existing = 0
    for row in data["users"]:
        found = db.execute(
            select(SystemUser).where(SystemUser.username == row["username"])
        ).scalars().first()
        if found is not None:
            existing += 1
            continue

        # Parola hiçbir zaman düz metin yazılmaz.
        salt, digest = hash_password(row["password"])
        faculty = faculties.get(row.get("faculty_code") or "")
        department = departments.get(row.get("department_code") or "")
        db.add(
            SystemUser(
                username=row["username"],
                full_name=row["full_name"],
                password_salt=salt,
                password_hash=digest,
                role=row["role"],
                faculty_id=faculty.id if faculty else None,
                department_id=department.id if department else None,
            )
        )
        created += 1

    db.commit()
    counter.add("Sistem kullanıcıları (Modül 14)", created, existing)


# ----------------------------------------------------------------------------
# 8) Akademik başarı (program × yıl)
# ----------------------------------------------------------------------------


def _clamp(value: float, low: float, high: float) -> float:
    """Değeri sınırlar içinde tutar."""
    return max(low, min(high, value))


def seed_academic_success(db: Session, counter: Counter) -> None:
    """Program bazlı başarı, geçme, bırakma ve mezuniyet oranlarını üretir."""
    spec = load("08_academic_success.json")
    rng = random.Random(spec["random_seed"])
    bounds = spec["bounds"]
    noise = spec["yearly_noise_range"]

    programs = {p.code: p for p in db.execute(select(AcademicProgram)).scalars()}
    years = spec["academic_years"]

    # Her programın ölçüm yaptığı öğrenci sayısı, o programa KAYITLI TOPLAM
    # öğrenci sayısıdır. Kayıt görüntüsündeki "yerleşen" sayısı yalnızca o yıl
    # yeni gelenleri kapsar; onu ağırlık olarak kullanmak üniversite toplamını
    # 4000 yerine ~900 gösterirdi ve ekranlar arasında tutarsızlık yaratırdı.
    from sqlalchemy import func as _func

    program_totals = {
        program_id: count
        for program_id, count in db.execute(
            select(Student.academic_program_id, _func.count(Student.id))
            .where(Student.is_active.is_(True))
            .group_by(Student.academic_program_id)
        )
    }

    created = existing = 0
    for year_index, academic_year in enumerate(years):
        for code, params in spec["programs"].items():
            program = programs.get(code)
            if program is None:
                continue

            found = db.execute(
                select(AcademicSuccessRecord).where(
                    AcademicSuccessRecord.academic_program_id == program.id,
                    AcademicSuccessRecord.academic_year == academic_year,
                )
            ).scalars().first()
            if found is not None:
                existing += 1
                continue

            drift = params["yearly_trend"] * year_index
            jitter = rng.uniform(noise["min"], noise["max"])

            pass_rate = _clamp(
                params["base_pass_rate"] + drift + jitter,
                bounds["pass_rate"]["min"], bounds["pass_rate"]["max"],
            )
            # Ortalama başarı puanı geçme oranıyla aynı yönde hareket eder;
            # ters yönde hareket etmesi veri hatası sayılırdı.
            score = _clamp(
                params["base_score"] + drift * 0.8 + jitter * 0.7,
                bounds["average_score"]["min"], bounds["average_score"]["max"],
            )
            # Bırakma oranı geçme oranıyla TERS yönde hareket eder.
            dropout = _clamp(
                params["dropout_base"] - drift * 0.5 + jitter * 0.4,
                bounds["dropout_rate"]["min"], bounds["dropout_rate"]["max"],
            )
            graduation = _clamp(
                params["graduation_base"] + drift * 0.7 + jitter * 0.5,
                bounds["graduation_rate"]["min"], bounds["graduation_rate"]["max"],
            )

            measured = program_totals.get(program.id)
            if not measured:
                # Öğrencisi olmayan program için kontenjan üzerinden makul bir sayı.
                measured = max(1, int(program.quota * 0.85))

            db.add(
                AcademicSuccessRecord(
                    academic_program_id=program.id,
                    academic_year=academic_year,
                    measured_student_count=measured,
                    course_pass_rate=quantize_money(Decimal(str(round(pass_rate, 2)))),
                    average_success_score=quantize_money(Decimal(str(round(score, 2)))),
                    dropout_rate=quantize_money(Decimal(str(round(dropout, 2)))),
                    graduation_rate=quantize_money(Decimal(str(round(graduation, 2)))),
                    # Mezun sayısı: programın öğrenci sayısı × mezuniyet oranı,
                    # 4 yıllık öğrenim süresine bölünerek yıllık mezun elde edilir.
                    graduate_count=int(measured * graduation / 100 / 4),
                )
            )
            created += 1

    db.commit()
    counter.add("Akademik başarı kayıtları", created, existing)


# ----------------------------------------------------------------------------
# 9) Sanayi iş birliği ve bölgesel katkı
# ----------------------------------------------------------------------------


def seed_engagement(db: Session, counter: Counter) -> None:
    """Sanayi iş birliği ve bölgesel katkı kayıtlarını ekler."""
    data = load("09_engagement.json")
    faculties = {f.code: f for f in db.execute(select(Faculty)).scalars()}

    created_ic = existing_ic = 0
    for academic_year, rows in data["industry_collaboration"].items():
        for faculty_code, values in rows.items():
            faculty = faculties.get(faculty_code)
            if faculty is None:
                continue
            found = db.execute(
                select(IndustryCollaborationRecord).where(
                    IndustryCollaborationRecord.faculty_id == faculty.id,
                    IndustryCollaborationRecord.academic_year == academic_year,
                )
            ).scalars().first()
            if found is not None:
                existing_ic += 1
                continue
            db.add(
                IndustryCollaborationRecord(
                    faculty_id=faculty.id,
                    academic_year=academic_year,
                    active_partnerships=values["active_partnerships"],
                    joint_projects=values["joint_projects"],
                    funded_research_musd=quantize_money(
                        Decimal(str(values["funded_research_musd"]))
                    ),
                    intern_students=values["intern_students"],
                    signed_protocols=values["signed_protocols"],
                )
            )
            created_ic += 1
    db.commit()
    counter.add("Sanayi iş birliği kayıtları", created_ic, existing_ic)

    created_rc = existing_rc = 0
    for academic_year, values in data["regional_contribution"].items():
        found = db.execute(
            select(RegionalContributionRecord).where(
                RegionalContributionRecord.academic_year == academic_year
            )
        ).scalars().first()
        if found is not None:
            existing_rc += 1
            continue
        db.add(RegionalContributionRecord(academic_year=academic_year, **values))
        created_rc += 1
    db.commit()
    counter.add("Bölgesel katkı kayıtları", created_rc, existing_rc)


def sync_scenario_baseline(db: Session, counter: Counter) -> None:
    """Aktif senaryo tabanını güncel mali dönemle eşitler.

    Neden gerekli: senaryo tabanı ile mali analiz modülü birbirinden bağımsız
    kurulmuştu ve aynı kurumun yıllık gelirini farklı söylüyorlardı. Bir karar
    destek sisteminde bu, verilen kararı doğrudan yanlış yapan bir tutarsızlıktır.
    Artık taban, güncel mali dönemin gerçek verisinden üretilip kaydediliyor.
    """
    from app.models import ScenarioBaseline
    from app.services.scenario_baseline_builder import build_from_financial_period

    assumptions = load("00_assumptions.json")
    current_year = assumptions["akademik_yillar"]["guncel"]

    try:
        derived = build_from_financial_period(db, current_year)
    except Exception as error:
        print(f"  UYARI: senaryo tabani mali donemden uretilemedi: {error}")
        counter.add("Senaryo tabanı (mali dönemle eşitlendi)", 0, 0)
        return

    active = db.execute(
        select(ScenarioBaseline).where(ScenarioBaseline.is_active.is_(True))
    ).scalars().first()

    fields = (
        "student_count", "annual_tuition_per_student", "scholarship_rate_percent",
        "annual_research_revenue", "annual_other_revenue", "annual_personnel_expense",
        "annual_education_expense", "annual_rd_expense",
        "annual_building_energy_expense", "annual_technology_expense",
        "academic_staff_count", "classroom_capacity", "laboratory_capacity",
    )

    if active is None:
        active = ScenarioBaseline(
            name=f"{current_year} kurumsal taban", is_active=True
        )
        for field in fields:
            setattr(active, field, getattr(derived, field))
        db.add(active)
        created, existing = 1, 0
    else:
        for field in fields:
            setattr(active, field, getattr(derived, field))
        active.name = f"{current_year} kurumsal taban"
        created, existing = 0, 1

    db.commit()
    counter.add("Senaryo tabanı (mali dönemle eşitlendi)", created, existing)


# ----------------------------------------------------------------------------
# Ana akış
# ----------------------------------------------------------------------------


def main() -> None:
    """Tüm demo verisini yükler."""
    print("=" * 68)
    print("ORTAK DEMO VERISI YUKLENIYOR")
    print(f"Kaynak klasor: {DATA_DIR}")
    print("=" * 68)

    init_db()
    counter = Counter()
    db: Session = SessionLocal()

    try:
        print("\n[1/3] Universite yapisi, ogrenci ve modul verileri...")
        seed_structure(db, counter)
        seed_students(db, counter)
        seed_enrollment_snapshots(db, counter)
        seed_academic_staff(db, counter)
        seed_facilities(db, counter)
        seed_finance(db, counter)
        seed_academic_success(db, counter)
        seed_engagement(db, counter)
        seed_kpis(db, counter)
        seed_users(db, counter)
    except Exception as error:
        db.rollback()
        print(f"\nHATA: Ortak veri yuklenirken sorun olustu: {error}")
        raise
    finally:
        db.close()

    # Modül 9 ve 10 kendi seed'lerini kullanır; yapı verisi hazır olduktan
    # sonra çalıştırılmaları gerekir.
    print("\n[2/3] Modul 9 (senaryo) ve Modul 10 (degerlendirme) seed'leri...")
    import seed_ranking_data
    import seed_scenario_data

    seed_scenario_data.seed()
    seed_ranking_data.seed()

    # Senaryo tabanini mali donemle esitle: iki modul ayni kurumun gelirini
    # farkli soylememelidir.
    print("\n[3/3] Senaryo tabani mali donemle esitleniyor...")
    db2: Session = SessionLocal()
    try:
        sync_scenario_baseline(db2, counter)
    finally:
        db2.close()

    print("\nOzet:")
    counter.report()
    print(
        "\nTamamlandi. Script tekrar calistirilirsa yeni kayit eklenmez;\n"
        "'Mevcut' sutunundaki sayilar artar."
    )


if __name__ == "__main__":
    main()
