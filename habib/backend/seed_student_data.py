"""Modül 2 (Student Analytics) için başlangıç verilerini ekleyen script.

Çalıştırma:
    python seed_data.py            # önce Modül 1 verileri (SWE, CENG programları)
    python seed_student_data.py    # sonra bu script

Script birden fazla kez çalıştırılsa bile aynı kayıtları tekrar eklemez.
seed_data.py ve seed_scenario_data.py dosyalarına dokunulmamıştır.

Üretilen veri DETERMİNİSTİKTİR: random.Random sabit bir tohum (seed) ile
oluşturulduğu için script her çalıştığında birebir aynı öğrenciler üretilir.
Bu, testlerin ve raporların tekrarlanabilir olmasını sağlar.
"""

import random
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal, init_db
from app.models import (
    AcademicProgram,
    ComparableUniversityProgram,
    ProgramEnrollmentSnapshot,
    Student,
    StudentAcademicRecord,
)

# Sabit tohum: aynı veri her seferinde yeniden üretilsin.
RANDOM_SEED: int = 20260726

# Hangi programlara öğrenci dağıtılacak (Modül 1 seed'inden gelen kodlar).
PROGRAM_CODES: Tuple[str, ...] = ("SWE-BSC", "CENG-BSC")

# Öğrenciler bu kayıt yıllarına dağıtılır.
ENROLLMENT_YEARS: Tuple[int, ...] = (2021, 2022, 2023, 2024, 2025)

TOTAL_STUDENTS: int = 120

FIRST_NAMES: Tuple[str, ...] = (
    "Ahmet", "Ayşe", "Mehmet", "Zeynep", "Mustafa", "Elif", "Ali", "Fatma",
    "Emre", "Selin", "Burak", "Deniz", "Can", "Ece", "Kaan", "Merve",
    "Omar", "Sara", "Ibrahim", "Layla", "Hasan", "Nur", "Yusuf", "Aylin",
)
LAST_NAMES: Tuple[str, ...] = (
    "Yılmaz", "Kaya", "Demir", "Çelik", "Şahin", "Yıldız", "Aydın", "Öztürk",
    "Arslan", "Doğan", "Kılıç", "Aslan", "Çetin", "Kara", "Koç", "Kurt",
    "Al-Sayed", "Hassan", "Petrov", "Novak", "Ahmadi", "Khan",
)
NATIONALITIES_LOCAL: Tuple[str, ...] = ("Türkiye",)
NATIONALITIES_INTERNATIONAL: Tuple[str, ...] = (
    "Azerbaycan", "Suriye", "Irak", "İran", "Pakistan", "Nijerya", "Somali", "Almanya",
)

# Durum dağılımı: her 100 öğrencide yaklaşık bu oranlarda üretilir.
# graduated ve dropped-out yalnızca eski kayıt yıllarına atanır (aşağıda kontrol ediliyor).
STATUS_WEIGHTS: Tuple[Tuple[str, int], ...] = (
    ("active", 52),
    ("graduated", 18),
    ("dropped-out", 10),
    ("non-renewed", 7),
    ("suspended", 3),
    ("newly-enrolled", 10),
)

SEMESTERS: Tuple[str, ...] = ("fall", "spring")

