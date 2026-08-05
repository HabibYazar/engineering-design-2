"""Modelin çağırabileceği araçlar.

Her araç MEVCUT servis katmanını sarmalar. Bu dosyada hiçbir formül yeniden
yazılmaz; öğrenci analitiği, mali özet, kapasite, personel ve senaryo motoru
kendi servislerinde ne hesaplıyorsa o döndürülür. Buradaki tek iş:

* kapsamı çözmek (`entity_resolver`),
* servisi çağırmak,
* sonucu araç şemasına oturtmak,
* ölçülemeyen değeri sıfır değil `None` olarak işaretlemek.

KAPSAM UYARISI — mali ve kapasite verisi
----------------------------------------
Mali dönem kayıtları ve fiziksel kapasite kayıtları ÜNİVERSİTE GENELİ tutulur;
program başına gelir/gider veya derslik ayrımı veride yoktur. Bu araçlar o
durumda kurum geneli sayıyı döndürür ve `notes` alanında bunu açıkça yazar.
Modelin sistem yönergesi de bu notu cevaba taşımasını zorunlu kılar. Program
başına bir sayı uydurmaktansa kapsamı dürüstçe söylemek doğrudur.
"""

import logging
from decimal import Decimal
from typing import List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.decimal_types import quantize_money
from app.models import AcademicProgram, Department, PhysicalFacility
from app.models.financial_period import FinancialPeriod
from app.schemas.scenarios import ScenarioInputCreate
from app.services import academic_staff_service, finance_service
from app.services import student_analytics_service as students
from app.services.assistant import entity_resolver
from app.services.assistant.entity_resolver import ResolvedEntity
from app.services.assistant.tool_registry import (
    ToolDefinition,
    ToolExecutionError,
    registry,
)
from app.services.assistant.tool_schemas import (
    AcademicStaffSummaryInput,
    AcademicStaffSummaryOutput,
    CapacitySummaryInput,
    CapacitySummaryOutput,
    EnrollmentScenarioInput,
    EnrollmentScenarioOutput,
    FinancialSummaryInput,
    FinancialSummaryOutput,
    MetricChange,
    ProgramSummaryInput,
    ProgramSummaryOutput,
    SalaryScenarioInput,
    SalaryScenarioOutput,
    ScenarioBaselineBlock,
    ScenarioProjectionBlock,
    ScopeInfo,
)
from app.services.scenario_baseline_builder import build_from_financial_period
from app.services.scenario_engine import (
    SIMULTANEOUS_CLASSROOM_USE,
    SIMULTANEOUS_LABORATORY_USE,
    ScenarioValidationError,
    build_comparison,
    calculate,
)
from app.services.scenario_recommendations import build_recommendation
from app.services.scenario_risk import evaluate

logger = logging.getLogger(__name__)

# Personel ihtiyacı hesabında kullanılan hedef oran. Tek yerde tanımlı;
# araçlar bu değeri kendi içlerinde tekrar yazmaz.
TARGET_STUDENT_STAFF_RATIO = Decimal("20")

# Mali servisler tutarları MİLYON USD olarak tutar (financial_period.py'de
# belgelenmiş). Araç şemaları "..._usd" diyor, yani TAM USD bekleniyor.
# Dönüşüm burada tek noktada yapılır; aksi halde model 50,4 milyon doları
# "50 dolar" diye okur.
MILLION = Decimal("1000000")

UNIVERSITY_WIDE_NOTE = (
    "Bu değer üniversite geneli kayıtlardan gelir; program veya bölüm başına "
    "ayrıştırılmış veri sistemde bulunmuyor."
)


# ---------------------------------------------------------------------------
# Ortak yardımcılar
# ---------------------------------------------------------------------------


def _scope_info(
    year: str,
    faculty: Optional[ResolvedEntity],
    department: Optional[ResolvedEntity],
    program: Optional[ResolvedEntity],
) -> ScopeInfo:
    label = (
        program.display_name
        if program
        else department.display_name
        if department
        else faculty.display_name
        if faculty
        else "Üniversite geneli"
    )
    return ScopeInfo(
        academic_year=year,
        faculty=faculty.display_name if faculty else None,
        department=department.display_name if department else None,
        program=program.display_name if program else None,
        label=label,
    )


