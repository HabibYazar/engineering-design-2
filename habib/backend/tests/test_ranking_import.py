"""Modül 10 kaynakları için veri entegrasyonu (import) testleri."""

import io
import json
from typing import Dict

import pandas as pd
import pytest
from fastapi.testclient import TestClient

IMPORT_BASE: str = "/api/data-integration"


def csv_bytes(rows: list) -> bytes:
    """Satır listesini CSV baytlarına çevirir."""
    return pd.DataFrame(rows).to_csv(index=False).encode("utf-8")


def xlsx_bytes(rows: list) -> bytes:
    """Satır listesini XLSX baytlarına çevirir."""
    buffer = io.BytesIO()
    pd.DataFrame(rows).to_excel(buffer, index=False, engine="openpyxl")
    return buffer.getvalue()


def json_bytes(rows: list) -> bytes:
    """Satır listesini JSON baytlarına çevirir."""
    return json.dumps(rows, ensure_ascii=False).encode("utf-8")


def upload(client: TestClient, resource: str, name: str, data: bytes, preview: bool = False):
    """Dosya yükleme isteğini gönderir."""
    return client.post(
        f"{IMPORT_BASE}/import/{resource}?preview={str(preview).lower()}",
        files={"file": (name, data)},
    )


# ===========================================================================
# 1) Kaynak ve şablon tanımları
# ===========================================================================


def test_resource_list_includes_new_types(client: TestClient):
    """Üç yeni kaynak türü desteklenen listede bulunur."""
    body = client.get(f"{IMPORT_BASE}/resources").json()
    for resource in (
        "institutional-metric-values",
        "benchmark-institutions",
        "benchmark-metric-values",
    ):
        assert resource in body["resource_types"]


def test_resource_list_reports_underscore_aliases(client: TestClient):
    """Alt çizgili yazımlar takma ad olarak bildirilir."""
    aliases = client.get(f"{IMPORT_BASE}/resources").json()["aliases"]
    assert aliases["institutional_metric_values"] == "institutional-metric-values"
    assert aliases["benchmark_institutions"] == "benchmark-institutions"
    assert aliases["benchmark_metric_values"] == "benchmark-metric-values"


@pytest.mark.parametrize(
    "resource,expected",
    [
        (
            "institutional-metric-values",
            "indicator_code,academic_year,period,value,numerator,denominator,"
            "data_status,source_reference,notes",
        ),
        (
            "benchmark-institutions",
            "name,country,city,institution_type,is_competitor,notes,is_active",
        ),
        (
            "benchmark-metric-values",
            "benchmark_institution_name,indicator_code,academic_year,period,value,"
            "source_reference",
        ),
    ],
)
def test_templates_for_new_resources(client: TestClient, resource, expected):
    """Yeni kaynakların şablon başlıkları doğrudur."""
    response = client.get(f"{IMPORT_BASE}/templates/{resource}")
    assert response.status_code == 200 and response.text.strip() == expected


@pytest.mark.parametrize(
    "alias",
    ["institutional_metric_values", "benchmark_institutions", "benchmark_metric_values"],
)
def test_templates_work_with_underscore_aliases(client: TestClient, alias):
    """Alt çizgili takma adlarla da şablon indirilebilir."""
    assert client.get(f"{IMPORT_BASE}/templates/{alias}").status_code == 200


def test_template_is_downloadable(client: TestClient):
    """Şablon indirilebilir başlıkla döner."""
    response = client.get(f"{IMPORT_BASE}/templates/institutional-metric-values")
    assert "attachment" in response.headers.get("content-disposition", "")


# ===========================================================================
# 2) Kurumsal gösterge verisi içe aktarımı
# ===========================================================================


def test_import_metric_values_csv(client: TestClient):
    """CSV ile gösterge verisi aktarılabilir."""
    rows = [
        {
            "indicator_code": "the-patent-count",
            "academic_year": "2012-2013",
            "period": "annual",
            "value": 4,
            "data_status": "available",
            "source_reference": "TTO raporu",
        }
    ]
    response = upload(client, "institutional-metric-values", "metrics.csv", csv_bytes(rows))
    assert response.status_code == 200 and response.json()["imported_rows"] == 1


