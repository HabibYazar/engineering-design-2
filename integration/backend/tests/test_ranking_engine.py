"""Hesaplama motoru birim testleri (Modül 10).

resolve_effective_value, normalize_score, readiness ve risk fonksiyonları saf
fonksiyonlar olduğu için veritabanı olmadan test edilir.
"""

from decimal import Decimal

import pytest

from app.schemas.ranking_evaluations import (
    DataStatus,
    EvaluationRiskLevel,
    IndicatorDirection,
)
from app.services.ranking_calculation_service import (
    MetricSnapshot,
    evaluate_indicator,
    normalize_score,
    resolve_effective_value,
)
from app.services.ranking_readiness_service import (
    DATA_STATUS_READINESS_FACTOR,
    calculate_risk_level,
    clamp_score,
    compliance_score,
    is_usable,
    readiness_factor,
    weighted_average,
)
from tests.conftest import build_indicator


# ===========================================================================
# 1) Etkin değer hesaplama (calculation_type)
# ===========================================================================


def test_raw_calculation_returns_value_directly():
    """raw tipinde girilen değer doğrudan kullanılır."""
    indicator = build_indicator(calculation_type="raw")
    value, notes = resolve_effective_value(
        indicator, MetricSnapshot(value=Decimal("42.5"), data_status="available")
    )
    assert value == Decimal("42.50")
    assert notes == []


def test_manual_calculation_returns_value_directly():
    """manual tipinde girilen değer doğrudan kullanılır."""
    indicator = build_indicator(calculation_type="manual")
    value, _ = resolve_effective_value(
        indicator, MetricSnapshot(value=Decimal("77"), data_status="available")
    )
    assert value == Decimal("77.00")


def test_score_calculation_returns_value_directly():
    """score tipinde 0-100 arası değer doğrudan kullanılır."""
    indicator = build_indicator(calculation_type="score")
    value, _ = resolve_effective_value(
        indicator, MetricSnapshot(value=Decimal("63.25"), data_status="available")
    )
    assert value == Decimal("63.25")


def test_percentage_calculation_uses_numerator_and_denominator():
    """percentage tipinde pay/payda × 100 hesaplanır."""
    indicator = build_indicator(calculation_type="percentage")
    value, _ = resolve_effective_value(
        indicator,
        MetricSnapshot(numerator=Decimal("20"), denominator=Decimal("120")),
    )
    assert value == Decimal("16.67")


def test_ratio_calculation_uses_numerator_and_denominator():
    """ratio tipinde pay/payda hesaplanır (yüzdeye çevrilmez)."""
    indicator = build_indicator(calculation_type="ratio")
    value, _ = resolve_effective_value(
        indicator,
        MetricSnapshot(numerator=Decimal("120"), denominator=Decimal("6")),
    )
    assert value == Decimal("20.00")


def test_boolean_true_maps_to_hundred():
    """boolean tipinde sıfırdan farklı değer 100 puana çevrilir."""
    indicator = build_indicator(calculation_type="boolean")
    value, _ = resolve_effective_value(indicator, MetricSnapshot(value=Decimal("1")))
    assert value == Decimal("100.00")


def test_boolean_false_maps_to_zero():
    """boolean tipinde sıfır değeri 0 puana çevrilir."""
    indicator = build_indicator(calculation_type="boolean")
    value, _ = resolve_effective_value(indicator, MetricSnapshot(value=Decimal("0")))
    assert value == Decimal("0")


def test_zero_denominator_returns_none_with_note():
    """Payda sıfırsa değer üretilmez ve açıklayıcı not eklenir."""
    indicator = build_indicator(calculation_type="ratio")
    value, notes = resolve_effective_value(
        indicator, MetricSnapshot(numerator=Decimal("10"), denominator=Decimal("0"))
    )
    assert value is None
    assert any("payda sıfır" in note for note in notes)


def test_percentage_falls_back_to_value_when_parts_missing():
    """Pay/payda yoksa girilen value kullanılır ve not düşülür."""
    indicator = build_indicator(calculation_type="percentage")
    value, notes = resolve_effective_value(
        indicator, MetricSnapshot(value=Decimal("18.4"))
    )
    assert value == Decimal("18.40")
    assert any("doğrudan value" in note for note in notes)


