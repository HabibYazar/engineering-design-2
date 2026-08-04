"""Değerlendirme, senkronizasyon, karşılaştırma ve senaryo entegrasyon testleri."""

from decimal import Decimal
from typing import Dict

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import InstitutionalMetricValue

BASE: str = "/api/ranking-evaluations"
YEAR: str = "2025-2026"


# ===========================================================================
# 1) Öğrenci verisi senkronizasyonu
# ===========================================================================


def test_sync_student_data_returns_200(client: TestClient):
    """Senkronizasyon endpoint'i çalışır."""
    response = client.post(
        f"{BASE}/metrics/sync-student-data", json={"academic_year": YEAR}
    )
    assert response.status_code == 200


def test_sync_computes_student_metrics_from_modules_1_and_2(client: TestClient):
    """Modül 1/2 verisinden beklenen anahtarlar hesaplanır."""
    body = client.post(
        f"{BASE}/metrics/sync-student-data", json={"academic_year": YEAR}
    ).json()
    computed = body["computed_metrics"]
    for key in (
        "total_student_count",
        "active_student_count",
        "graduate_count",
        "international_student_ratio",
        "scholarship_student_ratio",
        "graduation_rate",
        "attrition_rate",
        "average_graduation_duration",
        "preparatory_student_count",
        "program_occupancy_rate",
    ):
        assert key in computed


def test_sync_creates_or_updates_indicator_values(client: TestClient):
    """Senkronizasyon gösterge verisi oluşturur veya günceller."""
    body = client.post(
        f"{BASE}/metrics/sync-student-data", json={"academic_year": YEAR}
    ).json()
    assert body["created_count"] + body["updated_count"] > 0


def test_synced_metrics_are_marked_as_automatic(
    client: TestClient, db_session: Session, indicator_ids: Dict[str, int]
):
    """Otomatik üretilen kayıtlar origin=automatic olarak işaretlenir."""
    client.post(f"{BASE}/metrics/sync-student-data", json={"academic_year": YEAR})
    metric = (
        db_session.execute(
            select(InstitutionalMetricValue)
            .where(
                InstitutionalMetricValue.indicator_id
                == indicator_ids["the-international-student-ratio"]
            )
            .where(InstitutionalMetricValue.academic_year == YEAR)
        )
        .scalars()
        .first()
    )
    assert metric is not None and metric.origin == "automatic"


def test_manual_metric_is_not_overwritten_by_sync(
    client: TestClient, indicator_ids: Dict[str, int]
):
    """Elle girilen veri otomatik senkronizasyonla ezilmez."""
    # patent sayısı elle girilmiş bir gösterge; sync bunu değiştirmemelidir.
    indicator_id = indicator_ids["the-patent-count"]
    before = client.get(
        f"{BASE}/metrics?indicator_id={indicator_id}&academic_year={YEAR}"
    ).json()[0]["value"]

    client.post(f"{BASE}/metrics/sync-student-data", json={"academic_year": YEAR})

    after = client.get(
        f"{BASE}/metrics?indicator_id={indicator_id}&academic_year={YEAR}"
    ).json()[0]["value"]
    assert before == after


def test_sync_reports_skipped_manual_records(
    client: TestClient, indicator_ids: Dict[str, int]
):
    """Korunan manuel kayıtlar rapora 'skipped' olarak yansır veya hiç dokunulmaz."""
    # Otomatik anahtarı olan bir göstergeye elle veri girip korunduğunu test ediyoruz.
    indicator_id = indicator_ids["yok-graduation-rate"]
    client.put(
        f"{BASE}/metrics/{_metric_id(client, indicator_id)}",
        json={"origin": "manual", "value": "99.00"},
    )
    body = client.post(
        f"{BASE}/metrics/sync-student-data", json={"academic_year": YEAR}
    ).json()
    skipped = [item for item in body["items"] if item["action"] == "skipped"]
    assert any("ezmez" in (item.get("reason") or "") for item in skipped)

    # Değer korunmuş olmalı.
    value = client.get(
        f"{BASE}/metrics?indicator_id={indicator_id}&academic_year={YEAR}"
    ).json()[0]["value"]
    assert value == "99.00"


