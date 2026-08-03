"""Demo veri seti üreteci.

NEDEN ÜRETİLİYOR?
----------------
Modül 13'ün `sample_data/` klasöründeki CSV'ler yalnızca 3-4 satırdır ve içlerinde
bilerek bozuk değerler (`evet`/`1`/`true` karışık) bulunur; bunlar içe aktarma
doğrulayıcısını sınamak için yazılmış hatalı veri örnekleridir, analiz verisi değildir.
Trend, sürdürülebilirlik puanı ve erken uyarı üretebilmek için birden fazla akademik
yılı kapsayan tutarlı bir veri setine ihtiyaç vardır.

VERİNİN TUTARLILIĞI
-------------------
Kontenjan, kayıt sayısı ve taban puanlar elle tanımlanmıştır (gerçekçi senaryolar).
Mezun, terk ve kayıt yenilememe sayıları ise UYDURULMAZ; üretilen öğrenci
popülasyonundan SAYILARAK çıkarılır. Böylece snapshot tablosu ile öğrenci tablosu
birbiriyle çelişmez.

Üretim `random.Random(RANDOM_SEED)` ile deterministiktir: aynı kod her çalıştığında
aynı veriyi üretir, demoda sayılar değişmez.
"""

import random
from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.orm import Session

from module_03_ogrenci_analitigi.models import (
    AcademicProgram,
    ProgramEnrollmentSnapshot,
    Student,
    StudentAcademicRecord,
)

RANDOM_SEED = 20260731

# Analizlerin "bugün" kabul ettiği akademik yıl.
CURRENT_ACADEMIC_YEAR = "2026-2027"
CURRENT_YEAR = 2026

# Öğrenci üretilen kohort yılları (kayıt yılları).
COHORT_YEARS = [2020, 2021, 2022, 2023, 2024, 2025, 2026]

# Snapshot (yıllık kayıt fotoğrafı) üretilen akademik yıllar.
SNAPSHOT_YEARS = ["2024-2025", "2025-2026", "2026-2027"]

# Taban puan karşılaştırmaları için Ankara ve Türkiye ortalamaları (yıl bazlı).
MARKET_SCORES: Dict[int, Dict[str, float]] = {
    2024: {"national": 388.5, "ankara": 405.2},
    2025: {"national": 391.3, "ankara": 408.4},
    2026: {"national": 394.1, "ankara": 411.6},
}

# Öğrenci adı üretimi için küçük havuzlar (yalnızca demo görünürlüğü için).
TR_FIRST_NAMES = [
    "Elif", "Burak", "Zeynep", "Mert", "Ayşe", "Emre", "Selin", "Kaan",
    "Deniz", "Ece", "Onur", "İrem", "Berk", "Nisa", "Can", "Melis",
]
TR_LAST_NAMES = [
    "Yıldız", "Demir", "Kaya", "Şahin", "Çelik", "Yılmaz", "Aydın",
    "Arslan", "Doğan", "Koç", "Öztürk", "Kurt",
]
INTL_NAMES = [
    ("Omar", "Hassan", "Irak"), ("Amina", "Diallo", "Senegal"),
    ("Yusuf", "Rahman", "Bangladeş"), ("Leila", "Karimi", "İran"),
    ("Ahmed", "Farouk", "Mısır"), ("Nadia", "Popescu", "Romanya"),
    ("Ivan", "Petrov", "Bulgaristan"), ("Sara", "Al-Amin", "Ürdün"),
]

