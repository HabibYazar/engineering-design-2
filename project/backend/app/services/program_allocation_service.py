"""Program düzeyinde kaynak kapasitesi — merkezi formül katmanı.

BURASI TEK KAYNAKTIR. Koltuk-saat, istasyon-saat, FTE ve yoğun saat talebi
formülleri yalnızca burada tanımlıdır; araçlar, senaryo motoru ve raporlar bu
fonksiyonları çağırır. İki farklı yerde yazılan aynı formül er ya da geç
birbirinden ayrılır.

BİRİM SÖZLÜĞÜ
-------------
* koltuk-saat        — bir dersliğin haftalık kapasitesi (koltuk × saat)
* istasyon-saat      — bir laboratuvarın haftalık kapasitesi
* eş zamanlı kişi    — yoğun saatte aynı anda mekânda bulunan öğrenci sayısı
* FTE                — tam zaman eşdeğeri öğretim üyesi

"Kişi" tek başına kapasite birimi DEĞİLDİR: 60 kişilik bir derslik haftada
40 saat açıksa kapasitesi 2.400 koltuk-saattir.
"""

import logging
from dataclasses import dataclass, field
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AcademicProgram,
    AcademicStaff,
    PhysicalFacility,
    ProgramAcademicStaffAllocation,
    ProgramFacilityAllocation,
)
from app.models.program_allocation import WEEKLY_AVAILABLE_HOURS

logger = logging.getLogger(__name__)

# --- Planlama varsayımları. Hepsi tek yerde, hepsi cevaplarda açıklanır. ---

#: Bir öğrencinin haftada yüz yüze geçirdiği derslik saati.
WEEKLY_CLASSROOM_HOURS_PER_STUDENT: Decimal = Decimal("18")

#: Laboratuvar gerektiren programlarda öğrenci başına haftalık laboratuvar saati.
WEEKLY_LABORATORY_HOURS_PER_STUDENT: Decimal = Decimal("4")

#: Yoğun saatte aynı anda derslikte bulunan öğrenci oranı.
PEAK_CLASSROOM_CONCURRENCY: Decimal = Decimal("0.35")

#: Yoğun saatte aynı anda laboratuvarda bulunan öğrenci oranı.
PEAK_LABORATORY_CONCURRENCY: Decimal = Decimal("0.18")

#: Hedef öğrenci / FTE öğretim üyesi oranı.
TARGET_STUDENT_FTE_RATIO: Decimal = Decimal("20")

#: Bir FTE öğretim üyesinin haftalık ders yükü (saat).
WEEKLY_TEACHING_HOURS_PER_FTE: Decimal = Decimal("12")

LABORATORY_TYPES = ("laboratory", "studio", "workshop")


def _q2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class AllocationValidationError(ValueError):
    """Tahsis kuralı ihlal edildi."""


# ---------------------------------------------------------------------------
# Personel tahsisi
# ---------------------------------------------------------------------------


@dataclass
class ProgramStaffCapacity:
    """Bir programın akademik personel kapasitesi."""

    academic_year: str
    program_id: int
    #: Programda ders veren KİŞİ sayısı.
    headcount: int
    #: Tam zaman eşdeğeri. 12 kişi = 8,5 FTE olabilir.
    fte: Decimal
    #: Haftalık toplam ders saati.
    weekly_course_hours: int
    #: Ana kadrosu bu programda olan kişi sayısı.
    primary_headcount: int
    notes: List[str] = field(default_factory=list)


