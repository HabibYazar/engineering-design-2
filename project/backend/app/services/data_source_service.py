"""Güvenli dosya inceleme, eşleme, doğrulama ve ikincil veri çözümleme."""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import unicodedata
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from fastapi import HTTPException, status
from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    AcademicProgram,
    AcademicStaff,
    Department,
    Faculty,
    UploadedDataSource,
    UploadedMetricRecord,
)
from app.services import auth_service
from app.services.manual_metric_registry import MANUAL_METRIC_REGISTRY, list_definitions
from app.services.manual_metric_service import (
    authoritative_value,
    exact_scope,
    validate_academic_year,
)
from app.services.scope import Scope, resolve


MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_IMPORT_ROWS = 50_000
PREVIEW_ROWS = 20
UPLOAD_DIR = Path(__file__).resolve().parents[3] / "user_data" / "uploads"
SUPPORTED_FILE_TYPES = {"csv", "xlsx", "xls", "json", "db"}
SOURCE_LABEL = "Kullanıcı veri kaynağı"

ENTITY_FIELDS = {
    "university", "faculty", "department", "program", "academic_year",
    "date", "academic_name", "title",
}


def _norm(value: Any) -> str:
    text_value = str(value or "").strip().casefold().replace("ı", "i")
    text_value = "".join(
        ch for ch in unicodedata.normalize("NFKD", text_value)
        if not unicodedata.combining(ch)
    )
    return re.sub(r"[^a-z0-9]+", "_", text_value).strip("_")


ALIASES: dict[str, set[str]] = {
    "university": {"universite", "university", "kurum"},
    "faculty": {"fakulte", "faculty", "fakulte_adi", "faculty_name"},
    "department": {"bolum", "department", "bolum_adi", "department_name"},
    "program": {"program", "program_adi", "program_name", "program_kodu", "program_code"},
    "academic_year": {"yil", "donem", "academic_year", "akademik_yil"},
    "date": {"tarih", "date"},
    "academic_name": {"ad_soyad", "akademisyen", "academic_name", "full_name"},
    "title": {"unvan", "title", "akademik_unvan"},
    "citation_count": {"atif", "atif_sayisi", "citation", "citation_count", "citations"},
    "project_count": {"proje", "proje_sayisi", "project", "project_count", "projects"},
    "patent_count": {"patent", "patent_sayisi", "patent_count", "patents"},
    "classroom_utilization_rate": {
        "derslik_kullanim_orani", "classroom_utilization", "classroom_utilization_rate"
    },
    "laboratory_utilization_rate": {
        "laboratuvar_kullanim_orani", "lab_kullanim_orani",
        "laboratory_utilization", "laboratory_utilization_rate",
    },
    "total_income": {"gelir", "toplam_gelir", "income", "total_income"},
    "total_expense": {"gider", "toplam_gider", "expense", "total_expense"},
    "personnel_cost": {"personel_gideri", "personel_maliyeti", "personnel_cost"},
}

# Kayıt defterine eklenen her anahtar, açıkça ek bir eş anlamlısı
# tanımlanmasa bile kendi kararlı anahtarıyla otomatik eşlenebilir.
for _metric_key in MANUAL_METRIC_REGISTRY:
    ALIASES.setdefault(_metric_key, {_metric_key})


def semantic_fields() -> list[dict]:
    fields = [
        {"key": key, "label": label, "kind": "entity"}
        for key, label in [
            ("university", "Üniversite"), ("faculty", "Fakülte"),
            ("department", "Bölüm"), ("program", "Program"),
            ("academic_year", "Akademik Yıl"), ("date", "Tarih"),
            ("academic_name", "Akademisyen Adı"), ("title", "Unvan"),
        ]
    ]
    fields.extend(
        {"key": item.key, "label": item.label, "kind": "metric", "unit": item.unit}
        for item in list_definitions()
    )
    return fields


def _error(code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=code, detail=detail)


def _file_type(filename: str) -> str:
    suffix = Path(filename or "").suffix.lower().lstrip(".")
    if suffix not in SUPPORTED_FILE_TYPES:
        raise _error(415, "Desteklenmeyen dosya. XLSX, XLS, CSV, JSON veya SQLite .db yükleyin.")
    return suffix


def _verify_signature(file_type: str, content: bytes) -> None:
    if not content:
        raise _error(400, "Yüklenen dosya boş.")
    if file_type == "xlsx" and not content.startswith(b"PK"):
        raise _error(400, "XLSX dosyası bozuk veya geçersiz.")
    if file_type == "xls" and not content.startswith(bytes.fromhex("D0CF11E0")):
        raise _error(400, "XLS dosyası bozuk veya geçersiz.")
    if file_type == "db" and not content.startswith(b"SQLite format 3\x00"):
        raise _error(400, "Dosya geçerli bir SQLite veritabanı değil.")


