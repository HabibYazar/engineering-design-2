"""Mali dönemden senaryo baseline'ı türetir.

Neden gerekli
-------------
Senaryo baseline'ı ile mali analiz modülü birbirinden bağımsızdı. Aynı kurumun
yıllık geliri senaryo ekranında bir, mali analiz ekranında başka bir sayı
gösteriyordu. Bir karar destek sisteminde bu, verilen kararı doğrudan yanlış
yapan bir tutarsızlıktır.

Artık kullanıcı bir mali dönem seçtiğinde, o dönemin gerçek gelir/gider
kalemlerinden ve sürücü değerlerinden geçici bir baseline üretilir. Senaryo
"2023-2024 rakamlarıyla maaşlara %2 zam yapsaydık ne olurdu" sorusunu da
cevaplayabilir hale gelir.

Üretilen baseline veritabanına YAZILMAZ; yalnızca hesaplama için kullanılan
geçici bir nesnedir. Kalıcı baseline kayıtları etkilenmez.
"""

from decimal import Decimal
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.decimal_types import quantize_money
from app.models import FinancialEntry, FinancialPeriod, ScenarioBaseline

ZERO = Decimal("0")
HUNDRED = Decimal("100")

# Mali kalemler milyon USD olarak saklanır; senaryo motoru tam USD ile çalışır.
MILLION = Decimal("1000000")

# Gider kalemlerinin senaryo motorundaki beş kovaya eşlenmesi.
# Senaryo motoru beş gider kalemi tanır; mali modülde dokuz kalem vardır.
# Eşleme burada tek yerde tanımlanır ki iki modül birbirinden kopmasın.
EXPENSE_BUCKETS = {
    "personnel": ("akademik personel", "idari personel", "burs"),
    "education": ("eğitim", "laboratuvar"),
    "rd": ("araştırma", "geliştirme", "ar-ge"),
    "building_energy": ("altyapı", "bakım", "enerji", "işletme"),
    "technology": ("bilgi teknolojileri", "teknoloji"),
}

# Gelir kalemlerinin eşlenmesi.
REVENUE_BUCKETS = {
    "tuition": ("öğrenim ücret",),
    "research": ("araştırma proje",),
    # kalan her şey "other"
}


def _bucket_for(category: str, buckets: dict) -> Optional[str]:
    """Kalem adını kovaya eşler; eşleşme yoksa None döner."""
    lowered = category.lower()
    for bucket, keywords in buckets.items():
        if any(keyword in lowered for keyword in keywords):
            return bucket
    return None