def test_computed_value_overrides_conflicting_manual_value():
    """Girilen değer ile hesaplanan değer çelişirse hesaplanan esas alınır."""
    indicator = build_indicator(calculation_type="percentage")
    value, notes = resolve_effective_value(
        indicator,
        MetricSnapshot(
            value=Decimal("99"), numerator=Decimal("20"), denominator=Decimal("120")
        ),
    )
    assert value == Decimal("16.67")
    assert any("uyuşmuyor" in note for note in notes)


def test_matching_manual_value_produces_no_conflict_note():
    """Girilen değer hesaplananla uyumluysa uyarı üretilmez."""
    indicator = build_indicator(calculation_type="percentage")
    _, notes = resolve_effective_value(
        indicator,
        MetricSnapshot(
            value=Decimal("16.67"), numerator=Decimal("20"), denominator=Decimal("120")
        ),
    )
    assert not any("uyuşmuyor" in note for note in notes)


def test_missing_snapshot_returns_none():
    """Hiç veri yoksa değer None döner."""
    indicator = build_indicator(calculation_type="raw")
    value, notes = resolve_effective_value(indicator, None)
    assert value is None and notes == []


def test_raw_falls_back_to_ratio_when_value_absent():
    """raw tipinde value yoksa pay/payda oranı kullanılır."""
    indicator = build_indicator(calculation_type="raw")
    value, notes = resolve_effective_value(
        indicator, MetricSnapshot(numerator=Decimal("50"), denominator=Decimal("4"))
    )
    assert value == Decimal("12.50")
    assert any("pay/payda oranı" in note for note in notes)


# ===========================================================================
# 2) Normalizasyon: higher_is_better
# ===========================================================================


@pytest.mark.parametrize(
    "value,expected",
    [
        (Decimal("0"), Decimal("0.00")),  # minimum -> 0
        (Decimal("5"), Decimal("25.00")),  # çeyrek yol
        (Decimal("10"), Decimal("50.00")),  # yarı yol
        (Decimal("15"), Decimal("75.00")),  # dörtte üç
        (Decimal("20"), Decimal("100.00")),  # hedef -> 100
        (Decimal("35"), Decimal("100.00")),  # hedefin üstü de 100
        (Decimal("-5"), Decimal("0.00")),  # minimumun altı 0
    ],
)
def test_higher_is_better_linear_scaling(value, expected):
    """higher_is_better yönünde minimum-target arası doğrusal ölçeklenir."""
    indicator = build_indicator(
        direction="higher_is_better",
        minimum_value=Decimal("0"),
        target_value=Decimal("20"),
        maximum_value=Decimal("60"),
    )
    score, _ = normalize_score(indicator, value)
    assert score == expected


def test_higher_is_better_uses_maximum_when_target_missing():
    """Hedef yoksa maximum hedef olarak kullanılır ve not düşülür."""
    indicator = build_indicator(
        direction="higher_is_better", minimum_value=Decimal("0"), maximum_value=Decimal("50")
    )
    score, notes = normalize_score(indicator, Decimal("25"))
    assert score == Decimal("50.00")
    assert any("maximum_value hedef kabul edildi" in note for note in notes)


def test_higher_is_better_clamps_when_no_bounds():
    """Hiç sınır yoksa değer 0-100 aralığına kırpılır ve not düşülür."""
    indicator = build_indicator(direction="higher_is_better")
    score, notes = normalize_score(indicator, Decimal("140"))
    assert score == Decimal("100.00")
    assert any("kırpılarak" in note for note in notes)


def test_higher_is_better_equal_bounds_uses_threshold():
    """minimum ve target eşitse eşik karşılaştırması uygulanır."""
    indicator = build_indicator(
        direction="higher_is_better",
        minimum_value=Decimal("10"),
        target_value=Decimal("10"),
    )
    above, notes = normalize_score(indicator, Decimal("12"))
    below, _ = normalize_score(indicator, Decimal("8"))
    assert above == Decimal("100.00") and below == Decimal("0")
    assert any("eşik" in note for note in notes)