# ---------------------------------------------------------------------------
# PROGRAM PROFİLLERİ
# ---------------------------------------------------------------------------
# intakes            : kohort yılı -> o yıl programa kaydolan öğrenci sayısı
# min_scores         : yıl -> programın taban puanı
# annual_dropout     : bir öğrencinin bir yılda programı bırakma temel olasılığı
# risk_trend         : True ise son yıllarda terk olasılığı artar (erken uyarı senaryosu)
# intl_ratio         : uluslararası öğrenci oranı
# prep_ratio         : hazırlık sınıfı okuma oranı
# gpa_mean           : ortalama GNO
#
# Senaryo dağılımı bilinçlidir: SWE/IE güçlü, EE/ARCH istikrarlı, ME zayıflıyor,
# CENG ve CE sert düşüşte (alarm üretmeli), MSE kritik derecede küçük (birleşme adayı).
PROGRAM_PROFILES: List[dict] = [
    {
        "code": "SWE-BSC", "name": "Yazılım Mühendisliği", "quota": 85,
        "intakes": {2020: 74, 2021: 76, 2022: 78, 2023: 79, 2024: 80, 2025: 83, 2026: 84},
        "min_scores": {2024: 441.0, 2025: 448.2, 2026: 452.3},
        "annual_dropout": 0.020, "risk_trend": False,
        "intl_ratio": 0.18, "prep_ratio": 0.55, "scholarship_ratio": 0.62, "gpa_mean": 3.05,
    },
    {
        "code": "CENG-BSC", "name": "Bilgisayar Mühendisliği", "quota": 100,
        "intakes": {2020: 98, 2021: 97, 2022: 95, 2023: 94, 2024: 92, 2025: 71, 2026: 38},
        "min_scores": {2024: 428.4, 2025: 385.0, 2026: 344.2},
        "annual_dropout": 0.050, "risk_trend": True,
        "intl_ratio": 0.22, "prep_ratio": 0.50, "scholarship_ratio": 0.58, "gpa_mean": 2.62,
    },
    {
        "code": "EE-BSC", "name": "Elektrik-Elektronik Mühendisliği", "quota": 70,
        "intakes": {2020: 69, 2021: 69, 2022: 68, 2023: 67, 2024: 66, 2025: 64, 2026: 61},
        "min_scores": {2024: 402.5, 2025: 398.1, 2026: 395.4},
        "annual_dropout": 0.030, "risk_trend": False,
        "intl_ratio": 0.10, "prep_ratio": 0.40, "scholarship_ratio": 0.45, "gpa_mean": 2.84,
    },
    {
        "code": "ME-BSC", "name": "Makine Mühendisliği", "quota": 65,
        "intakes": {2020: 63, 2021: 62, 2022: 60, 2023: 58, 2024: 55, 2025: 48, 2026: 41},
        "min_scores": {2024: 372.3, 2025: 364.0, 2026: 357.1},
        "annual_dropout": 0.045, "risk_trend": True,
        "intl_ratio": 0.07, "prep_ratio": 0.35, "scholarship_ratio": 0.40, "gpa_mean": 2.61,
    },
    {
        "code": "IE-BSC", "name": "Endüstri Mühendisliği", "quota": 60,
        "intakes": {2020: 59, 2021: 59, 2022: 59, 2023: 58, 2024: 58, 2025: 57, 2026: 56},
        "min_scores": {2024: 415.2, 2025: 412.4, 2026: 409.8},
        "annual_dropout": 0.025, "risk_trend": False,
        "intl_ratio": 0.09, "prep_ratio": 0.45, "scholarship_ratio": 0.50, "gpa_mean": 2.97,
    },
    {
        "code": "CE-BSC", "name": "İnşaat Mühendisliği", "quota": 60,
        "intakes": {2020: 48, 2021: 45, 2022: 42, 2023: 38, 2024: 34, 2025: 27, 2026: 21},
        "min_scores": {2024: 341.0, 2025: 332.5, 2026: 318.7},
        "annual_dropout": 0.070, "risk_trend": True,
        "intl_ratio": 0.05, "prep_ratio": 0.25, "scholarship_ratio": 0.35, "gpa_mean": 2.38,
    },
    {
        "code": "ARCH-BSC", "name": "Mimarlık", "quota": 50,
        "intakes": {2020: 49, 2021: 49, 2022: 48, 2023: 48, 2024: 47, 2025: 45, 2026: 44},
        "min_scores": {2024: 398.6, 2025: 395.2, 2026: 392.0},
        "annual_dropout": 0.035, "risk_trend": False,
        "intl_ratio": 0.12, "prep_ratio": 0.30, "scholarship_ratio": 0.42, "gpa_mean": 2.79,
    },
    {
        "code": "MSE-BSC", "name": "Malzeme Bilimi ve Mühendisliği", "quota": 40,
        "intakes": {2020: 28, 2021: 26, 2022: 24, 2023: 21, 2024: 18, 2025: 15, 2026: 11},
        "min_scores": {2024: 336.4, 2025: 329.0, 2026: 321.3},
        "annual_dropout": 0.060, "risk_trend": True,
        "intl_ratio": 0.06, "prep_ratio": 0.28, "scholarship_ratio": 0.38, "gpa_mean": 2.45,
    },
]

