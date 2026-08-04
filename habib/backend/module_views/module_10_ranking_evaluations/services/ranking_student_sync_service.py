"""Modül 1 ve 2 verisinden otomatik gösterge değeri üretme servisi.

Öğrenci tarafındaki veriler (toplam öğrenci, uluslararası oran, mezuniyet oranı,
program doluluğu vb.) zaten sistemde bulunduğu için THE/QS/YÖK göstergelerine
elle girilmesine gerek yoktur. Bu servis o verileri okuyup ilgili göstergelere
yazar.

ÖNEMLİ: Sistemde akademik personel modeli bulunmadığı için personel sayısı,
yayın, atıf, araştırma geliri gibi veriler UYDURULMAZ. Bu göstergeler
InstitutionalMetricValue üzerinden elle veya içe aktarımla doldurulur.

ÖNCELİK KURALI: Elle girilmiş (manual) ve içe aktarılmış (imported) veriler
otomatik senkronizasyonla EZİLMEZ. Doğrulanmış insan verisi otomatik veriden
önceliklidir. Bu davranış overwrite_manual=true ile bilinçli olarak değiştirilebilir.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import (
    AcademicProgram,
    EvaluationDimension,
    EvaluationFramework,
    EvaluationIndicator,
    InstitutionalMetricValue,
    ProgramEnrollmentSnapshot,
    Student,
)
from app.schemas.ranking_evaluations import (
    DataStatus,
    MetricOrigin,
    MetricPeriod,
    StudentMetricSyncResponse,
    SyncedMetricItem,
)
from app.services.ranking_readiness_service import ZERO, quantize

# Doktora ve lisans programlarını ayırt etmek için kullanılan anahtar kelimeler.
DOCTORAL_KEYWORDS: tuple = ("doctor", "phd", "doktora")
BACHELOR_KEYWORDS: tuple = ("bachelor", "lisans", "undergraduate")


@dataclass
class ComputedMetric:
    """Modül 1/2'den hesaplanan tek bir gösterge değeri."""

    value: Optional[Decimal] = None
    numerator: Optional[Decimal] = None
    denominator: Optional[Decimal] = None
    data_status: str = DataStatus.AVAILABLE.value
    note: Optional[str] = None

    def display(self) -> str:
        """Cevapta gösterilecek okunabilir metni üretir."""
        if self.value is None:
            return f"(hesaplanamadı: {self.note or 'veri yok'})"
        if self.numerator is not None and self.denominator is not None:
            return f"{self.value} ({self.numerator}/{self.denominator})"
        return str(self.value)


def _ratio_metric(
    numerator: Decimal, denominator: Decimal, as_percentage: bool = True
) -> ComputedMetric:
    """Pay/payda üzerinden oran veya yüzde metriği üretir."""
    # Payda sıfırsa oran hesaplanamaz; uydurma değer üretmek yerine
    # veriyi "missing" işaretleyip nedenini not ediyoruz.
    if denominator == ZERO:
        return ComputedMetric(
            data_status=DataStatus.MISSING.value,
            note="payda sıfır olduğu için oran hesaplanamadı",
        )

    raw: Decimal = numerator / denominator
    if as_percentage:
        raw = raw * Decimal("100")

    return ComputedMetric(
        value=quantize(raw),
        numerator=quantize(numerator),
        denominator=quantize(denominator),
    )