# ===========================================================================
# 3) Normalizasyon: lower_is_better
# ===========================================================================


@pytest.mark.parametrize(
    "value,expected",
    [
        (Decimal("10"), Decimal("100.00")),  # hedefin altı -> 100
        (Decimal("15"), Decimal("100.00")),  # hedef -> 100
        (Decimal("25"), Decimal("71.43")),
        (Decimal("32.5"), Decimal("50.00")),  # tam orta
        (Decimal("50"), Decimal("0.00")),  # maximum -> 0
        (Decimal("70"), Decimal("0.00")),  # maximumun üstü de 0
    ],
)
def test_lower_is_better_linear_scaling(value, expected):
    """lower_is_better yönünde target-maximum arası ters doğrusal ölçeklenir."""
    indicator = build_indicator(
        direction="lower_is_better",
        minimum_value=Decimal("5"),
        target_value=Decimal("15"),
        maximum_value=Decimal("50"),
    )
    score, _ = normalize_score(indicator, value)
    assert score == expected


def test_lower_is_better_without_maximum_uses_binary_check():
    """maximum yoksa hedefe göre ikili değerlendirme yapılır."""
    indicator = build_indicator(
        direction="lower_is_better", target_value=Decimal("20")
    )
    good, notes = normalize_score(indicator, Decimal("18"))
    bad, _ = normalize_score(indicator, Decimal("25"))
    assert good == Decimal("100.00") and bad == Decimal("0")
    assert any("ikili değerlendirme" in note for note in notes)


def test_lower_is_better_defaults_target_from_minimum():
    """Hedef yoksa minimum hedef kabul edilir ve not düşülür."""
    indicator = build_indicator(
        direction="lower_is_better",
        minimum_value=Decimal("2"),
        maximum_value=Decimal("10"),
    )
    score, notes = normalize_score(indicator, Decimal("2"))
    assert score == Decimal("100.00")
    assert any("hedef kabul edildi" in note for note in notes)


# ===========================================================================
# 4) Normalizasyon: target_is_best
# ===========================================================================


@pytest.mark.parametrize(
    "value,expected",
    [
        (Decimal("4"), Decimal("100.00")),  # tam hedef
        (Decimal("3"), Decimal("0.00")),  # minimum
        (Decimal("3.5"), Decimal("50.00")),  # hedefin altında yarı yol
        (Decimal("8"), Decimal("0.00")),  # maximum
        (Decimal("6"), Decimal("50.00")),  # hedefin üstünde yarı yol
    ],
)
def test_target_is_best_scaling(value, expected):
    """target_is_best yönünde hedeften uzaklaştıkça skor düşer."""
    indicator = build_indicator(
        direction="target_is_best",
        minimum_value=Decimal("3"),
        target_value=Decimal("4"),
        maximum_value=Decimal("8"),
    )
    score, _ = normalize_score(indicator, value)
    assert score == expected


def test_target_is_best_without_maximum_uses_ratio_fallback():
    """maximum yoksa hedefin üstü oransal değerlendirilir."""
    indicator = build_indicator(
        direction="target_is_best",
        minimum_value=Decimal("0"),
        target_value=Decimal("10"),
    )
    score, notes = normalize_score(indicator, Decimal("20"))
    assert score == Decimal("50.00")
    assert any("oransal" in note for note in notes)


def test_target_is_best_without_minimum_uses_ratio_fallback():
    """minimum yoksa hedefin altı oransal değerlendirilir."""
    indicator = build_indicator(
        direction="target_is_best", target_value=Decimal("10")
    )
    score, notes = normalize_score(indicator, Decimal("4"))
    assert score == Decimal("40.00")
    assert any("oransal" in note for note in notes)


def test_normalize_returns_none_for_missing_value():
    """Değer yoksa skor da None döner."""
    indicator = build_indicator(direction="higher_is_better")
    score, notes = normalize_score(indicator, None)
    assert score is None and notes == []


# ===========================================================================
# 5) Readiness katsayıları
# ===========================================================================


