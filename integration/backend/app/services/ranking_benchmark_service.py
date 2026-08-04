"""Karşılaştırma (benchmark) analizi servisi.

Kurumun gösterge değerlerini şu referanslarla karşılaştırır:
  - önceki akademik yıllar (kendi geçmişi)
  - Türkiye ulusal ortalaması
  - benzer üniversiteler
  - seçilmiş rakip üniversiteler

Yeterli karşılaştırma verisi yoksa sıralama/yüzdelik ÜRETİLMEZ; bunun yerine
cevapta açık bir uyarı döndürülür. Az veriden sıralama üretmek yanıltıcı olurdu.
"""

from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    BenchmarkInstitution,
    BenchmarkMetricValue,
    EvaluationDimension,
    EvaluationFramework,
    EvaluationIndicator,
    InstitutionalMetricValue,
)
from app.schemas.ranking_evaluations import (
    BenchmarkComparisonResponse,
    BenchmarkComparisonRow,
    BenchmarkScope,
    IndicatorDirection,
    MetricPeriod,
    PerformanceStatus,
)
from app.services.ranking_calculation_service import (
    MetricSnapshot,
    resolve_effective_value,
)
from app.services.ranking_readiness_service import ZERO, quantize

# Sıralama ve yüzdelik hesaplamak için gereken en az karşılaştırma kaydı sayısı.
MIN_BENCHMARK_COUNT_FOR_RANK: int = 3

# Bu yüzdelik farkın içinde kalan değerler "ortalamaya yakın" kabul edilir.
NEAR_THRESHOLD_PERCENT: Decimal = Decimal("5.00")

# institution_type -> hangi kapsamda değerlendirileceği.
SCOPE_INSTITUTION_TYPES: Dict[str, tuple] = {
    BenchmarkScope.NATIONAL.value: ("national-average",),
    BenchmarkScope.SIMILAR.value: ("similar",),
    BenchmarkScope.COMPETITORS.value: ("competitor",),
}


def _select_institutions(
    db: Session, scope: str
) -> List[BenchmarkInstitution]:
    """Kapsam parametresine göre karşılaştırılacak kurumları getirir."""
    statement = select(BenchmarkInstitution).where(BenchmarkInstitution.is_active.is_(True))

    if scope == BenchmarkScope.COMPETITORS.value:
        # Rakipler hem tip hem de is_competitor bayrağı üzerinden seçilebilir.
        statement = statement.where(BenchmarkInstitution.is_competitor.is_(True))
    elif scope in SCOPE_INSTITUTION_TYPES:
        statement = statement.where(
            BenchmarkInstitution.institution_type.in_(SCOPE_INSTITUTION_TYPES[scope])
        )

    return list(db.execute(statement.order_by(BenchmarkInstitution.name)).scalars().all())


def _indicator_effective_value(
    indicator: EvaluationIndicator, metric: Optional[InstitutionalMetricValue]
) -> Optional[Decimal]:
    """Kurumun kendi gösterge değerini hesaplama motoruyla aynı kuralla çözer."""
    if metric is None:
        return None
    value, _ = resolve_effective_value(indicator, MetricSnapshot.from_model(metric))
    return value


def _performance_status(
    university_value: Optional[Decimal],
    benchmark_average: Optional[Decimal],
    direction: str,
) -> PerformanceStatus:
    """Kurumun karşılaştırma ortalamasına göre konumunu belirler."""
    if university_value is None or benchmark_average is None or benchmark_average == ZERO:
        return PerformanceStatus.UNKNOWN

    difference_percent: Decimal = (
        (university_value - benchmark_average) / abs(benchmark_average) * Decimal("100")
    )

    # Küçük farklar "yakın" sayılır; her 0.1 puanlık sapmayı üstünlük/altlık
    # olarak raporlamak yöneticiyi yanıltırdı.
    if abs(difference_percent) <= NEAR_THRESHOLD_PERCENT:
        return PerformanceStatus.NEAR

    # Düşük değerin iyi olduğu göstergelerde yön ters çevrilir.
    if direction == IndicatorDirection.LOWER_IS_BETTER.value:
        return (
            PerformanceStatus.ABOVE if difference_percent < ZERO else PerformanceStatus.BELOW
        )
    return PerformanceStatus.ABOVE if difference_percent > ZERO else PerformanceStatus.BELOW


