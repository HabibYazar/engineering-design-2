"""THE / QS / YÖK değerlendirme hesaplama motoru.

Bütün skor formülleri bu dosyadadır. Router hesap yapmaz; yalnızca buradaki
fonksiyonları çağırır.

UYARI: Üretilen skorlar gerçek THE/QS/YÖK sıralaması DEĞİLDİR. Kurumun kendi
verisine dayanan iç performans izleme, veri hazırlık ve uyum göstergeleridir.

Hesaplama zinciri:
    ham veri  ->  etkin değer  ->  0-100 performans skoru
              ->  boyut skoru  ->  çerçeve skoru  ->  uyum skoru  ->  risk
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, DivisionByZero, InvalidOperation
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    DimensionAssessment,
    EvaluationDimension,
    EvaluationFramework,
    EvaluationIndicator,
    FrameworkAssessment,
    InstitutionalMetricValue,
)
from app.schemas.ranking_evaluations import (
    AssessmentDetailResponse,
    CalculationType,
    DataStatus,
    DimensionAssessmentResponse,
    EvaluationRiskLevel,
    IndicatorAssessmentDetail,
    IndicatorDirection,
    MetricOrigin,
    MetricPeriod,
    MissingDataItem,
    MissingDataSummary,
)
from app.services.ranking_readiness_service import (
    HUNDRED,
    ZERO,
    clamp_score,
    compliance_score,
    calculate_risk_level,
    is_usable,
    quantize,
    readiness_factor,
    weighted_average,
)

# Ağırlık toplamının 100 kabul edilmesi için izin verilen sapma.
# Ondalık ağırlıklarda (33.33 × 3 = 99.99) küçük farklar normaldir.
WEIGHT_TOLERANCE: Decimal = Decimal("0.50")

# En güçlü / en zayıf gösterge listelerinde kaç kayıt döneceği.
TOP_INDICATOR_LIMIT: int = 5

# Pay/payda ile hesaplanan değer ile elle girilen value arasındaki
# kabul edilebilir fark. Bunun üzerindeki sapmada hesaplanan değer esas alınır
# ve duruma not düşülür.
VALUE_MISMATCH_TOLERANCE: Decimal = Decimal("0.01")


@dataclass
class MetricSnapshot:
    """Bir göstergenin tek bir dönemdeki ham verisi.

    Veritabanı satırından da, what-if senaryosunda üretilen geçici değerden de
    oluşturulabilir. Böylece hesaplama motoru "veri nereden geldi" sorusuyla
    ilgilenmeden aynı kodu çalıştırır.
    """

    value: Optional[Decimal] = None
    numerator: Optional[Decimal] = None
    denominator: Optional[Decimal] = None
    data_status: str = DataStatus.MISSING.value
    origin: Optional[str] = None

    @classmethod
    def from_model(cls, metric: InstitutionalMetricValue) -> "MetricSnapshot":
        """Veritabanı kaydından anlık görüntü üretir."""
        return cls(
            value=metric.value,
            numerator=metric.numerator,
            denominator=metric.denominator,
            data_status=metric.data_status,
            origin=metric.origin,
        )


# ===========================================================================
# 1) Etkin değer hesaplama
# ===========================================================================


def resolve_effective_value(
    indicator: EvaluationIndicator,
    snapshot: Optional[MetricSnapshot],
) -> Tuple[Optional[Decimal], List[str]]:
    """Göstergenin calculation_type'ına göre etkin değerini hesaplar."""
    notes: List[str] = []

    if snapshot is None:
        return None, notes

    calculation_type: str = indicator.calculation_type

    # percentage ve ratio türlerinde pay/payda varsa hesaplanan değer esastır.
    if calculation_type in (CalculationType.PERCENTAGE.value, CalculationType.RATIO.value):
        if snapshot.numerator is not None and snapshot.denominator is not None:
            if snapshot.denominator == ZERO:
                notes.append(
                    f"'{indicator.code}': payda sıfır olduğu için oran hesaplanamadı."
                )
                return None, notes
            try:
                computed: Decimal = snapshot.numerator / snapshot.denominator
            except (DivisionByZero, InvalidOperation):
                notes.append(f"'{indicator.code}': oran hesaplanamadı (geçersiz sayı).")
                return None, notes

            if calculation_type == CalculationType.PERCENTAGE.value:
                computed = computed * HUNDRED

            computed = quantize(computed)

            # Elle girilen value ile hesaplanan değer çelişiyorsa hesaplanan
            # değeri esas alıp durumu açıkça not ediyoruz. Sessizce birini
            # seçmek, raporu okuyanı yanıltırdı.
            if (
                snapshot.value is not None
                and abs(quantize(snapshot.value) - computed) > VALUE_MISMATCH_TOLERANCE
            ):
                notes.append(
                    f"'{indicator.code}': girilen değer ({quantize(snapshot.value)}) ile "
                    f"pay/payda üzerinden hesaplanan değer ({computed}) uyuşmuyor; "
                    "hesaplanan değer esas alındı."
                )
            return computed, notes

        # Pay/payda yoksa elle girilen değere düşülür.
        if snapshot.value is not None:
            notes.append(
                f"'{indicator.code}': pay/payda girilmediği için doğrudan value kullanıldı."
            )
            return quantize(snapshot.value), notes
        return None, notes

    # boolean: sıfırdan farklı her değer "var" kabul edilir.
    if calculation_type == CalculationType.BOOLEAN.value:
        if snapshot.value is None:
            return None, notes
        return (HUNDRED if snapshot.value != ZERO else ZERO), notes

    # raw / manual / score: doğrudan girilen değer.
    if snapshot.value is not None:
        return quantize(snapshot.value), notes

    # score/raw türünde value yoksa ama pay/payda varsa oran olarak değerlendiriyoruz.
    if snapshot.numerator is not None and snapshot.denominator not in (None, ZERO):
        notes.append(
            f"'{indicator.code}': value girilmediği için pay/payda oranı kullanıldı."
        )
        return quantize(snapshot.numerator / snapshot.denominator), notes

    return None, notes


