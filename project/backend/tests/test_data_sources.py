"""Dosya tabanlı ikincil veri kaynağı sisteminin uçtan uca testleri."""

import json
import sqlite3
from datetime import datetime
from io import BytesIO

import pandas as pd
import pytest
from sqlalchemy import select

from app.models import AcademicStaff, Department, Faculty, UploadedDataSource, UploadedMetricRecord
from app.services import data_source_service
from app.services.assistant.data_access import uploaded_academic_metrics
from app.services.scope import resolve


@pytest.fixture(autouse=True)
def isolated_upload_directory(monkeypatch, tmp_path):
    target = tmp_path / "uploads"
    monkeypatch.setattr(data_source_service, "UPLOAD_DIR", target)
    return target


@pytest.fixture()
def faculty_ids(db_session):
    rows = list(db_session.execute(select(Faculty).order_by(Faculty.id)).scalars())
    assert rows
    department = db_session.execute(
        select(Department).where(Department.faculty_id == rows[0].id).order_by(Department.id)
    ).scalars().first()
    assert department is not None
    return rows[0].id, department.id


def _xlsx(rows: list[dict]) -> bytes:
    output = BytesIO()
    pd.DataFrame(rows).to_excel(output, index=False, engine="openpyxl")
    return output.getvalue()


def _sqlite_file(tmp_path, rows: list[tuple]) -> bytes:
    path = tmp_path / "source.db"
    connection = sqlite3.connect(path)
    connection.execute('CREATE TABLE "Performans" ("Yil" TEXT, "Atif" INTEGER)')
    connection.executemany('INSERT INTO "Performans" VALUES (?, ?)', rows)
    connection.commit()
    connection.close()
    return path.read_bytes()


