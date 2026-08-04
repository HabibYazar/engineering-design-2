"""What-if senaryolarının değerlendirme skorlarına etkisini hesaplayan servis.

Mevcut Modül 9 senaryo motoruna DOKUNULMAZ. Bu servis bağımsız çalışır ve
yalnızca Modül 10 göstergelerine etkiyi hesaplar.

ÖNEMLİ: Bu analiz gerçek THE/QS/YÖK sıralamasındaki değişimi TAHMİN ETMEZ.
Sadece sistemde tanımlı iç değerlendirme skorlarına etkiyi gösterir.

Veritabanına hiçbir yazma yapılmaz: mevcut gösterge değerleri okunur, bellekte
kopyalanıp senaryo değişkenleriyle güncellenir ve hesaplama motoru bu geçici
anlık görüntülerle yeniden çalıştırılır.
"""

from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    EvaluationDimension,
    EvaluationFramework,
    EvaluationIndicator,
    InstitutionalMetricValue,
)
from app.schemas.ranking_evaluations import (
    AssessmentDetailResponse,
    DataStatus,
    FrameworkImpact,
    ImpactedDimension,
    ImpactedIndicator,
    ImpactPreviewRequest,
    ImpactPreviewResponse,
    MetricPeriod,
)
from app.services.ranking_calculation_service import (
    MetricSnapshot,
    evaluate_framework,
)
from app.services.ranking_readiness_service import ZERO, quantize

# İstekteki alan adları ile göstergelerdeki impact değişken adları birebir aynıdır.
IMPACT_VARIABLE_FIELDS: tuple = (
    "citation_count",
    "publication_count",
    "academic_staff_count",
    "international_student_count",
    "international_academic_staff_count",
    "doctoral_graduate_count",
    "research_income",
    "industry_income",
    "patent_count",
    "total_student_count",
)


def _collect_deltas(request: ImpactPreviewRequest) -> Dict[str, Decimal]:
    """İstekten sıfırdan farklı değişkenleri toplar."""
    # Sıfır olan değişkenler senaryoyu etkilemediği için raporu kalabalıklaştırmasın.
    deltas: Dict[str, Decimal] = {}
    for field_name in IMPACT_VARIABLE_FIELDS:
        value: Decimal = getattr(request, field_name)
        if value != ZERO:
            deltas[field_name] = Decimal(str(value))
    return deltas