# ===========================================================================
# 2) 0-100 normalizasyon
# ===========================================================================


def _resolve_bounds(
    indicator: EvaluationIndicator,
) -> Tuple[Optional[Decimal], Optional[Decimal], Optional[Decimal], List[str]]:
    """Normalizasyon sınırlarını, eksik olanlar için makul varsayılanlarla döndürür."""
    notes: List[str] = []
    minimum = indicator.minimum_value
    target = indicator.target_value
    maximum = indicator.maximum_value

    direction: str = indicator.direction

    if direction == IndicatorDirection.HIGHER_IS_BETTER.value:
        # Alt sınır verilmemişse 0 kabul edilir (çoğu gösterge negatif olamaz).
        if minimum is None:
            minimum = ZERO
            notes.append(
                f"'{indicator.code}': minimum_value tanımlı değil, 0 kabul edildi."
            )
        # Hedef yoksa üst sınır hedef gibi kullanılır.
        if target is None and maximum is not None:
            target = maximum
            notes.append(
                f"'{indicator.code}': target_value tanımlı değil, maximum_value hedef kabul edildi."
            )

    elif direction == IndicatorDirection.LOWER_IS_BETTER.value:
        # Hedef yoksa alt sınır (veya 0) hedef kabul edilir.
        if target is None:
            target = minimum if minimum is not None else ZERO
            notes.append(
                f"'{indicator.code}': target_value tanımlı değil, "
                f"{target} değeri hedef kabul edildi."
            )

    return minimum, target, maximum, notes