def compute_student_metrics(db: Session) -> Dict[str, ComputedMetric]:
    """Modül 1 ve 2 verisinden tüm otomatik gösterge değerlerini hesaplar.

    Tüm sayımlar tek bir toplu sorguda yapılır; öğrenci kayıtları Python
    belleğine çekilmez.
    """
    # --- Öğrenci sayımları (tek sorgu) ---
    row = db.execute(
        select(
            func.count(Student.id).label("total"),
            func.coalesce(
                func.sum(
                    case((Student.current_status.in_(["active", "newly-enrolled"]), 1), else_=0)
                ),
                0,
            ).label("active"),
            func.coalesce(
                func.sum(case((Student.current_status == "newly-enrolled", 1), else_=0)), 0
            ).label("newly_enrolled"),
            func.coalesce(
                func.sum(case((Student.current_status == "graduated", 1), else_=0)), 0
            ).label("graduated"),
            func.coalesce(
                func.sum(case((Student.current_status == "dropped-out", 1), else_=0)), 0
            ).label("dropped_out"),
            func.coalesce(
                func.sum(case((Student.current_status == "non-renewed", 1), else_=0)), 0
            ).label("non_renewed"),
            func.coalesce(
                func.sum(case((Student.preparatory_school.is_(True), 1), else_=0)), 0
            ).label("preparatory"),
            func.coalesce(
                func.sum(case((Student.is_international.is_(True), 1), else_=0)), 0
            ).label("international"),
            func.coalesce(
                func.sum(case((Student.scholarship_rate_percent > 0, 1), else_=0)), 0
            ).label("scholarship"),
            func.avg(
                case(
                    (
                        Student.actual_graduation_year.isnot(None),
                        Student.actual_graduation_year - Student.enrollment_year,
                    ),
                    else_=None,
                )
            ).label("avg_graduation_duration"),
        )
        .select_from(Student)
        .where(Student.is_active.is_(True))
    ).one()

    total = Decimal(int(row.total or 0))
    active = Decimal(int(row.active or 0))
    graduated = Decimal(int(row.graduated or 0))
    dropped = Decimal(int(row.dropped_out or 0))
    non_renewed = Decimal(int(row.non_renewed or 0))

    metrics: Dict[str, ComputedMetric] = {}

    # --- Ham sayımlar ---
    metrics["total_student_count"] = ComputedMetric(value=quantize(total))
    metrics["active_student_count"] = ComputedMetric(value=quantize(active))
    metrics["newly_enrolled_student_count"] = ComputedMetric(
        value=quantize(Decimal(int(row.newly_enrolled or 0)))
    )
    metrics["graduate_count"] = ComputedMetric(value=quantize(graduated))
    metrics["preparatory_student_count"] = ComputedMetric(
        value=quantize(Decimal(int(row.preparatory or 0)))
    )
    metrics["international_student_count"] = ComputedMetric(
        value=quantize(Decimal(int(row.international or 0)))
    )

    # --- Oranlar ---
    metrics["international_student_ratio"] = _ratio_metric(
        Decimal(int(row.international or 0)), total
    )
    metrics["scholarship_student_ratio"] = _ratio_metric(
        Decimal(int(row.scholarship or 0)), total
    )
    # Mezuniyet oranı paydası: mezun + aktif + bırakan (Modül 2 ile aynı formül).
    metrics["graduation_rate"] = _ratio_metric(graduated, graduated + active + dropped)
    metrics["attrition_rate"] = _ratio_metric(dropped, total)
    metrics["non_renewal_rate"] = _ratio_metric(non_renewed, total)

    # --- Ortalama mezuniyet süresi ---
    if row.avg_graduation_duration is None:
        metrics["average_graduation_duration"] = ComputedMetric(
            data_status=DataStatus.MISSING.value,
            note="henüz mezun öğrenci kaydı yok",
        )
    else:
        metrics["average_graduation_duration"] = ComputedMetric(
            value=quantize(Decimal(str(row.avg_graduation_duration)))
        )

    # --- Program doluluk oranı (en güncel snapshot yılı üzerinden) ---
    latest_year: Optional[str] = db.execute(
        select(func.max(ProgramEnrollmentSnapshot.academic_year))
    ).scalar()

    if latest_year:
        quota_row = db.execute(
            select(
                func.coalesce(func.sum(ProgramEnrollmentSnapshot.quota), 0),
                func.coalesce(func.sum(ProgramEnrollmentSnapshot.enrolled_student_count), 0),
            ).where(ProgramEnrollmentSnapshot.academic_year == latest_year)
        ).one()
        metrics["program_occupancy_rate"] = _ratio_metric(
            Decimal(int(quota_row[1])), Decimal(int(quota_row[0]))
        )
    else:
        metrics["program_occupancy_rate"] = ComputedMetric(
            data_status=DataStatus.MISSING.value,
            note="program snapshot verisi bulunamadı",
        )

    # --- Doktora / lisans kırılımı ---
    # Programın degree_level alanına bakarak öğrenci sayısı sayılır.
    level_rows = db.execute(
        select(
            func.lower(AcademicProgram.degree_level).label("level"),
            func.count(Student.id).label("student_count"),
        )
        .select_from(AcademicProgram)
        .join(Student, Student.academic_program_id == AcademicProgram.id)
        .where(Student.is_active.is_(True))
        .group_by(func.lower(AcademicProgram.degree_level))
    ).all()

    doctoral_total = Decimal(0)
    bachelor_total = Decimal(0)
    for level, student_count in level_rows:
        level_text: str = str(level or "")
        if any(keyword in level_text for keyword in DOCTORAL_KEYWORDS):
            doctoral_total += Decimal(int(student_count))
        elif any(keyword in level_text for keyword in BACHELOR_KEYWORDS):
            bachelor_total += Decimal(int(student_count))

    metrics["doctoral_student_count"] = ComputedMetric(value=quantize(doctoral_total))

    if bachelor_total == ZERO:
        metrics["doctoral_to_bachelor_ratio"] = ComputedMetric(
            data_status=DataStatus.MISSING.value,
            note="lisans programı öğrencisi bulunamadı",
        )
    else:
        metrics["doctoral_to_bachelor_ratio"] = _ratio_metric(
            doctoral_total, bachelor_total, as_percentage=True
        )

    # --- Bölüm/program bazlı trend göstergesi ---
    # Aktif program sayısı, akademik yapının genişliğini gösterir ve
    # bazı YÖK göstergelerinde payda olarak kullanılır.
    program_count: int = int(
        db.execute(
            select(func.count(AcademicProgram.id)).where(AcademicProgram.is_active.is_(True))
        ).scalar()
        or 0
    )
    metrics["active_program_count"] = ComputedMetric(value=quantize(Decimal(program_count)))

    if program_count == 0:
        metrics["students_per_program"] = ComputedMetric(
            data_status=DataStatus.MISSING.value, note="aktif program yok"
        )
    else:
        metrics["students_per_program"] = _ratio_metric(
            total, Decimal(program_count), as_percentage=False
        )

    return metrics