# Terk olasılığının yıllara göre çarpanı. risk_trend=True olan programlarda son iki
# yılda terk artar; erken uyarı modülünün yakalaması gereken sinyal budur.
RISK_YEAR_MULTIPLIER = {2020: 1.0, 2021: 1.0, 2022: 1.0, 2023: 1.1, 2024: 1.3, 2025: 1.8, 2026: 2.4}

NORMAL_DURATION_YEARS = 4
# Mezuniyetin beklenen yıla göre gecikmesi: 0 yıl %72, 1 yıl %20, 2 yıl %8.
GRADUATION_DELAY_WEIGHTS = [(0, 0.72), (1, 0.20), (2, 0.08)]

# ABU PDF'inin yeni istediği göstergeler için ek sabitler.
# Ayrı bir RANDOM_SEED + 1 akışı kullanılır ki mevcut mezuniyet/terk/GNO
# rastgeleliği (ve dolayısıyla testlerdeki bilinen sayılar) etkilenmesin.
EMPLOYMENT_RATE = 0.82
FULL_SCHOLARSHIP_SCORE_BONUS = 15.0


def _weighted_choice(rng: random.Random, weighted: List[tuple]) -> int:
    """Ağırlıklı seçenek listesinden bir değer döndürür."""
    values = [item[0] for item in weighted]
    weights = [item[1] for item in weighted]
    return rng.choices(values, weights=weights, k=1)[0]


def _academic_year_label(start_year: int) -> str:
    """2026 -> '2026-2027' biçiminde akademik yıl etiketi üretir."""
    return f"{start_year}-{start_year + 1}"