def _build_overrides(
    db: Session,
    indicators: List[EvaluationIndicator],
    academic_year: str,
    period: str,
    deltas: Dict[str, Decimal],
) -> Dict[int, MetricSnapshot]:
    """Senaryo değişkenlerine göre geçici gösterge anlık görüntüleri üretir."""
    if not deltas or not indicators:
        return {}

    indicator_ids: List[int] = [indicator.id for indicator in indicators]
    current_metrics: Dict[int, InstitutionalMetricValue] = {
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

    overrides: Dict[int, MetricSnapshot] = {}

    for indicator in indicators:
        numerator_variable: Optional[str] = indicator.impact_numerator_variable
        denominator_variable: Optional[str] = indicator.impact_denominator_variable

        numerator_delta: Decimal = deltas.get(numerator_variable or "", ZERO)
        denominator_delta: Decimal = deltas.get(denominator_variable or "", ZERO)

        # Bu gösterge senaryodan etkilenmiyorsa dokunulmaz.
        if numerator_delta == ZERO and denominator_delta == ZERO:
            continue

        metric: Optional[InstitutionalMetricValue] = current_metrics.get(indicator.id)
        if metric is None or metric.numerator is None or metric.denominator is None:
            # Pay/payda verisi olmadan senaryo etkisi hesaplanamaz; gösterge atlanır.
            # Uydurma bir başlangıç değeri üretmek sonucu yanıltırdı.
            continue

        new_numerator: Decimal = metric.numerator + numerator_delta
        new_denominator: Decimal = metric.denominator + denominator_delta

        # Payda sıfır veya negatife düşerse senaryo geçersizdir; gösterge atlanır.
        if new_denominator <= ZERO:
            continue
        if new_numerator < ZERO:
            new_numerator = ZERO

        overrides[indicator.id] = MetricSnapshot(
            value=None,  # değer pay/paydadan yeniden hesaplansın
            numerator=quantize(new_numerator),
            denominator=quantize(new_denominator),
            data_status=metric.data_status,
            origin=metric.origin,
        )

    return overrides


def _applied_variables(
    indicator: EvaluationIndicator, deltas: Dict[str, Decimal]
) -> List[str]:
    """Bir göstergeye hangi senaryo değişkenlerinin uygulandığını listeler."""
    applied: List[str] = []
    if indicator.impact_numerator_variable in deltas:
        applied.append(indicator.impact_numerator_variable)
    if indicator.impact_denominator_variable in deltas:
        applied.append(indicator.impact_denominator_variable)
    return applied


def _indicator_lookup(assessment: AssessmentDetailResponse) -> Dict[int, tuple]:
    """Değerlendirme sonucundaki göstergeleri id'ye göre indeksler."""
    lookup: Dict[int, tuple] = {}
    for dimension in assessment.dimensions:
        for detail in dimension.indicators:
            lookup[detail.indicator_id] = (detail, dimension)
    return lookup


def build_impact_preview(
    db: Session, request: ImpactPreviewRequest
) -> ImpactPreviewResponse:
    """Senaryo değişkenlerinin çerçeve skorlarına etkisini hesaplar."""
    deltas: Dict[str, Decimal] = _collect_deltas(request)

    # --- Değerlendirilecek çerçeveler ---
    framework_statement = select(EvaluationFramework).where(
        EvaluationFramework.is_active.is_(True)
    )
    if request.framework_code is not None:
        framework_statement = framework_statement.where(
            EvaluationFramework.code == request.framework_code.value
        )
    frameworks: List[EvaluationFramework] = list(
        db.execute(framework_statement.order_by(EvaluationFramework.id)).scalars().all()
    )

    period: str = request.period.value
    impacts: List[FrameworkImpact] = []
    total_impacted: int = 0
    recommendations: List[str] = []

    for framework in frameworks:
        # Senaryodan etkilenebilecek göstergeler (impact değişkeni tanımlı olanlar).
        indicators: List[EvaluationIndicator] = list(
            db.execute(
                select(EvaluationIndicator)
                .join(
                    EvaluationDimension,
                    EvaluationIndicator.dimension_id == EvaluationDimension.id,
                )
                .where(EvaluationDimension.framework_id == framework.id)
                .where(EvaluationIndicator.is_active.is_(True))
            )
            .scalars()
            .all()
        )

        overrides: Dict[int, MetricSnapshot] = _build_overrides(
            db, indicators, request.academic_year, period, deltas
        )

        # Önce mevcut durum, sonra senaryo sonrası durum hesaplanır.
        # Her ikisi de salt okuma; veritabanına yazma yok.
        before: AssessmentDetailResponse = evaluate_framework(
            db, framework, request.academic_year, period
        )
        after: AssessmentDetailResponse = evaluate_framework(
            db, framework, request.academic_year, period, snapshot_overrides=overrides
        )

        before_lookup = _indicator_lookup(before)
        after_lookup = _indicator_lookup(after)

        indicator_by_id: Dict[int, EvaluationIndicator] = {
            indicator.id: indicator for indicator in indicators
        }

        impacted_indicators: List[ImpactedIndicator] = []
        for indicator_id in overrides:
            before_detail, _ = before_lookup.get(indicator_id, (None, None))
            after_detail, after_dimension = after_lookup.get(indicator_id, (None, None))
            if before_detail is None or after_detail is None:
                continue

            indicator = indicator_by_id[indicator_id]

            value_change: Optional[Decimal] = None
            if (
                before_detail.effective_value is not None
                and after_detail.effective_value is not None
            ):
                value_change = quantize(
                    after_detail.effective_value - before_detail.effective_value
                )

            score_change: Optional[Decimal] = None
            if (
                before_detail.performance_score is not None
                and after_detail.performance_score is not None
            ):
                score_change = quantize(
                    after_detail.performance_score - before_detail.performance_score
                )

            impacted_indicators.append(
                ImpactedIndicator(
                    indicator_id=indicator_id,
                    indicator_code=after_detail.indicator_code,
                    indicator_name=after_detail.indicator_name,
                    framework_code=framework.code,
                    dimension_name=after_dimension.dimension_name if after_dimension else "",
                    unit=after_detail.unit,
                    before_value=before_detail.effective_value,
                    after_value=after_detail.effective_value,
                    value_change=value_change,
                    before_score=before_detail.performance_score,
                    after_score=after_detail.performance_score,
                    score_change=score_change,
                    applied_variables=_applied_variables(indicator, deltas),
                )
            )

        total_impacted += len(impacted_indicators)

        # --- Etkilenen boyutlar ---
        before_dimensions = {d.dimension_id: d for d in before.dimensions}
        impacted_dimensions: List[ImpactedDimension] = []
        for after_dimension in after.dimensions:
            before_dimension = before_dimensions.get(after_dimension.dimension_id)
            if before_dimension is None:
                continue
            change: Decimal = quantize(
                after_dimension.performance_score - before_dimension.performance_score
            )
            if change == ZERO:
                continue
            impacted_dimensions.append(
                ImpactedDimension(
                    dimension_id=after_dimension.dimension_id,
                    dimension_code=after_dimension.dimension_code,
                    dimension_name=after_dimension.dimension_name,
                    before_score=before_dimension.performance_score,
                    after_score=after_dimension.performance_score,
                    score_change=change,
                )
            )

        impacts.append(
            FrameworkImpact(
                framework_id=framework.id,
                framework_code=framework.code,
                framework_name=framework.name,
                before_performance=before.performance_score,
                after_performance=after.performance_score,
                performance_change=quantize(
                    after.performance_score - before.performance_score
                ),
                before_readiness=before.readiness_score,
                after_readiness=after.readiness_score,
                readiness_change=quantize(after.readiness_score - before.readiness_score),
                before_compliance=before.compliance_score,
                after_compliance=after.compliance_score,
                compliance_change=quantize(
                    after.compliance_score - before.compliance_score
                ),
                before_risk=before.risk_level,
                after_risk=after.risk_level,
                risk_changed=before.risk_level != after.risk_level,
                impacted_dimensions=impacted_dimensions,
                impacted_indicators=impacted_indicators,
            )
        )

    # --- Türkçe öneriler ---
    recommendations = _build_impact_recommendations(deltas, impacts, total_impacted)

    return ImpactPreviewResponse(
        academic_year=request.academic_year,
        period=MetricPeriod(period),
        persisted=False,
        applied_changes={key: str(value) for key, value in deltas.items()},
        frameworks=impacts,
        total_impacted_indicator_count=total_impacted,
        recommendations=recommendations,
    )


def _build_impact_recommendations(
    deltas: Dict[str, Decimal],
    impacts: List[FrameworkImpact],
    total_impacted: int,
) -> List[str]:
    """Senaryo sonucuna göre Türkçe yorum ve öneriler üretir."""
    recommendations: List[str] = []

    if not deltas:
        recommendations.append(
            "Hiçbir senaryo değişkeni girilmedi; skorlarda değişim beklenmiyor."
        )
        return recommendations

    if total_impacted == 0:
        recommendations.append(
            "Girilen değişkenler hiçbir göstergeyi etkilemedi. Bunun nedeni ilgili "
            "göstergelerde pay/payda verisinin bulunmaması olabilir; önce eksik veriler "
            "tamamlanmalıdır."
        )
        return recommendations

    for impact in impacts:
        if impact.performance_change > ZERO:
            recommendations.append(
                f"{impact.framework_code}: Senaryo performans skorunu "
                f"{impact.before_performance} seviyesinden {impact.after_performance} "
                f"seviyesine, yani {impact.performance_change} puan yükseltiyor. "
                f"En çok etkilenen boyut sayısı: {len(impact.impacted_dimensions)}."
            )
        elif impact.performance_change < ZERO:
            recommendations.append(
                f"{impact.framework_code}: Senaryo performans skorunu "
                f"{abs(impact.performance_change)} puan düşürüyor. Değişkenler gözden "
                "geçirilmelidir."
            )
        else:
            recommendations.append(
                f"{impact.framework_code}: Senaryonun performans skoruna net etkisi yok."
            )

        if impact.risk_changed:
            recommendations.append(
                f"{impact.framework_code}: Risk seviyesi '{impact.before_risk.value}' "
                f"seviyesinden '{impact.after_risk.value}' seviyesine değişiyor."
            )

        # En yüksek katkıyı sağlayan gösterge öne çıkarılır.
        gainers = [
            item
            for item in impact.impacted_indicators
            if item.score_change is not None and item.score_change > ZERO
        ]
        if gainers:
            best = max(gainers, key=lambda item: item.score_change)
            recommendations.append(
                f"{impact.framework_code}: En yüksek kazanç '{best.indicator_name}' "
                f"göstergesinde ({best.score_change} puan). Bu alandaki yatırım "
                "önceliklendirilebilir."
            )

    if impacts and all(impact.readiness_change == ZERO for impact in impacts):
        recommendations.append(
            "Senaryo veri hazırlık (readiness) skorunu değiştirmiyor; eksik veriler "
            "senaryodan bağımsız olarak tamamlanmalıdır."
        )

    return recommendations
