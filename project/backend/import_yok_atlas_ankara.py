"""Import the Ankara-only 2022-2024 YÖK Atlas extract as secondary data.

The importer never writes to the source files or to authoritative project
tables.  Atlas values are stored at source-row/metric grain in their own
table.  Consumers resolve existing project values first and use this table
only to fill a missing comparison metric.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable, Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.database import SessionLocal, init_db
from app.models import (
    AcademicProgram,
    DataSourceConflict,
    YokAtlasBenchmarkMetric,
    YksPlacementRecord,
)
from app.models.university_headcount import HOME_UNIVERSITY
from app.services.program_equivalence import (
    canonical_faculty_key,
    canonical_program_key,
    is_aggregate_label,
    program_language,
)


SOURCE_DATASET = "YÖK Atlas dataset 2025"
SOURCE_FILE = "yokatlas_ankara_2022_plus.csv"
UNIVERSITIES_FILE = "yokatlas_ankara_universiteler.csv"
EXPECTED_SOURCE_ROWS = 1768
EXPECTED_PROGRAM_UNIVERSITIES = 21
SUPPORTED_YEARS = (2022, 2023, 2024)

DEFAULT_SOURCE_DIR = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "yokatlas_ankara_2022_plus_output"
)

# metric -> (unit, source column stem).  2022 uses the source's original
# `yerlesme2022` spelling; it is intentionally not renamed in the CSV.
METRIC_COLUMNS = {
    "quota": ("kişi", {y: f"kontenjan{y}" for y in SUPPORTED_YEARS}),
    "placed": (
        "kişi",
        {2022: "yerlesme2022", 2023: "yerlesen2023", 2024: "yerlesen2024"},
    ),
    "base_score": ("puan", {y: f"puan{y}" for y in SUPPORTED_YEARS}),
    "success_rank": ("sıra", {y: f"sira{y}" for y in SUPPORTED_YEARS}),
    "preference_total": (
        "tercih",
        {2022: "tercihtoplam2022", 2023: "tercihtoplam2023"},
    ),
    "preference_first": (
        "tercih",
        {2022: "tercihbirinci2022", 2023: "tercihbirinci2023"},
    ),
    "preference_top3": (
        "tercih",
        {2022: "tercihilkuc2022", 2023: "tercihilkuc2023"},
    ),
    "preference_top9": (
        "tercih",
        {2022: "tercihilkdokuz2022", 2023: "tercihilkdokuz2023"},
    ),
}

_YEAR_COLUMN = re.compile(r"(20\d{2})$")
_SCHOLARSHIP = re.compile(
    r"\((Burslu|Ücretli|%\s*\d+\s*(?:İndirimli|Burslu)|Tam Burslu)\)",
    re.IGNORECASE,
)
_STORAGE_QUANTUM = Decimal("0.000000000000001")


def _storage_value(value: Decimal) -> Decimal:
    return Decimal(value).quantize(_STORAGE_QUANTUM, rounding=ROUND_HALF_UP)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _decimal(raw: object, metric: str) -> Optional[Decimal]:
    text = "" if raw is None else str(raw).strip()
    if not text:
        return None
    try:
        value = Decimal(text.replace(",", "."))
    except InvalidOperation as exc:
        raise ValueError(f"Geçersiz sayı: {raw!r} ({metric})") from exc
    # A score/rank of zero is the source's no-placement sentinel, not a real
    # admission threshold.  Quota/placed zero remains a real value.
    if metric in {"base_score", "success_rank"} and value <= 0:
        return None
    return value


def _scholarship(description: str) -> Optional[str]:
    match = _SCHOLARSHIP.search(description or "")
    return re.sub(r"\s+", " ", match.group(1)).strip() if match else None


def _academic_year(source_year: int) -> str:
    return f"{source_year}-{source_year + 1}"


def _read_csv(path: Path) -> tuple[list[dict], list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
        return rows, list(reader.fieldnames or [])


def validate_source(source_dir: Path) -> dict:
    """Validate the immutable source contract before touching the database."""
    program_path = source_dir / SOURCE_FILE
    universities_path = source_dir / UNIVERSITIES_FILE
    if not program_path.is_file() or not universities_path.is_file():
        raise FileNotFoundError(f"YÖK Atlas kaynak dosyaları bulunamadı: {source_dir}")

    rows, columns = _read_csv(program_path)
    university_rows, _ = _read_csv(universities_path)
    if len(rows) != EXPECTED_SOURCE_ROWS:
        raise ValueError(
            f"Kaynak satır sayısı {len(rows)}; beklenen {EXPECTED_SOURCE_ROWS}."
        )

    non_ankara = [r.get("id") for r in rows if (r.get("il") or "").strip().upper() != "ANKARA"]
    if non_ankara:
        raise ValueError(f"Ankara dışı program satırı bulundu: {non_ankara[:10]}")
    metadata_non_ankara = [
        r.get("isim") for r in university_rows
        if (r.get("il") or "").strip().upper() != "ANKARA"
    ]
    if metadata_non_ankara:
        raise ValueError(
            "Ankara dışı üniversite metadata satırı bulundu: "
            f"{metadata_non_ankara[:10]}"
        )

    program_universities = sorted({(r.get("universite") or "").strip() for r in rows})
    if len(program_universities) != EXPECTED_PROGRAM_UNIVERSITIES:
        raise ValueError(
            f"Program verisinde {len(program_universities)} üniversite var; "
            f"beklenen {EXPECTED_PROGRAM_UNIVERSITIES}."
        )

    metric_stems = {
        column.rstrip("0123456789")
        for _, (_, year_columns) in METRIC_COLUMNS.items()
        for column in year_columns.values()
    }
    metric_years = {
        int(match.group(1))
        for column in columns
        if column.rstrip("0123456789") in metric_stems
        if (match := _YEAR_COLUMN.search(column))
    }
    if metric_years != set(SUPPORTED_YEARS):
        raise ValueError(
            f"Metrik yılları {sorted(metric_years)}; beklenen "
            f"{list(SUPPORTED_YEARS)}."
        )

    # Detect literal duplicate source rows without treating distinct source
    # program codes/scholarship tracks as duplicates.
    fingerprints: set[tuple] = set()
    duplicate_ids: list[str] = []
    non_id_columns = [column for column in columns if column != "id"]
    for row in rows:
        fingerprint = tuple(row.get(column, "") for column in non_id_columns)
        if fingerprint in fingerprints:
            duplicate_ids.append(str(row.get("id") or ""))
        else:
            fingerprints.add(fingerprint)

    return {
        "program_path": program_path,
        "universities_path": universities_path,
        "rows": rows,
        "columns": columns,
        "university_rows": university_rows,
        "program_universities": program_universities,
        "years": sorted(metric_years),
        "duplicate_ids": duplicate_ids,
        "program_hash": _sha256(program_path),
        "universities_hash": _sha256(universities_path),
    }


def _row_metrics(row: dict) -> Iterable[dict]:
    for metric, (unit, year_columns) in METRIC_COLUMNS.items():
        for year, column in year_columns.items():
            value = _decimal(row.get(column), metric)
            if value is None:
                continue
            yield {
                "source_year": year,
                "academic_year": _academic_year(year),
                "metric": metric,
                "value": _storage_value(value),
                "source_raw_value": str(row.get(column)).strip(),
                "unit": unit,
                "derived": False,
                "methodology": (
                    f"YÖK Atlas {column} kaynak hücresinin doğrudan değeri; "
                    "hücre dönüştürülmedi veya tahmin edilmedi."
                ),
            }

    for year in SUPPORTED_YEARS:
        quota = _decimal(row.get(f"kontenjan{year}"), "quota")
        placed_column = "yerlesme2022" if year == 2022 else f"yerlesen{year}"
        placed = _decimal(row.get(placed_column), "placed")
        if quota is None or quota <= 0 or placed is None:
            continue
        yield {
            "source_year": year,
            "academic_year": _academic_year(year),
            "metric": "occupancy_percent",
            "value": (placed / quota * Decimal("100")).quantize(
                _STORAGE_QUANTUM, rounding=ROUND_HALF_UP
            ),
            "source_raw_value": None,
            "unit": "%",
            "derived": True,
            "methodology": (
                f"YÖK Atlas {placed_column} / kontenjan{year} × 100; "
                "yerleşen kohortu doluluğudur."
            ),
        }


def _aggregate(values: list[Decimal], metric: str) -> Optional[Decimal]:
    if not values:
        return None
    if metric == "base_score":
        return min(v for v in values if v > 0)
    if metric == "success_rank":
        return max(v for v in values if v > 0)
    return sum(values, Decimal("0"))


def _authoritative_conflicts(db: Session, source_rows: list[dict]) -> tuple[int, int]:
    """Cross-check ABÜ Atlas rows; keep and record internal YKS values."""
    atlas: dict[tuple[str, int, str], list[Decimal]] = defaultdict(list)
    for row in source_rows:
        if (row.get("universite") or "").strip().upper() != HOME_UNIVERSITY:
            continue
        key = canonical_program_key(row.get("isim"))
        if not key:
            continue
        for item in _row_metrics(row):
            if item["metric"] in {"quota", "placed", "base_score", "success_rank"}:
                atlas[(key, item["source_year"], item["metric"])].append(item["value"])

    internal: dict[tuple[str, int, str], list[Decimal]] = defaultdict(list)
    program_ids: dict[str, list[int]] = defaultdict(list)
    records = db.execute(
        select(YksPlacementRecord, AcademicProgram)
        .join(AcademicProgram, AcademicProgram.id == YksPlacementRecord.academic_program_id)
        .where(YksPlacementRecord.placement_year.in_(SUPPORTED_YEARS))
    ).all()
    for record, program in records:
        key = canonical_program_key(program.name)
        if not key:
            continue
        program_ids[key].append(program.id)
        fields = {
            "quota": record.quota,
            "placed": record.placed_students,
            "base_score": record.base_score,
            "success_rank": record.success_rank,
        }
        for metric, raw in fields.items():
            value = _decimal(raw, metric)
            if value is not None:
                internal[(key, record.placement_year, metric)].append(value)

    conflicts = 0
    equal = 0
    for identity in sorted(set(atlas) & set(internal)):
        key, year, metric = identity
        incoming = _aggregate(atlas[identity], metric)
        existing = _aggregate(internal[identity], metric)
        if incoming == existing:
            equal += 1
            continue
        conflicts += 1
        record_id = min(program_ids[key])
        field_name = f"yok_atlas_{metric}_{year}"
        already = db.execute(
            select(DataSourceConflict.id).where(
                DataSourceConflict.table_name == "academic_programs",
                DataSourceConflict.record_id == record_id,
                DataSourceConflict.field_name == field_name,
                DataSourceConflict.incoming_source == SOURCE_DATASET,
            )
        ).scalar_one_or_none()
        if already is None:
            db.add(
                DataSourceConflict(
                    table_name="academic_programs",
                    record_id=record_id,
                    field_name=field_name,
                    record_label=f"{key} · {year}",
                    existing_value=str(existing),
                    existing_source="Mevcut ABÜ ÖSYM/YKS verisi",
                    incoming_value=str(incoming),
                    incoming_source=SOURCE_DATASET,
                    resolution="kept_existing",
                    note=(
                        "YÖK Atlas ikincil kaynaktır; mevcut yetkili değer "
                        "korundu ve Atlas değeri yalnızca karşılaştırma "
                        "provenance tablosunda kaldı."
                    ),
                )
            )
    return conflicts, equal


def import_yok_atlas(
    db: Session,
    source_dir: Path = DEFAULT_SOURCE_DIR,
    *,
    purge: bool = False,
    check_only: bool = False,
) -> dict:
    audit = validate_source(Path(source_dir))
    rows = audit["rows"]
    slugs = {
        (r.get("isim") or "").strip(): (r.get("slug") or "").strip() or None
        for r in audit["university_rows"]
    }

    result = {
        "source_rows": len(rows),
        "ankara_universities": len(audit["program_universities"]),
        "years": audit["years"],
        "non_ankara_rows": 0,
        "older_metrics_imported": 0,
        "valid_program_rows": 0,
        "inserted": 0,
        "unchanged": 0,
        "skipped_missing_cells": 0,
        "skipped_aggregate_rows": 0,
        "skipped_duplicate_rows": len(audit["duplicate_ids"]),
        "conflicts": 0,
        "authoritative_equal": 0,
        "source_hash_before": {
            SOURCE_FILE: audit["program_hash"],
            UNIVERSITIES_FILE: audit["universities_hash"],
        },
    }
    if check_only:
        # Count candidates using exactly the same parser as the real import.
        duplicates = set(audit["duplicate_ids"])
        for row in rows:
            if str(row.get("id") or "") in duplicates:
                continue
            if is_aggregate_label(row.get("isim")):
                result["skipped_aggregate_rows"] += 1
                continue
            key = canonical_program_key(row.get("isim"))
            if not key:
                result["skipped_aggregate_rows"] += 1
                continue
            result["valid_program_rows"] += 1
            parsed_metrics = list(_row_metrics(row))
            possible_cells = (
                sum(len(columns) for _, columns in METRIC_COLUMNS.values())
                + len(SUPPORTED_YEARS)
            )
            result["inserted"] += len(parsed_metrics)
            result["skipped_missing_cells"] += possible_cells - len(parsed_metrics)
        result["source_hash_after"] = dict(result["source_hash_before"])
        result["source_files_unchanged"] = True
        return result

    if purge:
        db.execute(
            delete(YokAtlasBenchmarkMetric).where(
                YokAtlasBenchmarkMetric.source_dataset == SOURCE_DATASET
            )
        )
        db.flush()

    existing = {
        (row.source_file, row.source_program_code, row.source_year, row.metric): row
        for row in db.execute(
            select(YokAtlasBenchmarkMetric).where(
                YokAtlasBenchmarkMetric.source_dataset == SOURCE_DATASET
            )
        ).scalars()
    }
    duplicates = set(audit["duplicate_ids"])

    for row in rows:
        source_code = str(row.get("id") or "").strip()
        if source_code in duplicates:
            continue
        if is_aggregate_label(row.get("isim")):
            result["skipped_aggregate_rows"] += 1
            continue
        canonical_key = canonical_program_key(row.get("isim"))
        if not canonical_key:
            result["skipped_aggregate_rows"] += 1
            continue
        result["valid_program_rows"] += 1

        university = (row.get("universite") or "").strip()
        faculty = (row.get("fakulte") or "").strip()
        program = (row.get("isim") or "").strip()
        description = (row.get("aciklama") or "").strip()
        parsed_metrics = list(_row_metrics(row))

        possible_cells = sum(len(columns) for _, columns in METRIC_COLUMNS.values()) + len(SUPPORTED_YEARS)
        result["skipped_missing_cells"] += possible_cells - len(parsed_metrics)

        for item in parsed_metrics:
            natural_key = (SOURCE_FILE, source_code, item["source_year"], item["metric"])
            current = existing.get(natural_key)
            if current is not None:
                if item["derived"]:
                    # SQLite's NUMERIC adapter passes through binary float;
                    # compare the published six-decimal derived ratio.
                    same = Decimal(current.value).quantize(Decimal("0.000001")) == Decimal(
                        item["value"]
                    ).quantize(Decimal("0.000001"))
                else:
                    # Direct metrics are audited by the exact original cell
                    # text, so numeric adapter rounding cannot create a false
                    # conflict on a rerun.
                    same = current.source_raw_value == item["source_raw_value"]
                if same:
                    result["unchanged"] += 1
                else:
                    result["conflicts"] += 1
                continue

            metric_row = YokAtlasBenchmarkMetric(
                university_name=university,
                faculty_name=faculty,
                canonical_faculty_key=canonical_faculty_key(faculty),
                program_name=program,
                canonical_program_key=canonical_key,
                city="ANKARA",
                university_type=(row.get("unitur") or "").strip() or None,
                program_language=program_language(description),
                scholarship_type=_scholarship(description),
                source_description=description or None,
                source_dataset=SOURCE_DATASET,
                source_file=SOURCE_FILE,
                source_program_code=source_code,
                source_university_code=slugs.get(university),
                source_row_identity=json.dumps(
                    {
                        "id": source_code,
                        "university": university,
                        "faculty": faculty,
                        "program": program,
                        "description": description or None,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                **item,
            )
            db.add(metric_row)
            existing[natural_key] = metric_row
            result["inserted"] += 1

    db.flush()
    authoritative_conflicts, authoritative_equal = _authoritative_conflicts(db, rows)
    result["conflicts"] += authoritative_conflicts
    result["authoritative_equal"] = authoritative_equal
    db.commit()

    after = {
        SOURCE_FILE: _sha256(audit["program_path"]),
        UNIVERSITIES_FILE: _sha256(audit["universities_path"]),
    }
    result["source_hash_after"] = after
    result["source_files_unchanged"] = after == result["source_hash_before"]
    if not result["source_files_unchanged"]:
        raise RuntimeError("YÖK Atlas kaynak dosyası aktarım sırasında değişti.")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ankara YÖK Atlas 2022-2024 verisini ikincil kaynak olarak aktarır."
    )
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument(
        "--purge",
        action="store_true",
        help="Yalnızca daha önce aktarılmış YÖK Atlas ikincil satırlarını siler.",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Kaynağı doğrular ve aday metrikleri sayar; veritabanına yazmaz.",
    )
    args = parser.parse_args()

    init_db()
    with SessionLocal() as db:
        result = import_yok_atlas(
            db, args.source_dir, purge=args.purge, check_only=args.check_only
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