def _build_students_for_program(
    rng: random.Random, profile: dict, program: AcademicProgram
) -> tuple:
    """Bir program için öğrencileri ve olay geçmişlerini üretir.

    Döndürdüğü ikinci değer, her öğrencinin hangi yıl terk ettiği / kaydını
    yenilemediği bilgisidir; snapshot sayıları buradan sayılarak çıkarılır.
    """
    students: List[Student] = []
    # events[student_number] = {"dropped_year": int|None, "non_renewed_years": set[int]}
    events: Dict[str, dict] = {}

    for cohort in COHORT_YEARS:
        intake = profile["intakes"][cohort]
        for index in range(intake):
            number = f"{profile['code'].split('-')[0]}{cohort}{index + 1:04d}"

            is_international = rng.random() < profile["intl_ratio"]
            if is_international:
                first, last, nationality = rng.choice(INTL_NAMES)
            else:
                first = rng.choice(TR_FIRST_NAMES)
                last = rng.choice(TR_LAST_NAMES)
                nationality = "Türkiye"

            has_scholarship = rng.random() < profile["scholarship_ratio"]
            scholarship = rng.choice([25, 50, 75, 100]) if has_scholarship else 0

            is_prep = rng.random() < profile["prep_ratio"]
            expected_graduation = cohort + NORMAL_DURATION_YEARS + (1 if is_prep else 0)

            # --- Terk ve kayıt yenilememe olayları yıl yıl simüle edilir ---
            dropped_year = None
            non_renewed_years = set()
            base_dropout = profile["annual_dropout"]

            for year in range(cohort, min(expected_graduation, CURRENT_YEAR) + 1):
                multiplier = RISK_YEAR_MULTIPLIER[year] if profile["risk_trend"] else 1.0
                if rng.random() < base_dropout * multiplier:
                    dropped_year = year
                    break
                # Kaydını yenilemeyen ama resmen ayrılmamış öğrenciler.
                if rng.random() < base_dropout * multiplier * 0.6:
                    non_renewed_years.add(year)

            # --- Duruma karar verilir ---
            actual_graduation = None
            if dropped_year is not None:
                status = "dropped-out"
                is_active = False
            else:
                delay = _weighted_choice(rng, GRADUATION_DELAY_WEIGHTS)
                candidate_graduation = expected_graduation + delay
                if candidate_graduation <= CURRENT_YEAR:
                    actual_graduation = candidate_graduation
                    status = "graduated"
                    is_active = False
                elif cohort == CURRENT_YEAR:
                    status = "newly-enrolled"
                    is_active = True
                else:
                    status = "active"
                    is_active = True

            # GNO yalnızca ders almış öğrenciler için anlamlıdır.
            if cohort == CURRENT_YEAR:
                gpa = None
            else:
                gpa = round(min(4.0, max(0.4, rng.gauss(profile["gpa_mean"], 0.45))), 2)

            students.append(
                Student(
                    student_number=number,
                    first_name=first,
                    last_name=last,
                    gender=rng.choice(["female", "male"]),
                    nationality=nationality,
                    is_international=is_international,
                    scholarship_rate_percent=scholarship,
                    enrollment_year=cohort,
                    current_status=status,
                    status_change_year=dropped_year,
                    preparatory_school=is_prep,
                    academic_program=program,
                    current_gpa=gpa,
                    expected_graduation_year=expected_graduation,
                    actual_graduation_year=actual_graduation,
                    is_active=is_active,
                )
            )
            events[number] = {
                "dropped_year": dropped_year,
                "non_renewed_years": non_renewed_years,
                "gpa_mean": profile["gpa_mean"],
                # Akademik başarı düşüşü yalnızca riskli programlarda görülür;
                # sağlıklı programlar yatay seyreder. Böylece Modül 11'in
                # "akademik göstergeler düşüyor" alarmı gerçekten ayırt edici olur.
                "gpa_drift": -0.09 if profile["risk_trend"] else 0.0,
            }

    return students, events


def _build_snapshots(
    profile: dict, program: AcademicProgram, students: List[Student], events: Dict[str, dict]
) -> List[ProgramEnrollmentSnapshot]:
    """Öğrenci popülasyonundan yıllık kayıt fotoğraflarını türetir."""
    snapshots = []
    for label in SNAPSHOT_YEARS:
        start_year = int(label.split("-")[0])

        graduated = sum(1 for s in students if s.actual_graduation_year == start_year)
        dropped = sum(
            1 for s in students if events[s.student_number]["dropped_year"] == start_year
        )
        non_renewed = sum(
            1 for s in students if start_year in events[s.student_number]["non_renewed_years"]
        )

        snapshots.append(
            ProgramEnrollmentSnapshot(
                academic_program=program,
                academic_year=label,
                quota=profile["quota"],
                enrolled_student_count=profile["intakes"][start_year],
                minimum_admission_score=profile["min_scores"][start_year],
                national_average_minimum_score=MARKET_SCORES[start_year]["national"],
                ankara_average_minimum_score=MARKET_SCORES[start_year]["ankara"],
                full_scholarship_minimum_admission_score=(
                    profile["min_scores"][start_year] + FULL_SCHOLARSHIP_SCORE_BONUS
                ),
                graduated_student_count=graduated,
                dropped_out_student_count=dropped,
                non_renewed_student_count=non_renewed,
            )
        )
    return snapshots