def _resolve(db: Session, payload) -> Tuple[str, Optional[ResolvedEntity], Optional[ResolvedEntity], Optional[ResolvedEntity]]:
    """Kapsam çözümlemesini araç hatasına çevirir."""
    try:
        return entity_resolver.resolve_scope(
            db,
            academic_year=getattr(payload, "academic_year", None),
            faculty=getattr(payload, "faculty", None),
            department=getattr(payload, "department", None),
            program=getattr(payload, "program", None),
        )
    except entity_resolver.EntityResolutionError as exc:
        message = exc.message
        if exc.candidates:
            message += " Seçenekler: " + ", ".join(exc.candidates)
        raise ToolExecutionError(message, kind=exc.kind) from exc


def _dec(value) -> Optional[Decimal]:
    """Değeri Decimal'e çevirir; None ise None bırakır."""
    if value is None:
        return None
    return quantize_money(value)


def _usd(value_in_millions) -> Optional[Decimal]:
    """Milyon USD cinsinden bir tutarı tam USD'ye çevirir."""
    if value_in_millions is None:
        return None
    return quantize_money(Decimal(str(value_in_millions)) * MILLION)


def _period(db: Session, academic_year: str) -> Optional[FinancialPeriod]:
    return db.execute(
        select(FinancialPeriod).where(FinancialPeriod.academic_year == academic_year)
    ).scalars().first()


def _staff_count(
    db: Session,
    academic_year: str,
    faculty: Optional[ResolvedEntity],
    department: Optional[ResolvedEntity],
) -> Optional[int]:
    """Kapsamdaki akademik personel sayısı. Veri yoksa None."""
    rows = academic_staff_service.list_staff(
        db,
        skip=0,
        limit=10_000,
        department_id=department.id if department else None,
        faculty_id=faculty.id if faculty else None,
        academic_year=academic_year,
    )
    return len(rows) if rows else None


# ---------------------------------------------------------------------------
# 1) get_program_summary
# ---------------------------------------------------------------------------