def sync_student_metrics(
    db: Session,
    academic_year: str,
    period: str = MetricPeriod.ANNUAL.value,
    overwrite_manual: bool = False,
) -> StudentMetricSyncResponse:
    """Otomatik göstergeleri hesaplayıp InstitutionalMetricValue tablosuna yazar."""
    computed: Dict[str, ComputedMetric] = compute_student_metrics(db)

    # auto_source_key tanımlı tüm aktif göstergeler tek sorguda alınır.
    indicator_rows = db.execute(
        select(EvaluationIndicator, EvaluationFramework.code)
        .join(EvaluationDimension, EvaluationIndicator.dimension_id == EvaluationDimension.id)
        .join(EvaluationFramework, EvaluationDimension.framework_id == EvaluationFramework.id)
        .where(EvaluationIndicator.auto_source_key.isnot(None))
        .where(EvaluationIndicator.is_active.is_(True))
        .order_by(EvaluationIndicator.id)
    ).all()

    indicator_ids: List[int] = [indicator.id for indicator, _ in indicator_rows]
    existing: Dict[int, InstitutionalMetricValue] = {}
    if indicator_ids:
        existing = {
            metric.indicator_id: metric
            for metric in db.execute(
                select(InstitutionalMetricValue)
                .where(InstitutionalMetricValue.indicator_id.in_(indicator_ids))
                .where(InstitutionalMetricValue.academic_year == academic_year)
                .where(InstitutionalMetricValue.period == period)
            )
            .scalars()
            .all()
        }

    items: List[SyncedMetricItem] = []
    created_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    matched_keys: set = set()

    for indicator, framework_code in indicator_rows:
        source_key: str = indicator.auto_source_key
        metric_data: Optional[ComputedMetric] = computed.get(source_key)

        if metric_data is None:
            # Gösterge tanımında olan ama servis tarafından hesaplanmayan anahtar.
            skipped_count += 1
            items.append(
                SyncedMetricItem(
                    indicator_id=indicator.id,
                    indicator_code=indicator.code,
                    framework_code=framework_code,
                    auto_source_key=source_key,
                    action="skipped",
                    reason=(
                        f"'{source_key}' anahtarı için otomatik hesaplama tanımlı değil; "
                        "bu gösterge elle veya içe aktarımla doldurulmalıdır."
                    ),
                )
            )
            continue

        matched_keys.add(source_key)
        current: Optional[InstitutionalMetricValue] = existing.get(indicator.id)

        # Öncelik kuralı: elle girilmiş / içe aktarılmış veri korunur.
        if (
            current is not None
            and current.origin != MetricOrigin.AUTOMATIC.value
            and not overwrite_manual
        ):
            skipped_count += 1
            items.append(
                SyncedMetricItem(
                    indicator_id=indicator.id,
                    indicator_code=indicator.code,
                    framework_code=framework_code,
                    auto_source_key=source_key,
                    action="skipped",
                    previous_value=current.value,
                    new_value=metric_data.value,
                    reason=(
                        f"Kayıt '{current.origin}' kaynaklı olduğu için korundu; "
                        "otomatik veri elle girilmiş veriyi ezmez."
                    ),
                )
            )
            continue

        if current is None:
            current = InstitutionalMetricValue(
                indicator_id=indicator.id,
                academic_year=academic_year,
                period=period,
            )
            db.add(current)
            action = "created"
            created_count += 1
            previous_value = None
        else:
            action = "updated"
            updated_count += 1
            previous_value = current.value

        current.value = metric_data.value
        current.numerator = metric_data.numerator
        current.denominator = metric_data.denominator
        current.data_status = metric_data.data_status
        current.origin = MetricOrigin.AUTOMATIC.value
        current.source_reference = "Modül 1/2 otomatik senkronizasyonu"
        current.notes = metric_data.note
        current.measured_at = datetime.now()

        items.append(
            SyncedMetricItem(
                indicator_id=indicator.id,
                indicator_code=indicator.code,
                framework_code=framework_code,
                auto_source_key=source_key,
                action=action,
                previous_value=previous_value,
                new_value=metric_data.value,
                reason=metric_data.note,
            )
        )

    # Hesaplanan ama hiçbir göstergeye bağlanmamış anahtarlar bildirilir;
    # böylece gösterge tanımı eksikse fark edilir.
    unmatched: List[str] = sorted(set(computed.keys()) - matched_keys)

    return StudentMetricSyncResponse(
        academic_year=academic_year,
        period=MetricPeriod(period),
        created_count=created_count,
        updated_count=updated_count,
        skipped_count=skipped_count,
        unmatched_source_keys=unmatched,
        computed_metrics={key: value.display() for key, value in computed.items()},
        items=items,
        message=(
            f"{created_count} gösterge oluşturuldu, {updated_count} gösterge güncellendi, "
            f"{skipped_count} gösterge atlandı."
        ),
    )
