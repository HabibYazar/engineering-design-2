"""Araçların girdi ve çıktı sözleşmeleri.

Her araç bir girdi modeliyle çağrılır ve bir çıktı modeli döndürür. Model bu
şemaların dışına çıkamaz:

* Girdide serbest metin yalnızca BİRİM ADIDIR. SQL parçası, tablo adı, sütun
  adı veya endpoint yolu alan hiçbir alan yoktur.
* Çıktı modelden geçmeden modele gönderilmez; şemaya uymayan sonuç atılır.

Ölçülemeyen değerler `None` döner ve `notes` alanında sebebi yazar. Sıfır bir
ölçüm sonucudur, eksik veri değildir; ikisi karıştırılırsa model "0 öğrenci
var" der.
"""

from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

# Girdi modellerinin ortak ayarı: bilinmeyen alan sessizce yok sayılmaz.
# Model "program_name" yerine "programName" gönderirse hata alsın; sessiz
# yok sayma yanlış kapsamda doğru görünen bir cevap üretirdi.
STRICT = ConfigDict(extra="forbid")

# Birim adı alanlarının ortak açıklaması.
_FACULTY_DESC = "Fakülte adı veya kodu (örn. 'Mühendislik ve Mimarlık Fakültesi', 'FEA')."
_DEPARTMENT_DESC = "Bölüm adı veya kodu (örn. 'Bilgisayar Mühendisliği', 'CENG')."
_PROGRAM_DESC = "Program adı veya kodu (örn. 'Bilgisayar Mühendisliği Lisans Programı', 'CENG-BSC')."
_YEAR_DESC = "Akademik yıl (örn. '2025-2026'). Boş bırakılırsa en güncel yıl kullanılır."


class ScopeInput(BaseModel):
    """Fakülte / bölüm / program kapsamı olan araçların ortak girdisi."""

    model_config = STRICT

    academic_year: Optional[str] = Field(default=None, description=_YEAR_DESC)
    faculty: Optional[str] = Field(default=None, description=_FACULTY_DESC)
    department: Optional[str] = Field(default=None, description=_DEPARTMENT_DESC)
    program: Optional[str] = Field(default=None, description=_PROGRAM_DESC)


class ScopeInfo(BaseModel):
    """Sonucun hangi kapsama ait olduğu. Model bunu cevabında belirtmek zorunda."""

    academic_year: str
    faculty: Optional[str] = None
    department: Optional[str] = None
    program: Optional[str] = None
    #: Kapsamın tek cümlelik özeti (ör. "Üniversite geneli", "Bilgisayar Mühendisliği").
    label: str


# Bir metriğin ait olduğu organizasyon kapsamı.
SCOPE_UNIVERSITY = "university"
SCOPE_FACULTY = "faculty"
SCOPE_DEPARTMENT = "department"
SCOPE_PROGRAM = "program"


class ScopedMetric(BaseModel):
    """Kapsamı, birimi ve formülü açıkça yazılmış tek bir gösterge.

    NEDEN GEREKLİ
    -------------
    Canlı testte tek bir cevap bloğunda program öğrenci sayısı (370 → 426)
    ile üniversite geneli personel (180) ve derslik talebi (1.420) etiketsiz
    yan yana gösterildi. Okuyan yönetici 426 öğrencilik bir programın
    1.420 kişilik derslik talebi ürettiğini sanıyor.

    Her gösterge artık hangi kapsama ait olduğunu, hangi birimde ölçüldüğünü
    ve nasıl hesaplandığını kendisi taşır. Kapsamı belirsiz bir sayı
    gösterilmez.
    """

    key: str
    label: str
    scope_type: str = Field(description="university | faculty | department | program")
    scope_name: str = Field(description="Kapsamın görünen adı.")
    unit: str = Field(description="öğrenci | kişi | eş zamanlı kişi | USD | %")
    baseline: Optional[Decimal] = None
    scenario: Optional[Decimal] = None
    change: Optional[Decimal] = None
    formula: Optional[str] = Field(
        default=None, description="Değerin nasıl hesaplandığı."
    )
    note: Optional[str] = Field(
        default=None, description="Veri yoksa veya kapsam sınırlıysa açıklama."
    )


# ---------------------------------------------------------------------------
# 1) Program özeti
# ---------------------------------------------------------------------------


