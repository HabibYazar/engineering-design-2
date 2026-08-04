"""Mevcut modüllerin (1, 2, 9, 13) bozulmadığını doğrulayan regresyon testleri."""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient


# ===========================================================================
# Genel uygulama
# ===========================================================================


@pytest.mark.parametrize("path", ["/", "/health", "/docs", "/openapi.json"])
def test_core_endpoints_respond(client: TestClient, path):
    """Kök, sağlık ve dokümantasyon endpoint'leri çalışır."""
    assert client.get(path).status_code == 200


def test_health_reports_healthy(client: TestClient):
    """Sağlık kontrolü 'healthy' döndürür."""
    assert client.get("/health").json()["status"] == "healthy"


def test_openapi_contains_all_module_paths(client: TestClient):
    """OpenAPI şeması dört modülün de yollarını içerir."""
    paths = client.get("/openapi.json").json()["paths"]
    assert any(path.startswith("/api/faculties") for path in paths)
    assert any(path.startswith("/api/students") for path in paths)
    assert any(path.startswith("/api/scenarios") for path in paths)
    assert any(path.startswith("/api/data-integration") for path in paths)
    assert any(path.startswith("/api/ranking-evaluations") for path in paths)


# ===========================================================================
# Modül 1 - Üniversite yapısı
# ===========================================================================


@pytest.mark.parametrize(
    "path",
    [
        "/api/faculties",
        "/api/departments",
        "/api/programs",
        "/api/administrative-units",
    ],
)
def test_module1_list_endpoints(client: TestClient, path):
    """Modül 1 listeleme endpoint'leri çalışır."""
    assert client.get(path).status_code == 200


def test_module1_seed_data_present(client: TestClient):
    """Modül 1 seed verisi yerinde durur."""
    codes = {item["code"] for item in client.get("/api/faculties?limit=500").json()}
    assert "FEA" in codes


def test_module1_create_faculty(client: TestClient):
    """Fakülte oluşturma 201 döndürür."""
    response = client.post(
        "/api/faculties", json={"name": "Regression Faculty M10", "code": "M10REG"}
    )
    assert response.status_code == 201


def test_module1_duplicate_code_conflicts(client: TestClient):
    """Tekrar eden fakülte kodu 409 döndürür."""
    client.post("/api/faculties", json={"name": "Dup Faculty M10", "code": "M10DUP"})
    response = client.post(
        "/api/faculties", json={"name": "Dup Faculty M10 B", "code": "M10DUP"}
    )
    assert response.status_code == 409


def test_module1_missing_id_returns_404(client: TestClient):
    """Olmayan fakülte 404 döndürür."""
    assert client.get("/api/faculties/999999").status_code == 404


def test_module1_soft_delete_preserved(client: TestClient):
    """Fakülte silinmez, pasifleştirilir."""
    created = client.post(
        "/api/faculties", json={"name": "Soft Delete M10", "code": "M10SD"}
    ).json()
    response = client.delete(f"/api/faculties/{created['id']}")
    assert response.status_code == 200 and response.json()["is_active"] is False


def test_module1_department_requires_valid_faculty(client: TestClient):
    """Geçersiz faculty_id 404 döndürür."""
    response = client.post(
        "/api/departments",
        json={"faculty_id": 999999, "name": "Ghost Dept", "code": "M10GH"},
    )
    assert response.status_code == 404


# ===========================================================================
# Modül 2 - Öğrenci analitiği
# ===========================================================================


@pytest.mark.parametrize(
    "path",
    [
        "/api/students",
        "/api/student-analytics/overview",
        "/api/student-analytics/by-program",
        "/api/student-analytics/by-department",
        "/api/student-analytics/by-faculty",
        "/api/student-analytics/alerts",
        "/api/student-analytics/program-snapshots",
        "/api/student-analytics/comparable-programs",
    ],
)
def test_module2_endpoints(client: TestClient, path):
    """Modül 2 endpoint'leri çalışır."""
    assert client.get(path).status_code == 200


def test_module2_overview_counts_seed_students(client: TestClient):
    """Öğrenci özeti seed verisini yansıtır."""
    body = client.get("/api/student-analytics/overview").json()
    assert body["total_students"] >= 120


def test_module2_overview_percentages_are_two_decimals(client: TestClient):
    """Yüzdeler iki ondalık basamakla döner."""
    body = client.get("/api/student-analytics/overview").json()
    for field in (
        "scholarship_student_percentage",
        "international_student_percentage",
        "average_gpa",
    ):
        assert len(str(body[field]).split(".")[1]) == 2


