"""CRUD endpoint testleri (Modül 10)."""

from typing import Dict

import pytest
from fastapi.testclient import TestClient

BASE: str = "/api/ranking-evaluations"


# ===========================================================================
# Framework CRUD
# ===========================================================================


def test_list_frameworks_returns_seeded_data(client: TestClient):
    """Seed'den gelen üç çerçeve listelenir."""
    response = client.get(f"{BASE}/frameworks")
    assert response.status_code == 200
    codes = {item["code"] for item in response.json()}
    assert {"THE", "QS", "YOK"}.issubset(codes)


def test_framework_list_reports_balanced_weights(client: TestClient):
    """Seed çerçevelerinin boyut ağırlıkları 100 toplar."""
    for item in client.get(f"{BASE}/frameworks").json():
        assert item["total_dimension_weight"] == "100.00"
        assert item["weight_is_balanced"] is True


def test_framework_list_filters_by_code(client: TestClient):
    """framework_code filtresi çalışır."""
    response = client.get(f"{BASE}/frameworks?framework_code=QS")
    assert all(item["code"] == "QS" for item in response.json())


def test_framework_list_filters_by_active(client: TestClient):
    """is_active filtresi çalışır."""
    response = client.get(f"{BASE}/frameworks?is_active=true")
    assert all(item["is_active"] is True for item in response.json())


def test_framework_list_supports_pagination(client: TestClient):
    """skip/limit sayfalaması çalışır."""
    response = client.get(f"{BASE}/frameworks?skip=0&limit=1")
    assert len(response.json()) == 1


def test_create_framework(client: TestClient):
    """Yeni çerçeve oluşturulabilir."""
    response = client.post(
        f"{BASE}/frameworks",
        json={"code": "THE", "name": "THE Test 2001", "methodology_year": 2001},
    )
    assert response.status_code == 201
    assert response.json()["methodology_year"] == 2001


def test_create_framework_duplicate_code_and_year_conflicts(client: TestClient):
    """Aynı kod + metodoloji yılı ikinci kez eklenemez."""
    payload = {"code": "QS", "name": "QS Test 2002", "methodology_year": 2002}
    assert client.post(f"{BASE}/frameworks", json=payload).status_code == 201
    duplicate = client.post(f"{BASE}/frameworks", json=payload)
    assert duplicate.status_code == 409
    assert "zaten tanımlı" in duplicate.json()["detail"]


def test_same_code_different_year_is_allowed(client: TestClient):
    """Aynı kod farklı metodoloji yılıyla eklenebilir."""
    first = client.post(
        f"{BASE}/frameworks",
        json={"code": "YOK", "name": "YOK 2003", "methodology_year": 2003},
    )
    second = client.post(
        f"{BASE}/frameworks",
        json={"code": "YOK", "name": "YOK 2004", "methodology_year": 2004},
    )
    assert first.status_code == 201 and second.status_code == 201


def test_get_framework_detail(client: TestClient, framework_ids: Dict[str, int]):
    """Çerçeve detayı boyut ve gösterge sayısıyla döner."""
    response = client.get(f"{BASE}/frameworks/{framework_ids['THE']}")
    assert response.status_code == 200
    assert response.json()["dimension_count"] == 5


def test_get_missing_framework_returns_404(client: TestClient):
    """Olmayan çerçeve 404 döndürür."""
    assert client.get(f"{BASE}/frameworks/999999").status_code == 404


def test_update_framework(client: TestClient):
    """Çerçeve güncellenebilir."""
    created = client.post(
        f"{BASE}/frameworks",
        json={"code": "THE", "name": "Update Test", "methodology_year": 2005},
    ).json()
    response = client.put(
        f"{BASE}/frameworks/{created['id']}", json={"name": "Updated Name"}
    )
    assert response.status_code == 200 and response.json()["name"] == "Updated Name"


