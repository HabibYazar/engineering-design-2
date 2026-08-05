"""What-if senaryo hesaplama motoru.

Bütün formüller bu dosyada toplanmıştır. Router, risk servisi ve ARAYÜZ hesap
yapmaz; sadece buradan çıkan sonucu kullanır. Böylece bir formül değiştiğinde
tek bir dosyaya dokunmak yeterli olur ve hesaplar tek yerden test edilebilir.

Para ve oran hesaplarının tamamı Decimal ile yapılır. Float kullanılsaydı
0.1 + 0.2 = 0.30000000000000004 türü sapmalar milyonluk bütçelerde
sent değil, dolar seviyesinde hataya dönüşürdü.

TÜM PARASAL DEĞERLER USD CİNSİNDENDİR.

Entegrasyon sonrası düzeltilen hatalar
--------------------------------------
1. Maaş değişikliği senaryosu yoktu. Personel gideri yalnızca kişi sayısıyla
   değişebiliyordu; "maaşlara %2 zam" sorusu cevaplanamıyordu.
2. Kapasite yeterliliği, tüm öğrencilerin aynı anda derslikte olduğu
   varsayımıyla hesaplanıyordu. Artık eş zamanlı kullanım katsayısı uygulanıyor.
3. Baseline mali dönemden bağımsızdı; senaryo ekranı ile mali analiz ekranı
   aynı kurumun gelirini farklı söylüyordu. Artık baseline seçilen mali
   dönemden türetiliyor.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Dict, Optional

from app.core.decimal_types import quantize_count, quantize_money
from app.schemas.scenarios import CapacityStatus, ScenarioInputCreate

if TYPE_CHECKING:
    from app.models.scenario_baseline import ScenarioBaseline

# Sık kullanılan sabitler.
ZERO: Decimal = Decimal("0")
HUNDRED: Decimal = Decimal("100")

# Kapasitenin bu oranın üzerinde dolması "sınırda" (tight) kabul edilir.
TIGHT_CAPACITY_THRESHOLD: Decimal = Decimal("0.90")

# Eş zamanlı kullanım katsayıları.
# Tüm öğrenciler aynı anda derslikte bulunmaz; ders programı gün ve saate
# yayılır. Katsayısız karşılaştırma her kurumu "kapasitesi yetersiz"
# gösteriyordu ve uyarı anlamsızlaşıyordu.
# Kaynak: shared_demo_data/00_assumptions.json → kapasite_varsayimlari
SIMULTANEOUS_CLASSROOM_USE: Decimal = Decimal("0.35")
SIMULTANEOUS_LABORATORY_USE: Decimal = Decimal("0.18")

# Kontenjan artışının öğrenci sayısına yansıma oranı.
# Kontenjan açmak tek başına öğrenci getirmez; mevcut doluluk oranı kadarı dolar.
# Bu katsayı olmadan "kontenjanı %50 artır" senaryosu geliri gerçekçi olmayan
# biçimde %50 artırırdı.
QUOTA_FILL_ELASTICITY: Decimal = Decimal("0.85")


class ScenarioValidationError(Exception):
    """Baseline ile birlikte değerlendirildiğinde geçersiz olan girdiler.

    Şema katmanı tek başına yakalayamaz; çünkü kuralın sonucu baseline'a
    bağlıdır (örneğin -600 derslik değişimi, baseline 500 ise geçersizdir).
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
    baseline_scholarship_rate_percent: Decimal
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

    # --- Maaş ayrıntısı (yeni) ---
    baseline_average_academic_salary: Decimal
    projected_average_academic_salary: Decimal
    baseline_academic_personnel_expense: Decimal
    projected_academic_personnel_expense: Decimal

    # --- Eş zamanlı kapasite talebi (yeni) ---
    simultaneous_classroom_demand: int
    simultaneous_laboratory_demand: int


def growth_factor(percent: Decimal) -> Decimal:
    """Yüzdesel değişimi çarpan katsayısına çevirir (%10 -> 1.10)."""
    return Decimal("1") + (Decimal(str(percent)) / HUNDRED)


def safe_divide(numerator: Decimal, denominator: Decimal) -> Decimal:
    """Sıfıra bölmeyi engelleyerek bölme yapar; payda sıfırsa 0 döner.

    Personel veya öğrenci sayısı sıfıra düşen senaryolarda program çökmesin,
    bunun yerine risk servisi durumu "critical" olarak raporlasın diye böyle
    yapıldı.
    """
    if denominator == ZERO:
        return ZERO
    return numerator / denominator