def _actor(db: Session, token: Optional[str], scope: Scope) -> Optional[str]:
    if not token:
        return None
    actor = auth_service.get_session(token)
    if actor is None:
        raise _error(401, "Oturum geçersiz veya sona ermiş.")
    if actor["role"] == "Admin":
        return actor["username"]
    if actor["role"] == "Dekan" and scope.faculty_id == actor.get("faculty_id"):
        return actor["username"]
    if actor["role"] == "Bölüm Başkanı" and scope.department_id == actor.get("department_id"):
        return actor["username"]
    raise _error(403, "Bu kapsamda veri kaynağı yönetme yetkiniz yok.")


def _source_path(source: UploadedDataSource) -> Path:
    root = UPLOAD_DIR.resolve()
    path = Path(source.stored_path).resolve()
    if path.parent != root or path.name != source.stored_filename:
        raise _error(500, "Veri kaynağı depolama yolu güvenli değil.")
    return path


def source_provenance(source: UploadedDataSource) -> dict:
    """Normalize uploaded-source provenance without promoting it to authority."""
    provenance = (source.source_label or SOURCE_LABEL).strip() or SOURCE_LABEL
    marker = f"{provenance}\n{source.notes or ''}".upper()
    return {
        "source_type": "uploaded",
        "source_label": provenance,
        "provenance": provenance,
        "is_synthetic": (
            "SYNTHETIC_GENERATED" in marker or "IS_SYNTHETIC=TRUE" in marker
        ),
        "uploaded_source_id": source.id,
        "filename": source.original_filename,
    }


def source_to_dict(source: UploadedDataSource, *, include_validation: bool = False) -> dict:
    provenance = source_provenance(source)
    result = {
        "id": source.id,
        "original_filename": source.original_filename,
        "file_type": source.file_type,
        "selected_sheet": source.selected_sheet,
        "selected_table": source.selected_table,
        "status": source.status,
        "source_label": provenance["source_label"],
        "provenance": provenance["provenance"],
        "is_synthetic": provenance["is_synthetic"],
        "checksum_sha256": source.checksum_sha256,
        "scope_type": source.scope_type,
        "faculty_id": source.faculty_id,
        "department_id": source.department_id,
        "program_id": source.program_id,
        "academic_year": source.academic_year,
        "row_count": source.row_count,
        "imported_row_count": source.imported_row_count,
        "unmatched_row_count": source.unmatched_row_count,
        "conflict_count": source.conflict_count,
        "uploaded_by": source.uploaded_by,
        "notes": source.notes,
        "is_active": source.is_active,
        "uploaded_at": source.uploaded_at,
        "imported_at": source.imported_at,
        "deleted_at": source.deleted_at,
        "mapping": json.loads(source.mapping_json) if source.mapping_json else None,
    }
    if include_validation:
        result["validation"] = json.loads(source.validation_json) if source.validation_json else None
    return result


def create_source(
    db: Session, *, original_filename: str, content: bytes, scope_type: str,
    faculty_id: Optional[int], department_id: Optional[int], program_id: Optional[int],
    academic_year: Optional[str], notes: Optional[str], session_token: Optional[str],
) -> UploadedDataSource:
    if len(content) > MAX_UPLOAD_BYTES:
        raise _error(413, "Dosya 20 MB yükleme sınırını aşıyor.")
    file_type = _file_type(original_filename)
    _verify_signature(file_type, content)
    scope = exact_scope(db, scope_type, faculty_id, department_id, program_id)
    if academic_year:
        validate_academic_year(academic_year)
    uploaded_by = _actor(db, session_token, scope)
    checksum = hashlib.sha256(content).hexdigest()
    existing = db.execute(
        select(UploadedDataSource).where(
            UploadedDataSource.checksum_sha256 == checksum,
            UploadedDataSource.is_active.is_(True),
        )
    ).scalars().first()
    if existing:
        raise _error(409, f"Bu dosya daha önce yüklenmiş: {existing.original_filename}")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stored_filename = f"{uuid.uuid4().hex}.{file_type}"
    path = (UPLOAD_DIR / stored_filename).resolve()
    if path.parent != UPLOAD_DIR.resolve():
        raise _error(500, "Güvenli depolama yolu oluşturulamadı.")
    path.write_bytes(content)
    source = UploadedDataSource(
        original_filename=Path(original_filename).name[:500] or f"upload.{file_type}",
        stored_filename=stored_filename,
        stored_path=str(path),
        file_type=file_type,
        checksum_sha256=checksum,
        scope_type=scope.level,
        faculty_id=scope.faculty_id,
        department_id=scope.department_id,
        program_id=scope.academic_program_id,
        academic_year=academic_year,
        uploaded_by=uploaded_by,
        notes=(notes or "").strip() or None,
    )
    db.add(source)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        path.unlink(missing_ok=True)
        raise _error(409, "Bu dosya daha önce yüklenmiş.") from exc
    db.refresh(source)
    return source