def test_import_metric_values_xlsx(client: TestClient):
    """XLSX ile gösterge verisi aktarılabilir."""
    rows = [
        {
            "indicator_code": "the-patent-count",
            "academic_year": "2011-2012",
            "value": 3,
            "data_status": "available",
        }
    ]
    response = upload(client, "institutional-metric-values", "metrics.xlsx", xlsx_bytes(rows))
    assert response.status_code == 200 and response.json()["imported_rows"] == 1


def test_import_metric_values_json(client: TestClient):
    """JSON ile gösterge verisi aktarılabilir."""
    rows = [
        {
            "indicator_code": "the-patent-count",
            "academic_year": "2010-2011",
            "value": 2,
            "data_status": "available",
        }
    ]
    response = upload(client, "institutional-metric-values", "metrics.json", json_bytes(rows))
    assert response.status_code == 200 and response.json()["imported_rows"] == 1


def test_import_resolves_indicator_code_to_id(client: TestClient, indicator_ids: Dict[str, int]):
    """indicator_code doğru göstergeye bağlanır."""
    rows = [
        {
            "indicator_code": "the-patent-count",
            "academic_year": "2009-2010",
            "value": 1,
        }
    ]
    upload(client, "institutional-metric-values", "m.csv", csv_bytes(rows))
    metrics = client.get(
        f"/api/ranking-evaluations/metrics"
        f"?indicator_id={indicator_ids['the-patent-count']}&academic_year=2009-2010"
    ).json()
    assert len(metrics) == 1


def test_import_accepts_numerator_denominator(client: TestClient):
    """Pay/payda ile gösterge verisi aktarılabilir."""
    rows = [
        {
            "indicator_code": "the-citation-impact",
            "academic_year": "2012-2013",
            "numerator": 80,
            "denominator": 30,
            "data_status": "available",
        }
    ]
    response = upload(client, "institutional-metric-values", "m.csv", csv_bytes(rows))
    assert response.json()["imported_rows"] == 1


def test_import_with_invalid_indicator_code_reports_error(client: TestClient):
    """Geçersiz gösterge kodu satır hatası üretir."""
    rows = [
        {"indicator_code": "yok-boyle-bir-gosterge", "academic_year": "2012-2013", "value": 1}
    ]
    body = upload(client, "institutional-metric-values", "bad.csv", csv_bytes(rows)).json()
    assert body["error_rows"] == 1
    assert any(item["field"] == "indicator_code" for item in body["errors"])


def test_import_duplicate_row_is_reported_as_conflict(client: TestClient):
    """Aynı gösterge + yıl + dönem ikinci kez aktarılamaz."""
    rows = [
        {"indicator_code": "the-patent-count", "academic_year": "2008-2009", "value": 1}
    ]
    first = upload(client, "institutional-metric-values", "d.csv", csv_bytes(rows))
    second = upload(client, "institutional-metric-values", "d.csv", csv_bytes(rows))
    assert first.json()["imported_rows"] == 1
    assert second.json()["conflict_rows"] == 1


def test_import_detects_duplicate_within_file(client: TestClient):
    """Dosya içindeki tekrar eden satır çakışma olarak raporlanır."""
    rows = [
        {"indicator_code": "the-patent-count", "academic_year": "2007-2008", "value": 1},
        {"indicator_code": "the-patent-count", "academic_year": "2007-2008", "value": 2},
    ]
    body = upload(client, "institutional-metric-values", "dup.csv", csv_bytes(rows)).json()
    assert body["imported_rows"] == 1 and body["conflict_rows"] == 1
    assert any("dosya içinde" in item["message"] for item in body["errors"])


def test_import_rejects_malformed_decimal(client: TestClient):
    """Sayıya çevrilemeyen değer satır hatası üretir."""
    rows = [
        {
            "indicator_code": "the-patent-count",
            "academic_year": "2006-2007",
            "value": "bes-adet",
        }
    ]
    body = upload(client, "institutional-metric-values", "bad.csv", csv_bytes(rows)).json()
    assert body["error_rows"] == 1
    assert any(item["field"] == "value" for item in body["errors"])


