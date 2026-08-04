"""What-if senaryo hesaplama motoru.

Bütün formüller bu dosyada toplanmıştır. Router ve risk servisleri hesap yapmaz,
sadece buradan çıkan sonucu kullanır. Böylece bir formül değiştiğinde tek bir
dosyaya dokunmak yeterli olur ve hesaplar tek bir yerden test edilebilir.

Para ve oran hesaplarının tamamı Decimal ile yapılır. Float kullanılsaydı
0.1 + 0.2 = 0.30000000000000004 türü sapmalar milyonluk bütçelerde
kuruş değil, lira seviyesinde hataya dönüşürdü.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from app.core.decimal_types import quantize_count, quantize_money
from app.schemas.scenarios import CapacityStatus, ScenarioInputCreate

if TYPE_CHECKING:
    from app.models.scenario_baseline import ScenarioBaseline

# Sık kullanılan sabitler.
ZERO: Decimal = Decimal("0")
HUNDRED: Decimal = Decimal("100")

# Kapasitenin bu oranın üzerinde dolması "sınırda" (tight) kabul edilir.
# Henüz aşılmamıştır ama yönetici erken uyarı alsın diye ayrı bir durum tanımlandı.
TIGHT_CAPACITY_THRESHOLD: Decimal = Decimal("0.90")


class ScenarioValidationError(Exception):
    """Baseline ile birlikte değerlendirildiğinde geçersiz olan girdileri temsil eder.

    Şema katmanı tek başına yakalayamaz; çünkü kuralın sonucu baseline'a bağlıdır
    (örneğin -600 derslik değişimi, baseline 500 ise geçersizdir).
    """

    def __init__(self, message: str, field: str) -> None:
        super().__init__(message)
        self.message: str = message
        self.field: str = field


@dataclass
class ScenarioComputation:
    """Bir simülasyonun tüm hesaplanmış değerlerini taşıyan sonuç nesnesi."""

    # --- Öğrenci ---
    baseline_student_count: int
    projected_student_count: int

    # --- Gelir kalemleri ---
    baseline_revenue: Decimal
    projected_revenue: Decimal
    projected_tuition_revenue: Decimal
    projected_research_revenue: Decimal
    projected_other_revenue: Decimal
    effective_scholarship_rate_percent: Decimal
    scholarship_deduction: Decimal

    # --- Gider kalemleri ---
    baseline_expenditure: Decimal
    projected_expenditure: Decimal
    projected_personnel_expense: Decimal
    projected_education_expense: Decimal
    projected_rd_expense: Decimal
    projected_building_energy_expense: Decimal
    projected_technology_expense: Decimal

    # --- Personel ---
    baseline_staff_count: int
    projected_staff_count: int
    baseline_student_staff_ratio: Decimal
    projected_student_staff_ratio: Decimal

    # --- Maliyet ---
    baseline_cost_per_student: Decimal
    projected_cost_per_student: Decimal

    # --- Kapasite ---
    baseline_classroom_capacity: int
    projected_classroom_capacity: int
    baseline_laboratory_capacity: int
    projected_laboratory_capacity: int
    classroom_capacity_status: CapacityStatus
    laboratory_capacity_status: CapacityStatus

    # --- Bütçe dengesi ---
    baseline_balance: Decimal
    projected_balance: Decimal


def growth_factor(percent: Decimal) -> Decimal:
    """Yüzdesel değişimi çarpan katsayısına çevirir (%10 -> 1.10)."""
    # Formüllerde sürekli (1 + p/100) tekrar ettiği için tek fonksiyona alındı.
    return Decimal("1") + (Decimal(str(percent)) / HUNDRED)


def safe_divide(numerator: Decimal, denominator: Decimal) -> Decimal:
    """Sıfıra bölmeyi engelleyerek bölme yapar; payda sıfırsa 0 döner.

    Personel veya öğrenci sayısı sıfıra düşen senaryolarda program çökmesin,
    bunun yerine risk servisi durumu "critical" olarak raporlasın diye böyle yapıldı.
    """
    if denominator == ZERO:
        return ZERO
    return numerator / denominator


def _capacity_status(demand: Decimal, capacity: Decimal) -> CapacityStatus:
    """Talebi kapasiteyle karşılaştırıp yeterlilik durumunu belirler."""
    # Kapasite sıfır veya negatifse talep karşılanamıyor demektir.
    if capacity <= ZERO:
        return CapacityStatus.INSUFFICIENT
    if demand > capacity:
        return CapacityStatus.INSUFFICIENT
    if demand >= capacity * TIGHT_CAPACITY_THRESHOLD:
        return CapacityStatus.TIGHT
    return CapacityStatus.SUFFICIENT


def _validate_against_baseline(
    baseline: "ScenarioBaseline",
    data: ScenarioInputCreate,
) -> None:
    """Baseline ile birleştiğinde anlamsız hale gelen girdileri reddeder."""
    # Kapasite değişimi negatif olabilir ama sonucun negatife düşmesi fiziksel olarak imkânsız.
    projected_classroom: int = baseline.classroom_capacity + data.classroom_capacity_change
    if projected_classroom < 0:
        raise ScenarioValidationError(
            f"Derslik kapasitesi değişimi geçersiz: mevcut kapasite "
            f"{baseline.classroom_capacity}, uygulanan değişim {data.classroom_capacity_change}. "
            "Sonuç kapasite sıfırın altına düşemez.",
            field="classroom_capacity_change",
        )

    projected_laboratory: int = baseline.laboratory_capacity + data.laboratory_capacity_change
    if projected_laboratory < 0:
        raise ScenarioValidationError(
            f"Laboratuvar kapasitesi değişimi geçersiz: mevcut kapasite "
            f"{baseline.laboratory_capacity}, uygulanan değişim {data.laboratory_capacity_change}. "
            "Sonuç kapasite sıfırın altına düşemez.",
            field="laboratory_capacity_change",
        )


def calculate(
    baseline: "ScenarioBaseline",
    data: ScenarioInputCreate,
    student_count_override: Optional[int] = None,
) -> ScenarioComputation:
    """Baseline ve girdi parametrelerine göre tüm senaryo sonuçlarını hesaplar.

    student_count_override verilirse başlangıç öğrenci sayısı baseline yerine
    bu değerden alınır (Modül 2 canlı öğrenci verisi entegrasyonu). Baseline
    nesnesi değiştirilmez; aksi halde geçici bir hesap kalıcı veriyi bozardı.
    """
    _validate_against_baseline(baseline, data)

    # ------------------------------------------------------------------
    # 1) MEVCUT DURUM (baseline) hesapları
    # ------------------------------------------------------------------
    effective_student_count: int = (
        student_count_override if student_count_override is not None else baseline.student_count
    )
    baseline_student_count: Decimal = Decimal(effective_student_count)
    baseline_staff_count: Decimal = Decimal(baseline.academic_staff_count)

    baseline_gross_tuition: Decimal = baseline_student_count * baseline.annual_tuition_per_student
    baseline_scholarship: Decimal = baseline_gross_tuition * (
        baseline.scholarship_rate_percent / HUNDRED
    )
    baseline_tuition_revenue: Decimal = baseline_gross_tuition - baseline_scholarship

    baseline_revenue: Decimal = (
        baseline_tuition_revenue
        + baseline.annual_research_revenue
        + baseline.annual_other_revenue
    )

    baseline_expenditure: Decimal = (
        baseline.annual_personnel_expense
        + baseline.annual_education_expense
        + baseline.annual_rd_expense
        + baseline.annual_building_energy_expense
        + baseline.annual_technology_expense
    )

    baseline_ratio: Decimal = safe_divide(baseline_student_count, baseline_staff_count)
    baseline_cost_per_student: Decimal = safe_divide(baseline_expenditure, baseline_student_count)

    # ------------------------------------------------------------------
    # 2) ÖĞRENCİ SAYISI
    # ------------------------------------------------------------------
    # Öğrenci sayısı sayılabilir bir değer olduğu için en yakın tam sayıya yuvarlanır.
    projected_student_raw: Decimal = baseline_student_count * growth_factor(
        data.student_change_percent
    )
    projected_student_count: Decimal = quantize_count(projected_student_raw)

    # ------------------------------------------------------------------
    # 3) GELİRLER
    # ------------------------------------------------------------------
    gross_tuition_revenue: Decimal = (
        projected_student_count
        * baseline.annual_tuition_per_student
        * growth_factor(data.tuition_change_percent)
    )

    # Burs oranı: mevcut orana yüzde puanı olarak eklenir (%35 + %10 = %45).
    effective_scholarship_rate: Decimal = (
        baseline.scholarship_rate_percent + data.scholarship_change_percent
    )
    scholarship_deduction: Decimal = gross_tuition_revenue * (
        effective_scholarship_rate / HUNDRED
    )
    projected_tuition_revenue: Decimal = gross_tuition_revenue - scholarship_deduction

    projected_research_revenue: Decimal = baseline.annual_research_revenue * growth_factor(
        data.research_funding_change_percent
    )
    # Diğer gelirler senaryo parametrelerinden etkilenmiyor kabul edildi.
    projected_other_revenue: Decimal = baseline.annual_other_revenue

    projected_revenue: Decimal = (
        projected_tuition_revenue + projected_research_revenue + projected_other_revenue
    )

    # ------------------------------------------------------------------
    # 4) GİDERLER
    # ------------------------------------------------------------------
    # Ortalama personel maliyeti: toplam personel gideri / personel sayısı.
    # İşe alınan/çıkarılan her akademisyen bütçeyi bu tutar kadar etkiler.
    average_staff_cost: Decimal = safe_divide(
        baseline.annual_personnel_expense, baseline_staff_count
    )
    projected_personnel_expense: Decimal = baseline.annual_personnel_expense + (
        Decimal(data.academic_staff_change) * average_staff_cost
    )

    # Eğitim gideri hem öğrenci sayısından hem enflasyondan etkilenir.
    projected_education_expense: Decimal = (
        baseline.annual_education_expense
        * growth_factor(data.student_change_percent)
        * growth_factor(data.inflation_percent)
    )

    # Ar-Ge gideri araştırma fonuyla birlikte büyür, enflasyondan da etkilenir.
    projected_rd_expense: Decimal = (
        baseline.annual_rd_expense
        * growth_factor(data.research_funding_change_percent)
        * growth_factor(data.inflation_percent)
    )

    # Bina ve enerji gideri yalnızca enflasyona bağlı kabul edildi.
    projected_building_energy_expense: Decimal = (
        baseline.annual_building_energy_expense * growth_factor(data.inflation_percent)
    )

    # Teknoloji gideri büyük ölçüde ithal olduğu için hem enflasyondan hem kurdan etkilenir.
    projected_technology_expense: Decimal = (
        baseline.annual_technology_expense
        * growth_factor(data.inflation_percent)
        * growth_factor(data.exchange_rate_change_percent)
    )

    projected_expenditure: Decimal = (
        projected_personnel_expense
        + projected_education_expense
        + projected_rd_expense
        + projected_building_energy_expense
        + projected_technology_expense
    )

    # ------------------------------------------------------------------
    # 5) PERSONEL, ORAN VE MALİYET
    # ------------------------------------------------------------------
    projected_staff_count: Decimal = baseline_staff_count + Decimal(data.academic_staff_change)

    # safe_divide sayesinde personel sıfıra düşse bile hesap çökmez;
    # bu durum risk servisinde "critical" olarak raporlanır.
    projected_ratio: Decimal = safe_divide(projected_student_count, projected_staff_count)
    projected_cost_per_student: Decimal = safe_divide(
        projected_expenditure, projected_student_count
    )

    # ------------------------------------------------------------------
    # 6) KAPASİTE
    # ------------------------------------------------------------------
    projected_classroom_capacity: Decimal = Decimal(
        baseline.classroom_capacity + data.classroom_capacity_change
    )
    projected_laboratory_capacity: Decimal = Decimal(
        baseline.laboratory_capacity + data.laboratory_capacity_change
    )

    return ScenarioComputation(
        baseline_student_count=int(effective_student_count),
        projected_student_count=int(projected_student_count),
        baseline_revenue=quantize_money(baseline_revenue),
        projected_revenue=quantize_money(projected_revenue),
        projected_tuition_revenue=quantize_money(projected_tuition_revenue),
        projected_research_revenue=quantize_money(projected_research_revenue),
        projected_other_revenue=quantize_money(projected_other_revenue),
        effective_scholarship_rate_percent=quantize_money(effective_scholarship_rate),
        scholarship_deduction=quantize_money(scholarship_deduction),
        baseline_expenditure=quantize_money(baseline_expenditure),
        projected_expenditure=quantize_money(projected_expenditure),
        projected_personnel_expense=quantize_money(projected_personnel_expense),
        projected_education_expense=quantize_money(projected_education_expense),
        projected_rd_expense=quantize_money(projected_rd_expense),
        projected_building_energy_expense=quantize_money(projected_building_energy_expense),
        projected_technology_expense=quantize_money(projected_technology_expense),
        baseline_staff_count=int(baseline.academic_staff_count),
        projected_staff_count=int(projected_staff_count),
        baseline_student_staff_ratio=quantize_money(baseline_ratio),
        projected_student_staff_ratio=quantize_money(projected_ratio),
        baseline_cost_per_student=quantize_money(baseline_cost_per_student),
        projected_cost_per_student=quantize_money(projected_cost_per_student),
        baseline_classroom_capacity=int(baseline.classroom_capacity),
        projected_classroom_capacity=int(projected_classroom_capacity),
        baseline_laboratory_capacity=int(baseline.laboratory_capacity),
        projected_laboratory_capacity=int(projected_laboratory_capacity),
        classroom_capacity_status=_capacity_status(
            projected_student_count, projected_classroom_capacity
        ),
        laboratory_capacity_status=_capacity_status(
            projected_student_count, projected_laboratory_capacity
        ),
        baseline_balance=quantize_money(baseline_revenue - baseline_expenditure),
        projected_balance=quantize_money(projected_revenue - projected_expenditure),
    )