def normalize_score(
    indicator: EvaluationIndicator,
    value: Optional[Decimal],
) -> Tuple[Optional[Decimal], List[str]]:
    """Gösterge değerini yönüne göre 0-100 aralığına normalize eder."""
    if value is None:
        return None, []

    minimum, target, maximum, notes = _resolve_bounds(indicator)
    direction: str = indicator.direction

    # --- Yüksek daha iyi ---
    if direction == IndicatorDirection.HIGHER_IS_BETTER.value:
        if target is None:
            # Sınır yoksa açıklanabilir fallback: değeri 0-100 aralığına kırp.
            notes.append(
                f"'{indicator.code}': hedef sınır tanımlı olmadığı için ham değer "
                "0-100 aralığına kırpılarak skor olarak kullanıldı."
            )
            return clamp_score(value), notes

        if target == minimum:
            # Aralık sıfırsa doğrusal ölçekleme yapılamaz; eşik testi uygulanır.
            notes.append(
                f"'{indicator.code}': minimum ve target eşit olduğu için eşik "
                "karşılaştırması uygulandı."
            )
            return (HUNDRED if value >= target else ZERO), notes

        if value >= target:
            return HUNDRED, notes
        if value <= minimum:
            return ZERO, notes
        return clamp_score((value - minimum) / (target - minimum) * HUNDRED), notes

    # --- Düşük daha iyi ---
    if direction == IndicatorDirection.LOWER_IS_BETTER.value:
        if maximum is None:
            notes.append(
                f"'{indicator.code}': maximum_value tanımlı olmadığı için hedefe göre "
                "ikili değerlendirme yapıldı (hedefin altı 100, üstü 0)."
            )
            return (HUNDRED if value <= (target or ZERO) else ZERO), notes

        if maximum == target:
            notes.append(
                f"'{indicator.code}': target ve maximum eşit olduğu için eşik "
                "karşılaştırması uygulandı."
            )
            return (HUNDRED if value <= target else ZERO), notes

        if value <= target:
            return HUNDRED, notes
        if value >= maximum:
            return ZERO, notes
        return clamp_score((maximum - value) / (maximum - target) * HUNDRED), notes

    # --- Hedefe yakınlık en iyi ---
    # target_is_best: hedefte 100, sınırlara yaklaştıkça 0'a düşer.
    if value == target:
        return HUNDRED, notes

    if value < target:
        if minimum is None:
            notes.append(
                f"'{indicator.code}': minimum_value tanımlı olmadığı için hedefin altındaki "
                "değerler oransal olarak değerlendirildi."
            )
            if target == ZERO:
                return ZERO, notes
            return clamp_score(value / target * HUNDRED), notes
        if target == minimum:
            return HUNDRED, notes
        if value <= minimum:
            return ZERO, notes
        return clamp_score((value - minimum) / (target - minimum) * HUNDRED), notes

    # value > target
    if maximum is None:
        notes.append(
            f"'{indicator.code}': maximum_value tanımlı olmadığı için hedefin üstündeki "
            "değerler oransal olarak değerlendirildi."
        )
        if value == ZERO:
            return ZERO, notes
        return clamp_score(target / value * HUNDRED), notes
    if maximum == target:
        return HUNDRED, notes
    if value >= maximum:
        return ZERO, notes
    return clamp_score((maximum - value) / (maximum - target) * HUNDRED), notes


# ===========================================================================
# 3) Gösterge değerlendirmesi
# ===========================================================================


def evaluate_indicator(
    indicator: EvaluationIndicator,
    snapshot: Optional[MetricSnapshot],
) -> IndicatorAssessmentDetail:
    """Tek bir göstergeyi değerlendirip detay nesnesi üretir."""
    notes: List[str] = []
    status: str = snapshot.data_status if snapshot else DataStatus.MISSING.value

    effective_value: Optional[Decimal] = None
    score: Optional[Decimal] = None

    # missing / invalid veriden skor üretilmez; hesaplama boşuna çalışmasın.
    if snapshot is not None and is_usable(status):
        effective_value, value_notes = resolve_effective_value(indicator, snapshot)
        notes.extend(value_notes)

        if effective_value is None:
            # Durum "available" işaretli ama sayısal veri çıkmadıysa geçersiz sayılır.
            notes.append(
                f"'{indicator.code}': veri durumu '{status}' olmasına rağmen sayısal "
                "değer üretilemedi, gösterge geçersiz kabul edildi."
            )
            status = DataStatus.INVALID.value
        else:
            score, score_notes = normalize_score(indicator, effective_value)
            notes.extend(score_notes)

    return IndicatorAssessmentDetail(
        indicator_id=indicator.id,
        indicator_code=indicator.code,
        indicator_name=indicator.name,
        unit=indicator.unit,
        weight=indicator.weight,
        direction=IndicatorDirection(indicator.direction),
        calculation_type=CalculationType(indicator.calculation_type),
        data_status=DataStatus(status),
        origin=MetricOrigin(snapshot.origin) if snapshot and snapshot.origin else None,
        raw_value=snapshot.value if snapshot else None,
        effective_value=effective_value,
        performance_score=score,
        readiness_factor=readiness_factor(status),
        target_value=indicator.target_value,
        data_source=indicator.data_source,
        calculation_notes=notes,
    )