def _build_academic_records(
    rng: random.Random, students: List[Student], events: Dict[str, dict]
) -> List[StudentAcademicRecord]:
    """Son üç akademik yıl için dönemlik akademik kayıtları üretir."""
    records = []
    for student in students:
        info = events[student.student_number]
        dropped_year = info["dropped_year"]
        gpa_mean = info["gpa_mean"]

        for label in SNAPSHOT_YEARS:
            start_year = int(label.split("-")[0])

            # Öğrenci o yıl okulda değilse kayıt üretilmez.
            if student.enrollment_year > start_year:
                continue
            if dropped_year is not None and start_year > dropped_year:
                continue
            if (
                student.actual_graduation_year is not None
                and start_year >= student.actual_graduation_year
            ):
                continue

            renewed = start_year not in info["non_renewed_years"]
            # Riskli programlarda yıl ilerledikçe başarı düşer; diğerlerinde sabittir.
            drift = info["gpa_drift"] * (start_year - 2024)

            for semester in ("fall", "spring"):
                semester_gpa = round(
                    min(4.0, max(0.3, rng.gauss(gpa_mean + drift, 0.42))), 2
                )
                registered = rng.randint(4, 7)
                failed = 0 if semester_gpa >= 2.0 else rng.randint(1, 2)
                passed = registered - failed
                attempted = registered * 5
                earned = passed * 5

                records.append(
                    StudentAcademicRecord(
                        student=student,
                        academic_year=label,
                        semester=semester,
                        registered_course_count=registered,
                        passed_course_count=passed,
                        failed_course_count=failed,
                        earned_credits=earned,
                        attempted_credits=attempted,
                        semester_gpa=semester_gpa,
                        cumulative_gpa=semester_gpa,
                        registration_renewed=renewed,
                    )
                )
    return records


def _assign_employment(employment_rng: random.Random, students: List[Student]) -> None:
    """Mezun öğrencilere istihdam durumu atar (PDF: "Graduate employment rate").

    Ayrı bir RNG akışı kullanır ve öğrenci üretiminden SONRA, tüm alanlar
    belirlendikten sonra çalışır; böylece mevcut mezuniyet/terk/GNO
    rastgeleliğini (ve testlerdeki bilinen sayıları) etkilemez.
    """
    for student in students:
        if student.current_status == "graduated":
            student.is_employed = employment_rng.random() < EMPLOYMENT_RATE


def seed_all(db: Session) -> dict:
    """Veritabanını demo verisiyle doldurur ve üretilen kayıt sayılarını döndürür."""
    rng = random.Random(RANDOM_SEED)
    employment_rng = random.Random(RANDOM_SEED + 1)
    counts = {"programs": 0, "students": 0, "snapshots": 0, "academic_records": 0}

    for profile in PROGRAM_PROFILES:
        program = AcademicProgram(
            name=profile["name"],
            code=profile["code"],
            degree_level="Bachelor",
            duration_years=NORMAL_DURATION_YEARS,
            quota=profile["quota"],
            is_active=True,
        )
        db.add(program)

        students, events = _build_students_for_program(rng, profile, program)
        snapshots = _build_snapshots(profile, program, students, events)
        records = _build_academic_records(rng, students, events)
        _assign_employment(employment_rng, students)

        db.add_all(students)
        db.add_all(snapshots)
        db.add_all(records)

        counts["programs"] += 1
        counts["students"] += len(students)
        counts["snapshots"] += len(snapshots)
        counts["academic_records"] += len(records)

    db.commit()
    return counts


def seed_if_empty(db: Session) -> dict:
    """Veritabanı boşsa doldurur; doluysa hiçbir şey yapmaz."""
    existing = db.execute(select(AcademicProgram.id).limit(1)).first()
    if existing is not None:
        return {"skipped": True}
    result = seed_all(db)
    result["skipped"] = False
    return result