def build_from_financial_period(db: Session, academic_year: str) -> ScenarioBaseline:
    """Verilen mali dönemin gerçek verisinden geçici bir baseline üretir."""
    period: Optional[FinancialPeriod] = db.execute(
        select(FinancialPeriod).where(FinancialPeriod.academic_year == academic_year)
    ).scalars().first()

    if period is None:
        available: List[str] = [
            p.academic_year
            for p in db.execute(
                select(FinancialPeriod).order_by(FinancialPeriod.academic_year)
            ).scalars()
        ]
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"'{academic_year}' için mali dönem bulunamadı. "
                f"Mevcut dönemler: {', '.join(available) if available else 'hiç yok'}."
            ),
        )

    entries: List[FinancialEntry] = list(
        db.execute(
            select(FinancialEntry).where(FinancialEntry.financial_period_id == period.id)
        ).scalars()
    )

    if not entries:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"'{academic_year}' döneminde gelir/gider kalemi girilmemiş. "
                "Bu dönemden senaryo tabanı üretilemez."
            ),
        )

    # --- Gelirler ---
    revenue = {"tuition": ZERO, "research": ZERO, "other": ZERO}
    for entry in entries:
        if entry.kind != "revenue":
            continue
        bucket = _bucket_for(entry.category, REVENUE_BUCKETS) or "other"
        revenue[bucket] += entry.amount * MILLION

    # --- Giderler ---
    expense = {key: ZERO for key in EXPENSE_BUCKETS}
    expense["technology"] = ZERO
    for entry in entries:
        if entry.kind != "expenditure":
            continue
        bucket = _bucket_for(entry.category, EXPENSE_BUCKETS) or "technology"
        expense[bucket] += entry.amount * MILLION

    # --- Öğrenim ücreti ve burs oranı ---
    # Mali kayıttaki öğrenim ücreti geliri BRÜTTÜR (burs gideri ayrı kalemdir).
    # Senaryo motoru brüt ücret ve burs oranıyla çalıştığı için sürücü
    # değerleri doğrudan kullanılıyor.
    student_count = period.total_students or 0
    tuition_per_student = period.list_tuition_per_student_usd or ZERO
    if tuition_per_student == ZERO and student_count:
        # Sürücü değer girilmemişse brüt gelirden geri hesaplanır.
        tuition_per_student = revenue["tuition"] / Decimal(student_count)

    scholarship_rate = period.average_scholarship_rate_percent or ZERO

    # Burs gideri personel kovasına düşmesin: senaryo motorunda burs, gelirden
    # düşülen bir kalemdir. Gider tarafından çıkarılıyor ki iki kez sayılmasın.
    scholarship_expense = ZERO
    for entry in entries:
        if entry.kind == "expenditure" and "burs" in entry.category.lower():
            scholarship_expense += entry.amount * MILLION
    expense["personnel"] -= scholarship_expense

    baseline = ScenarioBaseline(
        name=f"{academic_year} mali dönemi",
        student_count=student_count,
        annual_tuition_per_student=quantize_money(tuition_per_student),
        scholarship_rate_percent=quantize_money(scholarship_rate),
        annual_research_revenue=quantize_money(revenue["research"]),
        annual_other_revenue=quantize_money(revenue["other"]),
        annual_personnel_expense=quantize_money(expense["personnel"]),
        annual_education_expense=quantize_money(expense["education"]),
        annual_rd_expense=quantize_money(expense["rd"]),
        annual_building_energy_expense=quantize_money(expense["building_energy"]),
        annual_technology_expense=quantize_money(expense["technology"]),
        academic_staff_count=period.academic_staff_count or 0,
        classroom_capacity=_capacity_from_facilities(db, "classroom"),
        laboratory_capacity=_capacity_from_facilities(db, "laboratory"),
        is_active=False,
    )
    # Geçici nesne; oturuma eklenmez, veritabanına yazılmaz.
    return baseline


def _capacity_from_facilities(db: Session, facility_type: str) -> int:
    """Kapasiteyi fiziksel mekân modülünden okur.

    Baseline'a elle kapasite yazmak yerine gerçek mekân envanterinden
    toplanıyor; böylece bir derslik eklendiğinde senaryo da güncel kapasiteyi
    kullanıyor.
    """
    from sqlalchemy import func

    from app.models import PhysicalFacility

    total = db.execute(
        select(func.sum(PhysicalFacility.capacity)).where(
            PhysicalFacility.facility_type == facility_type,
            PhysicalFacility.is_active.is_(True),
        )
    ).scalar()
    return int(total or 0)


def available_periods(db: Session) -> List[str]:
    """Senaryo tabanı üretilebilecek mali dönemler.

    Kalemi olmayan (henüz gerçekleşmemiş) dönemler listelenmez; seçilseler
    sıfır tabanlı anlamsız bir senaryo üretirlerdi.
    """
    rows = db.execute(
        select(FinancialPeriod.academic_year)
        .join(FinancialEntry, FinancialEntry.financial_period_id == FinancialPeriod.id)
        .group_by(FinancialPeriod.academic_year)
        .order_by(FinancialPeriod.academic_year)
    ).scalars()
    result = []
    for year in rows:
        period = db.execute(
            select(FinancialPeriod).where(FinancialPeriod.academic_year == year)
        ).scalars().first()
        # Öğrenci sayısı sıfır olan planlama yılından anlamlı senaryo çıkmaz.
        if period and period.total_students > 0:
            result.append(year)
    return result