def test_import_accepts_comma_decimal_separator(client: TestClient):
    """Türkçe Excel'den gelen virgüllü ondalık kabul edilir."""
    rows = [
        {
            "indicator_code": "the-teaching-reputation",
            "academic_year": "2006-2007",
            "value": "42,50",
        }
    ]
    body = upload(client, "institutional-metric-values", "comma.csv", csv_bytes(rows)).json()
    assert body["imported_rows"] == 1


def test_import_rejects_negative_value(client: TestClient):
    """Negatif gösterge değeri reddedilir."""
    rows = [
        {"indicator_code": "the-patent-count", "academic_year": "2005-2006", "value": -5}
    ]
    body = upload(client, "institutional-metric-values", "neg.csv", csv_bytes(rows)).json()
    assert body["error_rows"] == 1


def test_import_rejects_invalid_academic_year(client: TestClient):
    """Geçersiz akademik yıl biçimi reddedilir."""
    rows = [{"indicator_code": "the-patent-count", "academic_year": "2005", "value": 1}]
    body = upload(client, "institutional-metric-values", "year.csv", csv_bytes(rows)).json()
    assert body["error_rows"] == 1
    assert any(item["field"] == "academic_year" for item in body["errors"])


def test_import_rejects_invalid_data_status(client: TestClient):
    """Tanımsız data_status değeri reddedilir."""
    rows = [
        {
            "indicator_code": "the-patent-count",
            "academic_year": "2004-2005",
            "value": 1,
            "data_status": "belki",
        }
    ]
    body = upload(client, "institutional-metric-values", "status.csv", csv_bytes(rows)).json()
    assert any(item["field"] == "data_status" for item in body["errors"])


def test_import_rejects_invalid_period(client: TestClient):
    """Tanımsız dönem değeri reddedilir."""
    rows = [
        {
            "indicator_code": "the-patent-count",
            "academic_year": "2004-2005",
            "value": 1,
            "period": "quarter",
        }
    ]
    body = upload(client, "institutional-metric-values", "period.csv", csv_bytes(rows)).json()
    assert any(item["field"] == "period" for item in body["errors"])


def test_import_preview_does_not_persist(client: TestClient):
    """Ön izleme veritabanına kayıt yazmaz."""
    before = len(client.get("/api/ranking-evaluations/metrics?limit=500").json())
    rows = [
        {"indicator_code": "the-patent-count", "academic_year": "2003-2004", "value": 9}
    ]
    body = upload(
        client, "institutional-metric-values", "p.csv", csv_bytes(rows), preview=True
    ).json()
    after = len(client.get("/api/ranking-evaluations/metrics?limit=500").json())
    assert body["valid_rows"] == 1 and body["imported_rows"] == 0
    assert before == after


def test_import_works_with_underscore_alias(client: TestClient):
    """Alt çizgili kaynak adıyla da içe aktarım yapılabilir."""
    rows = [
        {"indicator_code": "the-patent-count", "academic_year": "2002-2003", "value": 1}
    ]
    response = upload(client, "institutional_metric_values", "alias.csv", csv_bytes(rows))
    assert response.status_code == 200 and response.json()["imported_rows"] == 1


def test_import_partial_file_imports_valid_rows_only(client: TestClient):
    """Hatalı satır diğer geçerli satırların aktarımını engellemez."""
    rows = [
        {"indicator_code": "the-patent-count", "academic_year": "2001-2002", "value": 1},
        {"indicator_code": "gecersiz-kod", "academic_year": "2001-2002", "value": 1},
    ]
    body = upload(client, "institutional-metric-values", "mix.csv", csv_bytes(rows)).json()
    assert body["imported_rows"] == 1 and body["error_rows"] == 1
    assert body["status"] == "partial"


# ===========================================================================
# 3) Karşılaştırma kurumu içe aktarımı
# ===========================================================================


def test_import_benchmark_institutions_csv(client: TestClient):
    """CSV ile karşılaştırma kurumu aktarılabilir."""
    rows = [
        {
            "name": "Import Test Üniversitesi 1 (demo)",
            "country": "Türkiye",
            "city": "Bursa",
            "institution_type": "similar",
            "is_competitor": "hayir",
            "is_active": "evet",
        }
    ]
    response = upload(client, "benchmark-institutions", "inst.csv", csv_bytes(rows))
    assert response.status_code == 200 and response.json()["imported_rows"] == 1