def build_comparison(
    db: Session,
    academic_year: str,
    period: str = MetricPeriod.ANNUAL.value,
    framework_code: Optional[str] = None,
    indicator_id: Optional[int] = None,
    scope: str = BenchmarkScope.ALL.value,
) -> BenchmarkComparisonResponse:
    """Gösterge bazında karşılaştırma raporu üretir."""
    warnings: List[str] = []

    # --- Karşılaştırılacak göstergeler ---
    indicator_statement = (
        select(EvaluationIndicator, EvaluationDimension, EvaluationFramework)
        .join(EvaluationDimension, EvaluationIndicator.dimension_id == EvaluationDimension.id)
        .join(EvaluationFramework, EvaluationDimension.framework_id == EvaluationFramework.id)
        .where(EvaluationIndicator.is_active.is_(True))
        .order_by(EvaluationIndicator.id)
    )
    if framework_code:
        indicator_statement = indicator_statement.where(
            EvaluationFramework.code == framework_code
        )
    if indicator_id is not None:
        indicator_statement = indicator_statement.where(EvaluationIndicator.id == indicator_id)

    indicator_rows = db.execute(indicator_statement).all()
    if not indicator_rows:
        warnings.append("Seçilen filtrelere uyan gösterge bulunamadı.")
        return BenchmarkComparisonResponse(
            framework_code=framework_code,
            academic_year=academic_year,
            period=MetricPeriod(period),
            scope=BenchmarkScope(scope),
            warnings=warnings,
        )

    indicator_ids: List[int] = [indicator.id for indicator, _, _ in indicator_rows]

    # --- Kurumun kendi değerleri (tek sorgu) ---
    own_metrics: Dict[int, InstitutionalMetricValue] = {
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

    # --- Önceki yıllar kapsamı: karşılaştırma kendi geçmişimizle yapılır ---
    if scope == BenchmarkScope.PREVIOUS_YEARS.value:
        return _build_previous_year_comparison(
            db, indicator_rows, own_metrics, academic_year, period, framework_code, warnings
        )

    # --- Karşılaştırma kurumları ---
    institutions: List[BenchmarkInstitution] = _select_institutions(db, scope)
    if not institutions:
        warnings.append(
            f"'{scope}' kapsamında tanımlı karşılaştırma kurumu bulunmuyor; "
            "karşılaştırma yapılamadı."
        )

    institution_ids: List[int] = [institution.id for institution in institutions]

    # --- Karşılaştırma değerleri (tek sorgu) ---
    benchmark_values: Dict[int, List[Decimal]] = {}
    if institution_ids:
        for row in db.execute(
            select(BenchmarkMetricValue)
            .where(BenchmarkMetricValue.indicator_id.in_(indicator_ids))
            .where(BenchmarkMetricValue.benchmark_institution_id.in_(institution_ids))
            .where(BenchmarkMetricValue.academic_year == academic_year)
            .where(BenchmarkMetricValue.period == period)
        ).scalars().all():
            benchmark_values.setdefault(row.indicator_id, []).append(row.value)

    rows: List[BenchmarkComparisonRow] = []
    above = near = below = 0

    for indicator, dimension, _framework in indicator_rows:
        university_value: Optional[Decimal] = _indicator_effective_value(
            indicator, own_metrics.get(indicator.id)
        )
        values: List[Decimal] = benchmark_values.get(indicator.id, [])

        row = BenchmarkComparisonRow(
            indicator_id=indicator.id,
            indicator_code=indicator.code,
            indicator_name=indicator.name,
            unit=indicator.unit,
            dimension_name=dimension.name,
            direction=IndicatorDirection(indicator.direction),
            university_value=university_value,
            benchmark_count=len(values),
        )

        if not values:
            row.warning = "Bu gösterge için karşılaştırma verisi bulunmuyor."
        else:
            average: Decimal = quantize(sum(values, ZERO) / Decimal(len(values)))
            row.benchmark_average = average

            if university_value is not None:
                row.difference = quantize(university_value - average)
                if average != ZERO:
                    row.percentage_difference = quantize(
                        (university_value - average) / abs(average) * Decimal("100")
                    )

            row.performance_status = _performance_status(
                university_value, average, indicator.direction
            )

            # Sıralama yalnızca yeterli veri varsa hesaplanır.
            if len(values) >= MIN_BENCHMARK_COUNT_FOR_RANK and university_value is not None:
                all_values: List[Decimal] = values + [university_value]
                reverse: bool = indicator.direction != IndicatorDirection.LOWER_IS_BETTER.value
                ordered = sorted(all_values, reverse=reverse)
                row.rank = ordered.index(university_value) + 1
                row.percentile = quantize(
                    Decimal(len(all_values) - row.rank) / Decimal(len(all_values)) * Decimal("100")
                )
            elif university_value is None:
                row.warning = "Kurumun kendi verisi girilmediği için karşılaştırma yapılamadı."
            else:
                row.warning = (
                    f"Sıralama için yeterli karşılaştırma verisi yok "
                    f"(en az {MIN_BENCHMARK_COUNT_FOR_RANK} kurum gerekir, "
                    f"{len(values)} kurum bulundu)."
                )

        if row.performance_status == PerformanceStatus.ABOVE:
            above += 1
        elif row.performance_status == PerformanceStatus.NEAR:
            near += 1
        elif row.performance_status == PerformanceStatus.BELOW:
            below += 1

        rows.append(row)

    unknown_count: int = sum(
        1 for row in rows if row.performance_status == PerformanceStatus.UNKNOWN
    )
    if unknown_count:
        warnings.append(
            f"{unknown_count} gösterge için yeterli veri bulunmadığından karşılaştırma yapılamadı."
        )

    return BenchmarkComparisonResponse(
        framework_code=framework_code,
        academic_year=academic_year,
        period=MetricPeriod(period),
        scope=BenchmarkScope(scope),
        compared_institution_count=len(institutions),
        compared_institutions=[institution.name for institution in institutions],
        rows=rows,
        above_count=above,
        near_count=near,
        below_count=below,
        warnings=warnings,
    )


def _build_previous_year_comparison(
    db: Session,
    indicator_rows: List[tuple],
    own_metrics: Dict[int, InstitutionalMetricValue],
    academic_year: str,
    period: str,
    framework_code: Optional[str],
    warnings: List[str],
) -> BenchmarkComparisonResponse:
    """Kurumu kendi geçmiş yıllarıyla karşılaştırır."""
    indicator_ids: List[int] = [indicator.id for indicator, _, _ in indicator_rows]

    # Seçilen yıl HARİÇ tüm geçmiş kayıtlar tek sorguda alınır.
    previous_values: Dict[int, List[Decimal]] = {}
    indicator_by_id = {indicator.id: indicator for indicator, _, _ in indicator_rows}

    for metric in (
        db.execute(
            select(InstitutionalMetricValue)
            .where(InstitutionalMetricValue.indicator_id.in_(indicator_ids))
            .where(InstitutionalMetricValue.academic_year < academic_year)
            .where(InstitutionalMetricValue.period == period)
        )
        .scalars()
        .all()
    ):
        indicator = indicator_by_id.get(metric.indicator_id)
        if indicator is None:
            continue
        value = _indicator_effective_value(indicator, metric)
        if value is not None:
            previous_values.setdefault(metric.indicator_id, []).append(value)

    rows: List[BenchmarkComparisonRow] = []
    above = near = below = 0

    for indicator, dimension, _framework in indicator_rows:
        university_value = _indicator_effective_value(indicator, own_metrics.get(indicator.id))
        history: List[Decimal] = previous_values.get(indicator.id, [])

        row = BenchmarkComparisonRow(
            indicator_id=indicator.id,
            indicator_code=indicator.code,
            indicator_name=indicator.name,
            unit=indicator.unit,
            dimension_name=dimension.name,
            direction=IndicatorDirection(indicator.direction),
            university_value=university_value,
            benchmark_count=len(history),
        )

        if not history:
            row.warning = "Karşılaştırılacak geçmiş yıl verisi bulunmuyor."
        else:
            average = quantize(sum(history, ZERO) / Decimal(len(history)))
            row.benchmark_average = average
            if university_value is not None:
                row.difference = quantize(university_value - average)
                if average != ZERO:
                    row.percentage_difference = quantize(
                        (university_value - average) / abs(average) * Decimal("100")
                    )
            row.performance_status = _performance_status(
                university_value, average, indicator.direction
            )

        if row.performance_status == PerformanceStatus.ABOVE:
            above += 1
        elif row.performance_status == PerformanceStatus.NEAR:
            near += 1
        elif row.performance_status == PerformanceStatus.BELOW:
            below += 1

        rows.append(row)

    warnings.append(
        "Karşılaştırma kurumun kendi geçmiş yıl ortalamasıyla yapılmıştır."
    )

    return BenchmarkComparisonResponse(
        framework_code=framework_code,
        academic_year=academic_year,
        period=MetricPeriod(period),
        scope=BenchmarkScope.PREVIOUS_YEARS,
        compared_institution_count=0,
        compared_institutions=["Kendi geçmiş yıllarımız"],
        rows=rows,
        above_count=above,
        near_count=near,
        below_count=below,
        warnings=warnings,
    )