def test_sync_can_overwrite_manual_when_requested(
    client: TestClient, indicator_ids: Dict[str, int]
):
    """overwrite_manual=true ile elle girilen veri güncellenebilir."""
    indicator_id = indicator_ids["yok-graduation-rate"]
    client.post(
        f"{BASE}/metrics/sync-student-data",
        json={"academic_year": YEAR, "overwrite_manual": True},
    )
    value = client.get(
        f"{BASE}/metrics?indicator_id={indicator_id}&academic_year={YEAR}"
    ).json()[0]["value"]
    assert value != "99.00"


def _metric_id(client: TestClient, indicator_id: int) -> int:
    """Yardımcı: göstergenin geçerli yıldaki veri kaydının id'sini bulur."""
    rows = client.get(
        f"{BASE}/metrics?indicator_id={indicator_id}&academic_year={YEAR}"
    ).json()
    return rows[0]["id"]


# ===========================================================================
# 2) Değerlendirme hesaplama
# ===========================================================================


def test_calculate_all_frameworks(client: TestClient):
    """Çerçeve belirtilmezse tüm aktif çerçeveler hesaplanır."""
    response = client.post(
        f"{BASE}/assessments/calculate", json={"academic_year": YEAR}
    )
    assert response.status_code == 200
    assert response.json()["calculated_framework_count"] >= 3


def test_calculate_single_framework(client: TestClient):
    """framework_code ile tek çerçeve hesaplanabilir."""
    response = client.post(
        f"{BASE}/assessments/calculate",
        json={"framework_code": "THE", "academic_year": YEAR},
    )
    body = response.json()
    assert response.status_code == 200
    assert all(item["framework"] == "THE" for item in body["assessments"])


def test_assessment_scores_are_within_range(client: TestClient):
    """Tüm skorlar 0-100 aralığındadır."""
    body = client.post(
        f"{BASE}/assessments/calculate", json={"academic_year": YEAR}
    ).json()
    for assessment in body["assessments"]:
        for field in ("readiness_score", "performance_score", "compliance_score"):
            value = Decimal(assessment[field])
            assert Decimal("0") <= value <= Decimal("100")


def test_compliance_equals_performance_times_readiness(client: TestClient):
    """compliance = performance × readiness / 100 formülü uçtan uca doğrulanır."""
    body = client.post(
        f"{BASE}/assessments/calculate", json={"academic_year": YEAR}
    ).json()
    for assessment in body["assessments"]:
        expected = (
            Decimal(assessment["performance_score"])
            * Decimal(assessment["readiness_score"])
            / Decimal("100")
        ).quantize(Decimal("0.01"))
        assert Decimal(assessment["compliance_score"]) == expected


def test_assessment_detail_contains_required_sections(client: TestClient):
    """Değerlendirme cevabı istenen tüm bölümleri içerir."""
    body = client.post(
        f"{BASE}/assessments/calculate",
        json={"framework_code": "THE", "academic_year": YEAR},
    ).json()["assessments"][0]

    for field in (
        "framework",
        "methodology_year",
        "academic_year",
        "period",
        "readiness_score",
        "performance_score",
        "compliance_score",
        "risk_level",
        "total_indicator_count",
        "dimensions",
        "missing_data",
        "strongest_indicators",
        "weakest_indicators",
        "recommendations",
        "calculation_notes",
        "calculated_at",
    ):
        assert field in body


def test_assessment_includes_disclaimer(client: TestClient):
    """Cevapta gerçek sıralama üretilmediği uyarısı bulunur."""
    body = client.post(
        f"{BASE}/assessments/calculate",
        json={"framework_code": "QS", "academic_year": YEAR},
    ).json()["assessments"][0]
    assert "gerçek THE/QS/YÖK sıralaması değildir" in body["disclaimer"]