# ===========================================================================
# 4) Boyut ve çerçeve değerlendirmesi
# ===========================================================================


def evaluate_dimension(
    dimension: EvaluationDimension,
    indicators: List[EvaluationIndicator],
    snapshots: Dict[int, MetricSnapshot],
) -> DimensionAssessmentResponse:
    """Bir boyutun performans ve hazırlık skorlarını hesaplar."""
    details: List[IndicatorAssessmentDetail] = [
        evaluate_indicator(indicator, snapshots.get(indicator.id))
        for indicator in indicators
    ]

    # --- Performans ---
    # Yalnızca skor üretilebilen göstergeler ağırlıklı ortalamaya girer.
    # Eksik veriyi 0 saymak, veri toplayamayan bir kurumu "kötü performanslı"
    # göstererek raporu yanıltırdı; eksiklik readiness skorunda ölçülür.
    scored_pairs: List[tuple] = [
        (detail.performance_score, detail.weight)
        for detail in details
        if detail.performance_score is not None and detail.weight > ZERO
    ]
    performance: Decimal = weighted_average(scored_pairs)

    # --- Hazırlık ---
    # required_for_readiness işaretli göstergeler dikkate alınır.
    required_indicators = [
        (detail, indicator)
        for detail, indicator in zip(details, indicators)
        if indicator.required_for_readiness
    ]
    if not required_indicators:
        # Hiç zorunlu gösterge yoksa tüm göstergeler üzerinden hesaplanır.
        required_indicators = list(zip(details, indicators))

    readiness_pairs: List[tuple] = [
        (detail.readiness_factor * HUNDRED, indicator.weight)
        for detail, indicator in required_indicators
        if indicator.weight > ZERO
    ]
    readiness: Decimal = weighted_average(readiness_pairs)

    missing_count: int = sum(
        1
        for detail in details
        if detail.data_status in (DataStatus.MISSING, DataStatus.INVALID)
    )
    available_count: int = sum(
        1 for detail in details if detail.data_status == DataStatus.AVAILABLE
    )

    weighted: Decimal = quantize(performance * dimension.weight / HUNDRED)
    dimension_compliance: Decimal = compliance_score(performance, readiness)

    return DimensionAssessmentResponse(
        dimension_id=dimension.id,
        dimension_code=dimension.code,
        dimension_name=dimension.name,
        dimension_weight=dimension.weight,
        readiness_score=readiness,
        performance_score=performance,
        weighted_score=weighted,
        missing_indicator_count=missing_count,
        available_indicator_count=available_count,
        total_indicator_count=len(details),
        risk_level=calculate_risk_level(dimension_compliance, readiness),
        indicators=details,
    )


def load_framework_structure(
    db: Session, framework_id: int
) -> List[EvaluationDimension]:
    """Bir çerçevenin aktif boyut ve göstergelerini tek sorguda yükler."""
    # selectinload ile göstergeler tek ek sorguda gelir; her boyut için ayrı
    # sorgu atmak (N+1) böylece önlenir.
    statement = (
        select(EvaluationDimension)
        .where(EvaluationDimension.framework_id == framework_id)
        .where(EvaluationDimension.is_active.is_(True))
        .options(selectinload(EvaluationDimension.indicators))
        .order_by(EvaluationDimension.display_order, EvaluationDimension.id)
    )
    return list(db.execute(statement).scalars().all())