def get_source(db: Session, source_id: int, *, active_only: bool = True) -> UploadedDataSource:
    source = db.get(UploadedDataSource, source_id)
    if source is None or (active_only and not source.is_active):
        raise _error(404, "Veri kaynağı bulunamadı.")
    return source


def _clean_value(value: Any) -> Any:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    return str(value).strip()


def _frame_rows(frame: pd.DataFrame) -> tuple[list[str], list[dict]]:
    if len(frame.index) > MAX_IMPORT_ROWS:
        raise _error(413, f"Dosya en fazla {MAX_IMPORT_ROWS:,} satır içerebilir.")
    columns = [str(column).strip() for column in frame.columns]
    if not columns or any(not column for column in columns) or len(set(columns)) != len(columns):
        raise _error(400, "Sütun adları boş veya yinelenmiş olamaz.")
    frame = frame.copy()
    frame.columns = columns
    return columns, [
        {key: _clean_value(value) for key, value in record.items()}
        for record in frame.to_dict(orient="records")
    ]


def _json_rows(content: bytes) -> tuple[list[str], list[dict]]:
    try:
        payload = json.loads(content.decode("utf-8-sig"))
    except Exception as exc:
        raise _error(400, f"JSON dosyası okunamadı: {exc}") from exc
    if isinstance(payload, dict):
        candidates = [payload[key] for key in ("records", "data", "items", "rows") if isinstance(payload.get(key), list)]
        if not candidates:
            candidates = [value for value in payload.values() if isinstance(value, list)]
        if len(candidates) != 1:
            raise _error(400, "JSON nesnesi tek bir kayıt dizisi içermelidir.")
        payload = candidates[0]
    if not isinstance(payload, list) or not payload:
        raise _error(400, "JSON dosyası boş olmayan bir nesne dizisi içermelidir.")
    if len(payload) > MAX_IMPORT_ROWS or any(not isinstance(row, dict) for row in payload):
        raise _error(400, "JSON kayıtları nesne olmalı ve satır sınırını aşmamalıdır.")
    columns: list[str] = []
    for row in payload:
        for key in row:
            key = str(key).strip()
            if key and key not in columns:
                columns.append(key)
    return columns, [{column: _clean_value(row.get(column)) for column in columns} for row in payload]


def _sqlite_tables(path: Path) -> list[str]:
    try:
        connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        connection.enable_load_extension(False)
        connection.execute("PRAGMA query_only = ON")
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        return [str(row[0]) for row in rows]
    except sqlite3.Error as exc:
        raise _error(400, f"SQLite dosyası okunamadı: {exc}") from exc
    finally:
        if "connection" in locals():
            connection.close()


def _read_source(source: UploadedDataSource, selected_sheet: Optional[str], selected_table: Optional[str]) -> dict:
    path = _source_path(source)
    if not path.is_file():
        raise _error(410, "Yüklenen dosya depolama alanında bulunamadı.")
    content = path.read_bytes()
    try:
        if source.file_type == "csv":
            frame = pd.read_csv(BytesIO(content), dtype=object, keep_default_na=False, sep=None, engine="python")
            columns, rows = _frame_rows(frame)
            return {"sheets": [], "tables": [], "selected_sheet": None, "selected_table": None, "columns": columns, "rows": rows}
        if source.file_type in {"xlsx", "xls"}:
            engine = "openpyxl" if source.file_type == "xlsx" else "xlrd"
            workbook = pd.ExcelFile(BytesIO(content), engine=engine)
            sheets = list(workbook.sheet_names)
            chosen = selected_sheet or source.selected_sheet or (sheets[0] if sheets else None)
            if not chosen or chosen not in sheets:
                raise _error(422, "Geçerli bir Excel sayfası seçin.")
            columns, rows = _frame_rows(pd.read_excel(workbook, sheet_name=chosen, dtype=object))
            return {"sheets": sheets, "tables": [], "selected_sheet": chosen, "selected_table": None, "columns": columns, "rows": rows}
        if source.file_type == "json":
            columns, rows = _json_rows(content)
            return {"sheets": [], "tables": [], "selected_sheet": None, "selected_table": None, "columns": columns, "rows": rows}

        tables = _sqlite_tables(path)
        chosen = selected_table or source.selected_table
        if not chosen:
            return {"sheets": [], "tables": tables, "selected_sheet": None, "selected_table": None, "columns": [], "rows": [], "requires_table_selection": True}
        if chosen not in tables:
            raise _error(422, "Geçerli bir SQLite tablosu seçin.")
        connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        try:
            connection.enable_load_extension(False)
            connection.execute("PRAGMA query_only = ON")
            quoted = '"' + chosen.replace('"', '""') + '"'
            count = connection.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0]
            if count > MAX_IMPORT_ROWS:
                raise _error(413, f"Tablo en fazla {MAX_IMPORT_ROWS:,} satır içerebilir.")
            frame = pd.read_sql_query(f"SELECT * FROM {quoted}", connection)
        finally:
            connection.close()
        columns, rows = _frame_rows(frame)
        return {"sheets": [], "tables": tables, "selected_sheet": None, "selected_table": chosen, "columns": columns, "rows": rows}
    except HTTPException:
        raise
    except Exception as exc:
        raise _error(400, f"Dosya okunamadı veya bozuk: {exc}") from exc