def validate_staff_allocation_totals(db: Session, academic_year: str) -> Dict[int, Decimal]:
    """Kişi başına toplam tahsisi hesaplar ve %100 sınırını denetler.

    Döndürdüğü sözlük: personel kimliği → toplam tahsis yüzdesi.
    Aşım varsa AllocationValidationError fırlatır; hangi kişinin ne kadar
    aştığı mesajda yazar.
    """
    rows = db.execute(
        select(
            ProgramAcademicStaffAllocation.academic_staff_id,
            ProgramAcademicStaffAllocation.allocation_percent,
        ).where(ProgramAcademicStaffAllocation.academic_year == academic_year)
    ).all()

    totals: Dict[int, Decimal] = {}
    for staff_id, percent in rows:
        totals[staff_id] = totals.get(staff_id, Decimal("0")) + Decimal(str(percent))

    over = {sid: total for sid, total in totals.items() if total > Decimal("100")}
    if over:
        raise AllocationValidationError(
            f"{academic_year}: toplam tahsisi %100'ü aşan personel var: "
            + ", ".join(f"#{sid} → %{total}" for sid, total in sorted(over.items())[:5])
        )
    return totals


def program_staff_capacity(
    db: Session, program_id: int, academic_year: str
) -> ProgramStaffCapacity:
    """Bir programın personel kapasitesi. Kişi sayısı ve FTE AYRI döndürülür."""
    rows = list(
        db.execute(
            select(ProgramAcademicStaffAllocation).where(
                ProgramAcademicStaffAllocation.program_id == program_id,
                ProgramAcademicStaffAllocation.academic_year == academic_year,
            )
        ).scalars()
    )

    if not rows:
        return ProgramStaffCapacity(
            academic_year=academic_year,
            program_id=program_id,
            headcount=0,
            fte=Decimal("0.00"),
            weekly_course_hours=0,
            primary_headcount=0,
            notes=[
                f"{academic_year} için bu programa tahsis edilmiş akademik "
                "personel kaydı bulunamadı."
            ],
        )

    total_fte = sum((row.fte for row in rows), Decimal("0"))
    return ProgramStaffCapacity(
        academic_year=academic_year,
        program_id=program_id,
        headcount=len(rows),
        fte=_q2(total_fte),
        weekly_course_hours=sum(row.weekly_course_hours for row in rows),
        primary_headcount=sum(1 for row in rows if row.is_primary),
    )


def required_staff_fte(student_count: int) -> Decimal:
    """Hedef orana göre gereken FTE.

    Formül: öğrenci sayısı / hedef öğrenci-FTE oranı
    """
    if student_count <= 0:
        return Decimal("0.00")
    return _q2(Decimal(student_count) / TARGET_STUDENT_FTE_RATIO)


def weekly_teaching_capacity_hours(fte: Decimal) -> Decimal:
    """FTE'nin haftalık ders verme kapasitesi (saat)."""
    return _q2(Decimal(str(fte)) * WEEKLY_TEACHING_HOURS_PER_FTE)


# ---------------------------------------------------------------------------
# Mekân tahsisi
# ---------------------------------------------------------------------------


@dataclass
class ProgramFacilityCapacity:
    """Bir programın bir mekân türündeki haftalık kapasitesi."""

    allocation_type: str
    #: Tahsisli mekân sayısı.
    facility_count: int
    #: Haftalık kapasite (koltuk-saat veya istasyon-saat).
    weekly_capacity_unit_hours: Decimal
    #: Yoğun saatte aynı anda barındırılabilen kişi.
    peak_concurrent_capacity: int
    #: Tahsisli mekânların kodları — hangi mekânlar sayıldığı görünsün.
    facility_codes: List[str] = field(default_factory=list)
    #: Paylaşımlı kullanım var mı?
    has_shared_usage: bool = False
    notes: List[str] = field(default_factory=list)


def _capacity_unit(allocation_type: str) -> str:
    return "istasyon-saat" if allocation_type in LABORATORY_TYPES else "koltuk-saat"