def load_metric_snapshots(
    db: Session,
    indicator_ids: List[int],
    academic_year: str,
    period: str,
) -> Dict[int, MetricSnapshot]:
    """İlgili göstergelerin dönem verilerini tek sorguda getirir."""
    if not indicator_ids:
        return {}

    statement = (
        select(InstitutionalMetricValue)
        .where(InstitutionalMetricValue.indicator_id.in_(indicator_ids))
        .where(InstitutionalMetricValue.academic_year == academic_year)
        .where(InstitutionalMetricValue.period == period)
    )
    return {
        metric.indicator_id: MetricSnapshot.from_model(metric)
        for metric in db.execute(statement).scalars().all()
    }


def build_missing_data_summary(
    framework: EvaluationFramework,
    dimensions: List[EvaluationDimension],
    dimension_results: List[DimensionAssessmentResponse],
) -> MissingDataSummary:
    """Eksik, kısmi ve geçersiz verileri readiness kaybıyla birlikte raporlar."""
    summary = MissingDataSummary()

    total_dimension_weight: Decimal = sum(
        (dimension.weight for dimension in dimensions), ZERO
    )

    dimension_by_id: Dict[int, EvaluationDimension] = {
        dimension.id: dimension for dimension in dimensions
    }

    for result in dimension_results:
        dimension = dimension_by_id[result.dimension_id]

        # Boyut içindeki zorunlu gösterge ağırlıklarının toplamı, kaybın
        # payda tarafını oluşturur.
        required_weight: Decimal = sum(
            (
                indicator.weight
                for indicator in dimension.indicators
                if indicator.required_for_readiness and indicator.is_active
            ),
            ZERO,
        )
        if required_weight == ZERO:
            required_weight = sum(
                (indicator.weight for indicator in dimension.indicators if indicator.is_active),
                ZERO,
            )

        indicator_by_id = {indicator.id: indicator for indicator in dimension.indicators}

        for detail in result.indicators:
            indicator = indicator_by_id.get(detail.indicator_id)
            if indicator is None or not indicator.required_for_readiness:
                continue

            status: DataStatus = detail.data_status
            if status == DataStatus.AVAILABLE:
                continue

            if status == DataStatus.MISSING:
                summary.missing_count += 1
                message = f"'{indicator.name}' göstergesi için veri girilmemiş."
            elif status == DataStatus.PARTIAL:
                summary.partial_count += 1
                message = f"'{indicator.name}' göstergesi için veri kısmi olarak girilmiş."
            elif status == DataStatus.INVALID:
                summary.invalid_count += 1
                message = f"'{indicator.name}' göstergesi için girilen veri geçersiz."
            else:  # estimated
                summary.estimated_count += 1
                message = f"'{indicator.name}' göstergesi tahmini veriyle dolduruldu."

            # Kayıp = boyut ağırlık payı × gösterge ağırlık payı × (1 - hazırlık katsayısı) × 100
            dimension_share: Decimal = (
                dimension.weight / total_dimension_weight
                if total_dimension_weight > ZERO
                else ZERO
            )
            indicator_share: Decimal = (
                indicator.weight / required_weight if required_weight > ZERO else ZERO
            )
            loss: Decimal = quantize(
                dimension_share
                * indicator_share
                * (Decimal("1.00") - detail.readiness_factor)
                * HUNDRED
            )
            summary.total_readiness_loss = quantize(summary.total_readiness_loss + loss)

            summary.items.append(
                MissingDataItem(
                    indicator_id=indicator.id,
                    indicator_code=indicator.code,
                    indicator_name=indicator.name,
                    dimension_code=dimension.code,
                    dimension_name=dimension.name,
                    framework_code=framework.code,
                    data_status=status,
                    expected_data_source=indicator.data_source,
                    estimated_readiness_loss=loss,
                    message=message,
                )
            )

    # En yüksek kayıp en üstte görünsün.
    summary.items.sort(key=lambda item: item.estimated_readiness_loss, reverse=True)
    return summary