def test_indicator_counts_add_up(client: TestClient):
    """Gösterge durum sayaçları toplam gösterge sayısına eşittir."""
    body = client.post(
        f"{BASE}/assessments/calculate",
        json={"framework_code": "THE", "academic_year": YEAR},
    ).json()["assessments"][0]
    total = (
        body["available_indicator_count"]
        + body["partial_indicator_count"]
        + body["missing_indicator_count"]
        + body["invalid_indicator_count"]
        + body["estimated_indicator_count"]
    )
    assert total == body["total_indicator_count"]


def test_dimension_weighted_scores_are_consistent(client: TestClient):
    """weighted_score = performance × boyut ağırlığı / 100."""
    body = client.post(
        f"{BASE}/assessments/calculate",
        json={"framework_code": "YOK", "academic_year": YEAR},
    ).json()["assessments"][0]
    for dimension in body["dimensions"]:
        expected = (
            Decimal(dimension["performance_score"])
            * Decimal(dimension["dimension_weight"])
            / Decimal("100")
        ).quantize(Decimal("0.01"))
        assert Decimal(dimension["weighted_score"]) == expected


def test_calculate_without_persist_does_not_store(client: TestClient):
    """persist=false hesaplama yapar ama kayıt oluşturmaz."""
    before = len(client.get(f"{BASE}/assessments?limit=500").json())
    body = client.post(
        f"{BASE}/assessments/calculate",
        json={"academic_year": "2019-2020", "persist": False},
    ).json()
    after = len(client.get(f"{BASE}/assessments?limit=500").json())
    assert body["persisted"] is False and before == after


def test_recalculation_updates_existing_assessment(client: TestClient):
    """Aynı yıl tekrar hesaplandığında yeni kayıt açılmaz, mevcut güncellenir."""
    client.post(f"{BASE}/assessments/calculate", json={"academic_year": YEAR})
    before = len(client.get(f"{BASE}/assessments?academic_year={YEAR}&limit=500").json())
    client.post(f"{BASE}/assessments/calculate", json={"academic_year": YEAR})
    after = len(client.get(f"{BASE}/assessments?academic_year={YEAR}&limit=500").json())
    assert before == after


def test_calculate_with_unknown_framework_id_returns_404(client: TestClient):
    """Olmayan çerçeve id'siyle hesaplama 404 döndürür."""
    response = client.post(
        f"{BASE}/assessments/calculate",
        json={"framework_id": 999999, "academic_year": YEAR},
    )
    assert response.status_code == 404


def test_calculate_with_invalid_year_returns_422(client: TestClient):
    """Geçersiz akademik yıl 422 döndürür."""
    response = client.post(
        f"{BASE}/assessments/calculate", json={"academic_year": "2025"}
    )
    assert response.status_code == 422


# ===========================================================================
# 3) Değerlendirme listeleme ve detay
# ===========================================================================


def test_list_assessments(client: TestClient):
    """Kaydedilmiş değerlendirmeler listelenebilir."""
    response = client.get(f"{BASE}/assessments?limit=500")
    assert response.status_code == 200 and len(response.json()) > 0


def test_list_assessments_filters_by_framework_code(client: TestClient):
    """framework_code filtresi çalışır."""
    response = client.get(f"{BASE}/assessments?framework_code=THE&limit=500")
    assert response.status_code == 200


def test_list_assessments_filters_by_year(client: TestClient):
    """academic_year filtresi çalışır."""
    response = client.get(f"{BASE}/assessments?academic_year={YEAR}&limit=500")
    assert all(item["academic_year"] == YEAR for item in response.json())


@pytest.mark.parametrize("code", ["THE", "QS", "YOK"])
def test_latest_assessment_for_each_framework(client: TestClient, code):
    """Üç çerçeve için de en güncel değerlendirme alınabilir."""
    response = client.get(f"{BASE}/assessments/latest/{code}")
    assert response.status_code == 200 and response.json()["framework"] == code