def test_import_benchmark_institutions_json(client: TestClient):
    """JSON ile karşılaştırma kurumu aktarılabilir."""
    rows = [
        {
            "name": "Import Test Üniversitesi 2 (demo)",
            "country": "Türkiye",
            "institution_type": "competitor",
            "is_competitor": True,
        }
    ]
    response = upload(client, "benchmark-institutions", "inst.json", json_bytes(rows))
    assert response.json()["imported_rows"] == 1


def test_import_benchmark_institution_duplicate_name_conflicts(client: TestClient):
    """Aynı isimli kurum ikinci kez aktarılamaz."""
    rows = [{"name": "Import Duplicate Üniversitesi (demo)", "country": "Türkiye"}]
    upload(client, "benchmark-institutions", "i.csv", csv_bytes(rows))
    second = upload(client, "benchmark-institutions", "i.csv", csv_bytes(rows))
    assert second.json()["conflict_rows"] == 1


def test_import_benchmark_institution_rejects_invalid_type(client: TestClient):
    """Tanımsız kurum türü reddedilir."""
    rows = [
        {
            "name": "Bad Type Üniversitesi (demo)",
            "institution_type": "hayali-tur",
        }
    ]
    body = upload(client, "benchmark-institutions", "bad.csv", csv_bytes(rows)).json()
    assert any(item["field"] == "institution_type" for item in body["errors"])


def test_import_benchmark_institution_boolean_variants(client: TestClient):
    """is_competitor alanı Türkçe/İngilizce yazımları kabul eder."""
    rows = [
        {"name": "Bool Test A (demo)", "is_competitor": "evet"},
        {"name": "Bool Test B (demo)", "is_competitor": "1"},
        {"name": "Bool Test C (demo)", "is_competitor": "false"},
    ]
    body = upload(client, "benchmark-institutions", "bool.csv", csv_bytes(rows)).json()
    assert body["imported_rows"] == 3


# ===========================================================================
# 4) Karşılaştırma gösterge değeri içe aktarımı (iki üst kayıt)
# ===========================================================================


def test_import_benchmark_values_with_two_parents(client: TestClient):
    """Hem kurum hem gösterge kodu çözümlenerek aktarım yapılır."""
    upload(
        client,
        "benchmark-institutions",
        "parent.csv",
        csv_bytes([{"name": "Two Parent Üniversitesi (demo)", "country": "Türkiye"}]),
    )
    rows = [
        {
            "benchmark_institution_name": "Two Parent Üniversitesi (demo)",
            "indicator_code": "the-citation-impact",
            "academic_year": "2025-2026",
            "value": "3.90",
        }
    ]
    response = upload(client, "benchmark-metric-values", "bv.csv", csv_bytes(rows))
    assert response.status_code == 200 and response.json()["imported_rows"] == 1


def test_import_benchmark_values_xlsx(client: TestClient):
    """XLSX ile karşılaştırma değeri aktarılabilir."""
    upload(
        client,
        "benchmark-institutions",
        "p2.csv",
        csv_bytes([{"name": "Xlsx Parent Üniversitesi (demo)", "country": "Türkiye"}]),
    )
    rows = [
        {
            "benchmark_institution_name": "Xlsx Parent Üniversitesi (demo)",
            "indicator_code": "the-patent-count",
            "academic_year": "2025-2026",
            "value": 12,
        }
    ]
    assert (
        upload(client, "benchmark-metric-values", "bv.xlsx", xlsx_bytes(rows)).json()[
            "imported_rows"
        ]
        == 1
    )


def test_import_benchmark_values_invalid_institution(client: TestClient):
    """Geçersiz kurum adı satır hatası üretir."""
    rows = [
        {
            "benchmark_institution_name": "Olmayan Üniversite",
            "indicator_code": "the-patent-count",
            "academic_year": "2025-2026",
            "value": 1,
        }
    ]
    body = upload(client, "benchmark-metric-values", "bad.csv", csv_bytes(rows)).json()
    assert body["error_rows"] == 1
    assert any(
        item["field"] == "benchmark_institution_name" for item in body["errors"]
    )