class ProgramSummaryInput(BaseModel):
    """Program özeti girdisi. Program adı ZORUNLUDUR."""

    model_config = STRICT

    academic_year: Optional[str] = Field(default=None, description=_YEAR_DESC)
    faculty: Optional[str] = Field(default=None, description=_FACULTY_DESC)
    department: Optional[str] = Field(default=None, description=_DEPARTMENT_DESC)
    program: str = Field(description=_PROGRAM_DESC)


class ProgramSummaryOutput(BaseModel):
    scope: ScopeInfo
    #: Kapsamı etiketlenmiş göstergeler.
    scoped_metrics: List[ScopedMetric] = Field(default_factory=list)
    program_name: str
    student_count: Optional[int] = None
    quota: Optional[int] = None
    occupancy_rate: Optional[Decimal] = Field(default=None, description="Yüzde")
    graduation_rate: Optional[Decimal] = Field(default=None, description="Yüzde")
    dropout_rate: Optional[Decimal] = Field(default=None, description="Yüzde")
    academic_staff_count: Optional[int] = None
    student_staff_ratio: Optional[Decimal] = Field(
        default=None, description="Öğrenci / FTE öğretim üyesi"
    )
    # --- Program düzeyinde kadro tahsisi ---
    allocated_staff_headcount: Optional[int] = Field(
        default=None, description="Bu programda ders veren kişi sayısı."
    )
    allocated_staff_fte: Optional[Decimal] = Field(
        default=None,
        description="Tam zaman eşdeğeri. 12 kişi 8,5 FTE olabilir; ikisi farklıdır.",
    )
    weekly_teaching_capacity_hours: Optional[Decimal] = Field(
        default=None, description="Tahsisli kadronun haftalık ders verme kapasitesi."
    )
    target_student_staff_ratio: Optional[Decimal] = None
    notes: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 2) Mali özet
# ---------------------------------------------------------------------------


class FinancialSummaryInput(ScopeInput):
    pass


class FinancialSummaryOutput(BaseModel):
    scope: ScopeInfo
    #: Kapsamı etiketlenmiş göstergeler.
    scoped_metrics: List[ScopedMetric] = Field(default_factory=list)
    total_revenue_usd: Optional[Decimal] = None
    total_expenditure_usd: Optional[Decimal] = None
    net_balance_usd: Optional[Decimal] = None
    personnel_cost_usd: Optional[Decimal] = None
    scholarship_cost_usd: Optional[Decimal] = None
    cost_per_student_usd: Optional[Decimal] = None
    currency: str = "USD"
    notes: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 3) Kapasite özeti
# ---------------------------------------------------------------------------


class CapacitySummaryInput(ScopeInput):
    pass


class CapacitySummaryOutput(BaseModel):
    """Kapasite özeti.

    BİRİMLER ZAMAN BOYUTU TAŞIR. "Kişi" tek başına kapasite birimi değildir:
    60 kişilik bir derslik haftada 40 saat açıksa kapasitesi 2.400
    koltuk-saattir.
    """

    scope: ScopeInfo
    #: Kapsamı etiketlenmiş göstergeler.
    scoped_metrics: List[ScopedMetric] = Field(default_factory=list)
    # --- Program düzeyinde tahsis (program verildiyse dolu) ---
    allocated_classrooms: Optional[int] = None
    allocated_laboratories: Optional[int] = None
    weekly_classroom_capacity_seat_hours: Optional[Decimal] = None
    weekly_classroom_demand_seat_hours: Optional[Decimal] = None
    weekly_laboratory_capacity_station_hours: Optional[Decimal] = None
    weekly_laboratory_demand_station_hours: Optional[Decimal] = None
    classroom_utilization_percent: Optional[Decimal] = None
    laboratory_utilization_percent: Optional[Decimal] = None
    peak_concurrent_capacity: Optional[int] = None
    peak_concurrent_demand: Optional[int] = None
    # --- Kurum geneli mekân envanteri ---
    classroom_capacity: Optional[int] = None
    laboratory_capacity: Optional[int] = None
    current_usage: Optional[int] = None
    occupancy_rate: Optional[Decimal] = Field(default=None, description="Yüzde")
    capacity_gap: Optional[int] = Field(
        default=None,
        description="Eş zamanlı talep eksi kapasite. Pozitif değer açık demektir.",
    )
    capacity_status: Optional[str] = Field(
        default=None, description="yeterli | sınırda | yetersiz | veri yok"
    )
    notes: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 4) Akademik personel özeti