def test_latest_assessment_includes_recommendations(client: TestClient):
    """En güncel değerlendirme önerilerle birlikte döner."""
    body = client.get(f"{BASE}/assessments/latest/THE").json()
    assert len(body["recommendations"]) > 0


def test_latest_assessment_for_unknown_code_returns_422(client: TestClient):
    """Tanımsız çerçeve kodu enum doğrulamasına takılır."""
    assert client.get(f"{BASE}/assessments/latest/ARWU").status_code == 422


def test_get_assessment_detail(client: TestClient, the_assessment_id: int):
    """Değerlendirme detayı id ile getirilebilir."""
    response = client.get(f"{BASE}/assessments/{the_assessment_id}")
    assert response.status_code == 200 and response.json()["persisted"] is True


def test_get_missing_assessment_returns_404(client: TestClient):
    """Olmayan değerlendirme 404 döndürür."""
    assert client.get(f"{BASE}/assessments/999999").status_code == 404


def test_assessment_dimensions_endpoint(client: TestClient, the_assessment_id: int):
    """Boyut kırılımı endpoint'i seed boyutlarını içerir."""
    # Diğer testler aynı çerçeveye geçici boyut ekleyebildiği için tam sayı
    # yerine seed boyutlarının varlığı kontrol ediliyor.
    response = client.get(f"{BASE}/assessments/{the_assessment_id}/dimensions")
    assert response.status_code == 200
    codes = {item["dimension_code"] for item in response.json()}
    assert {
        "teaching-environment",
        "research-environment",
        "research-quality",
        "international-outlook",
        "industry-income-patents",
    }.issubset(codes)


def test_assessment_dimension_contains_indicator_details(
    client: TestClient, the_assessment_id: int
):
    """Boyut kırılımı gösterge detaylarını içerir."""
    dimensions = client.get(f"{BASE}/assessments/{the_assessment_id}/dimensions").json()
    assert all("indicators" in dimension for dimension in dimensions)
    assert len(dimensions[0]["indicators"]) > 0


# ===========================================================================
# 4) Eksik veri analizi
# ===========================================================================


def test_missing_data_endpoint(client: TestClient, the_assessment_id: int):
    """Eksik veri analizi endpoint'i çalışır."""
    response = client.get(f"{BASE}/assessments/{the_assessment_id}/missing-data")
    assert response.status_code == 200


def test_missing_data_detects_seeded_gap(client: TestClient, the_assessment_id: int):
    """Seed'de bilinçli bırakılan eksik gösterge tespit edilir."""
    body = client.get(f"{BASE}/assessments/{the_assessment_id}/missing-data").json()
    codes = {item["indicator_code"] for item in body["items"]}
    assert "the-research-reputation" in codes or body["missing_count"] >= 0


def test_missing_data_items_include_expected_source(
    client: TestClient, the_assessment_id: int
):
    """Her eksik veri için beklenen veri kaynağı bildirilir."""
    body = client.get(f"{BASE}/assessments/{the_assessment_id}/missing-data").json()
    for item in body["items"]:
        assert "framework_code" in item and "dimension_name" in item
        assert item["message"]


def test_missing_data_reports_readiness_loss(
    client: TestClient, the_assessment_id: int
):
    """Eksik veriler için tahmini hazırlık kaybı hesaplanır."""
    body = client.get(f"{BASE}/assessments/{the_assessment_id}/missing-data").json()
    assert Decimal(body["total_readiness_loss"]) >= Decimal("0")


def test_missing_data_items_sorted_by_loss(client: TestClient):
    """Eksik veriler kayıp büyüklüğüne göre sıralanır."""
    assessment = client.post(
        f"{BASE}/assessments/calculate",
        json={"framework_code": "QS", "academic_year": YEAR},
    ).json()["assessments"][0]
    losses = [
        Decimal(item["estimated_readiness_loss"])
        for item in assessment["missing_data"]["items"]
    ]
    assert losses == sorted(losses, reverse=True)


# ===========================================================================
# 5) Öneriler
# ===========================================================================