def test_update_framework_to_existing_key_conflicts(client: TestClient):
    """Güncelleme sonucu mevcut bir kod+yıl ile çakışırsa 409 döner."""
    client.post(
        f"{BASE}/frameworks",
        json={"code": "THE", "name": "Conflict A", "methodology_year": 2006},
    )
    target = client.post(
        f"{BASE}/frameworks",
        json={"code": "THE", "name": "Conflict B", "methodology_year": 2007},
    ).json()
    response = client.put(
        f"{BASE}/frameworks/{target['id']}", json={"methodology_year": 2006}
    )
    assert response.status_code == 409


def test_update_missing_framework_returns_404(client: TestClient):
    """Olmayan çerçeve güncellenemez."""
    assert client.put(f"{BASE}/frameworks/999999", json={"name": "X Y"}).status_code == 404


def test_delete_framework_is_soft_delete(client: TestClient):
    """DELETE fiziksel silme yapmaz, pasifleştirir."""
    created = client.post(
        f"{BASE}/frameworks",
        json={"code": "QS", "name": "Soft Delete Test", "methodology_year": 2008},
    ).json()
    response = client.delete(f"{BASE}/frameworks/{created['id']}")
    assert response.status_code == 200 and response.json()["is_active"] is False
    assert client.get(f"{BASE}/frameworks/{created['id']}").status_code == 200


# ===========================================================================
# Dimension CRUD
# ===========================================================================


def test_list_dimensions(client: TestClient):
    """Boyutlar listelenebilir."""
    response = client.get(f"{BASE}/dimensions")
    assert response.status_code == 200 and len(response.json()) >= 19


def test_list_dimensions_filters_by_framework_code(client: TestClient):
    """framework_code filtresi boyutları daraltır."""
    response = client.get(f"{BASE}/dimensions?framework_code=THE")
    assert all(item["framework_code"] == "THE" for item in response.json())
    assert len(response.json()) == 5


def test_list_dimensions_filters_by_framework_id(
    client: TestClient, framework_ids: Dict[str, int]
):
    """framework_id filtresi çalışır."""
    response = client.get(f"{BASE}/dimensions?framework_id={framework_ids['QS']}")
    assert len(response.json()) == 9


def test_dimension_indicator_weights_are_balanced(client: TestClient):
    """Seed boyutlarındaki gösterge ağırlıkları 100 toplar."""
    for item in client.get(f"{BASE}/dimensions?framework_code=THE").json():
        assert item["weight_is_balanced"] is True


def test_create_dimension(client: TestClient, framework_ids: Dict[str, int]):
    """Yeni boyut oluşturulabilir."""
    response = client.post(
        f"{BASE}/dimensions",
        json={
            "framework_id": framework_ids["THE"],
            "code": "crud-test-dimension",
            "name": "CRUD Test Dimension",
            "weight": "10.00",
        },
    )
    assert response.status_code == 201
    assert response.json()["code"] == "crud-test-dimension"


def test_create_dimension_duplicate_code_conflicts(
    client: TestClient, framework_ids: Dict[str, int]
):
    """Aynı çerçevede aynı boyut kodu ikinci kez eklenemez."""
    payload = {
        "framework_id": framework_ids["QS"],
        "code": "duplicate-dimension",
        "name": "Duplicate",
        "weight": "5",
    }
    assert client.post(f"{BASE}/dimensions", json=payload).status_code == 201
    assert client.post(f"{BASE}/dimensions", json=payload).status_code == 409


def test_same_dimension_code_in_other_framework_is_allowed(
    client: TestClient, framework_ids: Dict[str, int]
):
    """Farklı çerçevelerde aynı boyut kodu kullanılabilir."""
    response = client.post(
        f"{BASE}/dimensions",
        json={
            "framework_id": framework_ids["YOK"],
            "code": "duplicate-dimension",
            "name": "Duplicate In Other Framework",
            "weight": "5",
        },
    )
    assert response.status_code == 201


def test_create_dimension_with_invalid_framework_returns_404(client: TestClient):
    """Geçersiz framework_id 404 döndürür."""
    response = client.post(
        f"{BASE}/dimensions",
        json={"framework_id": 999999, "code": "ghost", "name": "Ghost", "weight": "5"},
    )
    assert response.status_code == 404