def test_module2_program_analytics_has_occupancy(client: TestClient):
    """Program analitiği doluluk oranı içerir."""
    programs = client.get("/api/student-analytics/by-program").json()
    swe = next(item for item in programs if item["program_code"] == "SWE-BSC")
    assert swe["occupancy_rate"] == "98.75"


def test_module2_demand_trend_still_works(client: TestClient):
    """Talep trendi hesaplaması bozulmadı."""
    programs = client.get("/api/student-analytics/by-program").json()
    trends = {item["program_code"]: item["demand_trend"] for item in programs}
    assert trends["SWE-BSC"] == "increasing"
    assert trends["CENG-BSC"] == "decreasing"


def test_module2_trends_endpoint(client: TestClient):
    """Öğrenci trend endpoint'i çalışır."""
    response = client.get(
        "/api/student-analytics/trends?metric=total-students&start_year=2021&end_year=2025"
    )
    assert response.status_code == 200 and len(response.json()["points"]) == 5


def test_module2_alerts_still_produced(client: TestClient):
    """Erken uyarılar üretilmeye devam ediyor."""
    body = client.get("/api/student-analytics/alerts").json()
    assert body["total_alerts"] > 0


def test_module2_student_search(client: TestClient):
    """Öğrenci arama filtresi çalışır."""
    response = client.get("/api/students?search=Ahmet&limit=500")
    assert response.status_code == 200 and len(response.json()) > 0


def test_module2_duplicate_student_number_conflicts(client: TestClient, program_ids):
    """Tekrar eden öğrenci numarası 409 döndürür."""
    payload = {
        "student_number": "M10REG001",
        "first_name": "Regression",
        "last_name": "Test",
        "enrollment_year": 2025,
        "academic_program_id": program_ids["SWE-BSC"],
    }
    assert client.post("/api/students", json=payload).status_code == 201
    assert client.post("/api/students", json=payload).status_code == 409


def test_module2_program_demand_endpoint(client: TestClient, program_ids):
    """Program talep analizi çalışır."""
    response = client.get(
        f"/api/student-analytics/programs/{program_ids['SWE-BSC']}/demand"
    )
    assert response.status_code == 200 and response.json()["demand_trend"] == "increasing"


def test_module2_program_comparison_endpoint(client: TestClient, program_ids):
    """Program karşılaştırma analizi çalışır."""
    response = client.get(
        f"/api/student-analytics/programs/{program_ids['SWE-BSC']}/comparisons"
    )
    assert response.status_code == 200 and response.json()["similar_programs"]


# ===========================================================================
# Modül 9 - Senaryo analizi
# ===========================================================================


@pytest.mark.parametrize(
    "path", ["/api/scenarios", "/api/scenarios/baselines", "/api/scenarios/baselines/active"]
)
def test_module9_endpoints(client: TestClient, path):
    """Modül 9 endpoint'leri çalışır."""
    assert client.get(path).status_code == 200


def test_module9_baseline_seed_present(client: TestClient):
    """Senaryo baseline'ı seed'den geldi."""
    body = client.get("/api/scenarios/baselines/active").json()
    assert body["annual_tuition_per_student"] == "180000.00"


def test_module9_simulation_math_unchanged(client: TestClient):
    """Senaryo hesaplama sonuçları değişmedi."""
    scenario_id = client.post(
        "/api/scenarios",
        json={"name": "M10 Regression Scenario", "scenario_type": "economic-risk"},
    ).json()["id"]
    response = client.post(
        f"/api/scenarios/{scenario_id}/simulate",
        json={"inflation_percent": "50", "exchange_rate_change_percent": "30"},
    )
    body = response.json()
    assert response.status_code == 201
    assert body["breakdown"]["projected_technology_expense"] == "48750000.00"
    assert body["result"]["projected_expenditure"] == "586250000.00"


def test_module9_preview_does_not_persist(client: TestClient):
    """Senaryo ön izlemesi kayıt oluşturmaz."""
    before = len(client.get("/api/scenarios?limit=500").json())
    body = client.post(
        "/api/scenarios/preview", json={"student_change_percent": "10"}
    ).json()
    after = len(client.get("/api/scenarios?limit=500").json())
    assert body["preview"] is True and before == after