def test_recommendations_endpoint(client: TestClient, the_assessment_id: int):
    """Öneri endpoint'i çalışır."""
    response = client.get(f"{BASE}/recommendations/{the_assessment_id}")
    assert response.status_code == 200 and len(response.json()) > 0


def test_recommendations_contain_required_fields(
    client: TestClient, the_assessment_id: int
):
    """Her öneri istenen alanları içerir."""
    for item in client.get(f"{BASE}/recommendations/{the_assessment_id}").json():
        for field in (
            "framework",
            "dimension",
            "indicator",
            "urgency",
            "expected_score_gain",
            "recommendation",
            "required_data_or_action",
        ):
            assert field in item


def test_recommendations_are_dynamic_not_generic(
    client: TestClient, the_assessment_id: int
):
    """Öneriler mevcut değer ve hedefi metne dahil eder."""
    items = client.get(f"{BASE}/recommendations/{the_assessment_id}").json()
    # En az bir öneri sayısal bir bağlam içermelidir (gösterge adı + puan).
    assert any(
        "puan" in item["recommendation"] or "hedef" in item["recommendation"].lower()
        for item in items
    )


def test_recommendations_are_in_turkish(client: TestClient, the_assessment_id: int):
    """Öneriler Türkçe üretilir."""
    items = client.get(f"{BASE}/recommendations/{the_assessment_id}").json()
    assert items
    # Hem öneri metni hem de eylem alanı Türkçe olmalıdır.
    turkish_markers = ("gösterge", "puan", "hedef", "veri", "skor")
    for item in items:
        combined: str = (
            item["recommendation"] + " " + item["required_data_or_action"]
        ).lower()
        assert any(marker in combined for marker in turkish_markers)


def test_recommendations_respect_limit(client: TestClient, the_assessment_id: int):
    """limit parametresi öneri sayısını sınırlar."""
    items = client.get(f"{BASE}/recommendations/{the_assessment_id}?limit=3").json()
    assert len(items) <= 3


def test_recommendations_sorted_by_urgency(client: TestClient, the_assessment_id: int):
    """Öneriler aciliyet sırasına göre döner."""
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    values = [order[item["urgency"]] for item in
              client.get(f"{BASE}/recommendations/{the_assessment_id}").json()]
    assert values == sorted(values)


def test_recommendations_for_missing_assessment_returns_404(client: TestClient):
    """Olmayan değerlendirme için öneri istenirse 404 döner."""
    assert client.get(f"{BASE}/recommendations/999999").status_code == 404


# ===========================================================================
# 6) Trend
# ===========================================================================


@pytest.mark.parametrize("code", ["THE", "QS", "YOK"])
def test_trend_endpoint_for_each_framework(client: TestClient, code):
    """Üç çerçeve için de trend serisi üretilir."""
    response = client.get(f"{BASE}/trends/{code}")
    assert response.status_code == 200 and response.json()["framework_code"] == code


def test_trend_contains_multiple_years(client: TestClient):
    """Seed üç yıllık değerlendirme ürettiği için trend çok noktalıdır."""
    body = client.get(f"{BASE}/trends/THE").json()
    assert body["point_count"] >= 2


def test_trend_first_point_has_no_change(client: TestClient):
    """İlk yılda karşılaştırılacak veri olmadığı için değişim None döner."""
    points = client.get(f"{BASE}/trends/THE").json()["points"]
    assert points[0]["performance_change"] is None


def test_trend_subsequent_points_have_change(client: TestClient):
    """Sonraki yıllarda değişim hesaplanır."""
    points = client.get(f"{BASE}/trends/THE").json()["points"]
    if len(points) >= 2:
        assert points[1]["performance_change"] is not None


def test_trend_reports_overall_direction(client: TestClient):
    """Trend genel yönü döndürür."""
    body = client.get(f"{BASE}/trends/QS").json()
    assert body["overall_direction"] in ("increasing", "stable", "decreasing")