def _capacity_status(demand: Decimal, capacity: Decimal) -> CapacityStatus:
    """Eş zamanlı talebi kapasiteyle karşılaştırıp yeterlilik durumunu belirler."""
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

    projected_staff: int = baseline.academic_staff_count + data.academic_staff_change
    if projected_staff < 0:
        raise ScenarioValidationError(
            f"Akademik personel değişimi geçersiz: mevcut kadro "
            f"{baseline.academic_staff_count}, uygulanan değişim {data.academic_staff_change}. "
            "Personel sayısı sıfırın altına düşemez.",
            field="academic_staff_change",
        )

    # Efektif burs oranı %0-%100 dışına çıkamaz.
    effective_scholarship = baseline.scholarship_rate_percent + data.scholarship_change_percent
    if effective_scholarship < ZERO or effective_scholarship > HUNDRED:
        raise ScenarioValidationError(
            f"Burs oranı değişimi geçersiz: mevcut oran "
            f"%{baseline.scholarship_rate_percent}, eklenen {data.scholarship_change_percent} puan. "
            f"Sonuç %{effective_scholarship} olur; burs oranı %0-%100 aralığında olmalıdır.",
            field="scholarship_change_percent",
        )


def calculate(
    baseline: "ScenarioBaseline",
    data: ScenarioInputCreate,
    student_count_override: Optional[int] = None,
) -> ScenarioComputation:
    """Baseline ve girdi parametrelerine göre tüm senaryo sonuçlarını hesaplar.

    student_count_override verilirse başlangıç öğrenci sayısı baseline yerine
    bu değerden alınır (canlı öğrenci verisi entegrasyonu). Baseline nesnesi
    değiştirilmez; aksi halde geçici bir hesap kalıcı veriyi bozardı.
    """
    _validate_against_baseline(baseline, data)

    # ------------------------------------------------------------------
    # 1) MEVCUT DURUM (baseline)
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

    # Ortalama akademik maaş: toplam personel gideri / personel sayısı.
    # Maaş senaryosu bu değeri değiştirerek çalışır.
    baseline_average_salary: Decimal = safe_divide(
        baseline.annual_personnel_expense, baseline_staff_count
    )

    # ------------------------------------------------------------------
    # 2) ÖĞRENCİ SAYISI
    # ------------------------------------------------------------------
    # Öğrenci sayısı iki kaynaktan etkilenir:
    #   a) doğrudan öğrenci sayısı değişimi
    #   b) kontenjan değişimi (doluluk esnekliği kadar yansır)
    # Kontenjan artışının tamamı öğrenciye dönüşmez; boş kontenjan gelir üretmez.
    quota_effect: Decimal = (
        Decimal(str(data.quota_change_percent)) * QUOTA_FILL_ELASTICITY
    )
    combined_student_percent: Decimal = (
        Decimal(str(data.student_change_percent)) + quota_effect
    )
    projected_student_raw: Decimal = baseline_student_count * growth_factor(
        combined_student_percent
    )
    projected_student_count: Decimal = quantize_count(projected_student_raw)

    # Gider formüllerinde de aynı büyüme kullanılmalı. Yuvarlanmış öğrenci
    # sayısından türetiyoruz ki "öğrenci %10 arttı ama eğitim gideri %10,03
    # arttı" gibi açıklanamayan sapma oluşmasın.
    actual_student_growth: Decimal = safe_divide(
        projected_student_count, baseline_student_count
    ) if baseline_student_count != ZERO else Decimal("1")

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
    projected_other_revenue: Decimal = baseline.annual_other_revenue

    # Kalem bazlı gelir değişikliği: yönetici "yalnızca sanayi iş birliği
    # gelirini %20 artırsam" diyebilsin diye. Hangi kalemin hedeflendiği
    # target_revenue_category ile belirlenir.
    if data.target_revenue_category and data.revenue_item_change_percent != ZERO:
        factor = growth_factor(data.revenue_item_change_percent)
        category = data.target_revenue_category.lower()
        if "araştırma" in category or "research" in category:
            projected_research_revenue = projected_research_revenue * factor
        elif "öğrenim" in category or "tuition" in category:
            projected_tuition_revenue = projected_tuition_revenue * factor
        else:
            # Diğer tüm gelir kalemleri "diğer gelirler" havuzunda toplanır.
            projected_other_revenue = projected_other_revenue * factor

    projected_revenue: Decimal = (
        projected_tuition_revenue + projected_research_revenue + projected_other_revenue
    )

    # ------------------------------------------------------------------
    # 4) GİDERLER
    # ------------------------------------------------------------------
    # Personel gideri iki bağımsız etkenden değişir:
    #   a) kadro sayısı  (academic_staff_change)
    #   b) maaş seviyesi (academic_salary_change_percent)
    # Önce yeni kadro sayısı, sonra yeni ortalama maaş; ikisinin çarpımı
    # yeni personel gideridir. Sıralamanın önemi yok, çarpım değişmez;
    # ama ikisini ayrı tutmak "zammın etkisi ne kadardı" sorusunu
    # cevaplanabilir kılıyor.
    projected_staff_count: Decimal = baseline_staff_count + Decimal(data.academic_staff_change)
    projected_average_salary: Decimal = baseline_average_salary * growth_factor(
        data.academic_salary_change_percent
    )
    projected_personnel_expense: Decimal = projected_staff_count * projected_average_salary

    # İdari personel değişimi de personel giderine yansır. İdari kadro ayrı
    # bir baseline alanı olarak tutulmadığı için etkisi, akademik ortalama
    # maaşın %65'i varsayımıyla hesaplanır ve bu varsayım açıkça belgelenir.
    ADMIN_SALARY_RATIO = Decimal("0.65")
    if data.administrative_staff_change != 0 or data.administrative_salary_change_percent != ZERO:
        admin_unit_cost = baseline_average_salary * ADMIN_SALARY_RATIO
        admin_delta = (
            Decimal(data.administrative_staff_change)
            * admin_unit_cost
            * growth_factor(data.administrative_salary_change_percent)
        )
        projected_personnel_expense = projected_personnel_expense + admin_delta

    # Eğitim gideri öğrenci sayısıyla ve enflasyonla birlikte artar.
    projected_education_expense: Decimal = (
        baseline.annual_education_expense
        * actual_student_growth
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

    # Teknoloji gideri büyük ölçüde ithal olduğu için hem enflasyondan hem
    # kurdan etkilenir.
    projected_technology_expense: Decimal = (
        baseline.annual_technology_expense
        * growth_factor(data.inflation_percent)
        * growth_factor(data.exchange_rate_change_percent)
    )

    # Kalem bazlı gider değişikliği.
    if data.target_expense_category and data.expense_item_change_percent != ZERO:
        factor = growth_factor(data.expense_item_change_percent)
        category = data.target_expense_category.lower()
        if "personel" in category or "maaş" in category or "salary" in category:
            projected_personnel_expense = projected_personnel_expense * factor
        elif "eğitim" in category or "laboratuvar" in category:
            projected_education_expense = projected_education_expense * factor
        elif "araştırma" in category or "geliştirme" in category or "ar-ge" in category:
            projected_rd_expense = projected_rd_expense * factor
        elif "enerji" in category or "altyapı" in category or "bakım" in category:
            projected_building_energy_expense = projected_building_energy_expense * factor
        else:
            projected_technology_expense = projected_technology_expense * factor

    projected_expenditure: Decimal = (
        projected_personnel_expense
        + projected_education_expense
        + projected_rd_expense
        + projected_building_energy_expense
        + projected_technology_expense
    )

    # ------------------------------------------------------------------
    # 5) ORAN VE MALİYET
    # ------------------------------------------------------------------
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

    # Eş zamanlı talep: tüm öğrenciler aynı anda derslikte olmaz.
    classroom_demand: Decimal = quantize_count(
        projected_student_count * SIMULTANEOUS_CLASSROOM_USE
    )
    laboratory_demand: Decimal = quantize_count(
        projected_student_count * SIMULTANEOUS_LABORATORY_USE
    )

    return ScenarioComputation(
        baseline_student_count=int(effective_student_count),
        projected_student_count=int(projected_student_count),
        baseline_revenue=quantize_money(baseline_revenue),
        projected_revenue=quantize_money(projected_revenue),
        projected_tuition_revenue=quantize_money(projected_tuition_revenue),
        projected_research_revenue=quantize_money(projected_research_revenue),
        projected_other_revenue=quantize_money(projected_other_revenue),
        baseline_scholarship_rate_percent=quantize_money(baseline.scholarship_rate_percent),
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
            classroom_demand, projected_classroom_capacity
        ),
        laboratory_capacity_status=_capacity_status(
            laboratory_demand, projected_laboratory_capacity
        ),
        baseline_balance=quantize_money(baseline_revenue - baseline_expenditure),
        projected_balance=quantize_money(projected_revenue - projected_expenditure),
        baseline_average_academic_salary=quantize_money(baseline_average_salary),
        projected_average_academic_salary=quantize_money(projected_average_salary),
        baseline_academic_personnel_expense=quantize_money(
            baseline.annual_personnel_expense
        ),
        projected_academic_personnel_expense=quantize_money(projected_personnel_expense),
        simultaneous_classroom_demand=int(classroom_demand),
        simultaneous_laboratory_demand=int(laboratory_demand),
    )