# Program snapshot verileri: son 4 akademik yıl.
# SWE talebi artıyor (doluluk ve puan yükseliyor), CENG talebi düşüyor.
# Bu bilinçli tasarım, demand_trend ve erken uyarı kurallarını gerçek veriyle test etmeyi sağlar.
SNAPSHOT_DATA: Dict[str, List[dict]] = {
    "SWE-BSC": [
        {
            "academic_year": "2022-2023", "quota": 80, "enrolled_student_count": 62,
            "minimum_admission_score": "398.50", "national_average_minimum_score": "372.10",
            "ankara_average_minimum_score": "385.40", "graduated_student_count": 40,
            "dropped_out_student_count": 6, "non_renewed_student_count": 4,
        },
        {
            "academic_year": "2023-2024", "quota": 80, "enrolled_student_count": 70,
            "minimum_admission_score": "412.75", "national_average_minimum_score": "378.60",
            "ankara_average_minimum_score": "392.10", "graduated_student_count": 44,
            "dropped_out_student_count": 5, "non_renewed_student_count": 3,
        },
        {
            "academic_year": "2024-2025", "quota": 80, "enrolled_student_count": 76,
            "minimum_admission_score": "428.30", "national_average_minimum_score": "384.20",
            "ankara_average_minimum_score": "399.75", "graduated_student_count": 47,
            "dropped_out_student_count": 4, "non_renewed_student_count": 3,
        },
        {
            "academic_year": "2025-2026", "quota": 80, "enrolled_student_count": 79,
            "minimum_admission_score": "441.90", "national_average_minimum_score": "389.80",
            "ankara_average_minimum_score": "406.20", "graduated_student_count": 49,
            "dropped_out_student_count": 3, "non_renewed_student_count": 2,
        },
    ],
    "CENG-BSC": [
        {
            "academic_year": "2022-2023", "quota": 100, "enrolled_student_count": 88,
            "minimum_admission_score": "405.60", "national_average_minimum_score": "372.10",
            "ankara_average_minimum_score": "385.40", "graduated_student_count": 52,
            "dropped_out_student_count": 9, "non_renewed_student_count": 6,
        },
        {
            "academic_year": "2023-2024", "quota": 100, "enrolled_student_count": 74,
            "minimum_admission_score": "391.20", "national_average_minimum_score": "378.60",
            "ankara_average_minimum_score": "392.10", "graduated_student_count": 48,
            "dropped_out_student_count": 12, "non_renewed_student_count": 8,
        },
        {
            "academic_year": "2024-2025", "quota": 100, "enrolled_student_count": 58,
            "minimum_admission_score": "376.40", "national_average_minimum_score": "384.20",
            "ankara_average_minimum_score": "399.75", "graduated_student_count": 43,
            "dropped_out_student_count": 15, "non_renewed_student_count": 11,
        },
        {
            "academic_year": "2025-2026", "quota": 100, "enrolled_student_count": 44,
            "minimum_admission_score": "358.90", "national_average_minimum_score": "389.80",
            "ankara_average_minimum_score": "406.20", "graduated_student_count": 40,
            "dropped_out_student_count": 18, "non_renewed_student_count": 14,
        },
    ],
}

# Karşılaştırma için diğer üniversitelerin benzer programları.
COMPARABLE_PROGRAMS: Tuple[dict, ...] = (
    {
        "university_name": "Orta Doğu Teknik Üniversitesi", "program_name": "Computer Engineering",
        "city": "Ankara", "academic_year": "2025-2026", "quota": 130,
        "enrolled_student_count": 130, "occupancy_rate": "100.00",
        "minimum_admission_score": "498.40", "is_competitor": True,
    },
    {
        "university_name": "Hacettepe Üniversitesi", "program_name": "Computer Engineering",
        "city": "Ankara", "academic_year": "2025-2026", "quota": 120,
        "enrolled_student_count": 118, "occupancy_rate": "98.33",
        "minimum_admission_score": "471.25", "is_competitor": True,
    },
    {
        "university_name": "Gazi Üniversitesi", "program_name": "Computer Engineering",
        "city": "Ankara", "academic_year": "2025-2026", "quota": 110,
        "enrolled_student_count": 102, "occupancy_rate": "92.73",
        "minimum_admission_score": "442.60", "is_competitor": True,
    },
    {
        "university_name": "Ankara Üniversitesi", "program_name": "Software Engineering",
        "city": "Ankara", "academic_year": "2025-2026", "quota": 90,
        "enrolled_student_count": 78, "occupancy_rate": "86.67",
        "minimum_admission_score": "418.30", "is_competitor": False,
    },
    {
        "university_name": "Ege Üniversitesi", "program_name": "Computer Engineering",
        "city": "İzmir", "academic_year": "2025-2026", "quota": 100,
        "enrolled_student_count": 84, "occupancy_rate": "84.00",
        "minimum_admission_score": "402.15", "is_competitor": False,
    },
    {
        "university_name": "Karadeniz Teknik Üniversitesi", "program_name": "Software Engineering",
        "city": "Trabzon", "academic_year": "2025-2026", "quota": 80,
        "enrolled_student_count": 55, "occupancy_rate": "68.75",
        "minimum_admission_score": "364.80", "is_competitor": False,
    },
    {
        "university_name": "Akdeniz Üniversitesi", "program_name": "Computer Engineering",
        "city": "Antalya", "academic_year": "2025-2026", "quota": 85,
        "enrolled_student_count": 51, "occupancy_rate": "60.00",
        "minimum_admission_score": "351.40", "is_competitor": False,
    },
)