def evaluate_framework(
    db: Session,
    framework: EvaluationFramework,
    academic_year: str,
    period: str = MetricPeriod.ANNUAL.value,
    snapshot_overrides: Optional[Dict[int, MetricSnapshot]] = None,
) -> AssessmentDetailResponse:
    """Bir çerçevenin tüm skorlarını hesaplar ve detaylı rapor üretir.

    snapshot_overrides verilirse ilgili göstergelerin verisi bu değerlerle
    değiştirilir. What-if etki analizi bu parametreyi kullanır; veritabanına
    hiçbir yazma yapılmaz.
    """
    dimensions: List[EvaluationDimension] = load_framework_structure(db, framework.id)

    active_indicators: Dict[int, List[EvaluationIndicator]] = {
        dimension.id: [ind for ind in dimension.indicators if ind.is_active]
        for dimension in dimensions
    }
    all_indicator_ids: List[int] = [
        indicator.id
        for indicators in active_indicators.values()
        for indicator in indicators
    ]

    snapshots: Dict[int, MetricSnapshot] = load_metric_snapshots(
        db, all_indicator_ids, academic_year, period
    )
    if snapshot_overrides:
        snapshots = {**snapshots, **snapshot_overrides}

    dimension_results: List[DimensionAssessmentResponse] = [
        evaluate_dimension(dimension, active_indicators[dimension.id], snapshots)
        for dimension in dimensions
    ]

    # --- Çerçeve skorları ---
    # Performans: yalnızca skor üretebilmiş boyutlar ağırlıklı ortalamaya girer.
    performance_pairs: List[tuple] = [
        (result.performance_score, result.dimension_weight)
        for result in dimension_results
        if result.total_indicator_count > 0
        and result.dimension_weight > ZERO
        and any(detail.performance_score is not None for detail in result.indicators)
    ]
    performance: Decimal = weighted_average(performance_pairs)

    readiness_pairs: List[tuple] = [
        (result.readiness_score, result.dimension_weight)
        for result in dimension_results
        if result.dimension_weight > ZERO and result.total_indicator_count > 0
    ]
    readiness: Decimal = weighted_average(readiness_pairs)

    compliance: Decimal = compliance_score(performance, readiness)
    risk: EvaluationRiskLevel = calculate_risk_level(compliance, readiness)

    # --- Sayaçlar ---
    all_details: List[IndicatorAssessmentDetail] = [
        detail for result in dimension_results for detail in result.indicators
    ]
    counts: Dict[DataStatus, int] = {status: 0 for status in DataStatus}
    for detail in all_details:
        counts[detail.data_status] += 1

    # --- Notlar ---
    notes: List[str] = []
    total_weight: Decimal = sum((dimension.weight for dimension in dimensions), ZERO)
    if dimensions and abs(total_weight - HUNDRED) > WEIGHT_TOLERANCE:
        notes.append(
            f"Uyarı: '{framework.code}' çerçevesinin boyut ağırlıkları toplamı "
            f"{total_weight} (100 olmalı). Skorlar ağırlık toplamına göre normalize edildi."
        )
    if not dimensions:
        notes.append(
            f"'{framework.code}' çerçevesinde tanımlı aktif boyut yok; skorlar 0 döndü."
        )
    for detail in all_details:
        notes.extend(detail.calculation_notes)

    # --- En güçlü / en zayıf göstergeler ---
    scored_details = [d for d in all_details if d.performance_score is not None]
    strongest = sorted(scored_details, key=lambda d: d.performance_score, reverse=True)[
        :TOP_INDICATOR_LIMIT
    ]
    weakest = sorted(scored_details, key=lambda d: d.performance_score)[:TOP_INDICATOR_LIMIT]

    missing_summary: MissingDataSummary = build_missing_data_summary(
        framework, dimensions, dimension_results
    )

    return AssessmentDetailResponse(
        assessment_id=None,
        framework_id=framework.id,
        framework=framework.code,
        framework_name=framework.name,
        methodology_year=framework.methodology_year,
        academic_year=academic_year,
        period=MetricPeriod(period),
        readiness_score=readiness,
        performance_score=performance,
        compliance_score=compliance,
        risk_level=risk,
        total_indicator_count=len(all_details),
        available_indicator_count=counts[DataStatus.AVAILABLE],
        partial_indicator_count=counts[DataStatus.PARTIAL],
        missing_indicator_count=counts[DataStatus.MISSING],
        invalid_indicator_count=counts[DataStatus.INVALID],
        estimated_indicator_count=counts[DataStatus.ESTIMATED],
        dimensions=dimension_results,
        missing_data=missing_summary,
        strongest_indicators=strongest,
        weakest_indicators=weakest,
        recommendations=[],
        calculation_notes=notes,
        calculated_at=datetime.now(),
        persisted=False,
    )