def _upload(client, filename: str, content: bytes, faculty_id: int, year: str):
    response = client.post(
        "/api/data-sources/upload",
        files={"file": (filename, content, "application/octet-stream")},
        data={"scope_type": "faculty", "faculty_id": str(faculty_id), "academic_year": year},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _inspect(client, source_id: int, **selection):
    response = client.post(f"/api/data-sources/{source_id}/inspect", json=selection)
    assert response.status_code == 200, response.text
    return response.json()


def _validate(client, source_id: int, inspection: dict, mapping: dict | None = None):
    response = client.post(
        f"/api/data-sources/{source_id}/validate",
        json={
            "mapping": mapping or inspection["auto_mapping"],
            "selected_sheet": inspection.get("selected_sheet"),
            "selected_table": inspection.get("selected_table"),
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _import(client, source_id: int, inspection: dict, mapping: dict | None = None):
    response = client.post(
        f"/api/data-sources/{source_id}/import",
        json={
            "mapping": mapping or inspection["auto_mapping"],
            "selected_sheet": inspection.get("selected_sheet"),
            "selected_table": inspection.get("selected_table"),
            "confirm": True,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("performans.csv", b"Yil,Atif,Proje\n2090-2091,250,12\n"),
        ("performans.xlsx", _xlsx([{"Yil": "2090-2091", "Atif": 250, "Proje": 12}])),
        ("performans.json", json.dumps({"records": [{"Yil": "2090-2091", "Atif": 250, "Proje": 12}]}).encode()),
    ],
)
def test_csv_xlsx_json_preview_mapping_validation_import_delete(
    client, db_session, faculty_ids, filename, content
):
    faculty_id, _ = faculty_ids
    source = _upload(client, filename, content, faculty_id, "2090-2091")
    inspection = _inspect(client, source["id"])
    assert inspection["row_count"] == 1
    assert inspection["columns"] == ["Yil", "Atif", "Proje"]
    assert inspection["preview_rows"][0]["Atif"] == "250"
    assert inspection["auto_mapping"] == {
        "Yil": "academic_year", "Atif": "citation_count", "Proje": "project_count"
    }

    validation = _validate(client, source["id"], inspection)
    assert validation["summary"]["rows_read"] == 1
    assert validation["summary"]["rows_valid"] == 1, validation["summary"]
    assert validation["summary"]["new_missing_values"] == 2

    imported = _import(client, source["id"], inspection)
    assert imported["source"]["status"] == "imported"
    availability = client.get("/api/data-sources/availability", params={
        "metric_key": "citation_count", "scope_type": "faculty",
        "faculty_id": faculty_id, "academic_year": "2090-2091",
    }).json()
    assert availability["status"] == "uploaded"
    assert availability["resolved_value"] == "250.00"
    assert availability["filename"] == filename
    assert availability["source_type"] == "uploaded"
    assert availability["provenance"] == "Kullanıcı veri kaynağı"
    assert availability["is_synthetic"] is False

    deleted = client.delete(f"/api/data-sources/{source['id']}")
    assert deleted.status_code == 200
    db_session.expire_all()
    records = list(db_session.execute(select(UploadedMetricRecord).where(
        UploadedMetricRecord.uploaded_source_id == source["id"]
    )).scalars())
    assert records and all(not row.is_active for row in records)


def test_sqlite_lists_tables_and_reads_only_selected_table(client, faculty_ids, tmp_path):
    faculty_id, _ = faculty_ids
    source = _upload(
        client, "performans.db", _sqlite_file(tmp_path, [("2091-2092", 77)]),
        faculty_id, "2091-2092",
    )
    first = _inspect(client, source["id"])
    assert first["tables"] == ["Performans"]
    assert first["requires_table_selection"] is True
    assert first["preview_rows"] == []

    rejected = client.post(
        f"/api/data-sources/{source['id']}/inspect",
        json={"selected_table": 'Performans; DROP TABLE "Performans"'},
    )
    assert rejected.status_code == 422
    selected = _inspect(client, source["id"], selected_table="Performans")
    assert selected["columns"] == ["Yil", "Atif"]
    assert selected["preview_rows"][0]["Atif"] == "77"
    _validate(client, source["id"], selected)
    _import(client, source["id"], selected)
    client.delete(f"/api/data-sources/{source['id']}")


def test_authoritative_conflict_is_reported_and_survives_source_delete(client, db_session, faculty_ids):
    faculty_id, department_id = faculty_ids
    authority = AcademicStaff(
        staff_number="AUTH-UPLOAD-TEST", first_name="Yetkili", last_name="Kaynak",
        title="PROFESÖR", department_id=department_id, academic_year="2025-2026",
        citation_count=42,
    )
    db_session.add(authority)
    db_session.commit()
    before = client.get("/api/data-sources/availability", params={
        "metric_key": "citation_count", "scope_type": "faculty",
        "faculty_id": faculty_id, "academic_year": "2025-2026",
    })
    assert before.status_code == 200
    assert before.json()["status"] == "authoritative"
    assert before.json()["source_type"] == "authoritative"
    assert before.json()["is_synthetic"] is False
    source = _upload(client, "conflict.csv", b"Yil,Atif\n2025-2026,999999\n", faculty_id, "2025-2026")
    inspection = _inspect(client, source["id"])
    report = _validate(client, source["id"], inspection)["summary"]
    assert report["conflict_count"] == 1
    assert report["new_missing_values"] == 0
    assert report["conflict_examples"][0]["authoritative_source"]

    # Safety invariant: even if an already-imported secondary record overlaps
    # an authoritative identity, the normal resolver must still return authority.
    stored_source = db_session.get(UploadedDataSource, source["id"])
    stored_source.status = "imported"
    stored_source.source_label = "SYNTHETIC_GENERATED / precedence test"
    stored_source.row_count = stored_source.imported_row_count = 1
    stored_source.imported_at = datetime.now()
    db_session.add(UploadedMetricRecord(
        uploaded_source_id=source["id"], metric_key="citation_count",
        entity_type="metric", scope_type="faculty", faculty_id=faculty_id,
        academic_year="2025-2026", numeric_value=999999, unit="adet",
        original_row_number=2, raw_values_json='{"Atif":"999999"}',
    ))
    db_session.commit()
    overlap = client.get("/api/data-sources/availability", params={
        "metric_key": "citation_count", "scope_type": "faculty",
        "faculty_id": faculty_id, "academic_year": "2025-2026",
    }).json()
    assert overlap["status"] == "authoritative"
    assert overlap["resolved_value"] == before.json()["resolved_value"]
    assert overlap["resolved_value"] != "999999.00"
    assert overlap["uploaded_source_id"] is None
    client.delete(f"/api/data-sources/{source['id']}")
    after = client.get("/api/data-sources/availability", params={
        "metric_key": "citation_count", "scope_type": "faculty",
        "faculty_id": faculty_id, "academic_year": "2025-2026",
    }).json()
    assert after["status"] == "authoritative"
    assert after["resolved_value"] == before.json()["resolved_value"]
    db_session.delete(authority)
    db_session.commit()


def test_synthetic_source_provenance_is_explicit(client, db_session, faculty_ids):
    faculty_id, _ = faculty_ids
    source = _upload(
        client, "synthetic-test.csv", b"Yil,Atif\n2097-2098,17\n",
        faculty_id, "2097-2098",
    )
    stored = db_session.get(UploadedDataSource, source["id"])
    stored.source_label = "SYNTHETIC_GENERATED / controlled test import"
    stored.notes = "is_synthetic=true"
    db_session.commit()

    inspection = _inspect(client, source["id"])
    _import(client, source["id"], inspection)
    availability = client.get("/api/data-sources/availability", params={
        "metric_key": "citation_count", "scope_type": "faculty",
        "faculty_id": faculty_id, "academic_year": "2097-2098",
    }).json()
    assert availability["source_type"] == "uploaded"
    assert availability["source_label"] == "SYNTHETIC_GENERATED / controlled test import"
    assert availability["provenance"] == availability["source_label"]
    assert availability["is_synthetic"] is True
    assert availability["uploaded_source_id"] == source["id"]
    client.delete(f"/api/data-sources/{source['id']}")


def test_scope_year_isolation_latest_source_and_fallback(client, faculty_ids):
    faculty_id, department_id = faculty_ids
    first = _upload(client, "old.csv", b"Yil,Atif\n2092-2093,111\n", faculty_id, "2092-2093")
    first_inspection = _inspect(client, first["id"])
    _import(client, first["id"], first_inspection)
    second = _upload(client, "new.csv", b"Yil,Atif\n2092-2093,222\n", faculty_id, "2092-2093")
    second_inspection = _inspect(client, second["id"])
    _import(client, second["id"], second_inspection)

    params = {"metric_key": "citation_count", "scope_type": "faculty", "faculty_id": faculty_id, "academic_year": "2092-2093"}
    assert client.get("/api/data-sources/availability", params=params).json()["resolved_value"] == "222.00"
    department_params = {
        **params, "scope_type": "department", "department_id": department_id,
    }
    assert client.get("/api/data-sources/availability", params=department_params).json()["status"] == "unavailable"
    assert client.get("/api/data-sources/availability", params={**params, "academic_year": "2093-2094"}).json()["status"] == "unavailable"

    client.delete(f"/api/data-sources/{second['id']}")
    assert client.get("/api/data-sources/availability", params=params).json()["resolved_value"] == "111.00"
    client.delete(f"/api/data-sources/{first['id']}")
    assert client.get("/api/data-sources/availability", params=params).json()["status"] == "unavailable"


def test_duplicate_unmatched_and_malformed_files(client, faculty_ids):
    faculty_id, _ = faculty_ids
    content = b"Yil,Atif\n2094-2095,10\n"
    source = _upload(client, "duplicate.csv", content, faculty_id, "2094-2095")
    duplicate = client.post(
        "/api/data-sources/upload",
        files={"file": ("copy.csv", content, "text/csv")},
        data={"scope_type": "faculty", "faculty_id": str(faculty_id), "academic_year": "2094-2095"},
    )
    assert duplicate.status_code == 409
    assert "daha önce" in duplicate.json()["detail"]
    client.delete(f"/api/data-sources/{source['id']}")

    unmatched_source = _upload(
        client, "unmatched.csv", "Bolum,Yil,Atif\nOlmayan Bolum,2094-2095,10\n".encode(),
        faculty_id, "2094-2095",
    )
    inspection = _inspect(client, unmatched_source["id"])
    report = _validate(client, unmatched_source["id"], inspection)["summary"]
    assert report["rows_unmatched"] == 1
    assert report["new_missing_values"] == 0
    assert "eşleşmedi" in report["unmatched_examples"][0]["reason"]
    client.delete(f"/api/data-sources/{unmatched_source['id']}")

    malformed = client.post(
        "/api/data-sources/upload",
        files={"file": ("broken.xlsx", b"not an excel file", "application/octet-stream")},
        data={"scope_type": "faculty", "faculty_id": str(faculty_id), "academic_year": "2094-2095"},
    )
    assert malformed.status_code == 400


def test_ai_context_marks_filename_and_no_authoritative_table_is_changed(
    client, db_session, faculty_ids
):
    faculty_id, _ = faculty_ids
    before_staff = db_session.query(AcademicStaff).count()
    source = _upload(client, "ai-source.csv", b"Yil,Atif\n2095-2096,333\n", faculty_id, "2095-2096")
    inspection = _inspect(client, source["id"])
    _import(client, source["id"], inspection)
    db_session.expire_all()
    rows = uploaded_academic_metrics(db_session, resolve(db_session, faculty_id=faculty_id), "2095-2096")
    assert any("[Kullanıcı veri kaynağı: ai-source.csv]" in item.label for item in rows)
    assert db_session.query(AcademicStaff).count() == before_staff
    client.delete(f"/api/data-sources/{source['id']}")


def test_sources_store_provenance_and_soft_delete_only_their_records(client, db_session, faculty_ids):
    faculty_id, _ = faculty_ids
    source = _upload(client, "provenance.csv", b"Yil,Atif\n2096-2097,41\n", faculty_id, "2096-2097")
    inspection = _inspect(client, source["id"])
    _import(client, source["id"], inspection)
    db_session.expire_all()
    stored = db_session.get(UploadedDataSource, source["id"])
    record = db_session.execute(select(UploadedMetricRecord).where(
        UploadedMetricRecord.uploaded_source_id == source["id"]
    )).scalars().one()
    assert stored.checksum_sha256 and len(stored.checksum_sha256) == 64
    assert record.original_row_number == 2
    assert json.loads(record.raw_values_json)["Atif"] == "41"
    client.delete(f"/api/data-sources/{source['id']}")
    db_session.expire_all()
    assert db_session.get(UploadedDataSource, source["id"]).is_active is False
    assert db_session.get(UploadedMetricRecord, record.id).is_active is False