def _weighted_status(rng: random.Random, enrollment_year: int) -> str:
    """Kayıt yılına uygun bir öğrenci durumu seçer."""
    # 2025 girişli bir öğrencinin mezun olmuş olması mantıksız olurdu;
    # bu yüzden yeni kayıtlarda mezun/bırakmış durumları elenir.
    candidates: List[str] = []
    for status_value, weight in STATUS_WEIGHTS:
        if enrollment_year >= 2025 and status_value in ("graduated", "dropped-out"):
            continue
        if enrollment_year <= 2023 and status_value == "newly-enrolled":
            continue
        candidates.extend([status_value] * weight)
    return rng.choice(candidates)


def _build_students(programs: Dict[str, AcademicProgram]) -> List[dict]:
    """Deterministik olarak öğrenci verisi üretir."""
    rng = random.Random(RANDOM_SEED)
    students: List[dict] = []

    for index in range(1, TOTAL_STUDENTS + 1):
        enrollment_year: int = ENROLLMENT_YEARS[index % len(ENROLLMENT_YEARS)]
        program_code: str = PROGRAM_CODES[index % len(PROGRAM_CODES)]
        status_value: str = _weighted_status(rng, enrollment_year)

        # Her 6. öğrenci uluslararası, her 3. öğrenci burslu, her 9. öğrenci hazırlıkta.
        is_international: bool = index % 6 == 0
        has_scholarship: bool = index % 3 == 0
        is_preparatory: bool = index % 9 == 0 and enrollment_year >= 2024

        scholarship: Decimal = (
            Decimal(str(rng.choice([25, 50, 75, 100]))) if has_scholarship else Decimal("0")
        )

        # GPA dağılımı: çoğunluk 2.0-3.5 arasında, küçük bir grup düşük başarılı.
        gpa_value: float = round(rng.uniform(1.20, 3.95), 2)

        actual_graduation: Optional[int] = None
        if status_value == "graduated":
            # Mezuniyet süresi 4-6 yıl arasında değişir.
            actual_graduation = enrollment_year + rng.choice([4, 4, 4, 5, 5, 6])

        students.append(
            {
                "student_number": f"{enrollment_year}{index:04d}",
                "first_name": FIRST_NAMES[index % len(FIRST_NAMES)],
                "last_name": LAST_NAMES[index % len(LAST_NAMES)],
                "gender": ["male", "female", "female", "male", "other", "unspecified"][index % 6],
                "nationality": (
                    NATIONALITIES_INTERNATIONAL[index % len(NATIONALITIES_INTERNATIONAL)]
                    if is_international
                    else NATIONALITIES_LOCAL[0]
                ),
                "is_international": is_international,
                "scholarship_rate_percent": scholarship,
                "enrollment_year": enrollment_year,
                "current_status": status_value,
                "preparatory_school": is_preparatory,
                "academic_program_id": programs[program_code].id,
                "current_gpa": Decimal(str(gpa_value)),
                "expected_graduation_year": enrollment_year + 4,
                "actual_graduation_year": actual_graduation,
                "is_active": True,
            }
        )

    return students


def _build_records(rng: random.Random, student: Student) -> List[dict]:
    """Bir öğrenci için en az iki dönemlik akademik kayıt üretir."""
    records: List[dict] = []
    academic_year: str = f"{student.enrollment_year}-{student.enrollment_year + 1}"

    cumulative: float = float(student.current_gpa or Decimal("2.50"))

    for semester in SEMESTERS:
        registered: int = rng.choice([5, 6, 7])
        # Düşük GPA'lı öğrenciler daha fazla ders bırakır; veri gerçekçi olsun diye ilişkilendirildi.
        failed: int = 0 if cumulative >= 3.0 else rng.choice([0, 1, 1, 2])
        passed: int = registered - failed

        attempted: int = registered * 5
        earned: int = passed * 5

        semester_gpa: float = round(min(4.0, max(0.0, cumulative + rng.uniform(-0.3, 0.3))), 2)

        records.append(
            {
                "academic_year": academic_year,
                "semester": semester,
                "registered_course_count": registered,
                "passed_course_count": passed,
                "failed_course_count": failed,
                "earned_credits": earned,
                "attempted_credits": attempted,
                "semester_gpa": Decimal(str(semester_gpa)),
                "cumulative_gpa": Decimal(str(round(cumulative, 2))),
                # Kaydını yenilemeyen öğrencilerin son dönemi yenilenmemiş görünür.
                "registration_renewed": student.current_status != "non-renewed",
            }
        )

    return records