def test_get_dimension_detail(client: TestClient):
    """Boyut detayı gösterge sayısıyla döner."""
    # Seed'den gelen bir boyut seçiyoruz; testlerin eklediği geçici boyutlarda
    # henüz gösterge bulunmadığı için sonuç yanıltıcı olurdu.
    dimensions = client.get(f"{BASE}/dimensions?framework_code=THE").json()
    seeded = next(item for item in dimensions if item["code"] == "research-quality")
    response = client.get(f"{BASE}/dimensions/{seeded['id']}")
    assert response.status_code == 200 and response.json()["indicator_count"] >= 1


def test_get_missing_dimension_returns_404(client: TestClient):
    """Olmayan boyut 404 döndürür."""
    assert client.get(f"{BASE}/dimensions/999999").status_code == 404


def test_update_dimension_weight(client: TestClient, framework_ids: Dict[str, int]):
    """Boyut ağırlığı güncellenebilir."""
    created = client.post(
        f"{BASE}/dimensions",
        json={
            "framework_id": framework_ids["THE"],
            "code": "weight-update-test",
            "name": "Weight Update",
            "weight": "10",
        },
    ).json()
    response = client.put(f"{BASE}/dimensions/{created['id']}", json={"weight": "12.50"})
    assert response.status_code == 200 and response.json()["weight"] == "12.50"


def test_update_dimension_rejects_invalid_weight(
    client: TestClient, framework_ids: Dict[str, int]
):
    """Aralık dışı ağırlık güncellemesi reddedilir."""
    created = client.post(
        f"{BASE}/dimensions",
        json={
            "framework_id": framework_ids["THE"],
            "code": "bad-weight-test",
            "name": "Bad Weight",
            "weight": "10",
        },
    ).json()
    assert (
        client.put(f"{BASE}/dimensions/{created['id']}", json={"weight": "150"}).status_code
        == 422
    )


def test_delete_dimension_is_soft_delete(
    client: TestClient, framework_ids: Dict[str, int]
):
    """Boyut silinmez, pasifleştirilir."""
    created = client.post(
        f"{BASE}/dimensions",
        json={
            "framework_id": framework_ids["YOK"],
            "code": "soft-delete-dimension",
            "name": "Soft Delete",
            "weight": "5",
        },
    ).json()
    response = client.delete(f"{BASE}/dimensions/{created['id']}")
    assert response.status_code == 200 and response.json()["is_active"] is False


# ===========================================================================
# Indicator CRUD
# ===========================================================================


def test_list_indicators(client: TestClient):
    """Göstergeler listelenebilir."""
    response = client.get(f"{BASE}/indicators?limit=500")
    assert response.status_code == 200 and len(response.json()) >= 40


def test_list_indicators_filters_by_framework(client: TestClient):
    """framework_code filtresi göstergeleri daraltır."""
    response = client.get(f"{BASE}/indicators?framework_code=QS&limit=500")
    assert all(item["framework_code"] == "QS" for item in response.json())


def test_list_indicators_filters_by_required_for_readiness(client: TestClient):
    """required_for_readiness filtresi çalışır."""
    response = client.get(f"{BASE}/indicators?required_for_readiness=false&limit=500")
    assert all(item["required_for_readiness"] is False for item in response.json())


def test_indicator_response_includes_unit_when_defined(client: TestClient):
    """Birim tanımlıysa cevapta gösterilir."""
    indicators = client.get(f"{BASE}/indicators?framework_code=THE&limit=500").json()
    ratio_indicator = next(
        item for item in indicators if item["code"] == "the-international-student-ratio"
    )
    assert ratio_indicator["unit"] == "%"


def test_create_indicator(client: TestClient):
    """Yeni gösterge oluşturulabilir."""
    dimension_id = client.get(f"{BASE}/dimensions?framework_code=THE").json()[0]["id"]
    response = client.post(
        f"{BASE}/indicators",
        json={
            "dimension_id": dimension_id,
            "code": "crud-test-indicator",
            "name": "CRUD Test Indicator",
            "calculation_type": "ratio",
            "weight": "10",
            "direction": "higher_is_better",
            "minimum_value": "0",
            "target_value": "10",
        },
    )
    assert response.status_code == 201


