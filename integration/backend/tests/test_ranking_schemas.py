"""Şema ve model doğrulama testleri (Modül 10)."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.ranking_evaluations import (
    AssessmentCalculateRequest,
    BenchmarkValueCreate,
    DimensionCreate,
    FrameworkCreate,
    IndicatorCreate,
    MetricValueCreate,
    StudentMetricSyncRequest,
)


# ===========================================================================
# Framework şeması
# ===========================================================================


def test_framework_accepts_valid_payload():
    """Geçerli çerçeve gövdesi kabul edilir."""
    framework = FrameworkCreate(code="THE", name="THE 2026", methodology_year=2026)
    assert framework.code.value == "THE"


@pytest.mark.parametrize("code", ["THE", "QS", "YOK"])
def test_framework_accepts_supported_codes(code):
    """Üç çerçeve kodu da desteklenir."""
    assert FrameworkCreate(code=code, name="Test", methodology_year=2026).code.value == code


def test_framework_rejects_unknown_code():
    """Tanımsız çerçeve kodu reddedilir."""
    with pytest.raises(ValidationError):
        FrameworkCreate(code="ARWU", name="Test", methodology_year=2026)


@pytest.mark.parametrize("year", [1999, 2101, 0, -2026])
def test_framework_rejects_out_of_range_year(year):
    """Metodoloji yılı makul aralığın dışındaysa reddedilir."""
    with pytest.raises(ValidationError):
        FrameworkCreate(code="THE", name="Test", methodology_year=year)


def test_framework_rejects_short_name():
    """Çok kısa çerçeve adı reddedilir."""
    with pytest.raises(ValidationError):
        FrameworkCreate(code="THE", name="X", methodology_year=2026)


# ===========================================================================
# Dimension şeması
# ===========================================================================


def test_dimension_normalizes_code_to_lowercase():
    """Boyut kodu küçük harfe çevrilir ve boşlukları kırpılır."""
    dimension = DimensionCreate(
        framework_id=1, code="  Research-Environment  ", name="Research", weight="29"
    )
    assert dimension.code == "research-environment"


@pytest.mark.parametrize("weight", ["-1", "100.01", "150"])
def test_dimension_rejects_weight_out_of_range(weight):
    """Boyut ağırlığı 0-100 aralığı dışındaysa reddedilir."""
    with pytest.raises(ValidationError):
        DimensionCreate(framework_id=1, code="test", name="Test", weight=weight)


@pytest.mark.parametrize("weight", ["0", "0.5", "50", "100"])
def test_dimension_accepts_weight_in_range(weight):
    """0-100 aralığındaki ağırlıklar kabul edilir."""
    dimension = DimensionCreate(framework_id=1, code="test", name="Test", weight=weight)
    assert Decimal("0") <= dimension.weight <= Decimal("100")


def test_dimension_rejects_invalid_framework_id():
    """framework_id sıfır veya negatif olamaz."""
    with pytest.raises(ValidationError):
        DimensionCreate(framework_id=0, code="test", name="Test", weight="10")


def test_dimension_rejects_negative_display_order():
    """Gösterim sırası negatif olamaz."""
    with pytest.raises(ValidationError):
        DimensionCreate(
            framework_id=1, code="test", name="Test", weight="10", display_order=-1
        )


# ===========================================================================
# Indicator şeması
# ===========================================================================


def test_indicator_accepts_valid_payload():
    """Geçerli gösterge gövdesi kabul edilir."""
    indicator = IndicatorCreate(
        dimension_id=1,
        code="test-indicator",
        name="Test",
        calculation_type="ratio",
        weight="50",
        direction="higher_is_better",
        minimum_value="0",
        target_value="10",
        maximum_value="20",
    )
    assert indicator.code == "test-indicator"


def test_indicator_normalizes_code():
    """Gösterge kodu küçük harfe çevrilir."""
    indicator = IndicatorCreate(
        dimension_id=1, code="  THE-Citation-Impact ", name="Test", weight="10"
    )
    assert indicator.code == "the-citation-impact"


@pytest.mark.parametrize(
    "calculation_type", ["raw", "percentage", "ratio", "score", "boolean", "manual"]
)
def test_indicator_accepts_all_calculation_types(calculation_type):
    """Altı hesaplama türü de desteklenir."""
    indicator = IndicatorCreate(
        dimension_id=1,
        code=f"test-{calculation_type}",
        name="Test",
        weight="10",
        calculation_type=calculation_type,
    )
    assert indicator.calculation_type.value == calculation_type


def test_indicator_rejects_unknown_calculation_type():
    """Tanımsız hesaplama türü reddedilir."""
    with pytest.raises(ValidationError):
        IndicatorCreate(
            dimension_id=1, code="test", name="Test", weight="10", calculation_type="magic"
        )


@pytest.mark.parametrize(
    "direction", ["higher_is_better", "lower_is_better", "target_is_best"]
)
def test_indicator_accepts_all_directions(direction):
    """Üç yön değeri de desteklenir."""
    indicator = IndicatorCreate(
        dimension_id=1,
        code=f"test-{direction}",
        name="Test",
        weight="10",
        direction=direction,
        target_value="10",
    )
    assert indicator.direction.value == direction


def test_indicator_rejects_unknown_direction():
    """Tanımsız yön reddedilir."""
    with pytest.raises(ValidationError):
        IndicatorCreate(
            dimension_id=1, code="test", name="Test", weight="10", direction="sideways"
        )


def test_indicator_rejects_minimum_greater_than_maximum():
    """minimum > maximum tutarsızlığı reddedilir."""
    with pytest.raises(ValidationError, match="maximum_value"):
        IndicatorCreate(
            dimension_id=1,
            code="test",
            name="Test",
            weight="10",
            minimum_value="50",
            maximum_value="10",
        )


def test_indicator_rejects_target_below_minimum():
    """target < minimum tutarsızlığı reddedilir."""
    with pytest.raises(ValidationError, match="target_value"):
        IndicatorCreate(
            dimension_id=1,
            code="test",
            name="Test",
            weight="10",
            minimum_value="20",
            target_value="10",
        )


def test_indicator_rejects_target_above_maximum():
    """target > maximum tutarsızlığı reddedilir."""
    with pytest.raises(ValidationError, match="target_value"):
        IndicatorCreate(
            dimension_id=1,
            code="test",
            name="Test",
            weight="10",
            target_value="90",
            maximum_value="50",
        )


def test_target_is_best_requires_target_value():
    """target_is_best yönü hedef değer olmadan kullanılamaz."""
    with pytest.raises(ValidationError, match="target_value"):
        IndicatorCreate(
            dimension_id=1,
            code="test",
            name="Test",
            weight="10",
            direction="target_is_best",
        )


@pytest.mark.parametrize("weight", ["-5", "101", "999"])
def test_indicator_rejects_weight_out_of_range(weight):
    """Gösterge ağırlığı 0-100 aralığında olmalıdır."""
    with pytest.raises(ValidationError):
        IndicatorCreate(dimension_id=1, code="test", name="Test", weight=weight)


def test_indicator_accepts_equal_bounds():
    """Eşit sınır değerleri geçerlidir (eşik göstergeleri için)."""
    indicator = IndicatorCreate(
        dimension_id=1,
        code="test",
        name="Test",
        weight="10",
        minimum_value="10",
        target_value="10",
        maximum_value="10",
    )
    assert indicator.minimum_value == indicator.maximum_value


# ===========================================================================
# MetricValue şeması
# ===========================================================================


def test_metric_accepts_numerator_denominator():
    """Pay/payda ile gösterge verisi oluşturulabilir."""
    metric = MetricValueCreate(
        indicator_id=1, academic_year="2025-2026", numerator="20", denominator="120"
    )
    assert metric.denominator == Decimal("120")


def test_metric_rejects_zero_denominator():
    """Payda sıfır olamaz."""
    with pytest.raises(ValidationError, match="sıfır olamaz"):
        MetricValueCreate(
            indicator_id=1, academic_year="2025-2026", numerator="10", denominator="0"
        )


def test_metric_rejects_numerator_without_denominator_or_value():
    """Yalnızca pay verilirse oran hesaplanamaz."""
    with pytest.raises(ValidationError, match="denominator"):
        MetricValueCreate(indicator_id=1, academic_year="2025-2026", numerator="10")


def test_metric_rejects_available_status_without_data():
    """available işaretli kayıt sayısal veri içermelidir."""
    with pytest.raises(ValidationError, match="available"):
        MetricValueCreate(
            indicator_id=1, academic_year="2025-2026", data_status="available"
        )


def test_metric_allows_missing_status_without_data():
    """missing işaretli kayıt sayısal veri içermeyebilir."""
    metric = MetricValueCreate(
        indicator_id=1, academic_year="2025-2026", data_status="missing"
    )
    assert metric.value is None


@pytest.mark.parametrize(
    "academic_year", ["2025", "2025/2026", "25-26", "2025-2027", "abcd-efgh", ""]
)
def test_metric_rejects_invalid_academic_year(academic_year):
    """Akademik yıl YYYY-YYYY biçiminde ve ardışık olmalıdır."""
    with pytest.raises(ValidationError):
        MetricValueCreate(
            indicator_id=1, academic_year=academic_year, value="10"
        )


@pytest.mark.parametrize("academic_year", ["2023-2024", "2025-2026", "2030-2031"])
def test_metric_accepts_valid_academic_year(academic_year):
    """Geçerli akademik yıl biçimleri kabul edilir."""
    metric = MetricValueCreate(
        indicator_id=1, academic_year=academic_year, value="10"
    )
    assert metric.academic_year == academic_year


@pytest.mark.parametrize("period", ["annual", "fall", "spring", "summer"])
def test_metric_accepts_all_periods(period):
    """Dört dönem değeri de desteklenir."""
    metric = MetricValueCreate(
        indicator_id=1, academic_year="2025-2026", value="1", period=period
    )
    assert metric.period.value == period


def test_metric_rejects_unknown_period():
    """Tanımsız dönem reddedilir."""
    with pytest.raises(ValidationError):
        MetricValueCreate(
            indicator_id=1, academic_year="2025-2026", value="1", period="quarter"
        )


@pytest.mark.parametrize("status", ["available", "partial", "missing", "estimated", "invalid"])
def test_metric_accepts_all_data_statuses(status):
    """Beş veri durumu da desteklenir."""
    metric = MetricValueCreate(
        indicator_id=1, academic_year="2025-2026", value="1", data_status=status
    )
    assert metric.data_status.value == status


@pytest.mark.parametrize("origin", ["automatic", "manual", "imported"])
def test_metric_accepts_all_origins(origin):
    """Üç veri kaynağı da desteklenir."""
    metric = MetricValueCreate(
        indicator_id=1, academic_year="2025-2026", value="1", origin=origin
    )
    assert metric.origin.value == origin


def test_metric_defaults_to_manual_origin():
    """Kaynak belirtilmezse veri elle girilmiş sayılır."""
    metric = MetricValueCreate(indicator_id=1, academic_year="2025-2026", value="1")
    assert metric.origin.value == "manual"


# ===========================================================================
# Benchmark ve diğer şemalar
# ===========================================================================


def test_benchmark_value_requires_valid_year():
    """Karşılaştırma değeri geçerli akademik yıl ister."""
    with pytest.raises(ValidationError):
        BenchmarkValueCreate(
            benchmark_institution_id=1, indicator_id=1, academic_year="2025", value="10"
        )


def test_benchmark_value_accepts_decimal():
    """Karşılaştırma değeri Decimal olarak saklanır."""
    value = BenchmarkValueCreate(
        benchmark_institution_id=1,
        indicator_id=1,
        academic_year="2025-2026",
        value="22.40",
    )
    assert value.value == Decimal("22.40")


def test_assessment_request_requires_valid_year():
    """Değerlendirme isteği geçerli akademik yıl ister."""
    with pytest.raises(ValidationError):
        AssessmentCalculateRequest(academic_year="20252026")


def test_assessment_request_defaults_to_persist():
    """Değerlendirme varsayılan olarak kaydedilir."""
    request = AssessmentCalculateRequest(academic_year="2025-2026")
    assert request.persist is True


def test_assessment_request_can_disable_persistence():
    """persist=false ile deneme modu kullanılabilir."""
    request = AssessmentCalculateRequest(academic_year="2025-2026", persist=False)
    assert request.persist is False


def test_sync_request_defaults_protect_manual_data():
    """Senkronizasyon varsayılan olarak elle girilen veriyi ezmez."""
    request = StudentMetricSyncRequest(academic_year="2025-2026")
    assert request.overwrite_manual is False