def seed() -> None:
    """Öğrenci, akademik kayıt, snapshot ve karşılaştırma verilerini ekler."""
    init_db()
    db: Session = SessionLocal()

    created: Dict[str, int] = {"student": 0, "record": 0, "snapshot": 0, "comparable": 0}
    skipped: Dict[str, int] = {"student": 0, "record": 0, "snapshot": 0, "comparable": 0}

    try:
        # 1) Modül 1'den gelen programları bul.
        programs: Dict[str, AcademicProgram] = {}
        for code in PROGRAM_CODES:
            program: Optional[AcademicProgram] = (
                db.execute(select(AcademicProgram).where(AcademicProgram.code == code))
                .scalars()
                .first()
            )
            if program is None:
                print(
                    f"HATA: '{code}' kodlu program bulunamadi. "
                    "Once 'python seed_data.py' calistirin."
                )
                return
            programs[code] = program

        # 2) Öğrenciler
        # Mevcut öğrenci numaralarını tek sorguda alıp bellekte kontrol ediyoruz;
        # 120 öğrenci için 120 ayrı SELECT atmaktan çok daha hızlı.
        existing_numbers = {
            number for (number,) in db.execute(select(Student.student_number)).all()
        }

        new_students: List[Student] = []
        for data in _build_students(programs):
            if data["student_number"] in existing_numbers:
                skipped["student"] += 1
                continue
            student = Student(**data)
            db.add(student)
            new_students.append(student)
            created["student"] += 1

        # flush: öğrenci id'leri üretilsin ki akademik kayıtlar bağlanabilsin.
        db.flush()

        # 3) Akademik kayıtlar
        existing_record_keys = {
            (student_id, year, semester)
            for student_id, year, semester in db.execute(
                select(
                    StudentAcademicRecord.student_id,
                    StudentAcademicRecord.academic_year,
                    StudentAcademicRecord.semester,
                )
            ).all()
        }

        record_rng = random.Random(RANDOM_SEED + 1)
        for student in new_students:
            for record_data in _build_records(record_rng, student):
                key = (student.id, record_data["academic_year"], record_data["semester"])
                if key in existing_record_keys:
                    skipped["record"] += 1
                    continue
                db.add(StudentAcademicRecord(student_id=student.id, **record_data))
                created["record"] += 1

        # 4) Program snapshot'ları
        existing_snapshot_keys = {
            (program_id, year)
            for program_id, year in db.execute(
                select(
                    ProgramEnrollmentSnapshot.academic_program_id,
                    ProgramEnrollmentSnapshot.academic_year,
                )
            ).all()
        }

        for code, snapshots in SNAPSHOT_DATA.items():
            program_id: int = programs[code].id
            for snapshot_data in snapshots:
                if (program_id, snapshot_data["academic_year"]) in existing_snapshot_keys:
                    skipped["snapshot"] += 1
                    continue
                payload = dict(snapshot_data)
                # Puan alanları Decimal olarak saklanır.
                for field_name in (
                    "minimum_admission_score",
                    "national_average_minimum_score",
                    "ankara_average_minimum_score",
                ):
                    payload[field_name] = Decimal(payload[field_name])
                db.add(
                    ProgramEnrollmentSnapshot(academic_program_id=program_id, **payload)
                )
                created["snapshot"] += 1

        # 5) Karşılaştırma programları
        existing_comparable_keys = {
            (university, program, year)
            for university, program, year in db.execute(
                select(
                    ComparableUniversityProgram.university_name,
                    ComparableUniversityProgram.program_name,
                    ComparableUniversityProgram.academic_year,
                )
            ).all()
        }

        for comparable in COMPARABLE_PROGRAMS:
            key = (
                comparable["university_name"],
                comparable["program_name"],
                comparable["academic_year"],
            )
            if key in existing_comparable_keys:
                skipped["comparable"] += 1
                continue
            payload = dict(comparable)
            payload["occupancy_rate"] = Decimal(payload["occupancy_rate"])
            payload["minimum_admission_score"] = Decimal(payload["minimum_admission_score"])
            db.add(ComparableUniversityProgram(**payload))
            created["comparable"] += 1

        db.commit()

        print(
            "Ogrenci seed tamamlandi.\n"
            f"  Ogrenci        : eklenen {created['student']}, mevcut {skipped['student']}\n"
            f"  Akademik kayit : eklenen {created['record']}, mevcut {skipped['record']}\n"
            f"  Snapshot       : eklenen {created['snapshot']}, mevcut {skipped['snapshot']}\n"
            f"  Karsilastirma  : eklenen {created['comparable']}, mevcut {skipped['comparable']}"
        )

    except Exception as error:
        # Hata durumunda yarım veri kalmaması için tüm işlem geri alınır.
        db.rollback()
        print(f"Ogrenci seed sirasinda hata olustu: {error}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