def validate_facility_allocation_hours(db: Session, academic_year: str) -> Dict[int, int]:
    """Mekân başına toplam haftalık tahsisi denetler.

    Toplam, mekânın haftalık kullanılabilir saatini aşamaz.
    """
    rows = db.execute(
        select(
            ProgramFacilityAllocation.facility_id,
            ProgramFacilityAllocation.weekly_allocated_hours,
        ).where(ProgramFacilityAllocation.academic_year == academic_year)
    ).all()

    totals: Dict[int, int] = {}
    for facility_id, hours in rows:
        totals[facility_id] = totals.get(facility_id, 0) + int(hours)

    over = {fid: total for fid, total in totals.items() if total > WEEKLY_AVAILABLE_HOURS}
    if over:
        raise AllocationValidationError(
            f"{academic_year}: haftalık {WEEKLY_AVAILABLE_HOURS} saatlik sınırı "
            "aşan mekânlar: "
            + ", ".join(f"#{fid} → {total} saat" for fid, total in sorted(over.items())[:5])
        )
    return totals


def program_facility_capacity(
    db: Session, program_id: int, academic_year: str, allocation_types: tuple
) -> ProgramFacilityCapacity:
    """Bir programın belirli mekân türlerindeki haftalık kapasitesi.

    PAYLAŞIM DİKKATE ALINIR: bir laboratuvarı üç program paylaşıyorsa, o
    laboratuvarın tam kapasitesi hiçbirinin kapasitesi olarak sayılmaz.

    Formül:
        haftalık kapasite = Σ(mekân kapasitesi × programa tahsisli saat
                              × paylaşım payı)
    """
    rows = list(
        db.execute(
            select(ProgramFacilityAllocation, PhysicalFacility)
            .join(
                PhysicalFacility,
                ProgramFacilityAllocation.facility_id == PhysicalFacility.id,
            )
            .where(
                ProgramFacilityAllocation.program_id == program_id,
                ProgramFacilityAllocation.academic_year == academic_year,
                ProgramFacilityAllocation.allocation_type.in_(allocation_types),
                PhysicalFacility.is_active.is_(True),
            )
        ).all()
    )

    primary_type = allocation_types[0]
    if not rows:
        return ProgramFacilityCapacity(
            allocation_type=primary_type,
            facility_count=0,
            weekly_capacity_unit_hours=Decimal("0.00"),
            peak_concurrent_capacity=0,
            notes=[
                f"{academic_year} için bu programa tahsis edilmiş "
                f"{'laboratuvar' if primary_type in LABORATORY_TYPES else 'derslik'} "
                "kaydı bulunamadı."
            ],
        )

    total_unit_hours = Decimal("0")
    peak_capacity = Decimal("0")
    codes: List[str] = []
    shared = False

    for allocation, facility in rows:
        share = Decimal(str(allocation.shared_usage_percent)) / Decimal("100")
        if share < Decimal("1"):
            shared = True
        total_unit_hours += (
            Decimal(facility.capacity)
            * Decimal(allocation.weekly_allocated_hours)
            * share
        )
        # Yoğun saatte programa düşen koltuk: kapasite × paylaşım payı.
        peak_capacity += Decimal(facility.capacity) * share
        codes.append(facility.code)

    notes: List[str] = []
    if shared:
        notes.append(
            "Bazı mekânlar başka programlarla paylaşılıyor; kapasite yalnızca "
            "bu programa düşen pay kadar sayıldı."
        )

    return ProgramFacilityCapacity(
        allocation_type=primary_type,
        facility_count=len(rows),
        weekly_capacity_unit_hours=_q2(total_unit_hours),
        peak_concurrent_capacity=int(peak_capacity.to_integral_value()),
        facility_codes=sorted(codes),
        has_shared_usage=shared,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Talep formülleri
# ---------------------------------------------------------------------------


def weekly_classroom_demand_seat_hours(student_count: int) -> Decimal:
    """Haftalık derslik ihtiyacı (koltuk-saat).

    Formül: öğrenci sayısı × öğrenci başına haftalık yüz yüze ders saati
    """
    return _q2(Decimal(max(student_count, 0)) * WEEKLY_CLASSROOM_HOURS_PER_STUDENT)


def weekly_laboratory_demand_station_hours(student_count: int) -> Decimal:
    """Haftalık laboratuvar ihtiyacı (istasyon-saat)."""
    return _q2(Decimal(max(student_count, 0)) * WEEKLY_LABORATORY_HOURS_PER_STUDENT)


def peak_classroom_demand(student_count: int) -> int:
    """Yoğun saatte aynı anda derslikte olması beklenen öğrenci."""
    return int(
        (Decimal(max(student_count, 0)) * PEAK_CLASSROOM_CONCURRENCY).to_integral_value(
            rounding=ROUND_CEILING
        )
    )


def peak_laboratory_demand(student_count: int) -> int:
    """Yoğun saatte aynı anda laboratuvarda olması beklenen öğrenci."""
    return int(
        (
            Decimal(max(student_count, 0)) * PEAK_LABORATORY_CONCURRENCY
        ).to_integral_value(rounding=ROUND_CEILING)
    )


def utilization_percent(demand: Decimal, capacity: Decimal) -> Optional[Decimal]:
    """Kapasite kullanım oranı. Kapasite yoksa None — sıfır DEĞİL.

    Formül: talep / kapasite × 100. Talep kapasiteyi aşarsa %100'ün üzerine
    çıkar; bu KULLANIM oranıdır, karşılanma oranı değildir.
    """
    capacity_value = Decimal(str(capacity))
    if capacity_value <= 0:
        return None
    return _q2(Decimal(str(demand)) / capacity_value * Decimal("100"))


def coverage_percent(demand: Decimal, capacity: Decimal) -> Optional[Decimal]:
    """Talebin yüzde kaçı KARŞILANIYOR.

    Formül: min(kapasite, talep) / talep × 100

    Kullanım oranıyla karıştırılmamalı. 1.020 kapasite / 1.420 talep için
    kullanım %139,22, karşılanma ise %71,83'tür. "Talebin %139'u karşılanıyor"
    anlamsızdır; karşılanma oranı hiçbir zaman %100'ü aşamaz.
    """
    demand_value = Decimal(str(demand))
    capacity_value = Decimal(str(capacity))
    if demand_value <= 0:
        return None
    return _q2(min(capacity_value, demand_value) / demand_value * Decimal("100"))


def shortfall_percent(demand: Decimal, capacity: Decimal) -> Optional[Decimal]:
    """Talebin yüzde kaçı KARŞILANAMIYOR.

    Formül: 100 − karşılanma oranı. Kapasite talebi karşılıyorsa 0.
    """
    coverage = coverage_percent(demand, capacity)
    if coverage is None:
        return None
    return _q2(Decimal("100") - coverage)


# ---------------------------------------------------------------------------
# Birleşik program kapasite raporu
# ---------------------------------------------------------------------------


@dataclass
class ProgramCapacityReport:
    """Bir programın belirli bir öğrenci sayısındaki kaynak durumu."""

    academic_year: str
    program_id: int
    student_count: int

    staff: ProgramStaffCapacity
    required_fte: Decimal
    fte_gap: Decimal

    classroom: ProgramFacilityCapacity
    weekly_classroom_demand: Decimal
    classroom_utilization_percent: Optional[Decimal]
    classroom_coverage_percent: Optional[Decimal]
    classroom_shortfall_percent: Optional[Decimal]
    peak_classroom_demand: int
    peak_classroom_gap: int

    laboratory: ProgramFacilityCapacity
    weekly_laboratory_demand: Decimal
    laboratory_utilization_percent: Optional[Decimal]
    laboratory_coverage_percent: Optional[Decimal]
    laboratory_shortfall_percent: Optional[Decimal]
    peak_laboratory_demand: int
    peak_laboratory_gap: int

    notes: List[str] = field(default_factory=list)


def build_program_capacity_report(
    db: Session,
    program_id: int,
    academic_year: str,
    student_count: int,
) -> ProgramCapacityReport:
    """Bir programın kaynak kapasitesini verilen öğrenci sayısına göre üretir.

    Senaryo motoru bunu iki kez çağırır: mevcut ve senaryo öğrenci sayısıyla.
    Böylece "mevcut durum" ile "senaryo" aynı formülden geçer.
    """
    staff = program_staff_capacity(db, program_id, academic_year)
    required = required_staff_fte(student_count)

    classroom = program_facility_capacity(
        db, program_id, academic_year, ("classroom",)
    )
    laboratory = program_facility_capacity(
        db, program_id, academic_year, LABORATORY_TYPES
    )

    classroom_demand = weekly_classroom_demand_seat_hours(student_count)
    laboratory_demand = (
        weekly_laboratory_demand_station_hours(student_count)
        if laboratory.facility_count
        else Decimal("0.00")
    )

    notes: List[str] = list(staff.notes) + list(classroom.notes) + list(laboratory.notes)
    if not laboratory.facility_count:
        notes.append(
            "Bu program için laboratuvar tahsisi yok; laboratuvar ihtiyacı "
            "hesaplanmadı."
        )

    peak_class_demand = peak_classroom_demand(student_count)
    peak_lab_demand = (
        peak_laboratory_demand(student_count) if laboratory.facility_count else 0
    )

    return ProgramCapacityReport(
        academic_year=academic_year,
        program_id=program_id,
        student_count=student_count,
        staff=staff,
        required_fte=required,
        fte_gap=_q2(required - staff.fte),
        classroom=classroom,
        weekly_classroom_demand=classroom_demand,
        classroom_utilization_percent=utilization_percent(
            classroom_demand, classroom.weekly_capacity_unit_hours
        ),
        classroom_coverage_percent=coverage_percent(
            classroom_demand, classroom.weekly_capacity_unit_hours
        ),
        classroom_shortfall_percent=shortfall_percent(
            classroom_demand, classroom.weekly_capacity_unit_hours
        ),
        peak_classroom_demand=peak_class_demand,
        peak_classroom_gap=peak_class_demand - classroom.peak_concurrent_capacity,
        laboratory=laboratory,
        weekly_laboratory_demand=laboratory_demand,
        laboratory_utilization_percent=utilization_percent(
            laboratory_demand, laboratory.weekly_capacity_unit_hours
        ),
        laboratory_coverage_percent=coverage_percent(
            laboratory_demand, laboratory.weekly_capacity_unit_hours
        ),
        laboratory_shortfall_percent=shortfall_percent(
            laboratory_demand, laboratory.weekly_capacity_unit_hours
        ),
        peak_laboratory_demand=peak_lab_demand,
        peak_laboratory_gap=peak_lab_demand - laboratory.peak_concurrent_capacity,
        notes=notes,
    )


def university_total_fte(db: Session, academic_year: str) -> Decimal:
    """Bütün program tahsislerinin FTE toplamı.

    Bu değer, kurumun toplam akademik kapasitesini aşamaz: her kişinin
    tahsisi en fazla %100 olduğu için toplam FTE ≤ kişi sayısıdır.
    """
    rows = db.execute(
        select(ProgramAcademicStaffAllocation.allocation_percent).where(
            ProgramAcademicStaffAllocation.academic_year == academic_year
        )
    ).scalars()
    return _q2(sum((Decimal(str(row)) for row in rows), Decimal("0")) / Decimal("100"))


def allocated_staff_headcount(db: Session, academic_year: str) -> int:
    """Herhangi bir programa tahsis edilmiş TEKİL kişi sayısı."""
    rows = db.execute(
        select(ProgramAcademicStaffAllocation.academic_staff_id)
        .where(ProgramAcademicStaffAllocation.academic_year == academic_year)
        .distinct()
    ).scalars()
    return len(list(rows))