# ===========================================================================
# 5) Kalıcı kayıt
# ===========================================================================


def persist_assessment(
    db: Session,
    framework: EvaluationFramework,
    detail: AssessmentDetailResponse,
) -> FrameworkAssessment:
    """Hesaplanan değerlendirmeyi kaydeder; aynı yıl/dönem varsa günceller."""
    # Aynı çerçeve + yıl + dönem için tek kayıt tutuluyor; yeniden hesaplama
    # eski kaydı güncelliyor. Böylece geçmiş yıllar korunurken güncel yıl
    # her hesaplamada tazeleniyor.
    statement = (
        select(FrameworkAssessment)
        .where(FrameworkAssessment.framework_id == framework.id)
        .where(FrameworkAssessment.academic_year == detail.academic_year)
        .where(FrameworkAssessment.period == detail.period.value)
    )
    assessment: Optional[FrameworkAssessment] = db.execute(statement).scalars().first()

    notes_text: Optional[str] = "\n".join(detail.calculation_notes) or None

    if assessment is None:
        assessment = FrameworkAssessment(
            framework_id=framework.id,
            academic_year=detail.academic_year,
            period=detail.period.value,
        )
        db.add(assessment)

    assessment.readiness_score = detail.readiness_score
    assessment.performance_score = detail.performance_score
    assessment.compliance_score = detail.compliance_score
    assessment.missing_indicator_count = detail.missing_indicator_count
    assessment.partial_indicator_count = detail.partial_indicator_count
    assessment.available_indicator_count = detail.available_indicator_count
    assessment.risk_level = detail.risk_level.value
    assessment.calculation_notes = notes_text
    assessment.calculated_at = detail.calculated_at

    # id üretilsin ki boyut kayıtları bağlanabilsin.
    db.flush()

    # Boyut kırılımları: mevcut kayıtlar güncellenir, yenileri eklenir.
    existing_rows = {
        row.dimension_id: row
        for row in db.execute(
            select(DimensionAssessment).where(
                DimensionAssessment.framework_assessment_id == assessment.id
            )
        )
        .scalars()
        .all()
    }

    for result in detail.dimensions:
        row = existing_rows.get(result.dimension_id)
        if row is None:
            row = DimensionAssessment(
                framework_assessment_id=assessment.id,
                dimension_id=result.dimension_id,
            )
            db.add(row)
        row.readiness_score = result.readiness_score
        row.performance_score = result.performance_score
        row.weighted_score = result.weighted_score
        row.missing_indicator_count = result.missing_indicator_count
        row.risk_level = result.risk_level.value

    return assessment


# ===========================================================================
# 6) Ağırlık doğrulama yardımcıları
# ===========================================================================


def validate_dimension_weights(
    db: Session, framework_id: int
) -> Tuple[Decimal, bool]:
    """Bir çerçevenin boyut ağırlık toplamını ve dengeli olup olmadığını döndürür."""
    statement = (
        select(EvaluationDimension.weight)
        .where(EvaluationDimension.framework_id == framework_id)
        .where(EvaluationDimension.is_active.is_(True))
    )
    total: Decimal = sum(
        (Decimal(str(weight)) for weight in db.execute(statement).scalars().all()), ZERO
    )
    return quantize(total), abs(total - HUNDRED) <= WEIGHT_TOLERANCE


def validate_indicator_weights(db: Session, dimension_id: int) -> Tuple[Decimal, bool]:
    """Bir boyutun gösterge ağırlık toplamını ve dengeli olup olmadığını döndürür."""
    statement = (
        select(EvaluationIndicator.weight)
        .where(EvaluationIndicator.dimension_id == dimension_id)
        .where(EvaluationIndicator.is_active.is_(True))
    )
    total: Decimal = sum(
        (Decimal(str(weight)) for weight in db.execute(statement).scalars().all()), ZERO
    )
    return quantize(total), abs(total - HUNDRED) <= WEIGHT_TOLERANCE