def test_create_indicator_duplicate_code_conflicts(client: TestClient):
    """Gösterge kodu sistem genelinde benzersizdir."""
    dimension_id = client.get(f"{BASE}/dimensions?framework_code=QS").json()[0]["id"]
    payload = {
        "dimension_id": dimension_id,
        "code": "duplicate-indicator-code",
        "name": "Duplicate Indicator",
        "weight": "10",
    }
    assert client.post(f"{BASE}/indicators", json=payload).status_code == 201
    conflict = client.post(f"{BASE}/indicators", json=payload)
    assert conflict.status_code == 409
    assert "benzersiz" in conflict.json()["detail"]


def test_create_indicator_with_invalid_dimension_returns_404(client: TestClient):
    """Geçersiz dimension_id 404 döndürür."""
    response = client.post(
        f"{BASE}/indicators",
        json={
            "dimension_id": 999999,
            "code": "ghost-indicator",
            "name": "Ghost",
            "weight": "10",
        },
    )
    assert response.status_code == 404


def test_create_indicator_with_invalid_bounds_returns_422(client: TestClient):
    """Tutarsız sınır değerleri 422 döndürür."""
    dimension_id = client.get(f"{BASE}/dimensions?framework_code=THE").json()[0]["id"]
    response = client.post(
        f"{BASE}/indicators",
        json={
            "dimension_id": dimension_id,
            "code": "bad-bounds-indicator",
            "name": "Bad Bounds",
            "weight": "10",
            "minimum_value": "100",
            "maximum_value": "10",
        },
    )
    assert response.status_code == 422


def test_get_indicator_detail(client: TestClient, indicator_ids: Dict[str, int]):
    """Gösterge detayı boyut ve çerçeve bilgisiyle döner."""
    response = client.get(f"{BASE}/indicators/{indicator_ids['the-citation-impact']}")
    assert response.status_code == 200
    assert response.json()["framework_code"] == "THE"
    assert response.json()["dimension_code"] == "research-quality"


def test_get_missing_indicator_returns_404(client: TestClient):
    """Olmayan gösterge 404 döndürür."""
    assert client.get(f"{BASE}/indicators/999999").status_code == 404


def test_update_indicator_target(client: TestClient):
    """Gösterge hedef değeri güncellenebilir."""
    dimension_id = client.get(f"{BASE}/dimensions?framework_code=YOK").json()[0]["id"]
    created = client.post(
        f"{BASE}/indicators",
        json={
            "dimension_id": dimension_id,
            "code": "target-update-indicator",
            "name": "Target Update",
            "weight": "10",
            "minimum_value": "0",
            "target_value": "10",
            "maximum_value": "20",
        },
    ).json()
    response = client.put(
        f"{BASE}/indicators/{created['id']}", json={"target_value": "15"}
    )
    assert response.status_code == 200 and response.json()["target_value"] == "15.00"


def test_update_indicator_with_inconsistent_bounds_returns_422(client: TestClient):
    """Güncelleme sonucu sınırlar tutarsızlaşırsa 422 döner."""
    dimension_id = client.get(f"{BASE}/dimensions?framework_code=YOK").json()[0]["id"]
    created = client.post(
        f"{BASE}/indicators",
        json={
            "dimension_id": dimension_id,
            "code": "bound-check-indicator",
            "name": "Bound Check",
            "weight": "10",
            "minimum_value": "0",
            "target_value": "10",
            "maximum_value": "20",
        },
    ).json()
    response = client.put(
        f"{BASE}/indicators/{created['id']}", json={"target_value": "50"}
    )
    assert response.status_code == 422


def test_delete_indicator_is_soft_delete(client: TestClient):
    """Gösterge silinmez, pasifleştirilir."""
    dimension_id = client.get(f"{BASE}/dimensions?framework_code=QS").json()[0]["id"]
    created = client.post(
        f"{BASE}/indicators",
        json={
            "dimension_id": dimension_id,
            "code": "soft-delete-indicator",
            "name": "Soft Delete Indicator",
            "weight": "10",
        },
    ).json()
    response = client.delete(f"{BASE}/indicators/{created['id']}")
    assert response.status_code == 200 and response.json()["is_active"] is False


