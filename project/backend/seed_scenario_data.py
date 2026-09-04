"""Modül 9 (What-if Scenario Analysis) için başlangıç verilerini ekleyen script.

Çalıştırma:  python seed_scenario_data.py
Script birden fazla kez çalıştırılsa bile aynı kayıtları tekrar eklemez.

seed_data.py dosyasına dokunulmamıştır; bu script bağımsız çalışır ve
Modül 1 verilerine ihtiyaç duymaz.
"""

from decimal import Decimal
from typing import Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal, init_db
from app.models import Scenario, ScenarioBaseline

# Örnek baseline değerleri. Gerçek finans ve personel modülleri devreye girene kadar
# simülasyonların referans noktası bu kayıt olacak.
BASELINE_NAME: str = "2026 University Baseline"

BASELINE_VALUES: dict = {
    # TÜM TUTARLAR USD. Değerler shared_demo_data/05_finance.json içindeki
    # 2025-2026 mali dönemiyle tutarlıdır; seed_all_demo_data.py çalıştığında
    # bu taban zaten o dönemin gerçek verisiyle güncellenir. Buradaki değerler
    # yalnızca birim testlerinin kullandığı hafif veri kümesi içindir ve aynı
    # büyüklük mertebesinde tutulmuştur ki iki ortam birbirinden kopmasın.
    "student_count": 4000,
    "annual_tuition_per_student": Decimal("9500"),
    "scholarship_rate_percent": Decimal("38"),
    "annual_research_revenue": Decimal("5600000"),
    "annual_other_revenue": Decimal("6800000"),
    "annual_personnel_expense": Decimal("8210000"),
    "annual_education_expense": Decimal("5200000"),
    "annual_rd_expense": Decimal("4100000"),
    "annual_building_energy_expense": Decimal("10250000"),
    "annual_technology_expense": Decimal("2750000"),
    "academic_staff_count": 180,
    "classroom_capacity": 1020,
    "laboratory_capacity": 328,
    "is_active": True,
}

# Örnek senaryolar: her biri farklı bir senaryo türünü temsil ediyor.
SCENARIOS: list = [
    {
        "name": "Student Growth 10 Percent",
        "description": "Öğrenci sayısının %10 artması durumunda kapasite ve mali etkiler.",
        "scenario_type": "student-enrollment",
    },
    {
        "name": "Inflation and Exchange Rate Risk",
        "description": "Yüksek enflasyon ve kur artışının gider kalemlerine etkisi.",
        "scenario_type": "economic-risk",
    },
    {
        "name": "Academic Staff Expansion",
        "description": "Yeni akademik personel alımının bütçe ve öğrenci/öğretim üyesi oranına etkisi.",
        "scenario_type": "academic-staffing",
    },
    {
        "name": "Combined Growth Scenario",
        "description": "Öğrenci artışı, ücret artışı, personel alımı ve enflasyonun birlikte etkisi.",
        "scenario_type": "combined",
    },
]


def get_or_create_baseline(db: Session) -> Tuple[ScenarioBaseline, bool]:
    """Örnek baseline'ı adına göre arar; yoksa oluşturur."""
    # Benzersizlik kontrolünü name üzerinden yapıyoruz; baseline tablosunda
    # code gibi ayrı bir anahtar alan bulunmuyor.
    existing: Optional[ScenarioBaseline] = (
        db.execute(select(ScenarioBaseline).where(ScenarioBaseline.name == BASELINE_NAME))
        .scalars()
        .first()
    )
    if existing is not None:
        return existing, False

    # Yeni baseline aktif olacağı için varsa diğer aktif kayıtları pasifleştiriyoruz.
    for other in db.execute(
        select(ScenarioBaseline).where(ScenarioBaseline.is_active.is_(True))
    ).scalars().all():
        other.is_active = False

    baseline = ScenarioBaseline(name=BASELINE_NAME, **BASELINE_VALUES)
    db.add(baseline)
    db.flush()
    return baseline, True


def get_or_create_scenario(db: Session, data: dict) -> Tuple[Scenario, bool]:
    """Senaryoyu adına göre arar; yoksa oluşturur."""
    existing: Optional[Scenario] = (
        db.execute(select(Scenario).where(Scenario.name == data["name"])).scalars().first()
    )
    if existing is not None:
        return existing, False

    scenario = Scenario(status="draft", **data)
    db.add(scenario)
    db.flush()
    return scenario, True


def seed() -> None:
    """Örnek baseline ve senaryoları veritabanına ekler."""
    init_db()

    db: Session = SessionLocal()
    created: int = 0
    skipped: int = 0

    try:
        _, was_created = get_or_create_baseline(db)
        created += int(was_created)
        skipped += int(not was_created)

        for scenario_data in SCENARIOS:
            _, was_created = get_or_create_scenario(db, scenario_data)
            created += int(was_created)
            skipped += int(not was_created)

        db.commit()
        print(f"Senaryo seed tamamlandi. Eklenen: {created}, zaten mevcut: {skipped}")

    except Exception as error:
        # Hata durumunda yarım veri kalmaması için tüm işlem geri alınır.
        db.rollback()
        print(f"Senaryo seed sirasinda hata olustu: {error}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