def _handle_program_summary(db: Session, payload: ProgramSummaryInput) -> ProgramSummaryOutput:
    year, faculty, department, program = _resolve(db, payload)
    assert program is not None  # şema program alanını zorunlu tutuyor

    rows = students.build_program_analytics(
        db, academic_program_id=program.id, academic_year=year
    )
    if not rows:
        return ProgramSummaryOutput(
            scope=_scope_info(year, faculty, department, program),
            program_name=program.display_name,
            notes=[f"{program.display_name} için {year} yılında öğrenci verisi bulunamadı."],
        )

    row = rows[0]
    notes: List[str] = []

    # Bölüm personeli program başına ayrıştırılmış değil; oran bölüm
    # kadrosundan hesaplanır ve bu not cevaba taşınır.
    staff_count = _staff_count(db, year, faculty, department)
    if staff_count is None:
        notes.append("Bu kapsam için akademik personel kaydı bulunamadı.")
    else:
        notes.append(
            "Akademik personel sayısı bölüm düzeyinde tutulur; program başına "
            "ayrı kadro kaydı yoktur."
        )

    student_count = row.total_students or None
    ratio = (
        quantize_money(Decimal(student_count) / Decimal(staff_count))
        if student_count and staff_count
        else None
    )

    return ProgramSummaryOutput(
        scope=_scope_info(year, faculty, department, program),
        program_name=program.display_name,
        student_count=student_count,
        quota=row.quota or None,
        occupancy_rate=_dec(row.occupancy_rate),
        graduation_rate=_dec(row.graduation_rate),
        dropout_rate=_dec(row.attrition_rate),
        academic_staff_count=staff_count,
        student_staff_ratio=ratio,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# 2) get_financial_summary
# ---------------------------------------------------------------------------


def _handle_financial_summary(
    db: Session, payload: FinancialSummaryInput
) -> FinancialSummaryOutput:
    year, faculty, department, program = _resolve(db, payload)
    notes: List[str] = []

    summary = finance_service.financial_summary(db, year)

    # Bölüm bütçesi varsa kapsam daraltılabilir; program düzeyinde bütçe yok.
    department_row = None
    if department is not None:
        budgets = finance_service.list_department_budgets(db, year)
        for budget in budgets:
            if budget.department_id == department.id:
                department_row = finance_service.budget_to_dict(budget)
                break
        if department_row is None:
            notes.append(
                f"{department.display_name} için {year} yılında bölüm bütçesi girilmemiş; "
                "üniversite geneli rakamlar döndürüldü."
            )

    if program is not None:
        notes.append(
            "Mali kayıtlar program düzeyinde tutulmuyor. " + UNIVERSITY_WIDE_NOTE
        )

    if department_row is not None:
        return FinancialSummaryOutput(
            scope=_scope_info(year, faculty, department, program),
            total_revenue_usd=_usd(department_row["revenue"]),
            total_expenditure_usd=_usd(department_row["expenditure"]),
            net_balance_usd=_usd(department_row["balance"]),
            personnel_cost_usd=None,
            scholarship_cost_usd=None,
            cost_per_student_usd=_dec(
                Decimal(str(department_row["cost_per_student_thousand_usd"]))
                * Decimal("1000")
            )
            if department_row.get("cost_per_student_thousand_usd") is not None
            else None,
            notes=notes
            + [
                "Personel ve burs gideri bölüm bütçesinde ayrı kalem olarak "
                "tutulmuyor; bu iki değer için veri bulunamadı."
            ],
        )

    if faculty is not None:
        notes.append(
            "Fakülte düzeyinde ayrı mali dönem kaydı yok. " + UNIVERSITY_WIDE_NOTE
        )

    # Personel ve burs gideri özet sözlüğünde ayrı kalem olarak yoktur;
    # yalnızca oranları var. Tutarı oran × toplam ile geri hesaplamak yerine
    # kalem dökümünden okunur — yuvarlama hatası taşımasın.
    personnel = _entry_total(summary["expenditure_breakdown"], ("personel", "maaş", "maas"))
    scholarship = _entry_total(summary["expenditure_breakdown"], ("burs",))
    if personnel is None:
        notes.append("Personel gideri ayrı bir bütçe kalemi olarak bulunamadı.")
    if scholarship is None:
        notes.append("Burs gideri ayrı bir bütçe kalemi olarak bulunamadı.")

    return FinancialSummaryOutput(
        scope=_scope_info(year, faculty, department, program),
        total_revenue_usd=_usd(summary["total_revenue"]),
        total_expenditure_usd=_usd(summary["total_expenditure"]),
        net_balance_usd=_usd(summary["balance"]),
        personnel_cost_usd=_usd(personnel),
        scholarship_cost_usd=_usd(scholarship),
        cost_per_student_usd=_dec(summary.get("cost_per_student_usd")),
        notes=notes,
    )


def _entry_total(rows, keywords: Tuple[str, ...]) -> Optional[Decimal]:
    """Kalem dökümünden anahtar kelime içeren satırların toplamı (milyon USD)."""
    matched = [
        Decimal(str(row["amount"]))
        for row in rows
        if any(k in str(row.get("category", "")).lower() for k in keywords)
    ]
    return sum(matched, Decimal("0")) if matched else None


# ---------------------------------------------------------------------------
# 3) get_capacity_summary
# ---------------------------------------------------------------------------


def _handle_capacity_summary(
    db: Session, payload: CapacitySummaryInput
) -> CapacitySummaryOutput:
    year, faculty, department, program = _resolve(db, payload)
    notes: List[str] = []

    statement = select(PhysicalFacility).where(PhysicalFacility.is_active.is_(True))
    # Mekânlar bölüme bağlıdır; programa bağlı mekân kaydı yoktur.
    if department is not None:
        statement = statement.where(PhysicalFacility.department_id == department.id)
    elif faculty is not None:
        department_ids = [
            row.id
            for row in db.execute(
                select(Department).where(Department.faculty_id == faculty.id)
            ).scalars()
        ]
        statement = statement.where(PhysicalFacility.department_id.in_(department_ids))

    if program is not None:
        notes.append(
            "Derslik ve laboratuvar kayıtları bölüm düzeyinde tutulur; program "
            "başına mekân ayrımı yoktur."
        )

    facilities = list(db.execute(statement).scalars())
    if not facilities:
        return CapacitySummaryOutput(
            scope=_scope_info(year, faculty, department, program),
            capacity_status="veri yok",
            notes=notes + ["Bu kapsam için fiziksel mekân kaydı bulunamadı."],
        )

    classroom = sum(f.capacity for f in facilities if f.facility_type == "classroom")
    laboratory = sum(f.capacity for f in facilities if f.facility_type == "laboratory")
    total_capacity = sum(f.capacity for f in facilities)
    used = sum(f.occupied for f in facilities)

    occupancy = (
        quantize_money(Decimal(used) / Decimal(total_capacity) * Decimal("100"))
        if total_capacity
        else None
    )

    # Eş zamanlı talep: tüm öğrenciler aynı anda derslikte olmaz. Katsayılar
    # senaryo motorundan alınır; burada yeniden tanımlanmaz.
    #
    # academic_year GEÇİLMEZ: bu parametre "o yıl kayıt olan" öğrencileri
    # süzüyor (2025-2026 için 800), oysa derslik talebi KAYITLI TÜM
    # öğrencilerden doğar (4.000). Yıl filtresi verilseydi kapasite açığı
    # beşte bir görünürdü.
    overview = students.build_overview(db)
    student_total = int(overview.total_students or 0)
    simultaneous_demand = int(
        (Decimal(student_total) * SIMULTANEOUS_CLASSROOM_USE).to_integral_value()
    )

    gap: Optional[int] = None
    status: Optional[str] = None
    if department is None and faculty is None and program is None and classroom:
        gap = simultaneous_demand - classroom
        # Açık varsa yetersiz; kapasitenin %10'undan az payı kalmışsa sınırda.
        status = (
            "yetersiz" if gap > 0
            else "sınırda" if gap > -classroom * 0.1
            else "yeterli"
        )
        notes.append(
            f"Eş zamanlı derslik talebi, öğrencilerin %{SIMULTANEOUS_CLASSROOM_USE * 100:.0f}'inin "
            "aynı anda derste olduğu varsayımıyla hesaplanır."
        )
    else:
        notes.append(
            "Eş zamanlı kapasite açığı yalnızca üniversite geneli için hesaplanır; "
            "alt kapsamda öğrenci-mekân eşleşmesi verisi yok."
        )

    return CapacitySummaryOutput(
        scope=_scope_info(year, faculty, department, program),
        classroom_capacity=classroom or None,
        laboratory_capacity=laboratory or None,
        current_usage=used or None,
        occupancy_rate=occupancy,
        capacity_gap=gap,
        capacity_status=status,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# 4) get_academic_staff_summary
# ---------------------------------------------------------------------------


def _handle_staff_summary(
    db: Session, payload: AcademicStaffSummaryInput
) -> AcademicStaffSummaryOutput:
    year, faculty, department, program = _resolve(db, payload)
    notes: List[str] = []

    if program is not None:
        notes.append(
            "Akademik kadro bölüm düzeyinde tutulur; program başına ayrı kadro "
            "kaydı yoktur."
        )

    count = _staff_count(db, year, faculty, department)
    if count is None:
        return AcademicStaffSummaryOutput(
            scope=_scope_info(year, faculty, department, program),
            notes=notes + ["Bu kapsam için akademik personel kaydı bulunamadı."],
        )

    period = _period(db, year)
    average_salary = _dec(period.average_academic_salary_usd) if period else None
    if average_salary is None:
        notes.append(
            f"{year} için ortalama maaş bilgisi mali dönem kaydında bulunamadı."
        )
    else:
        notes.append(
            "Ortalama maaş üniversite geneli mali dönem kaydından gelir; "
            "kişi bazlı maaş verisi sistemde tutulmaz."
        )

    # İKİ FARKLI SAYI, AÇIKÇA AYRILIYOR.
    # Personel kayıtlarındaki kişi sayısı ile mali dönemin bordro
    # planlamasındaki kadro sayısı ayrı alanlarda döndürülür. Tek bir
    # "academic_staff_count" alanında birleştirmek, hangisinin neyi ölçtüğünü
    # belirsiz bırakıyordu.
    payroll_positions = period.academic_staff_count if period else None
    is_university_wide = faculty is None and department is None and program is None

    # Maaş maliyeti bordro kadrosundan hesaplanır: senaryo motoru da onu
    # kullanır, aksi halde asistan tek cevabın içinde çelişir.
    use_payroll = bool(is_university_wide and payroll_positions)
    cost_headcount = payroll_positions if use_payroll else count
    cost_basis = "bordro kadrosu" if use_payroll else "personel kayıtları"

    consistent: Optional[bool] = None
    if is_university_wide and payroll_positions is not None:
        consistent = payroll_positions == count
        if not consistent:
            notes.append(
                f"Personel kayıtlarında {count} kişi, {year} mali dönem bordro "
                f"planlamasında {payroll_positions} kadro görünüyor. Maaş maliyeti "
                f"bordro kadrosundan hesaplandı."
            )

    annual_cost = (
        quantize_money(Decimal(cost_headcount) * average_salary) if average_salary else None
    )

    # academic_year geçilmez: kayıtlı tüm öğrenciler sayılmalı (bkz. kapasite
    # aracındaki aynı gerekçe). Yıl filtresi öğrenci/öğretim üyesi oranını
    # olduğundan çok daha iyi gösterirdi.
    overview = students.build_overview(
        db,
        faculty_id=faculty.id if faculty else None,
        department_id=department.id if department else None,
        academic_program_id=program.id if program else None,
    )
    student_total = int(overview.total_students or 0)

    ratio = (
        quantize_money(Decimal(student_total) / Decimal(count))
        if student_total and count
        else None
    )
    recommended = (
        int(
            (Decimal(student_total) / TARGET_STUDENT_STAFF_RATIO)
            .to_integral_value(rounding="ROUND_CEILING")
        )
        if student_total
        else None
    )
    gap = recommended - count if recommended is not None else None

    return AcademicStaffSummaryOutput(
        scope=_scope_info(year, faculty, department, program),
        academic_staff_count=count,
        active_academic_staff_count=count,
        payroll_academic_positions=payroll_positions if is_university_wide else None,
        cost_basis=cost_basis,
        staffing_data_consistent=consistent,
        average_salary_usd=average_salary,
        annual_salary_cost_usd=annual_cost,
        student_staff_ratio=ratio,
        recommended_staff_count=recommended,
        staff_gap=gap,
        target_student_staff_ratio=TARGET_STUDENT_STAFF_RATIO,
        notes=notes
        + [
            f"Önerilen kadro, hedef öğrenci/öğretim üyesi oranı "
            f"{TARGET_STUDENT_STAFF_RATIO:.0f} kabul edilerek hesaplanmıştır. "
            f"Kadro açığı, personel kayıtlarındaki {count} kişiye göre hesaplanır.",
            f"Yıllık maaş maliyeti {cost_basis} ({cost_headcount}) üzerinden hesaplandı.",
        ],
    )


# ---------------------------------------------------------------------------
# Senaryo araçlarının ortak altyapısı
# ---------------------------------------------------------------------------


def _run_engine(db: Session, year: str, inputs: ScenarioInputCreate):
    """Mevcut senaryo motorunu çalıştırır. Formül BURADA yazılmaz."""
    try:
        baseline = build_from_financial_period(db, year)
    except Exception as exc:  # HTTPException dâhil
        raise ToolExecutionError(
            f"{year} için mali dönem verisi bulunamadı; senaryo çalıştırılamıyor.",
            kind="no_data",
        ) from exc

    try:
        computation = calculate(baseline, inputs)
    except ScenarioValidationError as exc:
        raise ToolExecutionError(
            f"Senaryo parametresi geçersiz: {exc.message}", kind="invalid_input"
        ) from exc

    risks, risk_level = evaluate(computation)
    recommendation = build_recommendation(computation, risks, risk_level)
    return baseline, computation, risks, recommendation


def _metric_changes(comparison_rows) -> List[MetricChange]:
    """Karşılaştırma satırlarını araç şemasına çevirir.

    BİRİM UYARISI: Senaryo motoru tutarları TAM USD olarak döndürür
    (baseline_revenue = 35.960.000), mali özet servisi ise MİLYON USD olarak
    (total_revenue = 35,96). İki katman farklı ölçek kullanıyor. Burada
    çarpma YAPILMAZ; çarpım yapıldığında %2 zammın maliyeti 6,1 milyon dolar
    yerine 6,1 trilyon dolar görünüyordu.
    """
    return [
        MetricChange(
            key=row.key,
            label=row.label,
            unit=row.unit,
            baseline_value=_dec(row.baseline_value),
            projected_value=_dec(row.projected_value),
            absolute_change=_dec(row.absolute_change),
            percent_change=_dec(row.percent_change)
            if row.percent_change is not None
            else None,
        )
        for row in comparison_rows
    ]


# ---------------------------------------------------------------------------
# 5) run_enrollment_change_scenario
# ---------------------------------------------------------------------------


def _handle_enrollment_scenario(
    db: Session, payload: EnrollmentScenarioInput
) -> EnrollmentScenarioOutput:
    year, faculty, department, program = _resolve(db, payload)
    assert program is not None

    rows = students.build_program_analytics(
        db, academic_program_id=program.id, academic_year=year
    )
    program_students = int(rows[0].total_students) if rows else 0
    if not program_students:
        raise ToolExecutionError(
            f"{program.display_name} için {year} yılında öğrenci verisi yok; "
            "senaryo çalıştırılamıyor.",
            kind="no_data",
        )

    # academic_year GEÇİLMEZ. Bu parametre "o yıl kayıt olan" öğrencileri
    # süzüyor (2025-2026 için 800), oysa payda KAYITLI TÜM öğrenciler olmalı
    # (4.000). Yıl filtresiyle %15'lik bir program artışı üniversite geneline
    # %1,4 yerine %7 olarak yansıyordu — beş kat abartılı bir mali etki.
    overview = students.build_overview(db)
    university_students = int(overview.total_students or 0)
    if not university_students:
        raise ToolExecutionError(
            f"{year} için üniversite geneli öğrenci verisi yok.", kind="no_data"
        )

    # Senaryo motoru KURUM GENELİ çalışır. Program düzeyindeki bir değişimi
    # kurum geneline çevirmek için değişen öğrenci sayısı toplam öğrenciye
    # oranlanır. Bu bir varsayım değil, aritmetik bir dönüşümdür ve
    # method_note ile cevaba taşınır.
    change_percent = Decimal(str(payload.student_change_percentage))
    added_students = (Decimal(program_students) * change_percent / Decimal("100")).quantize(
        Decimal("1")
    )
    university_change_percent = quantize_money(
        added_students / Decimal(university_students) * Decimal("100")
    )

    inputs = ScenarioInputCreate(student_change_percent=university_change_percent)
    baseline, computation, risks, recommendation = _run_engine(db, year, inputs)
    report = build_comparison(computation)

    financial = _metric_changes(report.financial)
    academic = _metric_changes(report.academic)
    capacity = _metric_changes(report.capacity)
    all_metrics = financial + academic + capacity

    def _find(key: str) -> Optional[MetricChange]:
        return next((m for m in all_metrics if m.key == key), None)

    revenue = _find("total_revenue")
    expenditure = _find("total_expenditure")
    balance = _find("balance")
    lab_capacity = _find("laboratory_capacity")
    lab_demand = _find("laboratory_demand")
    class_capacity = _find("classroom_capacity")
    class_demand = _find("classroom_demand")

    projected_program_students = program_students + int(added_students)

    # ZORUNLU METRİKLER — burada, veri katmanında hesaplanır.
    # Cevap oluşturucu hesap yapmaz; yalnızca bu değerleri biçimlendirir.
    def _int(metric, field: str) -> Optional[int]:
        if metric is None:
            return None
        value = getattr(metric, field)
        return int(value) if value is not None else None

    projected_lab_capacity = _int(lab_capacity, "projected_value")
    projected_lab_demand = _int(lab_demand, "projected_value")
    projected_class_capacity = _int(class_capacity, "projected_value")
    projected_class_demand = _int(class_demand, "projected_value")

    lab_gap = (
        projected_lab_demand - projected_lab_capacity
        if projected_lab_demand is not None and projected_lab_capacity is not None
        else None
    )
    class_gap = (
        projected_class_demand - projected_class_capacity
        if projected_class_demand is not None and projected_class_capacity is not None
        else None
    )
    if lab_gap is None and class_gap is None:
        capacity_status = None
    elif (lab_gap or 0) > 0 or (class_gap or 0) > 0:
        capacity_status = "yetersiz"
    else:
        capacity_status = "yeterli"

    # Personel ihtiyacı, senaryo sonrası üniversite öğrenci sayısına göre.
    projected_university_students = computation.projected_student_count
    recommended_staff = int(
        (Decimal(projected_university_students) / TARGET_STUDENT_STAFF_RATIO)
        .to_integral_value(rounding="ROUND_CEILING")
    )
    staff_gap = recommended_staff - computation.projected_staff_count

    return EnrollmentScenarioOutput(
        scope=_scope_info(year, faculty, department, program),
        program_student_change=int(added_students),
        student_change_percentage=change_percent,
        revenue_change_usd=revenue.absolute_change if revenue else None,
        net_balance_change_usd=balance.absolute_change if balance else None,
        baseline=ScenarioBaselineBlock(
            academic_year=year,
            program_student_count=program_students,
            university_student_count=computation.baseline_student_count,
            total_revenue_usd=revenue.baseline_value if revenue else None,
            total_expenditure_usd=expenditure.baseline_value if expenditure else None,
            net_balance_usd=balance.baseline_value if balance else None,
            academic_staff_count=computation.baseline_staff_count,
            laboratory_capacity=_int(lab_capacity, "baseline_value"),
            laboratory_demand=_int(lab_demand, "baseline_value"),
            classroom_capacity=_int(class_capacity, "baseline_value"),
            classroom_demand=_int(class_demand, "baseline_value"),
        ),
        scenario=ScenarioProjectionBlock(
            program_student_count=projected_program_students,
            university_student_count=computation.projected_student_count,
            total_revenue_usd=revenue.projected_value if revenue else None,
            total_expenditure_usd=expenditure.projected_value if expenditure else None,
            net_balance_usd=balance.projected_value if balance else None,
            academic_staff_count=computation.projected_staff_count,
            recommended_staff_count=recommended_staff,
            staff_gap=staff_gap,
            laboratory_capacity=projected_lab_capacity,
            laboratory_demand=projected_lab_demand,
            laboratory_gap=lab_gap,
            classroom_capacity=projected_class_capacity,
            classroom_demand=projected_class_demand,
            classroom_gap=class_gap,
            capacity_status=capacity_status,
        ),
        absolute_change=[m for m in all_metrics if m.absolute_change is not None],
        percentage_change=[m for m in all_metrics if m.percent_change is not None],
        affected_metrics=all_metrics,
        risks=[r.message for r in risks],
        recommendations=[recommendation] if recommendation else [],
        method_note=(
            f"{program.display_name} programındaki %{change_percent} artış "
            f"{int(added_students)} öğrenciye karşılık gelir. Senaryo motoru kurum geneli "
            f"çalıştığı için bu, üniversite toplamında %{university_change_percent} "
            f"değişim olarak uygulanmıştır. Mali ve kapasite etkileri kurum geneli değerlerdir."
        ),
        notes=[
            f"Taban: {year} mali dönemi gerçek gelir/gider kayıtları.",
            "Bu bir simülasyondur; veritabanına kayıt yazılmamıştır.",
        ],
    )


# ---------------------------------------------------------------------------
# 6) run_staff_salary_scenario
# ---------------------------------------------------------------------------


def _handle_salary_scenario(
    db: Session, payload: SalaryScenarioInput
) -> SalaryScenarioOutput:
    year, faculty, department, _ = _resolve(db, payload)
    notes: List[str] = []

    if faculty is not None or department is not None:
        notes.append(
            "Maaş senaryosu üniversite geneli mali dönem kaydı üzerinden çalışır; "
            "fakülte veya bölüm bazlı maaş bütçesi sistemde tutulmuyor."
        )

    inputs = ScenarioInputCreate(
        academic_salary_change_percent=Decimal(str(payload.salary_change_percentage))
    )
    _, computation, risks, recommendation = _run_engine(db, year, inputs)
    report = build_comparison(computation)
    metrics = _metric_changes(report.financial + report.academic + report.capacity)

    def _find(key: str) -> Optional[MetricChange]:
        return next((m for m in metrics if m.key == key), None)

    personnel = _find("personnel_expense")
    expenditure = _find("total_expenditure")
    balance = _find("balance")
    cost_per_student = _find("cost_per_student")

    return SalaryScenarioOutput(
        scope=_scope_info(year, faculty, department, None),
        salary_change_percentage=Decimal(str(payload.salary_change_percentage)),
        previous_annual_staff_cost_usd=personnel.baseline_value if personnel else None,
        new_annual_staff_cost_usd=personnel.projected_value if personnel else None,
        cost_change_usd=personnel.absolute_change if personnel else None,
        total_expenditure_change_usd=expenditure.absolute_change if expenditure else None,
        net_balance_change_usd=balance.absolute_change if balance else None,
        cost_per_student_change_usd=cost_per_student.absolute_change
        if cost_per_student
        else None,
        risks=[r.message for r in risks],
        recommendations=[recommendation] if recommendation else [],
        method_note=(
            f"Personel gideri = akademik personel sayısı × ortalama maaş. "
            f"%{payload.salary_change_percentage} zam yalnızca ortalama maaşı değiştirir; "
            f"kadro sayısı sabit kalır."
        ),
        notes=notes
        + [
            f"Taban: {year} mali dönemi gerçek gelir/gider kayıtları.",
            "Bu bir simülasyondur; veritabanına kayıt yazılmamıştır.",
        ],
    )


# ---------------------------------------------------------------------------
# Kayıt
# ---------------------------------------------------------------------------

# Veri kaynağı adları KULLANICIYA gösterilir; teknik araç adı gösterilmez.
registry.register(
    ToolDefinition(
        name="get_program_summary",
        description=(
            "Bir akademik programın öğrenci sayısı, kontenjan, doluluk oranı, "
            "mezuniyet ve bırakma oranı ile öğrenci/öğretim üyesi oranını döndürür. "
            "Mevcut durumu sorgular; senaryo çalıştırmaz."
        ),
        input_model=ProgramSummaryInput,
        output_model=ProgramSummaryOutput,
        handler=_handle_program_summary,
        timeout_seconds=15.0,
        required_permission="view_students",
        data_source="Öğrenci kayıtları",
    )
)

registry.register(
    ToolDefinition(
        name="get_financial_summary",
        description=(
            "Bir akademik yılın gelir, gider, net bütçe, personel gideri, burs "
            "gideri ve öğrenci başına maliyet değerlerini USD olarak döndürür. "
            "Bölüm verilirse o bölümün bütçesi kullanılır."
        ),
        input_model=FinancialSummaryInput,
        output_model=FinancialSummaryOutput,
        handler=_handle_financial_summary,
        timeout_seconds=15.0,
        required_permission="view_finance",
        data_source="Mali dönem kayıtları",
    )
)

registry.register(
    ToolDefinition(
        name="get_capacity_summary",
        description=(
            "Derslik ve laboratuvar kapasitesi, mevcut kullanım, doluluk oranı ve "
            "eş zamanlı kapasite açığını döndürür."
        ),
        input_model=CapacitySummaryInput,
        output_model=CapacitySummaryOutput,
        handler=_handle_capacity_summary,
        timeout_seconds=15.0,
        required_permission="view_physical_resources",
        data_source="Fiziksel kapasite kayıtları",
    )
)

registry.register(
    ToolDefinition(
        name="get_academic_staff_summary",
        description=(
            "Akademik personel sayısı, ortalama maaş, yıllık maaş maliyeti, "
            "öğrenci/öğretim üyesi oranı ve önerilen kadro sayısını döndürür."
        ),
        input_model=AcademicStaffSummaryInput,
        output_model=AcademicStaffSummaryOutput,
        handler=_handle_staff_summary,
        timeout_seconds=20.0,
        required_permission="view_academic_staff",
        data_source="Akademik personel kayıtları",
    )
)

registry.register(
    ToolDefinition(
        name="run_enrollment_change_scenario",
        description=(
            "Bir programdaki öğrenci sayısı değişiminin mali durum, personel ve "
            "kapasite üzerindeki etkisini hesaplar. Kullanıcı 'artarsa', 'azalırsa', "
            "'ne olur' gibi bir varsayım sorduğunda kullanılır. Mevcut durumu "
            "sormuşsa BU ARAÇ ÇAĞRILMAZ."
        ),
        input_model=EnrollmentScenarioInput,
        output_model=EnrollmentScenarioOutput,
        handler=_handle_enrollment_scenario,
        timeout_seconds=30.0,
        required_permission="run_scenarios",
        data_source="Senaryo motoru",
    )
)

registry.register(
    ToolDefinition(
        name="run_staff_salary_scenario",
        description=(
            "Akademik personel maaşlarındaki yüzdesel değişimin personel gideri, "
            "toplam gider, bütçe dengesi ve öğrenci başına maliyet üzerindeki "
            "etkisini hesaplar."
        ),
        input_model=SalaryScenarioInput,
        output_model=SalaryScenarioOutput,
        handler=_handle_salary_scenario,
        timeout_seconds=30.0,
        required_permission="run_scenarios",
        data_source="Senaryo motoru",
    )
)