def test_import_benchmark_values_invalid_indicator(client: TestClient):
    """Geçersiz gösterge kodu satır hatası üretir."""
    rows = [
        {
            "benchmark_institution_name": "Two Parent Üniversitesi (demo)",
            "indicator_code": "olmayan-gosterge",
            "academic_year": "2025-2026",
            "value": 1,
        }
    ]
    body = upload(client, "benchmark-metric-values", "bad2.csv", csv_bytes(rows)).json()
    assert any(item["field"] == "indicator_code" for item in body["errors"])


def test_import_benchmark_values_duplicate_conflicts(client: TestClient):
    """Aynı kurum + gösterge + yıl + dönem ikinci kez aktarılamaz."""
    upload(
        client,
        "benchmark-institutions",
        "p3.csv",
        csv_bytes([{"name": "Dup Value Üniversitesi (demo)", "country": "Türkiye"}]),
    )
    rows = [
        {
            "benchmark_institution_name": "Dup Value Üniversitesi (demo)",
            "indicator_code": "the-patent-count",
            "academic_year": "2024-2025",
            "value": 5,
        }
    ]
    upload(client, "benchmark-metric-values", "d.csv", csv_bytes(rows))
    second = upload(client, "benchmark-metric-values", "d.csv", csv_bytes(rows))
    assert second.json()["conflict_rows"] == 1


def test_import_benchmark_values_requires_value(client: TestClient):
    """value alanı zorunludur."""
    rows = [
        {
            "benchmark_institution_name": "Two Parent Üniversitesi (demo)",
            "indicator_code": "the-patent-count",
            "academic_year": "2023-2024",
        }
    ]
    body = upload(client, "benchmark-metric-values", "novalue.csv", csv_bytes(rows)).json()
    assert body["error_rows"] == 1


def test_import_benchmark_values_preview_does_not_persist(client: TestClient):
    """Karşılaştırma değeri ön izlemesi kayıt yazmaz."""
    rows = [
        {
            "benchmark_institution_name": "Two Parent Üniversitesi (demo)",
            "indicator_code": "the-patent-count",
            "academic_year": "2020-2021",
            "value": 7,
        }
    ]
    body = upload(
        client, "benchmark-metric-values", "pv.csv", csv_bytes(rows), preview=True
    ).json()
    assert body["imported_rows"] == 0 and body["valid_rows"] == 1


# ===========================================================================
# 5) Genel import davranışı
# ===========================================================================


def test_import_creates_job_record(client: TestClient):
    """Her içe aktarım bir iş kaydı oluşturur."""
    before = len(client.get(f"{IMPORT_BASE}/jobs?limit=500").json())
    upload(
        client,
        "institutional-metric-values",
        "job.csv",
        csv_bytes(
            [{"indicator_code": "the-patent-count", "academic_year": "2000-2001", "value": 1}]
        ),
    )
    after = len(client.get(f"{IMPORT_BASE}/jobs?limit=500").json())
    assert after == before + 1


def test_import_job_records_resource_type(client: TestClient):
    """İş kaydı kaynak türünü saklar."""
    upload(
        client,
        "benchmark-institutions",
        "jobtype.csv",
        csv_bytes([{"name": "Job Type Üniversitesi (demo)"}]),
    )
    jobs = client.get(f"{IMPORT_BASE}/jobs?resource_type=benchmark-institutions").json()
    assert jobs and jobs[0]["resource_type"] == "benchmark-institutions"


def test_unsupported_extension_returns_415(client: TestClient):
    """Desteklenmeyen dosya biçimi 415 döndürür."""
    response = client.post(
        f"{IMPORT_BASE}/import/institutional-metric-values",
        files={"file": ("data.txt", b"indicator_code,value\na,1\n", "text/plain")},
    )
    assert response.status_code == 415


def test_empty_file_returns_400(client: TestClient):
    """Boş dosya 400 döndürür."""
    response = client.post(
        f"{IMPORT_BASE}/import/benchmark-institutions",
        files={"file": ("empty.csv", b"", "text/csv")},
    )
    assert response.status_code == 400