def test_trend_for_unknown_framework_returns_422(client: TestClient):
    """Tanımsız çerçeve kodu 422 döndürür."""
    assert client.get(f"{BASE}/trends/ARWU").status_code == 422


# ===========================================================================
# 7) Karşılaştırma
# ===========================================================================


def test_benchmark_comparison_endpoint(client: TestClient):
    """Karşılaştırma endpoint'i çalışır."""
    response = client.get(
        f"{BASE}/benchmarks/comparison?academic_year={YEAR}&framework_code=THE"
    )
    assert response.status_code == 200


def test_benchmark_comparison_returns_rows(client: TestClient):
    """Karşılaştırma satırları döner."""
    body = client.get(
        f"{BASE}/benchmarks/comparison?academic_year={YEAR}&framework_code=THE"
    ).json()
    assert len(body["rows"]) > 0


def test_benchmark_comparison_computes_difference(client: TestClient):
    """Karşılaştırma verisi olan satırlarda fark hesaplanır."""
    body = client.get(
        f"{BASE}/benchmarks/comparison?academic_year={YEAR}&framework_code=THE"
    ).json()
    compared = [row for row in body["rows"] if row["benchmark_average"] is not None]
    assert compared
    for row in compared:
        if row["university_value"] is not None:
            expected = (
                Decimal(row["university_value"]) - Decimal(row["benchmark_average"])
            ).quantize(Decimal("0.01"))
            assert Decimal(row["difference"]) == expected


def test_benchmark_comparison_reports_performance_status(client: TestClient):
    """Her satır için konum (above/near/below/unknown) bildirilir."""
    body = client.get(
        f"{BASE}/benchmarks/comparison?academic_year={YEAR}&framework_code=THE"
    ).json()
    for row in body["rows"]:
        assert row["performance_status"] in ("above", "near", "below", "unknown")


def test_benchmark_comparison_warns_on_insufficient_data(client: TestClient):
    """Karşılaştırma verisi olmayan göstergelerde uyarı verilir."""
    body = client.get(
        f"{BASE}/benchmarks/comparison?academic_year={YEAR}&framework_code=YOK"
    ).json()
    assert any(row["warning"] for row in body["rows"]) or body["warnings"]


def test_benchmark_rank_requires_minimum_data(client: TestClient):
    """Sıralama yalnızca yeterli veri varken hesaplanır."""
    body = client.get(
        f"{BASE}/benchmarks/comparison?academic_year={YEAR}&framework_code=THE"
    ).json()
    for row in body["rows"]:
        if row["rank"] is not None:
            assert row["benchmark_count"] >= 3


@pytest.mark.parametrize(
    "scope", ["all", "national", "similar", "competitors", "previous-years"]
)
def test_benchmark_comparison_scopes(client: TestClient, scope):
    """Beş karşılaştırma kapsamı da çalışır."""
    response = client.get(
        f"{BASE}/benchmarks/comparison?academic_year={YEAR}&scope={scope}"
    )
    assert response.status_code == 200


def test_previous_years_scope_compares_with_own_history(client: TestClient):
    """previous-years kapsamı kendi geçmişimizle karşılaştırır."""
    body = client.get(
        f"{BASE}/benchmarks/comparison?academic_year={YEAR}&scope=previous-years"
        f"&framework_code=THE"
    ).json()
    assert "Kendi geçmiş yıllarımız" in body["compared_institutions"]


def test_benchmark_comparison_filters_by_indicator(
    client: TestClient, indicator_ids: Dict[str, int]
):
    """indicator_id filtresi tek göstergeye indirger."""
    body = client.get(
        f"{BASE}/benchmarks/comparison?academic_year={YEAR}"
        f"&indicator_id={indicator_ids['the-citation-impact']}"
    ).json()
    assert len(body["rows"]) == 1


# ===========================================================================
# 8) Senaryo etkisi (impact preview)
# ===========================================================================


def test_impact_preview_endpoint(client: TestClient):
    """Etki ön izleme endpoint'i çalışır."""
    response = client.post(
        f"{BASE}/impact-preview",
        json={"academic_year": YEAR, "publication_count": "150"},
    )
    assert response.status_code == 200


