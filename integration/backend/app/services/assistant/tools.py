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
from decimal import ROUND_HALF_UP, Decimal
from typing import List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.decimal_types import quantize_money
from app.models import AcademicProgram, Department, PhysicalFacility
from app.models.financial_period import FinancialPeriod
from app.schemas.scenarios import ScenarioInputCreate
from app.services import academic_staff_service, finance_service
from app.services import program_allocation_service as allocation
from app.services import student_analytics_service as students
from app.services import student_analytics_service as students_module
from app.services.assistant import entity_resolver
from app.services.assistant.entity_resolver import ResolvedEntity
from app.services.assistant.tool_registry import (
    ToolDefinition,
    ToolExecutionError,
    registry,
)
from app.services.assistant.tool_schemas import (
    SCOPE_DEPARTMENT,
    SCOPE_PROGRAM,
    SCOPE_UNIVERSITY,
    ScopedMetric,
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

MISSING_STATUS = "Veri bulunamadı"

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
    student_count = row.total_students or None

    # PROGRAM DÜZEYİNDE kadro tahsisi. Artık üniversite veya bölüm toplamı
    # program değeri gibi gösterilmiyor.
    staff = allocation.program_staff_capacity(db, program.id, year)
    notes.extend(staff.notes)

    headcount = staff.headcount or None
    fte = staff.fte if staff.headcount else None
    # Oran FTE üzerinden: 12 kişinin yarısı bu programda ders veriyorsa
    # gerçek kapasite 6 FTE'dir, 12 değil.
    ratio = (
        quantize_money(Decimal(student_count) / fte)
        if student_count and fte and fte > 0
        else None
    )
    if headcount and fte is not None and Decimal(headcount) != fte:
        notes.append(
            f"Programda {headcount} öğretim üyesi ders veriyor; tam zaman "
            f"eşdeğeri {fte} FTE'dir. Öğrenci/öğretim üyesi oranı FTE "
            "üzerinden hesaplanır."
        )

    return ProgramSummaryOutput(
        scope=_scope_info(year, faculty, department, program),
        program_name=program.display_name,
        student_count=student_count,
        quota=row.quota or None,
        occupancy_rate=_dec(row.occupancy_rate),
        graduation_rate=_dec(row.graduation_rate),
        dropout_rate=_dec(row.attrition_rate),
        academic_staff_count=headcount,
        allocated_staff_headcount=headcount,
        allocated_staff_fte=fte,
        weekly_teaching_capacity_hours=(
            allocation.weekly_teaching_capacity_hours(fte) if fte else None
        ),
        student_staff_ratio=ratio,
        target_student_staff_ratio=allocation.TARGET_STUDENT_FTE_RATIO,
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

    # PROGRAM VERİLDİYSE program tahsislerinden cevap ver. Kurum geneli
    # kapasiteyi program kapasitesi gibi göstermek yanıltıcıydı.
    if program is not None:
        return _program_capacity_summary(db, year, faculty, department, program)

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


def _program_capacity_summary(
    db: Session, year: str, faculty, department, program
) -> CapacitySummaryOutput:
    """Program düzeyinde kapasite. Birimler zaman boyutu taşır."""
    students = students_module.build_program_analytics(
        db, academic_program_id=program.id, academic_year=year
    )
    student_count = int(students[0].total_students) if students else 0

    report = allocation.build_program_capacity_report(
        db, program.id, year, student_count
    )
    program_name = program.display_name

    scoped = [
        ScopedMetric(
            key="weekly_classroom_capacity", label="Haftalık derslik kapasitesi",
            scope_type=SCOPE_PROGRAM, scope_name=program_name, unit="koltuk-saat",
            baseline=report.classroom.weekly_capacity_unit_hours,
            formula=(
                "Σ(derslik koltuk sayısı × programa tahsisli haftalık saat "
                "× paylaşım payı)"
            ),
            note="; ".join(report.classroom.notes) or None,
        ),
        ScopedMetric(
            key="weekly_classroom_demand", label="Haftalık derslik ihtiyacı",
            scope_type=SCOPE_PROGRAM, scope_name=program_name, unit="koltuk-saat",
            baseline=report.weekly_classroom_demand,
            formula=(
                f"öğrenci sayısı × {allocation.WEEKLY_CLASSROOM_HOURS_PER_STUDENT} "
                "(öğrenci başına haftalık yüz yüze ders saati)"
            ),
        ),
        ScopedMetric(
            key="classroom_utilization", label="Derslik kapasite kullanım oranı",
            scope_type=SCOPE_PROGRAM, scope_name=program_name, unit="%",
            baseline=report.classroom_utilization_percent,
            formula="haftalık ihtiyaç / haftalık kapasite × 100",
        ),
        ScopedMetric(
            key="peak_concurrent_capacity", label="Yoğun saatte barındırılabilen",
            scope_type=SCOPE_PROGRAM, scope_name=program_name, unit="eş zamanlı kişi",
            baseline=Decimal(report.classroom.peak_concurrent_capacity),
            formula="Σ(derslik koltuk sayısı × paylaşım payı)",
        ),
        ScopedMetric(
            key="peak_concurrent_demand", label="Yoğun saatte eş zamanlı talep",
            scope_type=SCOPE_PROGRAM, scope_name=program_name, unit="eş zamanlı kişi",
            baseline=Decimal(report.peak_classroom_demand),
            formula=(
                f"öğrenci sayısı × {allocation.PEAK_CLASSROOM_CONCURRENCY} "
                "(yoğun saat eş zamanlılık katsayısı)"
            ),
        ),
    ]

    if report.laboratory.facility_count:
        scoped.extend([
            ScopedMetric(
                key="weekly_laboratory_capacity", label="Haftalık laboratuvar kapasitesi",
                scope_type=SCOPE_PROGRAM, scope_name=program_name, unit="istasyon-saat",
                baseline=report.laboratory.weekly_capacity_unit_hours,
                formula=(
                    "Σ(istasyon sayısı × programa tahsisli haftalık saat "
                    "× paylaşım payı)"
                ),
                note="; ".join(report.laboratory.notes) or None,
            ),
            ScopedMetric(
                key="weekly_laboratory_demand", label="Haftalık laboratuvar ihtiyacı",
                scope_type=SCOPE_PROGRAM, scope_name=program_name, unit="istasyon-saat",
                baseline=report.weekly_laboratory_demand,
                formula=(
                    f"öğrenci sayısı × "
                    f"{allocation.WEEKLY_LABORATORY_HOURS_PER_STUDENT} "
                    "(öğrenci başına haftalık laboratuvar saati)"
                ),
            ),
            ScopedMetric(
                key="laboratory_utilization", label="Laboratuvar kullanım oranı",
                scope_type=SCOPE_PROGRAM, scope_name=program_name, unit="%",
                baseline=report.laboratory_utilization_percent,
                formula="haftalık ihtiyaç / haftalık kapasite × 100",
            ),
        ])

    gap = report.peak_classroom_demand - report.classroom.peak_concurrent_capacity
    status = "yetersiz" if gap > 0 else "yeterli"

    return CapacitySummaryOutput(
        scope=_scope_info(year, faculty, department, program),
        scoped_metrics=scoped,
        allocated_classrooms=report.classroom.facility_count or None,
        allocated_laboratories=report.laboratory.facility_count or None,
        weekly_classroom_capacity_seat_hours=report.classroom.weekly_capacity_unit_hours,
        weekly_classroom_demand_seat_hours=report.weekly_classroom_demand,
        weekly_laboratory_capacity_station_hours=(
            report.laboratory.weekly_capacity_unit_hours
            if report.laboratory.facility_count else None
        ),
        weekly_laboratory_demand_station_hours=(
            report.weekly_laboratory_demand if report.laboratory.facility_count else None
        ),
        classroom_utilization_percent=report.classroom_utilization_percent,
        laboratory_utilization_percent=report.laboratory_utilization_percent,
        peak_concurrent_capacity=report.classroom.peak_concurrent_capacity or None,
        peak_concurrent_demand=report.peak_classroom_demand or None,
        capacity_gap=gap,
        capacity_status=status,
        notes=report.notes + [
            "Kapasite değerleri zaman boyutu taşır: koltuk-saat ve "
            "istasyon-saat. 'Kişi' tek başına kapasite birimi değildir.",
            f"Tahsisli derslikler: {', '.join(report.classroom.facility_codes) or 'yok'}.",
        ],
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

    # ÜNİVERSİTE KADRO AÇIĞI — mevcut ve senaryo AYRI hesaplanır.
    #
    # Kurumun kadro açığı senaryodan önce de vardı. Toplam açığı senaryodan
    # doğmuş gibi göstermek, yöneticiye yanlış bir sebep-sonuç ilişkisi
    # sunar.
    baseline_recommended_staff = int(
        (Decimal(computation.baseline_student_count) / TARGET_STUDENT_STAFF_RATIO)
        .to_integral_value(rounding="ROUND_CEILING")
    )
    projected_university_students = computation.projected_student_count
    recommended_staff = int(
        (Decimal(projected_university_students) / TARGET_STUDENT_STAFF_RATIO)
        .to_integral_value(rounding="ROUND_CEILING")
    )
    baseline_staff_gap = baseline_recommended_staff - computation.baseline_staff_count
    staff_gap = recommended_staff - computation.projected_staff_count
    marginal_staff_requirement = recommended_staff - baseline_recommended_staff

    # ------------------------------------------------------------------
    # KAPSAM ETİKETLİ GÖSTERGELER
    #
    # Aynı blokta program ve üniversite sayılarını etiketsiz yan yana
    # göstermek yanıltıcıydı: 426 öğrencilik bir programın 1.420 kişilik
    # derslik talebi ürettiği sanılıyordu. Her gösterge artık kapsamını,
    # birimini ve formülünü kendisi taşır.
    # ------------------------------------------------------------------
    university_name = "Üniversite geneli"
    program_name = program.display_name
    department_name = department.display_name if department else None

    # PROGRAM DÜZEYİNDE KAYNAK RAPORU — mevcut ve senaryo öğrenci sayısıyla
    # AYNI formülden geçirilir. Artık kurum toplamı program değeri gibi
    # kullanılmıyor.
    base_report = allocation.build_program_capacity_report(
        db, program.id, year, program_students
    )
    scenario_report = allocation.build_program_capacity_report(
        db, program.id, year, projected_program_students
    )

    # Programın kendi eş zamanlı talebi, kurum geneliyle AYNI katsayıdan
    # türetilir. Kurum toplamını program talebi gibi göstermek yerine
    # programın payı ayrıca hesaplanır.
    program_classroom_demand = int(
        (Decimal(projected_program_students) * SIMULTANEOUS_CLASSROOM_USE)
        .to_integral_value()
    )
    program_laboratory_demand = int(
        (Decimal(projected_program_students) * SIMULTANEOUS_LABORATORY_USE)
        .to_integral_value()
    )
    baseline_program_classroom = int(
        (Decimal(program_students) * SIMULTANEOUS_CLASSROOM_USE).to_integral_value()
    )
    baseline_program_laboratory = int(
        (Decimal(program_students) * SIMULTANEOUS_LABORATORY_USE).to_integral_value()
    )

    # Program düzeyinde öğretim üyesi dağılımı VERİDE YOK. Bölüm kadrosu
    # ayrı bir kapsam olarak, kendi etiketiyle verilir.
    department_staff = _staff_count(db, year, faculty, department)
    recommended_program_staff = int(
        (Decimal(projected_program_students) / TARGET_STUDENT_STAFF_RATIO)
        .to_integral_value(rounding="ROUND_CEILING")
    )

    scoped: List[ScopedMetric] = [
        ScopedMetric(
            key="program_student_count", label="Öğrenci sayısı",
            scope_type=SCOPE_PROGRAM, scope_name=program_name, unit="öğrenci",
            baseline=Decimal(program_students),
            scenario=Decimal(projected_program_students),
            change=Decimal(int(added_students)),
            formula=f"mevcut öğrenci × (1 + %{change_percent} / 100)",
        ),
        ScopedMetric(
            key="program_staff_headcount", label="Programda ders veren öğretim üyesi",
            scope_type=SCOPE_PROGRAM, scope_name=program_name, unit="kişi",
            baseline=Decimal(base_report.staff.headcount),
            formula="programa tahsis edilmiş tekil öğretim üyesi sayısı",
            note="; ".join(base_report.staff.notes) or None,
        ),
        ScopedMetric(
            key="program_staff_fte", label="Program akademik kapasitesi",
            scope_type=SCOPE_PROGRAM, scope_name=program_name, unit="FTE",
            baseline=base_report.staff.fte,
            formula="Σ(tahsis yüzdesi / 100). Kişi sayısından farklıdır.",
        ),
        ScopedMetric(
            key="program_required_fte", label="Gerekli akademik kapasite",
            scope_type=SCOPE_PROGRAM, scope_name=program_name, unit="FTE",
            baseline=base_report.required_fte,
            scenario=scenario_report.required_fte,
            change=scenario_report.required_fte - base_report.required_fte,
            formula=(
                f"öğrenci sayısı / {allocation.TARGET_STUDENT_FTE_RATIO:.0f} "
                "(hedef öğrenci-FTE oranı)"
            ),
        ),
        ScopedMetric(
            key="program_baseline_fte_gap", label="Mevcut program açığı",
            scope_type=SCOPE_PROGRAM, scope_name=program_name, unit="FTE",
            baseline=base_report.fte_gap,
            formula="mevcut gerekli FTE − mevcut FTE",
            note="Bu açık senaryodan bağımsızdır; şu anda da vardır.",
        ),
        ScopedMetric(
            key="program_scenario_fte_gap", label="Senaryo sonrası program açığı",
            scope_type=SCOPE_PROGRAM, scope_name=program_name, unit="FTE",
            scenario=scenario_report.fte_gap,
            formula="senaryo gerekli FTE − mevcut FTE",
        ),
        ScopedMetric(
            key="program_marginal_fte", label="Senaryodan kaynaklanan ek ihtiyaç",
            scope_type=SCOPE_PROGRAM, scope_name=program_name, unit="FTE",
            change=scenario_report.required_fte - base_report.required_fte,
            formula="senaryo gerekli FTE − mevcut gerekli FTE",
        ),
        ScopedMetric(
            key="program_classroom_capacity", label="Program derslik kapasitesi",
            scope_type=SCOPE_PROGRAM, scope_name=program_name, unit="koltuk-saat",
            baseline=base_report.classroom.weekly_capacity_unit_hours,
            formula=(
                "Σ(derslik koltuk sayısı × tahsisli haftalık saat × paylaşım payı)"
            ),
            note="; ".join(base_report.classroom.notes) or None,
        ),
        ScopedMetric(
            key="program_classroom_demand", label="Program haftalık derslik ihtiyacı",
            scope_type=SCOPE_PROGRAM, scope_name=program_name, unit="koltuk-saat",
            baseline=base_report.weekly_classroom_demand,
            scenario=scenario_report.weekly_classroom_demand,
            change=(
                scenario_report.weekly_classroom_demand
                - base_report.weekly_classroom_demand
            ),
            formula=(
                f"öğrenci sayısı × {allocation.WEEKLY_CLASSROOM_HOURS_PER_STUDENT} "
                "(öğrenci başına haftalık ders saati)"
            ),
        ),
        ScopedMetric(
            key="program_classroom_utilization", label="Program derslik kullanım oranı",
            scope_type=SCOPE_PROGRAM, scope_name=program_name, unit="%",
            baseline=base_report.classroom_utilization_percent,
            scenario=scenario_report.classroom_utilization_percent,
            formula="haftalık ihtiyaç / haftalık kapasite × 100",
            note=(
                "Program MEVCUT durumda da tahsisli derslik kapasitesini "
                "aşıyor; senaryo bu sorunu oluşturmuyor, büyütüyor."
                if base_report.classroom_utilization_percent
                and base_report.classroom_utilization_percent > 100
                else None
            ),
        ),
        ScopedMetric(
            key="program_classroom_coverage", label="Derslik talebinin karşılanan oranı",
            scope_type=SCOPE_PROGRAM, scope_name=program_name, unit="%",
            baseline=base_report.classroom_coverage_percent,
            scenario=scenario_report.classroom_coverage_percent,
            formula="min(kapasite, talep) / talep × 100",
        ),
        ScopedMetric(
            key="program_classroom_shortfall", label="Derslik talebinin karşılanamayan oranı",
            scope_type=SCOPE_PROGRAM, scope_name=program_name, unit="%",
            baseline=base_report.classroom_shortfall_percent,
            scenario=scenario_report.classroom_shortfall_percent,
            formula="100 − karşılanan oran",
        ),
    ]

    if base_report.laboratory.facility_count:
        scoped.extend([
            ScopedMetric(
                key="program_laboratory_capacity", label="Program laboratuvar kapasitesi",
                scope_type=SCOPE_PROGRAM, scope_name=program_name, unit="istasyon-saat",
                baseline=base_report.laboratory.weekly_capacity_unit_hours,
                formula=(
                    "Σ(istasyon sayısı × tahsisli haftalık saat × paylaşım payı)"
                ),
                note="; ".join(base_report.laboratory.notes) or None,
            ),
            ScopedMetric(
                key="program_laboratory_demand", label="Program haftalık laboratuvar ihtiyacı",
                scope_type=SCOPE_PROGRAM, scope_name=program_name, unit="istasyon-saat",
                baseline=base_report.weekly_laboratory_demand,
                scenario=scenario_report.weekly_laboratory_demand,
                change=(
                    scenario_report.weekly_laboratory_demand
                    - base_report.weekly_laboratory_demand
                ),
                formula=(
                    f"öğrenci sayısı × "
                    f"{allocation.WEEKLY_LABORATORY_HOURS_PER_STUDENT}"
                ),
            ),
            ScopedMetric(
                key="program_laboratory_utilization", label="Program laboratuvar kullanım oranı",
                scope_type=SCOPE_PROGRAM, scope_name=program_name, unit="%",
                baseline=base_report.laboratory_utilization_percent,
                scenario=scenario_report.laboratory_utilization_percent,
                formula="haftalık ihtiyaç / haftalık kapasite × 100",
                note=(
                    "Program MEVCUT durumda da tahsisli laboratuvar "
                    "kapasitesini aşıyor."
                    if base_report.laboratory_utilization_percent
                    and base_report.laboratory_utilization_percent > 100
                    else None
                ),
            ),
            ScopedMetric(
                key="program_laboratory_coverage", label="Laboratuvar talebinin karşılanan oranı",
                scope_type=SCOPE_PROGRAM, scope_name=program_name, unit="%",
                baseline=base_report.laboratory_coverage_percent,
                scenario=scenario_report.laboratory_coverage_percent,
                formula="min(kapasite, talep) / talep × 100",
            ),
            ScopedMetric(
                key="program_laboratory_shortfall",
                label="Laboratuvar talebinin karşılanamayan oranı",
                scope_type=SCOPE_PROGRAM, scope_name=program_name, unit="%",
                baseline=base_report.laboratory_shortfall_percent,
                scenario=scenario_report.laboratory_shortfall_percent,
                formula="100 − karşılanan oran",
            ),
        ])
    else:
        scoped.append(
            ScopedMetric(
                key="program_laboratory_capacity", label="Program laboratuvar kapasitesi",
                scope_type=SCOPE_PROGRAM, scope_name=program_name, unit="istasyon-saat",
                note=(
                    "Bu programa tahsis edilmiş laboratuvar yok; laboratuvar "
                    "ihtiyacı hesaplanmadı."
                ),
            )
        )

    scoped.append(
        ScopedMetric(
            key="program_revenue_effect", label="Bu programdaki artışın ek gelir etkisi",
            scope_type=SCOPE_PROGRAM, scope_name=program_name, unit="USD",
            change=revenue.absolute_change if revenue else None,
            flow="inflow",
            formula=(
                "senaryo motorunun kurum geneli gelir farkı; artış yalnızca bu "
                "programdan geldiği için tamamı programa atfedilir"
            ),
        )
    )

    if department_name is not None:
        scoped.append(
            ScopedMetric(
                key="department_staff_count", label="Bölüm akademik personeli",
                scope_type=SCOPE_DEPARTMENT, scope_name=department_name, unit="kişi",
                baseline=Decimal(department_staff) if department_staff else None,
                note=(
                    None if department_staff
                    else "Bu bölüm için akademik personel kaydı bulunamadı."
                ),
            )
        )

    scoped.extend([
        ScopedMetric(
            key="university_total_revenue", label="Üniversite toplam yıllık geliri",
            scope_type=SCOPE_UNIVERSITY, scope_name=university_name, unit="USD",
            baseline=revenue.baseline_value if revenue else None,
            scenario=revenue.projected_value if revenue else None,
            change=revenue.absolute_change if revenue else None,
            flow="inflow",
            # TOPLAMDIR: aynı 329.840 USD hem burada hem "programdaki artışın
            # ek gelir etkisi" kaleminde durur. İkisi birden şelaleye katkı
            # sayılsaydı gelir iki kez hesaplanırdı.
            is_total=True,
            formula="öğrenim ücreti (burs sonrası) + araştırma + diğer gelirler",
        ),
        ScopedMetric(
            key="university_net_balance", label="Üniversite net bütçesi",
            scope_type=SCOPE_UNIVERSITY, scope_name=university_name, unit="USD",
            baseline=balance.baseline_value if balance else None,
            scenario=balance.projected_value if balance else None,
            change=balance.absolute_change if balance else None,
            flow="balance", is_total=True,
            formula="toplam gelir − toplam gider",
            note=(
                "Bu sonuç, gerekli EK PERSONEL ALIMI ve FİZİKSEL KAPASİTE "
                "YATIRIMLARI uygulanmadan öncesine aittir. Bu maliyetler "
                "hesaplandıktan sonra net finansal sürdürülebilirlik yeniden "
                "değerlendirilmelidir."
            ),
        ),
        ScopedMetric(
            key="university_staff_count", label="Üniversite akademik personeli",
            scope_type=SCOPE_UNIVERSITY, scope_name=university_name, unit="kişi",
            baseline=Decimal(computation.baseline_staff_count),
            scenario=Decimal(computation.projected_staff_count),
            change=Decimal(
                computation.projected_staff_count - computation.baseline_staff_count
            ),
            formula="mali dönem bordro kadrosu",
        ),
        ScopedMetric(
            key="university_recommended_staff", label="Üniversite için önerilen kadro",
            scope_type=SCOPE_UNIVERSITY, scope_name=university_name, unit="kişi",
            baseline=Decimal(baseline_recommended_staff),
            scenario=Decimal(recommended_staff),
            change=Decimal(marginal_staff_requirement),
            formula=(
                f"üniversite öğrenci sayısı / {TARGET_STUDENT_STAFF_RATIO:.0f} "
                "(hedef öğrenci-öğretim üyesi oranı)"
            ),
        ),
        ScopedMetric(
            key="university_staff_gap", label="Üniversite kadro açığı",
            scope_type=SCOPE_UNIVERSITY, scope_name=university_name, unit="kişi",
            baseline=Decimal(baseline_staff_gap),
            scenario=Decimal(staff_gap),
            change=Decimal(staff_gap - baseline_staff_gap),
            formula="önerilen kadro − mevcut kadro",
            note=(
                f"Kurumun {baseline_staff_gap} kişilik kadro açığı senaryodan "
                f"ÖNCE de vardı. Bu senaryonun eklediği ihtiyaç "
                f"{marginal_staff_requirement} kişidir."
            ),
        ),
        ScopedMetric(
            key="university_classroom_capacity", label="Üniversite derslik kapasitesi",
            scope_type=SCOPE_UNIVERSITY, scope_name=university_name, unit="kişi",
            baseline=Decimal(class_capacity.baseline_value) if class_capacity else None,
            scenario=Decimal(projected_class_capacity) if projected_class_capacity else None,
            formula="aktif dersliklerin toplam koltuk sayısı",
        ),
        ScopedMetric(
            key="university_classroom_demand", label="Üniversite eş zamanlı derslik talebi",
            scope_type=SCOPE_UNIVERSITY, scope_name=university_name,
            unit="eş zamanlı kişi",
            baseline=Decimal(class_demand.baseline_value) if class_demand else None,
            scenario=Decimal(projected_class_demand) if projected_class_demand else None,
            # DEĞİŞİM, açık DEĞİLDİR. İkisi karıştırıldığında 1.400 → 1.420
            # satırının yanında "+400" görünüyor ve değişim 400 sanılıyor.
            change=(
                Decimal(projected_class_demand) - Decimal(class_demand.baseline_value)
                if class_demand and projected_class_demand is not None
                else None
            ),
            formula=(
                f"üniversite toplam öğrenci sayısı × {SIMULTANEOUS_CLASSROOM_USE}"
            ),
        ),
        ScopedMetric(
            key="university_classroom_gap", label="Üniversite derslik kapasite açığı",
            scope_type=SCOPE_UNIVERSITY, scope_name=university_name,
            unit="eş zamanlı kişi",
            baseline=(
                Decimal(int(class_demand.baseline_value) - int(class_capacity.baseline_value))
                if class_demand and class_capacity else None
            ),
            scenario=Decimal(class_gap) if class_gap is not None else None,
            formula="eş zamanlı derslik talebi − derslik kapasitesi",
        ),
        ScopedMetric(
            key="university_classroom_coverage", label="Derslik talebinin karşılanan oranı",
            scope_type=SCOPE_UNIVERSITY, scope_name=university_name, unit="%",
            baseline=(
                allocation.coverage_percent(
                    Decimal(class_demand.baseline_value),
                    Decimal(class_capacity.baseline_value),
                )
                if class_demand and class_capacity else None
            ),
            scenario=(
                allocation.coverage_percent(
                    Decimal(projected_class_demand), Decimal(projected_class_capacity)
                )
                if projected_class_demand and projected_class_capacity else None
            ),
            formula="min(kapasite, talep) / talep × 100",
        ),
        ScopedMetric(
            key="university_classroom_shortfall",
            label="Derslik talebinin karşılanamayan oranı",
            scope_type=SCOPE_UNIVERSITY, scope_name=university_name, unit="%",
            baseline=(
                allocation.shortfall_percent(
                    Decimal(class_demand.baseline_value),
                    Decimal(class_capacity.baseline_value),
                )
                if class_demand and class_capacity else None
            ),
            scenario=(
                allocation.shortfall_percent(
                    Decimal(projected_class_demand), Decimal(projected_class_capacity)
                )
                if projected_class_demand and projected_class_capacity else None
            ),
            formula="100 − karşılanan oran",
        ),
        ScopedMetric(
            key="university_laboratory_capacity", label="Üniversite laboratuvar kapasitesi",
            scope_type=SCOPE_UNIVERSITY, scope_name=university_name, unit="kişi",
            baseline=Decimal(lab_capacity.baseline_value) if lab_capacity else None,
            scenario=Decimal(projected_lab_capacity) if projected_lab_capacity else None,
            formula="aktif laboratuvarların toplam koltuk sayısı",
        ),
        ScopedMetric(
            key="university_laboratory_demand", label="Üniversite eş zamanlı laboratuvar talebi",
            scope_type=SCOPE_UNIVERSITY, scope_name=university_name,
            unit="eş zamanlı kişi",
            baseline=Decimal(lab_demand.baseline_value) if lab_demand else None,
            scenario=Decimal(projected_lab_demand) if projected_lab_demand else None,
            change=(
                Decimal(projected_lab_demand) - Decimal(lab_demand.baseline_value)
                if lab_demand and projected_lab_demand is not None
                else None
            ),
            formula=(
                f"üniversite toplam öğrenci sayısı × {SIMULTANEOUS_LABORATORY_USE}"
            ),
        ),
        ScopedMetric(
            key="university_laboratory_gap", label="Üniversite laboratuvar kapasite açığı",
            scope_type=SCOPE_UNIVERSITY, scope_name=university_name,
            unit="eş zamanlı kişi",
            baseline=(
                Decimal(int(lab_demand.baseline_value) - int(lab_capacity.baseline_value))
                if lab_demand and lab_capacity else None
            ),
            scenario=Decimal(lab_gap) if lab_gap is not None else None,
            formula="eş zamanlı laboratuvar talebi − laboratuvar kapasitesi",
        ),
        ScopedMetric(
            key="university_laboratory_coverage",
            label="Laboratuvar talebinin karşılanan oranı",
            scope_type=SCOPE_UNIVERSITY, scope_name=university_name, unit="%",
            baseline=(
                allocation.coverage_percent(
                    Decimal(lab_demand.baseline_value),
                    Decimal(lab_capacity.baseline_value),
                )
                if lab_demand and lab_capacity else None
            ),
            scenario=(
                allocation.coverage_percent(
                    Decimal(projected_lab_demand), Decimal(projected_lab_capacity)
                )
                if projected_lab_demand and projected_lab_capacity else None
            ),
            formula="min(kapasite, talep) / talep × 100",
        ),
        ScopedMetric(
            key="university_laboratory_shortfall",
            label="Laboratuvar talebinin karşılanamayan oranı",
            scope_type=SCOPE_UNIVERSITY, scope_name=university_name, unit="%",
            baseline=(
                allocation.shortfall_percent(
                    Decimal(lab_demand.baseline_value),
                    Decimal(lab_capacity.baseline_value),
                )
                if lab_demand and lab_capacity else None
            ),
            scenario=(
                allocation.shortfall_percent(
                    Decimal(projected_lab_demand), Decimal(projected_lab_capacity)
                )
                if projected_lab_demand and projected_lab_capacity else None
            ),
            formula="100 − karşılanan oran",
        ),
        ScopedMetric(
            key="university_capacity_status", label="Kapasite durumu",
            scope_type=SCOPE_UNIVERSITY, scope_name=university_name, unit="durum",
            note=capacity_status or MISSING_STATUS,
        ),
    ])

    return EnrollmentScenarioOutput(
        scope=_scope_info(year, faculty, department, program),
        scoped_metrics=scoped,
        baseline_recommended_university_staff=baseline_recommended_staff,
        scenario_recommended_university_staff=recommended_staff,
        marginal_university_staff_requirement=marginal_staff_requirement,
        baseline_university_staff_gap=baseline_staff_gap,
        scenario_university_staff_gap=staff_gap,
        operating_budget_effect_before_investment=(
            balance.absolute_change if balance else None
        ),
        additional_staff_cost_included=False,
        facility_investment_cost_included=False,
        program_student_change=int(added_students),
        student_change_percentage=change_percent,
        revenue_change_usd=revenue.absolute_change if revenue else None,
        net_balance_change_usd=balance.absolute_change if balance else None,
        baseline=ScenarioBaselineBlock(
            academic_year=year,
            program_staff_headcount=base_report.staff.headcount or None,
            program_staff_fte=base_report.staff.fte,
            program_required_fte=base_report.required_fte,
            program_classroom_capacity_seat_hours=(
                base_report.classroom.weekly_capacity_unit_hours
            ),
            program_classroom_demand_seat_hours=base_report.weekly_classroom_demand,
            program_laboratory_capacity_station_hours=(
                base_report.laboratory.weekly_capacity_unit_hours
                if base_report.laboratory.facility_count else None
            ),
            program_laboratory_demand_station_hours=(
                base_report.weekly_laboratory_demand
                if base_report.laboratory.facility_count else None
            ),
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
            program_staff_fte=scenario_report.staff.fte,
            program_required_fte=scenario_report.required_fte,
            program_fte_gap=scenario_report.fte_gap,
            program_classroom_capacity_seat_hours=(
                scenario_report.classroom.weekly_capacity_unit_hours
            ),
            program_classroom_demand_seat_hours=scenario_report.weekly_classroom_demand,
            program_laboratory_capacity_station_hours=(
                scenario_report.laboratory.weekly_capacity_unit_hours
                if scenario_report.laboratory.facility_count else None
            ),
            program_laboratory_demand_station_hours=(
                scenario_report.weekly_laboratory_demand
                if scenario_report.laboratory.facility_count else None
            ),
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
    """Akademik maaş zammının mali etkisi.

    KRİTİK AYRIM — MAAŞ ARTIŞI GELİR DEĞİLDİR
    -----------------------------------------
    Zam yalnızca AKADEMİK personel giderini artırır. Gelir değişmez, idari
    maaşlar değişmez. Aynı tutarı hem gelir hem gider tarafına yazmak (ya da
    "toplam gider etkisi" ile "akademik personel gideri" kalemlerini birlikte
    katkı saymak) 612.000 USD'lik etkiyi iki kez saymak olurdu.

    Bu yüzden her parasal metrik iki alan taşır:
      * `flow`     — inflow (gelir) / outflow (gider) / balance (net sonuç)
      * `is_total` — bu kalem başka kalemlerin toplamı mı?
    Şelale grafiği yalnızca `is_total=False` katkıları kullanır.
    """
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

    academic = _find("personnel_expense")
    administrative = _find("administrative_personnel_expense")
    total_personnel = _find("total_personnel_expense")
    expenditure = _find("total_expenditure")
    revenue = _find("total_revenue")
    balance = _find("balance")
    cost_per_student = _find("cost_per_student")
    average_salary = _find("average_salary")
    staff_count = _find("staff_count")

    def _ratio(part: Optional[Decimal], whole: Optional[Decimal]) -> Optional[Decimal]:
        """Oran hesabı TEK YERDE. Payda yoksa uydurma değer üretilmez."""
        if part is None or not whole:
            return None
        return (Decimal(part) / Decimal(whole) * Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    baseline_ratio = _ratio(
        academic.baseline_value if academic else None,
        expenditure.baseline_value if expenditure else None,
    )
    scenario_ratio = _ratio(
        academic.projected_value if academic else None,
        expenditure.projected_value if expenditure else None,
    )
    baseline_total_ratio = _ratio(
        total_personnel.baseline_value if total_personnel else None,
        expenditure.baseline_value if expenditure else None,
    )
    scenario_total_ratio = _ratio(
        total_personnel.projected_value if total_personnel else None,
        expenditure.projected_value if expenditure else None,
    )

    university_name = "Üniversite geneli"
    percent = Decimal(str(payload.salary_change_percentage))

    def _money(
        key: str, label: str, source: Optional[MetricChange], *,
        flow: Optional[str], is_total: bool = False, formula: Optional[str] = None,
        note: Optional[str] = None,
    ) -> ScopedMetric:
        return ScopedMetric(
            key=key, label=label,
            scope_type=SCOPE_UNIVERSITY, scope_name=university_name, unit="USD",
            baseline=source.baseline_value if source else None,
            scenario=source.projected_value if source else None,
            change=source.absolute_change if source else None,
            semantic_type="monetary_change",
            flow=flow, is_total=is_total, formula=formula, note=note,
        )

    salary_scoped = [
        _money(
            "annual_staff_cost", "Akademik personel gideri", academic,
            flow="outflow",
            formula=f"akademik kadro × ortalama maaş × (1 + %{percent} / 100)",
        ),
        _money(
            "administrative_staff_cost", "İdari personel gideri", administrative,
            flow="outflow",
            formula="idari kadro × ortalama idari maaş",
            note="Bu senaryoda idari maaşlara zam yapılmamıştır; değer sabittir.",
        ),
        _money(
            "total_personnel_cost", "Toplam personel gideri", total_personnel,
            flow="outflow", is_total=True,
            formula="akademik personel gideri + idari personel gideri",
        ),
        _money(
            "total_expenditure", "Toplam kurum harcaması", expenditure,
            flow="outflow", is_total=True,
            formula="personel + eğitim + Ar-Ge + altyapı + teknoloji giderleri",
        ),
        _money(
            "university_total_revenue", "Üniversite toplam yıllık geliri", revenue,
            flow="inflow",
            formula="öğrenim ücreti (burs sonrası) + araştırma + diğer gelirler",
            note="Maaş artışı bir GELİR kalemi değildir; gelir bu senaryoda değişmez.",
        ),
        _money(
            "university_net_balance", "Net bütçe", balance,
            flow="balance", is_total=True,
            formula="toplam gelir − toplam harcama",
        ),
        ScopedMetric(
            key="academic_personnel_expense_ratio",
            label="Akademik personel giderinin toplam harcamaya oranı",
            scope_type=SCOPE_UNIVERSITY, scope_name=university_name, unit="%",
            baseline=baseline_ratio, scenario=scenario_ratio,
            semantic_type="utilization",
            formula="akademik personel gideri / toplam kurum harcaması × 100",
        ),
        ScopedMetric(
            key="total_personnel_expense_ratio",
            label="Toplam personel giderinin toplam harcamaya oranı",
            scope_type=SCOPE_UNIVERSITY, scope_name=university_name, unit="%",
            baseline=baseline_total_ratio, scenario=scenario_total_ratio,
            semantic_type="utilization",
            formula="toplam personel gideri / toplam kurum harcaması × 100",
        ),
        ScopedMetric(
            key="average_academic_salary", label="Ortalama akademik maaş",
            scope_type=SCOPE_UNIVERSITY, scope_name=university_name, unit="USD",
            baseline=average_salary.baseline_value if average_salary else None,
            scenario=average_salary.projected_value if average_salary else None,
            change=average_salary.absolute_change if average_salary else None,
            semantic_type="monetary_change",
            # Ortalama maaş bir BİRİM FİYATTIR, bütçe akışı değil; şelale
            # grafiği onu katkı kalemi sanmamalı.
            flow="unit_price",
            formula="akademik personel gideri / akademik kadro sayısı",
        ),
        ScopedMetric(
            key="academic_staff_count", label="Akademik kadro sayısı",
            scope_type=SCOPE_UNIVERSITY, scope_name=university_name, unit="kişi",
            baseline=staff_count.baseline_value if staff_count else None,
            scenario=staff_count.projected_value if staff_count else None,
            change=staff_count.absolute_change if staff_count else None,
            semantic_type="count_change",
            note="Bu senaryoda kadro sayısı SABİT tutulmuştur.",
        ),
        _money(
            # Öğrenci başına maliyet de bir birim fiyattır; bütçe kalemi değil.
            "cost_per_student", "Öğrenci başına maliyet", cost_per_student,
            flow="unit_price", is_total=True,
            formula="toplam kurum harcaması / öğrenci sayısı",
        ),
    ]

    # Senaryonun kapsamı. Bunlar VARSAYIMDIR, sonuç değil; ayrı alanda
    # taşınır ki arayüz doğru kutuya koysun.
    assumptions = [
        f"Yalnızca akademik personel maaşları %{_plain_percent(percent)} "
        "artırılmıştır; idari personel maaşları ve akademik kadro sayısı "
        "sabit tutulmuştur.",
        "Ek ders ödemeleri kapsam dışıdır; mali kayıtta ayrı kalem olarak "
        "tutulmuyor.",
        "Yan haklar ve işveren yükleri kapsam dışıdır; personel gideri "
        "kalemi brüt maaş toplamı olarak alınmıştır.",
        "Döviz kuru sabit kabul edilmiştir; bu senaryoda kur değişimi "
        "uygulanmamıştır.",
        "Enflasyon uygulanmamıştır; diğer gider kalemleri taban değerinde "
        "kalmıştır.",
    ]

    return SalaryScenarioOutput(
        scope=_scope_info(year, faculty, department, None),
        scoped_metrics=salary_scoped,
        salary_change_percentage=percent,
        previous_annual_staff_cost_usd=academic.baseline_value if academic else None,
        new_annual_staff_cost_usd=academic.projected_value if academic else None,
        cost_change_usd=academic.absolute_change if academic else None,
        previous_administrative_cost_usd=(
            administrative.baseline_value if administrative else None
        ),
        new_administrative_cost_usd=(
            administrative.projected_value if administrative else None
        ),
        previous_total_personnel_cost_usd=(
            total_personnel.baseline_value if total_personnel else None
        ),
        new_total_personnel_cost_usd=(
            total_personnel.projected_value if total_personnel else None
        ),
        previous_total_expenditure_usd=expenditure.baseline_value if expenditure else None,
        new_total_expenditure_usd=expenditure.projected_value if expenditure else None,
        total_expenditure_change_usd=expenditure.absolute_change if expenditure else None,
        previous_total_revenue_usd=revenue.baseline_value if revenue else None,
        new_total_revenue_usd=revenue.projected_value if revenue else None,
        revenue_change_usd=revenue.absolute_change if revenue else None,
        previous_net_balance_usd=balance.baseline_value if balance else None,
        new_net_balance_usd=balance.projected_value if balance else None,
        net_balance_change_usd=balance.absolute_change if balance else None,
        previous_personnel_expense_ratio_percent=baseline_ratio,
        new_personnel_expense_ratio_percent=scenario_ratio,
        previous_total_personnel_ratio_percent=baseline_total_ratio,
        new_total_personnel_ratio_percent=scenario_total_ratio,
        cost_per_student_change_usd=cost_per_student.absolute_change
        if cost_per_student
        else None,
        risks=[r.message for r in risks],
        recommendations=[recommendation] if recommendation else [],
        assumptions=assumptions,
        method_note=(
            f"Akademik personel gideri = akademik kadro sayısı × ortalama maaş. "
            f"%{_plain_percent(percent)} zam yalnızca ortalama maaşı değiştirir; "
            f"kadro sayısı ve idari personel gideri sabit kalır. Gelir tarafı "
            f"bu senaryodan etkilenmez."
        ),
        notes=notes
        + [
            f"Taban: {year} mali dönemi gerçek gelir/gider kayıtları.",
            "Bu bir simülasyondur; veritabanına kayıt yazılmamıştır.",
        ],
    )


def _plain_percent(value: Decimal) -> str:
    """Yüzdeyi gereksiz sıfırlar olmadan yazar: 10.00 -> "10"."""
    text = f"{Decimal(str(value)):.2f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


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
