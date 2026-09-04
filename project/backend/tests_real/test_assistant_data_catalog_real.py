"""Focused executive-assistant checks against the existing real database.

This suite is intentionally outside ``tests``/``tests_integration``: their
conftest files replace the database with seeded test fixtures.  These tests
perform read-only queries against ``integration/backend/university_management.db``
and never invoke a seed script.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal, engine
from app.services.assistant import chart_builder, data_catalog
from main import app

YEAR = "2025-2026"


@pytest.fixture(scope="module")
def db():
    database_path = Path(str(engine.url.database)).resolve()
    expected = (Path(__file__).resolve().parents[1] / "university_management.db").resolve()
    assert database_path == expected
    assert database_path.stat().st_size > 1_000_000
    with SessionLocal() as session:
        yield session


def query(db, question: str, *, faculty_id=None):
    scope = {"academic_year": YEAR}
    if faculty_id is not None:
        scope["faculty_id"] = faculty_id
    result = data_catalog.query_question(db, question, scope)
    charts = chart_builder.build_dataset_charts(result["dataset"], question)
    return result, charts


def values(dataset, metric="student_count"):
    selected = next(item for item in dataset["metrics"] if item["key"] == metric)
    return {row["code"]: row["value"] for row in selected["rows"]}


def assert_chart_uses_rows(dataset, charts):
    by_metric = {chart["metric"]: chart for chart in charts["charts"]}
    for metric in dataset["metrics"]:
        chart = by_metric[metric["key"]]
        expected = [round(float(row["value"]), 2) for row in metric["rows"]]
        assert chart["series"][0]["data"] == expected
        assert chart["data_rows"] == metric["rows"]


def test_01_faculty_student_prose_and_chart_agree_on_real_rows(db, monkeypatch):
    monkeypatch.setattr(
        "app.services.assistant.chat_service._catalog_interpretation",
        lambda *_args, **_kwargs: "",
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/assistant/chat",
            json={
                "message": "Fakültelere göre öğrenci sayılarını grafikle göster.",
                "academic_year": YEAR,
            },
        )
    assert response.status_code == 200
    body = response.json()
    assert "Fakülte bazlı veri bulunmamaktadır" not in body["answer"]
    assert values(body["structured_result"]) == {
        "INSTOPBIL": 1219,
        "MUHMIM": 803,
        "GUZSANTAS": 323,
        "HUKUK": 260,
    }
    assert "kohort" in body["answer"]
    assert_chart_uses_rows(body["structured_result"], {"charts": body["charts"]})



def test_02_global_endustri_ybs_resolution_ignores_selected_engineering_scope(db):
    question = (
        "Endüstri Mühendisliği ile Yönetim Bilişim Sistemlerinin öğrenci "
        "sayısını kıyaslayan grafik göster."
    )
    result, charts = query(db, question, faculty_id=4)
    dataset = result["dataset"]
    assert values(dataset) == {"ENDMUH": 102, "YONBILSIS": 302}
    ybs = next(row for row in dataset["rows"] if row["code"] == "YONBILSIS")
    assert ybs["entity_type"] == "department"
    assert "İNSAN VE TOPLUM" in ybs["parent_label"]
    assert all(row["code"] != "BILSISMUH" for row in dataset["rows"])
    assert_chart_uses_rows(dataset, charts)


def test_03_cross_scope_endustri_hukuk_discovers_common_metrics(db):
    result, charts = query(
        db, "Endüstri ile Hukuk'u kıyaslayan bir grafik gösterir misin?"
    )
    dataset = result["dataset"]
    assert values(dataset) == {"ENDMUH": 102, "HUKUK": 260}
    student_rows = next(
        metric["rows"] for metric in dataset["metrics"]
        if metric["key"] == "student_count"
    )
    types = {row["code"]: row["entity_type"] for row in student_rows}
    assert types == {"ENDMUH": "department", "HUKUK": "faculty"}
    assert {metric["key"] for metric in dataset["metrics"]} >= {
        "student_count", "academic_staff_count", "students_per_academic_staff"
    }
    assert_chart_uses_rows(dataset, charts)


def test_04_psychology_computer_uses_canonical_aliases(db):
    result, _ = query(
        db, "Psikoloji ile Bilgisayarı öğrenci sayısına göre karşılaştır."
    )
    assert values(result["dataset"]) == {"PSIKOLOJI": 512, "BILMUH": 310}


def test_05_engineering_children_are_globally_resolved_and_sorted(db):
    result, _ = query(
        db, "Mühendislikteki bütün bölümleri öğrenci sayısına göre sırala."
    )
    rows = result["dataset"]["rows"]
    assert [(row["code"], row["value"]) for row in rows] == [
        ("BILMUH", 310),
        ("YAZMUH", 148),
        ("ELEELEMUH", 124),
        ("BILSISMUH", 119),
        ("ENDMUH", 102),
    ]


def test_06_faculties_sort_by_real_academic_staff(db):
    result, _ = query(db, "Tüm fakülteleri akademisyen sayısına göre sırala.")
    assert values(result["dataset"], "academic_staff_count") == {
        "MUHMIM": 32,
        "INSTOPBIL": 31,
        "HUKUK": 18,
        "HAVUZABIL": 18,
        "GUZSANTAS": 14,
    }



def test_07_top_ten_staff_performance_comes_from_existing_service(db):
    result, charts = query(db, "En yüksek performans puanlı 10 akademisyeni grafikle.")
    rows = result["dataset"]["rows"]
    assert len(rows) == 10
    assert [row["value"] for row in rows] == sorted(
        (row["value"] for row in rows), reverse=True
    )
    assert all(row["entity_type"] == "academic_staff" for row in rows)
    assert_chart_uses_rows(result["dataset"], charts)


def test_08_truly_unknown_metric_is_unavailable_and_has_no_chart(db):
    result, charts = query(db, "Fakültelerin uzaylı sayısını grafikle.")
    assert result["available"] is False
    assert result["answer"] == data_catalog.UNAVAILABLE_MESSAGE
    assert charts["charts"] == []


@pytest.mark.parametrize(
    "question",
    [
        "Fakültelere göre öğrenci sayılarını grafikle göster.",
        "Endüstri Mühendisliği ile Yönetim Bilişim Sistemlerinin öğrenci sayısını kıyaslayan grafik göster.",
        "Endüstri ile Hukuk'u kıyaslayan bir grafik gösterir misin?",
        "En yüksek performans puanlı 10 akademisyeni grafikle.",
    ],
)
def test_09_every_chart_series_is_the_same_catalog_dataset(db, question):
    result, charts = query(db, question)
    assert_chart_uses_rows(result["dataset"], charts)


def test_10_university_current_headcount_remains_official_3626(db):
    result, charts = query(db, "Toplam öğrenci sayımız kaç?")
    dataset = result["dataset"]
    assert dataset["rows"][0]["value"] == 3626
    assert dataset["rows"][0]["source_type"] == "authoritative"
    assert "YÖK resmî kayıtlı öğrenci sayısı" in dataset["rows"][0]["source_label"]
    assert charts["charts"] == []


def test_11_endustri_ybs_comparison_with_plural_suffix_and_no_explicit_metric(db):
    with TestClient(app) as client:
        response = client.post(
            "/api/assistant/chat",
            json={
                "message": "Endüstri Mühendisliği ile Yönetim Bilişim Sistemleri bölümlerini grafikle kıyasla",
                "academic_year": YEAR,
            },
        )
    assert response.status_code == 200
    body = response.json()
    assert body["structured_result"]["available"] is True
    assert "veri mevcut kaynaklarda bulunmuyor" not in body["answer"].lower()
    assert values(body["structured_result"], "student_count") == {"ENDMUH": 102, "YONBILSIS": 302}
    assert len(body["charts"]) >= 1
    student_chart = next(c for c in body["charts"] if c["metric"] == "student_count")
    assert student_chart["series"][0]["data"] == [102.0, 302.0]


def test_12_psychology_computer_chat_route(db):
    with TestClient(app) as client:
        response = client.post(
            "/api/assistant/chat",
            json={
                "message": "Psikoloji ile Bilgisayarı öğrenci sayısına göre karşılaştır",
                "academic_year": YEAR,
            },
        )
    assert response.status_code == 200
    body = response.json()
    assert body["structured_result"]["available"] is True
    assert values(body["structured_result"], "student_count") == {"PSIKOLOJI": 512, "BILMUH": 310}