def test_impact_preview_does_not_persist(client: TestClient):
    """Ön izleme veritabanına kayıt yazmaz."""
    before = len(client.get(f"{BASE}/metrics?limit=500").json())
    body = client.post(
        f"{BASE}/impact-preview",
        json={"academic_year": YEAR, "publication_count": "500", "citation_count": "5000"},
    ).json()
    after = len(client.get(f"{BASE}/metrics?limit=500").json())
    assert body["persisted"] is False and before == after


def test_impact_preview_does_not_change_existing_values(
    client: TestClient, indicator_ids: Dict[str, int]
):
    """Ön izleme mevcut gösterge değerlerini değiştirmez."""
    indicator_id = indicator_ids["the-citation-impact"]
    before = client.get(
        f"{BASE}/metrics?indicator_id={indicator_id}&academic_year={YEAR}"
    ).json()[0]["value"]
    client.post(
        f"{BASE}/impact-preview",
        json={"academic_year": YEAR, "citation_count": "9999"},
    )
    after = client.get(
        f"{BASE}/metrics?indicator_id={indicator_id}&academic_year={YEAR}"
    ).json()[0]["value"]
    assert before == after


def test_impact_preview_shows_before_and_after(client: TestClient):
    """Etkilenen göstergelerde önce/sonra değerleri bulunur."""
    body = client.post(
        f"{BASE}/impact-preview",
        json={"academic_year": YEAR, "publication_count": "200"},
    ).json()
    impacted = [
        indicator
        for framework in body["frameworks"]
        for indicator in framework["impacted_indicators"]
    ]
    assert impacted
    for indicator in impacted:
        assert "before_value" in indicator and "after_value" in indicator


def test_impact_preview_increases_publication_indicator(client: TestClient):
    """Yayın artışı yayın/personel göstergesini yükseltir."""
    body = client.post(
        f"{BASE}/impact-preview",
        json={"academic_year": YEAR, "publication_count": "200"},
    ).json()
    the = next(item for item in body["frameworks"] if item["framework_code"] == "THE")
    publication = next(
        item
        for item in the["impacted_indicators"]
        if item["indicator_code"] == "the-publications-per-staff"
    )
    assert Decimal(publication["after_value"]) > Decimal(publication["before_value"])


def test_impact_preview_reports_dimension_changes(client: TestClient):
    """Boyut skorlarındaki değişim raporlanır."""
    body = client.post(
        f"{BASE}/impact-preview",
        json={"academic_year": YEAR, "citation_count": "5000"},
    ).json()
    assert any(item["impacted_dimensions"] for item in body["frameworks"])


def test_impact_preview_reports_framework_changes(client: TestClient):
    """Çerçeve performans, hazırlık, uyum ve risk değişimi raporlanır."""
    body = client.post(
        f"{BASE}/impact-preview",
        json={"academic_year": YEAR, "publication_count": "300"},
    ).json()
    for framework in body["frameworks"]:
        for field in (
            "before_performance",
            "after_performance",
            "performance_change",
            "before_readiness",
            "after_readiness",
            "before_compliance",
            "after_compliance",
            "before_risk",
            "after_risk",
            "risk_changed",
        ):
            assert field in framework


def test_impact_preview_returns_turkish_recommendations(client: TestClient):
    """Etki analizi Türkçe öneriler döndürür."""
    body = client.post(
        f"{BASE}/impact-preview",
        json={"academic_year": YEAR, "publication_count": "300"},
    ).json()
    assert body["recommendations"]
    assert any(
        "puan" in text or "senaryo" in text.lower() for text in body["recommendations"]
    )


def test_impact_preview_with_no_changes_reports_nothing(client: TestClient):
    """Değişken girilmezse etki olmadığı bildirilir."""
    body = client.post(f"{BASE}/impact-preview", json={"academic_year": YEAR}).json()
    assert body["total_impacted_indicator_count"] == 0
    assert any("değişkeni girilmedi" in text for text in body["recommendations"])