def _auto_mapping(columns: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    used: set[str] = set()
    for column in columns:
        normalized = _norm(column)
        matches = [semantic for semantic, aliases in ALIASES.items() if normalized in aliases]
        if len(matches) == 1 and matches[0] not in used:
            result[column] = matches[0]
            used.add(matches[0])
    return result


def inspect_source(db: Session, source_id: int, selected_sheet: Optional[str], selected_table: Optional[str]) -> dict:
    source = get_source(db, source_id)
    parsed = _read_source(source, selected_sheet, selected_table)
    if parsed.get("selected_sheet"):
        source.selected_sheet = parsed["selected_sheet"]
    if parsed.get("selected_table"):
        source.selected_table = parsed["selected_table"]
    source.row_count = len(parsed["rows"])
    source.status = "inspected"
    db.commit()
    return {
        "source": source_to_dict(source),
        "sheets": parsed["sheets"], "tables": parsed["tables"],
        "selected_sheet": parsed.get("selected_sheet"),
        "selected_table": parsed.get("selected_table"),
        "requires_table_selection": parsed.get("requires_table_selection", False),
        "row_count": len(parsed["rows"]), "columns": parsed["columns"],
        "preview_rows": parsed["rows"][:PREVIEW_ROWS],
        "auto_mapping": _auto_mapping(parsed["columns"]),
        "semantic_fields": semantic_fields(),
    }


def _unique_match(items: list[Any], raw: Any, *fields: str) -> Optional[Any]:
    needle = _norm(raw)
    if not needle:
        return None
    matches = [item for item in items if any(_norm(getattr(item, field, "")) == needle for field in fields)]
    return matches[0] if len(matches) == 1 else None


def _context_scope(db: Session, source: UploadedDataSource) -> Scope:
    return exact_scope(db, source.scope_type, source.faculty_id, source.department_id, source.program_id)


def _row_scope(db: Session, source: UploadedDataSource, row: dict, reverse: dict[str, str]) -> Scope:
    context = _context_scope(db, source)
    university_column = reverse.get("university")
    if university_column and row.get(university_column):
        if _norm(row[university_column]) not in {"abu", "ankara_bilim_universitesi", "ankara_science_university"}:
            raise ValueError("Üniversite eşleşmedi")

    faculties = list(db.execute(select(Faculty)).scalars())
    faculty = _unique_match(faculties, row.get(reverse.get("faculty", "")), "name", "code") if reverse.get("faculty") else None
    if reverse.get("faculty") and row.get(reverse["faculty"]) and faculty is None:
        raise ValueError("Fakülte eşleşmedi")

    departments_query = select(Department)
    if faculty:
        departments_query = departments_query.where(Department.faculty_id == faculty.id)
    departments = list(db.execute(departments_query).scalars())
    department = _unique_match(departments, row.get(reverse.get("department", "")), "name", "code") if reverse.get("department") else None
    if reverse.get("department") and row.get(reverse["department"]) and department is None:
        raise ValueError("Bölüm eşleşmedi")

    programs_query = select(AcademicProgram)
    if department:
        programs_query = programs_query.where(AcademicProgram.department_id == department.id)
    programs = list(db.execute(programs_query).scalars())
    program = _unique_match(programs, row.get(reverse.get("program", "")), "name", "code") if reverse.get("program") else None
    if reverse.get("program") and row.get(reverse["program"]) and program is None:
        raise ValueError("Program eşleşmedi")

    if program:
        candidate = resolve(db, academic_program_id=program.id)
    elif department:
        candidate = resolve(db, department_id=department.id)
    elif faculty:
        candidate = resolve(db, faculty_id=faculty.id)
    else:
        candidate = context

    if (
        candidate.level == context.level
        and candidate.faculty_id == context.faculty_id
        and candidate.department_id == context.department_id
        and candidate.academic_program_id == context.academic_program_id
    ):
        return candidate
    if context.faculty_ids is not None and candidate.faculty_id not in context.faculty_ids:
        raise ValueError("Satır yükleme kapsamının dışında")
    if context.department_ids is not None and candidate.department_id not in context.department_ids:
        raise ValueError("Satır yükleme kapsamının dışında")
    if context.program_ids is not None and candidate.academic_program_id not in context.program_ids:
        raise ValueError("Satır yükleme kapsamının dışında")
    return candidate


def _academic_staff_id(db: Session, row: dict, reverse: dict[str, str], scope: Scope, year: str) -> Optional[int]:
    column = reverse.get("academic_name")
    if not column or not row.get(column):
        return None
    statement = select(AcademicStaff).where(
        AcademicStaff.academic_year == year,
        AcademicStaff.is_active.is_(True),
    )
    if scope.department_ids is not None:
        statement = statement.where(AcademicStaff.department_id.in_(scope.department_ids or {-1}))
    staff = list(db.execute(statement).scalars())
    matches = [item for item in staff if _norm(item.full_name) == _norm(row[column])]
    if len(matches) != 1:
        raise ValueError("Akademisyen adı tekil olarak eşleşmedi")
    return matches[0].id


def _decimal(raw: Any) -> Decimal:
    text_value = str(raw).strip().replace(" ", "")
    if "," in text_value and "." not in text_value:
        text_value = text_value.replace(",", ".")
    try:
        value = Decimal(text_value)
    except InvalidOperation as exc:
        raise ValueError("Sayısal değer geçersiz") from exc
    if not value.is_finite():
        raise ValueError("Sayısal değer sonlu değil")
    return value


def _validate_mapping(columns: list[str], mapping: dict[str, str]) -> dict[str, str]:
    unknown_columns = set(mapping) - set(columns)
    if unknown_columns:
        raise _error(422, f"Dosyada bulunmayan sütunlar eşlendi: {', '.join(sorted(unknown_columns))}")
    allowed = ENTITY_FIELDS | set(MANUAL_METRIC_REGISTRY) | {"ignore"}
    unknown_fields = set(mapping.values()) - allowed
    if unknown_fields:
        raise _error(422, f"Bilinmeyen anlamsal alanlar: {', '.join(sorted(unknown_fields))}")
    active = [value for value in mapping.values() if value != "ignore"]
    if len(active) != len(set(active)):
        raise _error(422, "Bir anlamsal alana birden fazla sütun eşlenemez.")
    if not any(value in MANUAL_METRIC_REGISTRY for value in active):
        raise _error(422, "En az bir metrik sütunu eşlenmelidir.")
    return {column: semantic for column, semantic in mapping.items() if semantic != "ignore"}


def validation_report(
    db: Session, source: UploadedDataSource, mapping: dict[str, str],
    selected_sheet: Optional[str], selected_table: Optional[str],
) -> tuple[dict, list[dict]]:
    parsed = _read_source(source, selected_sheet, selected_table)
    mapping = _validate_mapping(parsed["columns"], mapping)
    reverse = {semantic: column for column, semantic in mapping.items()}
    metric_pairs = [(column, semantic) for column, semantic in mapping.items() if semantic in MANUAL_METRIC_REGISTRY]
    candidates: list[dict] = []
    unmatched: list[dict] = []
    conflicts: list[dict] = []
    valid_rows: set[int] = set()
    importable_rows: set[int] = set()

    for row_number, row in enumerate(parsed["rows"], start=2):
        try:
            row_scope = _row_scope(db, source, row, reverse)
            year = str(row.get(reverse.get("academic_year", "")) or source.academic_year or "").strip()
            validate_academic_year(year)
            staff_id = _academic_staff_id(db, row, reverse, row_scope, year)
            row_had_value = False
            row_candidates: list[dict] = []
            row_conflicts: list[dict] = []
            for column, metric_key in metric_pairs:
                raw = row.get(column)
                if raw in (None, ""):
                    continue
                row_had_value = True
                definition = MANUAL_METRIC_REGISTRY[metric_key]
                value = _decimal(raw)
                if definition.minimum is not None and value < definition.minimum:
                    raise ValueError(f"{definition.label}: minimum {definition.minimum}")
                if definition.maximum is not None and value > definition.maximum:
                    raise ValueError(f"{definition.label}: maksimum {definition.maximum}")
                if definition.integer_only and value != value.to_integral_value():
                    raise ValueError(f"{definition.label}: tam sayı gerekli")
                authority = authoritative_value(db, definition, row_scope, year)
                item = {
                    "metric_key": metric_key, "scope": row_scope,
                    "academic_staff_id": staff_id, "academic_year": year,
                    "numeric_value": value, "unit": definition.unit,
                    "original_row_number": row_number, "raw_values": row,
                }
                if authority is not None:
                    row_conflicts.append({
                        "row": row_number, "metric": definition.label,
                        "uploaded_value": str(value), "authoritative_value": str(authority.value),
                        "authoritative_source": authority.source_label,
                    })
                else:
                    row_candidates.append(item)
            if not row_had_value:
                raise ValueError("Eşlenen metrik sütunları boş")
            valid_rows.add(row_number)
            conflicts.extend(row_conflicts)
            candidates.extend(row_candidates)
            if row_candidates:
                importable_rows.add(row_number)
        except (ValueError, HTTPException) as exc:
            detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
            unmatched.append({"row": row_number, "reason": detail, "values": row})

    report = {
        "rows_read": len(parsed["rows"]),
        "rows_valid": len(valid_rows),
        "rows_unmatched": len(unmatched),
        "conflict_count": len(conflicts),
        "new_missing_values": len(candidates),
        "importable_row_count": len(importable_rows),
        "unmatched_examples": unmatched[:10],
        "conflict_examples": conflicts[:10],
        "mapping": mapping,
        "selected_sheet": parsed.get("selected_sheet"),
        "selected_table": parsed.get("selected_table"),
    }
    return report, candidates


def validate_source(
    db: Session, source_id: int, mapping: dict[str, str],
    selected_sheet: Optional[str], selected_table: Optional[str],
) -> dict:
    source = get_source(db, source_id)
    if source.status == "imported":
        raise _error(409, "İçe aktarılmış kaynak yeniden doğrulanamaz.")
    report, _ = validation_report(db, source, mapping, selected_sheet, selected_table)
    source.mapping_json = json.dumps(report["mapping"], ensure_ascii=False)
    source.validation_json = json.dumps(report, ensure_ascii=False, default=str)
    source.selected_sheet = report["selected_sheet"]
    source.selected_table = report["selected_table"]
    source.row_count = report["rows_read"]
    source.unmatched_row_count = report["rows_unmatched"]
    source.conflict_count = report["conflict_count"]
    source.status = "validated"
    db.commit()
    return {"source": source_to_dict(source), "summary": report}


def import_source(
    db: Session, source_id: int, mapping: dict[str, str],
    selected_sheet: Optional[str], selected_table: Optional[str], confirm: bool,
    session_token: Optional[str],
) -> dict:
    if not confirm:
        raise _error(422, "İçe aktarma onayı gerekli.")
    source = get_source(db, source_id)
    if source.status == "imported":
        raise _error(409, "Bu veri kaynağı zaten içe aktarılmış.")
    _actor(db, session_token, _context_scope(db, source))
    report, candidates = validation_report(db, source, mapping, selected_sheet, selected_table)
    for item in candidates:
        row_scope = item["scope"]
        db.add(UploadedMetricRecord(
            uploaded_source_id=source.id,
            metric_key=item["metric_key"], entity_type="academic_staff" if item["academic_staff_id"] else "metric",
            scope_type=row_scope.level, faculty_id=row_scope.faculty_id,
            department_id=row_scope.department_id, program_id=row_scope.academic_program_id,
            academic_staff_id=item["academic_staff_id"], academic_year=item["academic_year"],
            numeric_value=item["numeric_value"], unit=item["unit"],
            original_row_number=item["original_row_number"],
            raw_values_json=json.dumps(item["raw_values"], ensure_ascii=False, default=str),
        ))
    source.mapping_json = json.dumps(report["mapping"], ensure_ascii=False)
    source.validation_json = json.dumps(report, ensure_ascii=False, default=str)
    source.selected_sheet = report["selected_sheet"]
    source.selected_table = report["selected_table"]
    source.row_count = report["rows_read"]
    source.imported_row_count = report["importable_row_count"]
    source.unmatched_row_count = report["rows_unmatched"]
    source.conflict_count = report["conflict_count"]
    source.status = "imported"
    source.imported_at = datetime.now()
    db.commit()
    return {"source": source_to_dict(source, include_validation=True), "summary": report}


def list_sources(db: Session, *, include_deleted: bool = False) -> list[dict]:
    statement = select(UploadedDataSource)
    if not include_deleted:
        statement = statement.where(UploadedDataSource.is_active.is_(True))
    rows = db.execute(statement.order_by(UploadedDataSource.uploaded_at.desc(), UploadedDataSource.id.desc())).scalars()
    return [source_to_dict(row) for row in rows]


def delete_source(db: Session, source_id: int, session_token: Optional[str]) -> dict:
    source = get_source(db, source_id)
    _actor(db, session_token, _context_scope(db, source))
    db.query(UploadedMetricRecord).filter(
        UploadedMetricRecord.uploaded_source_id == source.id,
        UploadedMetricRecord.is_active.is_(True),
    ).update({UploadedMetricRecord.is_active: False}, synchronize_session=False)
    source.is_active = False
    source.status = "deleted"
    source.deleted_at = datetime.now()
    db.commit()
    path = _source_path(source)
    path.unlink(missing_ok=True)
    return {"id": source.id, "status": "deleted", "message": "Yalnızca bu kaynağa bağlı ikincil kayıtlar kaldırıldı."}


def _exact_record_scope(statement, scope: Scope):
    return statement.where(
        UploadedMetricRecord.scope_type == scope.level,
        UploadedMetricRecord.faculty_id.is_(None) if scope.faculty_id is None else UploadedMetricRecord.faculty_id == scope.faculty_id,
        UploadedMetricRecord.department_id.is_(None) if scope.department_id is None else UploadedMetricRecord.department_id == scope.department_id,
        UploadedMetricRecord.program_id.is_(None) if scope.academic_program_id is None else UploadedMetricRecord.program_id == scope.academic_program_id,
    )


def uploaded_value(db: Session, metric_key: str, academic_year: str, scope: Scope) -> Optional[dict]:
    statement = select(UploadedMetricRecord, UploadedDataSource).join(
        UploadedDataSource, UploadedMetricRecord.uploaded_source_id == UploadedDataSource.id
    ).where(
        UploadedMetricRecord.metric_key == metric_key,
        UploadedMetricRecord.academic_year == academic_year,
        UploadedMetricRecord.is_active.is_(True),
        UploadedDataSource.is_active.is_(True),
        UploadedDataSource.status == "imported",
    )
    pairs = db.execute(
        _exact_record_scope(statement, scope).order_by(
            UploadedDataSource.uploaded_at.desc(), UploadedDataSource.id.desc()
        )
    ).all()
    if not pairs:
        return None
    latest = pairs[0][1]
    records = [record for record, source in pairs if source.id == latest.id]
    values = [record.numeric_value for record in records if record.numeric_value is not None]
    if not values:
        return None
    return {
        "value": sum(values, Decimal("0")), "source": latest,
        "record_count": len(records),
    }


def governed_records(
    db: Session,
    *,
    metric_keys: tuple[str, ...] | list[str],
    academic_year: Optional[str] = None,
    scope: Optional[Scope] = None,
    record_scope_type: Optional[str] = None,
    entity_type: Optional[str] = None,
) -> list[dict]:
    """Kapsamdaki en yeni, aktif ve izlenebilir yüklenmiş satırları getirir.

    Bu fonksiyon yalnızca ikincil kaynağı okur; yetkili önceliği onu
    çağıran servis tarafından, yerel satır kimliği bazında uygulanır.
    Aynı kimlik birden fazla dosyada bulunursa en yeni aktif kaynak kazanır.
    Ad/kod metniyle eşleşme yapılmaz; sadece kayıtlı yabancı anahtarlar
    ve çözülmüş Scope kümeleri kullanılır.
    """
    keys = tuple(dict.fromkeys(metric_keys))
    if not keys:
        return []
    statement = (
        select(UploadedMetricRecord, UploadedDataSource)
        .join(
            UploadedDataSource,
            UploadedMetricRecord.uploaded_source_id == UploadedDataSource.id,
        )
        .where(
            UploadedMetricRecord.metric_key.in_(keys),
            UploadedMetricRecord.numeric_value.isnot(None),
            UploadedMetricRecord.is_active.is_(True),
            UploadedDataSource.is_active.is_(True),
            UploadedDataSource.status == "imported",
        )
    )
    if academic_year is not None:
        statement = statement.where(
            UploadedMetricRecord.academic_year == academic_year
        )
    if record_scope_type is not None:
        statement = statement.where(
            UploadedMetricRecord.scope_type == record_scope_type
        )
    if entity_type is not None:
        statement = statement.where(UploadedMetricRecord.entity_type == entity_type)
    if scope is not None:
        # Hangi kimlik sütununun kapsamı ifade ettiğini kaydın kendi
        # scope_type'ı belirler. Fakülte satırını torun program_id'leriyle
        # süzmek, geçerli fakülte metriğini yanlışlıkla dışlarıda bırakır.
        if record_scope_type == "program" and scope.program_ids is not None:
            statement = statement.where(
                UploadedMetricRecord.program_id.in_(scope.program_ids or {-1})
            )
        elif record_scope_type == "department" and scope.department_ids is not None:
            statement = statement.where(
                UploadedMetricRecord.department_id.in_(scope.department_ids or {-1})
            )
        elif record_scope_type == "faculty" and scope.faculty_ids is not None:
            statement = statement.where(
                UploadedMetricRecord.faculty_id.in_(scope.faculty_ids or {-1})
            )
        elif record_scope_type == "university" and not scope.is_university:
            statement = statement.where(UploadedMetricRecord.id == -1)
        elif record_scope_type is None:
            if scope.program_ids is not None:
                statement = statement.where(
                    UploadedMetricRecord.program_id.in_(scope.program_ids or {-1})
                )
            elif scope.department_ids is not None:
                statement = statement.where(
                    UploadedMetricRecord.department_id.in_(scope.department_ids or {-1})
                )
            elif scope.faculty_ids is not None:
                statement = statement.where(
                    UploadedMetricRecord.faculty_id.in_(scope.faculty_ids or {-1})
                )

    statement = statement.order_by(
        UploadedDataSource.uploaded_at.desc(),
        UploadedDataSource.id.desc(),
        UploadedMetricRecord.id.desc(),
    )
    result: list[dict] = []
    seen: set[tuple] = set()
    for record, source in db.execute(statement):
        identity = (
            record.metric_key,
            record.academic_year,
            record.scope_type,
            record.faculty_id,
            record.department_id,
            record.program_id,
            record.academic_staff_id,
        )
        if identity in seen:
            continue
        seen.add(identity)
        result.append(
            {
                "record": record,
                "source": source,
                "metric_key": record.metric_key,
                "academic_year": record.academic_year,
                "scope_type": record.scope_type,
                "faculty_id": record.faculty_id,
                "department_id": record.department_id,
                "program_id": record.program_id,
                "academic_staff_id": record.academic_staff_id,
                "value": record.numeric_value,
                "unit": record.unit,
                **source_provenance(source),
            }
        )
    return result


def governed_metric_years(db: Session, metric_keys: tuple[str, ...] | list[str]) -> list[str]:
    """Verilen ikincil metriklerden en az birini taşıyan dönemler."""
    keys = tuple(dict.fromkeys(metric_keys))
    if not keys:
        return []
    return list(
        db.execute(
            select(UploadedMetricRecord.academic_year)
            .join(
                UploadedDataSource,
                UploadedMetricRecord.uploaded_source_id == UploadedDataSource.id,
            )
            .where(
                UploadedMetricRecord.metric_key.in_(keys),
                UploadedMetricRecord.numeric_value.isnot(None),
                UploadedMetricRecord.is_active.is_(True),
                UploadedDataSource.is_active.is_(True),
                UploadedDataSource.status == "imported",
            )
            .distinct()
            .order_by(UploadedMetricRecord.academic_year)
        ).scalars()
    )


def availability(
    db: Session, *, metric_key: str, academic_year: str, scope_type: str,
    faculty_id: Optional[int], department_id: Optional[int], program_id: Optional[int],
) -> dict:
    definition = MANUAL_METRIC_REGISTRY.get(metric_key)
    if definition is None:
        raise _error(404, "Metrik tanımı bulunamadı.")
    validate_academic_year(academic_year)
    scope = exact_scope(db, scope_type, faculty_id, department_id, program_id)
    scope_dict = {
        "scope_type": scope.level, "scope_label": scope.label,
        "faculty_id": scope.faculty_id, "department_id": scope.department_id,
        "program_id": scope.academic_program_id,
    }
    authority = authoritative_value(db, definition, scope, academic_year)
    if authority is not None:
        return {
            "definition": definition.public_dict(), "scope": scope_dict,
            "academic_year": academic_year, "status": "authoritative", "can_upload": False,
            "resolved_value": authority.value, "unit": definition.unit,
            "source_type": "authoritative", "source_label": authority.source_label,
            "provenance": authority.source_label, "is_synthetic": False,
            "uploaded_source_id": None, "filename": None,
        }
    uploaded = uploaded_value(db, metric_key, academic_year, scope)
    if uploaded:
        source = uploaded["source"]
        provenance = source_provenance(source)
        return {
            "definition": definition.public_dict(), "scope": scope_dict,
            "academic_year": academic_year, "status": "uploaded", "can_upload": True,
            "resolved_value": uploaded["value"], "unit": definition.unit,
            **provenance,
        }
    return {
        "definition": definition.public_dict(), "scope": scope_dict,
        "academic_year": academic_year, "status": "unavailable", "can_upload": True,
        "resolved_value": None, "unit": definition.unit, "source_type": None,
        "source_label": None, "provenance": None, "is_synthetic": False,
        "uploaded_source_id": None, "filename": None,
    }


def uploaded_context_rows(db: Session, scope: Scope, academic_year: str, screen_key: Optional[str] = None) -> list[dict]:
    result = []
    for definition in list_definitions(screen_key=screen_key, scope_type=scope.level):
        if authoritative_value(db, definition, scope, academic_year) is not None:
            continue
        resolved = uploaded_value(db, definition.key, academic_year, scope)
        if not resolved:
            continue
        source = resolved["source"]
        result.append({
            "metric_key": definition.key, "label": definition.label,
            "value": resolved["value"], "unit": definition.unit,
            "source_type": "uploaded",
            "source_label": f"Kullanıcı veri kaynağı: {source.original_filename}",
            "uploaded_source_id": source.id, "filename": source.original_filename,
        })
    return result