# ===========================================================================
# Metric CRUD
# ===========================================================================


def test_list_metrics(client: TestClient):
    """Gösterge verileri listelenebilir."""
    response = client.get(f"{BASE}/metrics?limit=500")
    assert response.status_code == 200 and len(response.json()) > 0


def test_metric_list_includes_calculated_fields(client: TestClient):
    """Liste cevabında etkin değer ve performans skoru bulunur."""
    metrics = client.get(
        f"{BASE}/metrics?indicator_id=1&academic_year=2025-2026"
    ).json()
    if metrics:
        assert "effective_value" in metrics[0]
        assert "performance_score" in metrics[0]


@pytest.mark.parametrize("status", ["available", "partial", "estimated"])
def test_metric_list_filters_by_data_status(client: TestClient, status):
    """data_status filtresi çalışır."""
    response = client.get(f"{BASE}/metrics?data_status={status}&limit=500")
    assert all(item["data_status"] == status for item in response.json())


def test_metric_list_filters_by_framework(client: TestClient):
    """framework_code filtresi çalışır."""
    response = client.get(f"{BASE}/metrics?framework_code=YOK&limit=500")
    assert all(item["framework_code"] == "YOK" for item in response.json())


def test_metric_list_filters_by_academic_year(client: TestClient):
    """academic_year filtresi çalışır."""
    response = client.get(f"{BASE}/metrics?academic_year=2023-2024&limit=500")
    assert all(item["academic_year"] == "2023-2024" for item in response.json())


def test_metric_list_filters_by_origin(client: TestClient):
    """origin filtresi çalışır."""
    response = client.get(f"{BASE}/metrics?origin=automatic&limit=500")
    assert all(item["origin"] == "automatic" for item in response.json())


def test_create_metric(client: TestClient, indicator_ids: Dict[str, int]):
    """Yeni gösterge verisi oluşturulabilir."""
    response = client.post(
        f"{BASE}/metrics",
        json={
            "indicator_id": indicator_ids["the-patent-count"],
            "academic_year": "2020-2021",
            "value": "2",
        },
    )
    assert response.status_code == 201


def test_create_duplicate_metric_period_conflicts(
    client: TestClient, indicator_ids: Dict[str, int]
):
    """Aynı gösterge + yıl + dönem ikinci kez eklenemez."""
    payload = {
        "indicator_id": indicator_ids["the-patent-count"],
        "academic_year": "2019-2020",
        "value": "1",
    }
    assert client.post(f"{BASE}/metrics", json=payload).status_code == 201
    conflict = client.post(f"{BASE}/metrics", json=payload)
    assert conflict.status_code == 409
    assert "zaten mevcut" in conflict.json()["detail"]


def test_same_indicator_different_period_is_allowed(
    client: TestClient, indicator_ids: Dict[str, int]
):
    """Aynı gösterge farklı dönemle eklenebilir."""
    response = client.post(
        f"{BASE}/metrics",
        json={
            "indicator_id": indicator_ids["the-patent-count"],
            "academic_year": "2019-2020",
            "period": "fall",
            "value": "1",
        },
    )
    assert response.status_code == 201


def test_create_metric_with_invalid_indicator_returns_404(client: TestClient):
    """Geçersiz indicator_id 404 döndürür."""
    response = client.post(
        f"{BASE}/metrics",
        json={"indicator_id": 999999, "academic_year": "2025-2026", "value": "1"},
    )
    assert response.status_code == 404


def test_create_metric_with_zero_denominator_returns_422(
    client: TestClient, indicator_ids: Dict[str, int]
):
    """Payda sıfır olan veri reddedilir."""
    response = client.post(
        f"{BASE}/metrics",
        json={
            "indicator_id": indicator_ids["the-citation-impact"],
            "academic_year": "2018-2019",
            "numerator": "10",
            "denominator": "0",
        },
    )
    assert response.status_code == 422