@pytest.mark.parametrize(
    "status,expected",
    [
        ("available", Decimal("1.00")),
        ("estimated", Decimal("0.75")),
        ("partial", Decimal("0.50")),
        ("missing", Decimal("0.00")),
        ("invalid", Decimal("0.00")),
    ],
)
def test_readiness_factors_match_documented_values(status, expected):
    """Hazırlık katsayıları belgelenen değerlerle birebir aynıdır."""
    assert readiness_factor(status) == expected
    assert DATA_STATUS_READINESS_FACTOR[status] == expected


def test_readiness_factor_for_missing_record_is_zero():
    """Hiç kayıt olmayan (None) gösterge eksik sayılır."""
    assert readiness_factor(None) == Decimal("0.00")


@pytest.mark.parametrize(
    "status,expected",
    [
        ("available", True),
        ("partial", True),
        ("estimated", True),
        ("missing", False),
        ("invalid", False),
    ],
)
def test_usable_statuses(status, expected):
    """Yalnızca available/partial/estimated performans hesabına girer."""
    assert is_usable(status) is expected


# ===========================================================================
# 6) Uyum (compliance) ve risk
# ===========================================================================


@pytest.mark.parametrize(
    "performance,readiness,expected",
    [
        (Decimal("80"), Decimal("100"), Decimal("80.00")),
        (Decimal("80"), Decimal("50"), Decimal("40.00")),
        (Decimal("100"), Decimal("0"), Decimal("0.00")),
        (Decimal("0"), Decimal("100"), Decimal("0.00")),
        (Decimal("62.5"), Decimal("80"), Decimal("50.00")),
    ],
)
def test_compliance_formula(performance, readiness, expected):
    """compliance = performance × readiness / 100 formülü doğrulanır."""
    assert compliance_score(performance, readiness) == expected


@pytest.mark.parametrize(
    "compliance,expected",
    [
        (Decimal("90"), EvaluationRiskLevel.LOW),
        (Decimal("75"), EvaluationRiskLevel.LOW),
        (Decimal("74.99"), EvaluationRiskLevel.MEDIUM),
        (Decimal("50"), EvaluationRiskLevel.MEDIUM),
        (Decimal("49.99"), EvaluationRiskLevel.HIGH),
        (Decimal("25"), EvaluationRiskLevel.HIGH),
        (Decimal("24.99"), EvaluationRiskLevel.CRITICAL),
        (Decimal("0"), EvaluationRiskLevel.CRITICAL),
    ],
)
def test_risk_thresholds_with_full_readiness(compliance, expected):
    """Hazırlık tamken risk yalnızca uyum skoruna göre belirlenir."""
    assert calculate_risk_level(compliance, Decimal("100")) == expected


def test_low_readiness_forces_at_least_high_risk():
    """Hazırlık %50'nin altındayken risk 'low' görünemez."""
    # Uyum skoru yüksek olsa bile veri yetersizse risk yükseltilir.
    assert (
        calculate_risk_level(Decimal("90"), Decimal("40")) == EvaluationRiskLevel.HIGH
    )


def test_very_low_readiness_forces_critical_risk():
    """Hazırlık %25'in altındayken risk her zaman critical olur."""
    assert (
        calculate_risk_level(Decimal("95"), Decimal("10")) == EvaluationRiskLevel.CRITICAL
    )


def test_high_readiness_does_not_change_risk():
    """Hazırlık yeterliyken risk seviyesi yapay olarak değiştirilmez."""
    assert (
        calculate_risk_level(Decimal("80"), Decimal("85")) == EvaluationRiskLevel.LOW
    )


# ===========================================================================
# 7) Yardımcı fonksiyonlar
# ===========================================================================


def test_weighted_average_basic():
    """Ağırlıklı ortalama doğru hesaplanır."""
    assert weighted_average([(Decimal("100"), Decimal("50")), (Decimal("0"), Decimal("50"))]) == Decimal("50.00")


def test_weighted_average_respects_weights():
    """Farklı ağırlıklar sonucu doğru etkiler."""
    result = weighted_average(
        [(Decimal("100"), Decimal("75")), (Decimal("0"), Decimal("25"))]
    )
    assert result == Decimal("75.00")