# ----------------------------------------------------------------------------
# Baseline ↔ senaryo karşılaştırma raporu
# ----------------------------------------------------------------------------


def build_comparison(computation: ScenarioComputation):
    """Hesaplanan sonucu baseline ile karşılaştıran raporu üretir.

    Arayüzün "önceki değer / yeni değer / mutlak değişim / yüzde değişim"
    tablosunu çizebilmesi için gereken her şey buradan gelir. Arayüz kendi
    farkını hesaplamaz.
    """
    from app.services.scenario_comparison import ComparisonReport, compare

    c = computation
    report = ComparisonReport()

    # --- MALİ ETKİ ---
    report.financial = [
        compare("total_revenue", "Toplam gelir", "usd",
                c.baseline_revenue, c.projected_revenue, "Mali etki",
                higher_is_better=True,
                description="Öğrenim ücreti (burs sonrası), araştırma ve diğer gelirlerin toplamı."),
        compare("total_expenditure", "Toplam gider", "usd",
                c.baseline_expenditure, c.projected_expenditure, "Mali etki",
                higher_is_better=False,
                description="Personel, eğitim, Ar-Ge, bina-enerji ve teknoloji giderlerinin toplamı."),
        compare("balance", "Gelir–gider dengesi", "usd",
                c.baseline_balance, c.projected_balance, "Mali etki",
                higher_is_better=True,
                description="Toplam gelir eksi toplam gider. Negatif değer bütçe açığıdır."),
        compare("personnel_expense", "Personel gideri", "usd",
                c.baseline_academic_personnel_expense, c.projected_academic_personnel_expense,
                "Mali etki", higher_is_better=False,
                description="Akademik personel sayısı × ortalama maaş. Zam ve kadro değişimi buraya yansır."),
        compare("average_salary", "Ortalama akademik maaş", "usd",
                c.baseline_average_academic_salary, c.projected_average_academic_salary,
                "Mali etki", higher_is_better=None,
                description="Kişi başına yıllık brüt maaş."),
        compare("cost_per_student", "Öğrenci başına maliyet", "usd",
                c.baseline_cost_per_student, c.projected_cost_per_student,
                "Mali etki", higher_is_better=False,
                description="Toplam gider / öğrenci sayısı."),
    ]

    # --- AKADEMİK ETKİ ---
    report.academic = [
        compare("student_count", "Öğrenci sayısı", "count",
                Decimal(c.baseline_student_count), Decimal(c.projected_student_count),
                "Akademik etki", higher_is_better=None,
                description="Kayıtlı toplam öğrenci sayısı."),
        compare("staff_count", "Akademik personel sayısı", "count",
                Decimal(c.baseline_staff_count), Decimal(c.projected_staff_count),
                "Akademik etki", higher_is_better=None,
                description="Kadrolu akademik personel sayısı."),
        compare("student_staff_ratio", "Öğrenci / öğretim üyesi oranı", "ratio",
                c.baseline_student_staff_ratio, c.projected_student_staff_ratio,
                "Akademik etki", higher_is_better=False,
                description="Bir öğretim üyesine düşen öğrenci sayısı. Düşmesi eğitim kalitesi açısından olumludur."),
        compare("scholarship_rate", "Efektif burs oranı", "percent",
                c.baseline_scholarship_rate_percent, c.effective_scholarship_rate_percent,
                "Akademik etki", higher_is_better=None,
                description="Brüt öğrenim ücreti gelirinden düşülen burs oranı."),
    ]

    # --- KAPASİTE ETKİSİ ---
    report.capacity = [
        compare("classroom_capacity", "Derslik kapasitesi", "count",
                Decimal(c.baseline_classroom_capacity), Decimal(c.projected_classroom_capacity),
                "Kapasite etkisi", higher_is_better=True,
                description="Aynı anda derslikte ağırlanabilecek öğrenci sayısı."),
        compare("laboratory_capacity", "Laboratuvar kapasitesi", "count",
                Decimal(c.baseline_laboratory_capacity), Decimal(c.projected_laboratory_capacity),
                "Kapasite etkisi", higher_is_better=True,
                description="Aynı anda laboratuvarda ağırlanabilecek öğrenci sayısı."),
        compare("classroom_demand", "Eş zamanlı derslik talebi", "count",
                Decimal(c.baseline_student_count) * SIMULTANEOUS_CLASSROOM_USE,
                Decimal(c.simultaneous_classroom_demand),
                "Kapasite etkisi", higher_is_better=False,
                description=(
                    f"Öğrenci sayısı × %{SIMULTANEOUS_CLASSROOM_USE * HUNDRED:.0f} eş zamanlı "
                    "kullanım katsayısı. Tüm öğrenciler aynı anda derslikte bulunmaz."
                )),
        compare("laboratory_demand", "Eş zamanlı laboratuvar talebi", "count",
                Decimal(c.baseline_student_count) * SIMULTANEOUS_LABORATORY_USE,
                Decimal(c.simultaneous_laboratory_demand),
                "Kapasite etkisi", higher_is_better=False,
                description=(
                    f"Öğrenci sayısı × %{SIMULTANEOUS_LABORATORY_USE * HUNDRED:.0f} eş zamanlı "
                    "kullanım katsayısı."
                )),
    ]

    return report