def test_module9_live_student_data_integration(client: TestClient):
    """use_live_student_data parametresi çalışmaya devam ediyor."""
    body = client.post(
        "/api/scenarios/preview?use_live_student_data=true",
        json={"student_change_percent": "0"},
    ).json()
    assert body["student_data_source"] == "live-student-module"


def test_module9_default_uses_baseline(client: TestClient):
    """Varsayılan davranış baseline verisini kullanır."""
    body = client.post("/api/scenarios/preview", json={}).json()
    assert body["student_data_source"] == "baseline"


def test_module9_capacity_validation_still_active(client: TestClient):
    """Kapasite negatife düşerse 422 döner."""
    response = client.post(
        "/api/scenarios/preview", json={"classroom_capacity_change": -99999}
    )
    assert response.status_code == 422


def test_module9_risk_engine_still_works(client: TestClient):
    """Risk motoru kritik senaryoyu yakalar."""
    body = client.post(
        "/api/scenarios/preview", json={"scholarship_change_percent": "70"}
    ).json()
    assert body["risk_level"] == "critical"


def test_module9_missing_scenario_returns_404(client: TestClient):
    """Olmayan senaryo 404 döndürür."""
    assert client.post("/api/scenarios/999999/simulate", json={}).status_code == 404


# ===========================================================================
# Modül 13 - Veri entegrasyonu
# ===========================================================================


@pytest.mark.parametrize(
    "path", ["/api/data-integration/jobs", "/api/data-integration/resources"]
)
def test_module13_endpoints(client: TestClient, path):
    """Modül 13 endpoint'leri çalışır."""
    assert client.get(path).status_code == 200


@pytest.mark.parametrize(
    "resource,expected",
    [
        ("faculties", "name,code,description,is_active"),
        ("departments", "faculty_code,name,code,description,is_active"),
        (
            "programs",
            "department_code,name,code,degree_level,duration_years,quota,description,is_active",
        ),
        ("administrative-units", "name,code,description,is_active"),
    ],
)
def test_module13_existing_templates_unchanged(client: TestClient, resource, expected):
    """Mevcut şablon başlıkları değişmedi."""
    response = client.get(f"/api/data-integration/templates/{resource}")
    assert response.text.strip() == expected


def test_module13_faculty_import_still_works(client: TestClient):
    """Fakülte içe aktarımı çalışmaya devam ediyor."""
    response = client.post(
        "/api/data-integration/import/faculties",
        files={
            "file": (
                "reg.csv",
                b"name,code,description,is_active\nM10 Import Faculty,M10IMP,test,true\n",
                "text/csv",
            )
        },
    )
    assert response.status_code == 200 and response.json()["imported_rows"] == 1


def test_module13_conflict_detection_unchanged(client: TestClient):
    """Tekrar eden kod çakışma olarak raporlanır."""
    payload = b"name,code,is_active\nM10 Conflict Faculty,M10CNF,true\n"
    client.post(
        "/api/data-integration/import/faculties",
        files={"file": ("c.csv", payload, "text/csv")},
    )
    second = client.post(
        "/api/data-integration/import/faculties",
        files={"file": ("c.csv", payload, "text/csv")},
    )
    assert second.json()["conflict_rows"] == 1


def test_module13_unsupported_format_returns_415(client: TestClient):
    """Desteklenmeyen biçim 415 döndürür."""
    response = client.post(
        "/api/data-integration/import/faculties",
        files={"file": ("a.txt", b"x", "text/plain")},
    )
    assert response.status_code == 415


def test_module13_invalid_resource_returns_422(client: TestClient):
    """Tanımsız kaynak türü 422 döndürür."""
    response = client.post(
        "/api/data-integration/import/hayali-kaynak",
        files={"file": ("a.csv", b"name,code\nA,B\n", "text/csv")},
    )
    assert response.status_code == 422


def test_module13_student_import_still_works(client: TestClient):
    """Öğrenci içe aktarımı çalışmaya devam ediyor."""
    data = (
        b"student_number,first_name,last_name,enrollment_year,academic_program_code\n"
        b"M10IMP001,Import,Test,2025,SWE-BSC\n"
    )
    response = client.post(
        "/api/data-integration/import/students",
        files={"file": ("s.csv", data, "text/csv")},
    )
    assert response.status_code == 200 and response.json()["imported_rows"] == 1


def test_module13_resource_count_includes_all_modules(client: TestClient):
    """Kaynak listesi 11 kanonik türü içerir."""
    body = client.get("/api/data-integration/resources").json()
    assert len(body["resource_types"]) == 11