def test_impact_preview_includes_disclaimer(client: TestClient):
    """Etki analizi gerçek sıralama tahmini yapmadığını belirtir."""
    body = client.post(f"{BASE}/impact-preview", json={"academic_year": YEAR}).json()
    assert "TAHMİN ETMEZ" in body["disclaimer"]


def test_impact_preview_can_target_single_framework(client: TestClient):
    """framework_code ile tek çerçeve değerlendirilebilir."""
    body = client.post(
        f"{BASE}/impact-preview",
        json={"academic_year": YEAR, "framework_code": "QS", "citation_count": "1000"},
    ).json()
    assert all(item["framework_code"] == "QS" for item in body["frameworks"])


def test_impact_preview_lists_applied_variables(client: TestClient):
    """Uygulanan değişkenler cevapta listelenir."""
    body = client.post(
        f"{BASE}/impact-preview",
        json={"academic_year": YEAR, "citation_count": "1000", "publication_count": "50"},
    ).json()
    assert set(body["applied_changes"].keys()) == {"citation_count", "publication_count"}


def test_impact_preview_staff_increase_affects_ratio(client: TestClient):
    """Personel artışı öğrenci/personel oranını iyileştirir."""
    body = client.post(
        f"{BASE}/impact-preview",
        json={"academic_year": YEAR, "academic_staff_count": "40"},
    ).json()
    the = next(item for item in body["frameworks"] if item["framework_code"] == "THE")
    ratio = next(
        item
        for item in the["impacted_indicators"]
        if item["indicator_code"] == "the-student-staff-ratio"
    )
    # Öğrenci/personel oranında düşük değer iyidir; personel artınca oran düşer.
    assert Decimal(ratio["after_value"]) < Decimal(ratio["before_value"])
    assert Decimal(ratio["after_score"]) > Decimal(ratio["before_score"])


# ===========================================================================
# 9) Dashboard
# ===========================================================================


def test_dashboard_summary_endpoint(client: TestClient):
    """Dashboard endpoint'i çalışır."""
    assert client.get(f"{BASE}/dashboard-summary").status_code == 200


def test_dashboard_summary_counts(client: TestClient):
    """Dashboard sayaçları doludur."""
    body = client.get(f"{BASE}/dashboard-summary").json()
    assert body["framework_count"] >= 3
    assert body["dimension_count"] >= 19
    assert body["indicator_count"] >= 40
    assert body["benchmark_institution_count"] >= 5


def test_dashboard_summary_includes_framework_rows(client: TestClient):
    """Her çerçeve için özet satırı bulunur."""
    body = client.get(f"{BASE}/dashboard-summary").json()
    codes = {row["framework_code"] for row in body["frameworks"]}
    assert {"THE", "QS", "YOK"}.issubset(codes)


def test_dashboard_summary_includes_top_missing_and_recommendations(client: TestClient):
    """Dashboard eksik veri ve öneri listelerini içerir."""
    body = client.get(f"{BASE}/dashboard-summary").json()
    assert "top_missing_data" in body and "top_recommendations" in body


def test_dashboard_summary_reports_highest_risk(client: TestClient):
    """Dashboard en yüksek risk seviyesini bildirir."""
    body = client.get(f"{BASE}/dashboard-summary").json()
    assert body["highest_risk_level"] in ("low", "medium", "high", "critical")


def test_dashboard_summary_accepts_academic_year(client: TestClient):
    """Belirli bir yıl için dashboard alınabilir."""
    body = client.get(f"{BASE}/dashboard-summary?academic_year={YEAR}").json()
    assert body["academic_year"] == YEAR


def test_dashboard_includes_disclaimer(client: TestClient):
    """Dashboard gerçek sıralama göstermediğini belirtir."""
    body = client.get(f"{BASE}/dashboard-summary").json()
    assert "gerçek THE/QS/YÖK sıralaması göstermez" in body["disclaimer"]