# ---------------------------------------------------------------------------


class AcademicStaffSummaryInput(ScopeInput):
    pass


class AcademicStaffSummaryOutput(BaseModel):
    """Akademik personel özeti.

    İKİ AYRI SAYI, İKİ AYRI ANLAM
    -----------------------------
    `active_academic_staff_count` personel kayıtlarındaki kişi sayısıdır.
    `payroll_academic_positions` mali dönemin bordro planlamasındaki kadro
    sayısıdır. Normalde eşittirler; ayrıştıkları durumda hangisinin neyi
    ölçtüğü belirsiz kalmasın diye ikisi de ayrı alanlarda döndürülür ve
    maaş maliyetinin hangisinden hesaplandığı `cost_basis` alanında yazar.
    """

    scope: ScopeInfo
    #: Geriye uyum için korunur; `active_academic_staff_count` ile aynıdır.
    academic_staff_count: Optional[int] = Field(
        default=None,
        description=(
            "Personel kayıtlarındaki aktif kişi sayısı. "
            "active_academic_staff_count ile aynı değerdir."
        ),
    )
    active_academic_staff_count: Optional[int] = Field(
        default=None, description="Personel kayıtlarında bu yıl görünen kişi sayısı."
    )
    payroll_academic_positions: Optional[int] = Field(
        default=None,
        description="Mali dönem bordro planlamasındaki akademik kadro sayısı.",
    )
    cost_basis: Optional[str] = Field(
        default=None,
        description=(
            "Yıllık maaş maliyetinin hangi sayıdan hesaplandığı: "
            "'bordro kadrosu' veya 'personel kayıtları'."
        ),
    )
    staffing_data_consistent: Optional[bool] = Field(
        default=None,
        description="İki sayı eşitse True; ayrışıyorsa False.",
    )
    average_salary_usd: Optional[Decimal] = None
    annual_salary_cost_usd: Optional[Decimal] = None
    student_staff_ratio: Optional[Decimal] = None
    recommended_staff_count: Optional[int] = Field(
        default=None,
        description="Hedef öğrenci/öğretim üyesi oranına göre gereken personel sayısı.",
    )
    staff_gap: Optional[int] = Field(
        default=None, description="Önerilen eksi mevcut. Pozitif değer eksik demektir."
    )
    target_student_staff_ratio: Optional[Decimal] = None
    notes: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 5) Öğrenci sayısı değişimi senaryosu
# ---------------------------------------------------------------------------


class EnrollmentScenarioInput(BaseModel):
    model_config = STRICT

    academic_year: Optional[str] = Field(default=None, description=_YEAR_DESC)
    program: str = Field(description=_PROGRAM_DESC)
    student_change_percentage: Decimal = Field(
        ge=Decimal("-100"),
        le=Decimal("500"),
        description="Öğrenci sayısındaki yüzdesel değişim (örn. 15 = %15 artış).",
    )


class MetricChange(BaseModel):
    """Bir göstergenin taban ve senaryo değeri."""

    key: str
    label: str
    unit: str = Field(description="usd | count | percent | ratio")
    baseline_value: Optional[Decimal] = None
    projected_value: Optional[Decimal] = None
    absolute_change: Optional[Decimal] = None
    percent_change: Optional[Decimal] = None


class ScenarioBaselineBlock(BaseModel):
    """Senaryonun dayandığı mevcut durum."""

    academic_year: str
    # --- Program düzeyinde kaynak durumu ---
    program_staff_headcount: Optional[int] = None
    program_staff_fte: Optional[Decimal] = None
    program_required_fte: Optional[Decimal] = None
    program_classroom_capacity_seat_hours: Optional[Decimal] = None
    program_classroom_demand_seat_hours: Optional[Decimal] = None
    program_laboratory_capacity_station_hours: Optional[Decimal] = None
    program_laboratory_demand_station_hours: Optional[Decimal] = None

    program_student_count: Optional[int] = None
    university_student_count: Optional[int] = None
    total_revenue_usd: Optional[Decimal] = None
    total_expenditure_usd: Optional[Decimal] = None
    net_balance_usd: Optional[Decimal] = None
    academic_staff_count: Optional[int] = None
    laboratory_capacity: Optional[int] = None
    laboratory_demand: Optional[int] = None
    classroom_capacity: Optional[int] = None
    classroom_demand: Optional[int] = None