def test_get_metric_detail(client: TestClient):
    """Gösterge verisi detayı hesaplanmış değerle döner."""
    metric_id = client.get(f"{BASE}/metrics?limit=1").json()[0]["id"]
    response = client.get(f"{BASE}/metrics/{metric_id}")
    assert response.status_code == 200 and "effective_value" in response.json()


def test_get_missing_metric_returns_404(client: TestClient):
    """Olmayan gösterge verisi 404 döndürür."""
    assert client.get(f"{BASE}/metrics/999999").status_code == 404


def test_update_metric(client: TestClient, indicator_ids: Dict[str, int]):
    """Gösterge verisi güncellenebilir."""
    created = client.post(
        f"{BASE}/metrics",
        json={
            "indicator_id": indicator_ids["the-patent-count"],
            "academic_year": "2017-2018",
            "value": "3",
        },
    ).json()
    response = client.put(f"{BASE}/metrics/{created['id']}", json={"value": "9"})
    assert response.status_code == 200 and response.json()["value"] == "9.00"


def test_update_metric_to_existing_period_conflicts(
    client: TestClient, indicator_ids: Dict[str, int]
):
    """Güncelleme sonucu aynı dönem çakışırsa 409 döner."""
    client.post(
        f"{BASE}/metrics",
        json={
            "indicator_id": indicator_ids["yok-volunteer-hours"],
            "academic_year": "2016-2017",
            "value": "100",
        },
    )
    second = client.post(
        f"{BASE}/metrics",
        json={
            "indicator_id": indicator_ids["yok-volunteer-hours"],
            "academic_year": "2015-2016",
            "value": "200",
        },
    ).json()
    response = client.put(
        f"{BASE}/metrics/{second['id']}", json={"academic_year": "2016-2017"}
    )
    assert response.status_code == 409


def test_delete_metric(client: TestClient, indicator_ids: Dict[str, int]):
    """Gösterge verisi silinebilir."""
    created = client.post(
        f"{BASE}/metrics",
        json={
            "indicator_id": indicator_ids["the-patent-count"],
            "academic_year": "2014-2015",
            "value": "1",
        },
    ).json()
    assert client.delete(f"{BASE}/metrics/{created['id']}").status_code == 204
    assert client.get(f"{BASE}/metrics/{created['id']}").status_code == 404


# ===========================================================================
# Benchmark institution CRUD
# ===========================================================================


def test_list_benchmark_institutions(client: TestClient):
    """Karşılaştırma kurumları listelenebilir."""
    response = client.get(f"{BASE}/benchmarks/institutions")
    assert response.status_code == 200 and len(response.json()) >= 5


def test_seed_contains_three_national_and_two_competitor_institutions(client: TestClient):
    """Seed en az 3 Türkiye kurumu ve 2 rakip içerir."""
    institutions = client.get(f"{BASE}/benchmarks/institutions").json()
    turkish = [item for item in institutions if item["country"] == "Türkiye"]
    competitors = [item for item in institutions if item["is_competitor"]]
    assert len(turkish) >= 3 and len(competitors) >= 2


def test_benchmark_institutions_are_marked_as_demo(client: TestClient):
    """Seed kurumlarının demo olduğu notlarda belirtilir."""
    institutions = client.get(f"{BASE}/benchmarks/institutions").json()
    seeded = [item for item in institutions if item["notes"]]
    assert any("DEMO" in item["notes"] for item in seeded)


def test_filter_benchmark_institutions_by_competitor(client: TestClient):
    """is_competitor filtresi çalışır."""
    response = client.get(f"{BASE}/benchmarks/institutions?is_competitor=true")
    assert all(item["is_competitor"] is True for item in response.json())


def test_filter_benchmark_institutions_by_type(client: TestClient):
    """institution_type filtresi çalışır."""
    response = client.get(f"{BASE}/benchmarks/institutions?institution_type=similar")
    assert all(item["institution_type"] == "similar" for item in response.json())