def test_weighted_average_with_zero_total_weight_returns_zero():
    """Ağırlık toplamı sıfırsa sıfıra bölme oluşmaz."""
    assert weighted_average([(Decimal("80"), Decimal("0"))]) == Decimal("0.00")


def test_weighted_average_empty_list_returns_zero():
    """Boş liste sıfır döndürür."""
    assert weighted_average([]) == Decimal("0.00")


@pytest.mark.parametrize(
    "value,expected",
    [
        (Decimal("-10"), Decimal("0.00")),
        (Decimal("0"), Decimal("0.00")),
        (Decimal("55.555"), Decimal("55.56")),
        (Decimal("100"), Decimal("100.00")),
        (Decimal("150"), Decimal("100.00")),
    ],
)
def test_clamp_score_bounds_and_rounding(value, expected):
    """Skorlar 0-100 aralığına kırpılır ve iki basamağa yuvarlanır."""
    assert clamp_score(value) == expected


# ===========================================================================
# 8) Gösterge değerlendirmesi (evaluate_indicator)
# ===========================================================================


def test_evaluate_indicator_produces_score_for_available_data():
    """Kullanılabilir veriden hem etkin değer hem skor üretilir."""
    indicator = build_indicator(
        calculation_type="percentage",
        direction="higher_is_better",
        minimum_value=Decimal("0"),
        target_value=Decimal("25"),
    )
    detail = evaluate_indicator(
        indicator,
        MetricSnapshot(
            numerator=Decimal("20"), denominator=Decimal("120"), data_status="available"
        ),
    )
    assert detail.effective_value == Decimal("16.67")
    assert detail.performance_score == Decimal("66.68")
    assert detail.readiness_factor == Decimal("1.00")


def test_evaluate_indicator_skips_missing_data():
    """missing veriden skor üretilmez."""
    indicator = build_indicator()
    detail = evaluate_indicator(indicator, MetricSnapshot(data_status="missing"))
    assert detail.performance_score is None
    assert detail.data_status == DataStatus.MISSING


def test_evaluate_indicator_without_snapshot_is_missing():
    """Hiç kayıt yoksa gösterge eksik kabul edilir."""
    detail = evaluate_indicator(build_indicator(), None)
    assert detail.data_status == DataStatus.MISSING
    assert detail.readiness_factor == Decimal("0.00")


def test_evaluate_indicator_marks_unusable_available_data_as_invalid():
    """available işaretli ama sayısal değer üretmeyen veri geçersiz sayılır."""
    indicator = build_indicator(calculation_type="ratio")
    detail = evaluate_indicator(indicator, MetricSnapshot(data_status="available"))
    assert detail.data_status == DataStatus.INVALID
    assert any("geçersiz kabul edildi" in note for note in detail.calculation_notes)


def test_evaluate_indicator_partial_data_gets_half_readiness():
    """partial veri yarım hazırlık puanı alır ama skoru hesaplanır."""
    indicator = build_indicator(
        calculation_type="score", minimum_value=Decimal("0"), target_value=Decimal("100")
    )
    detail = evaluate_indicator(
        indicator, MetricSnapshot(value=Decimal("60"), data_status="partial")
    )
    assert detail.readiness_factor == Decimal("0.50")
    assert detail.performance_score == Decimal("60.00")


def test_evaluate_indicator_estimated_data_gets_three_quarter_readiness():
    """estimated veri 0.75 hazırlık katsayısı alır."""
    indicator = build_indicator(
        calculation_type="score", minimum_value=Decimal("0"), target_value=Decimal("100")
    )
    detail = evaluate_indicator(
        indicator, MetricSnapshot(value=Decimal("40"), data_status="estimated")
    )
    assert detail.readiness_factor == Decimal("0.75")


def test_evaluate_indicator_preserves_direction_and_unit():
    """Gösterge meta bilgileri sonuç nesnesine taşınır."""
    indicator = build_indicator(
        unit="%", direction="lower_is_better", calculation_type="ratio"
    )
    detail = evaluate_indicator(
        indicator,
        MetricSnapshot(
            numerator=Decimal("10"), denominator=Decimal("2"), data_status="available"
        ),
    )
    assert detail.unit == "%"
    assert detail.direction == IndicatorDirection.LOWER_IS_BETTER