class ScenarioProjectionBlock(BaseModel):
    """Senaryo sonrası durum."""

    # --- Program düzeyinde kaynak ihtiyacı ---
    program_staff_fte: Optional[Decimal] = None
    program_required_fte: Optional[Decimal] = None
    program_fte_gap: Optional[Decimal] = None
    program_classroom_capacity_seat_hours: Optional[Decimal] = None
    program_classroom_demand_seat_hours: Optional[Decimal] = None
    program_laboratory_capacity_station_hours: Optional[Decimal] = None
    program_laboratory_demand_station_hours: Optional[Decimal] = None

    program_student_count: Optional[int] = None
    university_student_count: Optional[int] = None
    total_revenue_usd: Optional[Decimal] = None
    total_expenditure_usd: Optional[Decimal] = None
    net_balance_usd: Optional[Decimal] = None
    academic_staff_count: Optional[int] = None
    recommended_staff_count: Optional[int] = None
    staff_gap: Optional[int] = None
    laboratory_capacity: Optional[int] = None
    laboratory_demand: Optional[int] = None
    laboratory_gap: Optional[int] = None
    classroom_capacity: Optional[int] = None
    classroom_demand: Optional[int] = None
    classroom_gap: Optional[int] = None
    capacity_status: Optional[str] = None


class EnrollmentScenarioOutput(BaseModel):
    """Öğrenci sayısı değişimi senaryosunun sonucu.

    ZORUNLU METRİKLER doğrudan alan olarak taşınır. Cevap oluşturucu bu
    alanları yalnızca BİÇİMLENDİRİR; hesap burada, veri katmanında yapılır.
    Model bir metriği atlarsa cevap eksik kalmasın diye zorunlu gerçekler
    backend tarafından ayrıca yazılır.
    """

    scope: ScopeInfo
    baseline: ScenarioBaselineBlock
    scenario: ScenarioProjectionBlock
    #: Program öğrenci sayısındaki mutlak değişim (senaryo eksi mevcut).
    program_student_change: Optional[int] = None
    #: Kullanıcının istediği yüzdesel değişim.
    student_change_percentage: Optional[Decimal] = None
    #: Toplam gelirdeki mutlak değişim (USD).
    revenue_change_usd: Optional[Decimal] = None
    #: Bütçe dengesindeki mutlak değişim (USD).
    net_balance_change_usd: Optional[Decimal] = None
    #: Kapsamı etiketlenmiş göstergeler. Cevap oluşturucu BU listeden yazar.
    scoped_metrics: List[ScopedMetric] = Field(default_factory=list)
    absolute_change: List[MetricChange] = Field(default_factory=list)
    percentage_change: List[MetricChange] = Field(default_factory=list)
    affected_metrics: List[MetricChange] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    #: Program düzeyindeki değişimin üniversite geneline yansıma oranı.
    method_note: str
    notes: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 6) Maaş değişimi senaryosu
# ---------------------------------------------------------------------------


class SalaryScenarioInput(BaseModel):
    model_config = STRICT

    academic_year: Optional[str] = Field(default=None, description=_YEAR_DESC)
    salary_change_percentage: Decimal = Field(
        ge=Decimal("-100"),
        le=Decimal("500"),
        description="Akademik personel maaşlarındaki yüzdesel değişim (örn. 2 = %2 zam).",
    )
    faculty: Optional[str] = Field(default=None, description=_FACULTY_DESC)
    department: Optional[str] = Field(default=None, description=_DEPARTMENT_DESC)


class SalaryScenarioOutput(BaseModel):
    """Maaş değişimi senaryosunun sonucu. Zorunlu metrikler alan olarak taşınır."""

    scope: ScopeInfo
    #: Kapsamı etiketlenmiş göstergeler.
    scoped_metrics: List[ScopedMetric] = Field(default_factory=list)
    salary_change_percentage: Optional[Decimal] = None
    previous_annual_staff_cost_usd: Optional[Decimal] = None
    new_annual_staff_cost_usd: Optional[Decimal] = None
    cost_change_usd: Optional[Decimal] = None
    total_expenditure_change_usd: Optional[Decimal] = None
    net_balance_change_usd: Optional[Decimal] = None
    cost_per_student_change_usd: Optional[Decimal] = None
    risks: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    method_note: str
    notes: List[str] = Field(default_factory=list)