def test_create_benchmark_institution(client: TestClient):
    """Yeni karşılaştırma kurumu eklenebilir."""
    response = client.post(
        f"{BASE}/benchmarks/institutions",
        json={
            "name": "CRUD Test Üniversitesi (demo)",
            "country": "Türkiye",
            "city": "Ankara",
            "institution_type": "similar",
        },
    )
    assert response.status_code == 201


def test_create_duplicate_benchmark_institution_conflicts(client: TestClient):
    """Aynı isimli kurum ikinci kez eklenemez."""
    payload = {"name": "Duplicate Test Üniversitesi (demo)", "country": "Türkiye"}
    assert client.post(f"{BASE}/benchmarks/institutions", json=payload).status_code == 201
    assert client.post(f"{BASE}/benchmarks/institutions", json=payload).status_code == 409


def test_get_benchmark_institution_detail(client: TestClient):
    """Karşılaştırma kurumu detayı getirilebilir."""
    institution_id = client.get(f"{BASE}/benchmarks/institutions").json()[0]["id"]
    assert client.get(f"{BASE}/benchmarks/institutions/{institution_id}").status_code == 200


def test_get_missing_benchmark_institution_returns_404(client: TestClient):
    """Olmayan kurum 404 döndürür."""
    assert client.get(f"{BASE}/benchmarks/institutions/999999").status_code == 404


def test_update_benchmark_institution(client: TestClient):
    """Karşılaştırma kurumu güncellenebilir."""
    created = client.post(
        f"{BASE}/benchmarks/institutions",
        json={"name": "Update Test Üniversitesi (demo)", "country": "Türkiye"},
    ).json()
    response = client.put(
        f"{BASE}/benchmarks/institutions/{created['id']}", json={"city": "İzmir"}
    )
    assert response.status_code == 200 and response.json()["city"] == "İzmir"


def test_delete_benchmark_institution_is_soft_delete(client: TestClient):
    """Kurum silinmez, pasifleştirilir."""
    created = client.post(
        f"{BASE}/benchmarks/institutions",
        json={"name": "Soft Delete Üniversitesi (demo)", "country": "Türkiye"},
    ).json()
    response = client.delete(f"{BASE}/benchmarks/institutions/{created['id']}")
    assert response.status_code == 200 and response.json()["is_active"] is False


def test_create_benchmark_value(client: TestClient, indicator_ids: Dict[str, int]):
    """Karşılaştırma gösterge değeri eklenebilir."""
    institution = client.post(
        f"{BASE}/benchmarks/institutions",
        json={"name": "Value Test Üniversitesi (demo)", "country": "Türkiye"},
    ).json()
    response = client.post(
        f"{BASE}/benchmarks/values",
        json={
            "benchmark_institution_id": institution["id"],
            "indicator_id": indicator_ids["the-citation-impact"],
            "academic_year": "2025-2026",
            "value": "3.20",
        },
    )
    assert response.status_code == 201


def test_create_duplicate_benchmark_value_conflicts(
    client: TestClient, indicator_ids: Dict[str, int]
):
    """Aynı kurum + gösterge + yıl + dönem ikinci kez eklenemez."""
    institution = client.post(
        f"{BASE}/benchmarks/institutions",
        json={"name": "Duplicate Value Üniversitesi (demo)", "country": "Türkiye"},
    ).json()
    payload = {
        "benchmark_institution_id": institution["id"],
        "indicator_id": indicator_ids["the-patent-count"],
        "academic_year": "2025-2026",
        "value": "5",
    }
    assert client.post(f"{BASE}/benchmarks/values", json=payload).status_code == 201
    assert client.post(f"{BASE}/benchmarks/values", json=payload).status_code == 409


def test_create_benchmark_value_with_invalid_indicator_returns_404(client: TestClient):
    """Geçersiz gösterge 404 döndürür."""
    institution = client.get(f"{BASE}/benchmarks/institutions").json()[0]
    response = client.post(
        f"{BASE}/benchmarks/values",
        json={
            "benchmark_institution_id": institution["id"],
            "indicator_id": 999999,
            "academic_year": "2025-2026",
            "value": "1",
        },
    )
    assert response.status_code == 404
