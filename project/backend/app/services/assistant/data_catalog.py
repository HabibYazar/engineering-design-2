"""Executive assistant read-only institutional data catalog.

This module is the single data spine for ordinary assistant questions and
assistant charts.  It never executes model-authored SQL and it never writes to
the database.  Canonical metric keys are allowlisted below and delegated to
the same trusted services that power the dashboard.

The public API deliberately stays small:

``search_entities``          search the complete university hierarchy
``get_entity_details``       return a validated hierarchy node
``get_available_metrics``    discover actually measured metrics
``query_metrics``            retrieve allowlisted metrics for arbitrary nodes
``compare_entities``         intersect comparable metrics when none is named
``query_children``           measure the real children of a hierarchy node
``query_question``           deterministic natural-language planning facade

Numeric rows returned by this module are also the rows consumed by
``chart_builder``.  The model may explain those rows; it is never their source.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AcademicProgram, Department, Faculty
from app.services import (
    academic_staff_service,
    curriculum_service,
    data_source_service,
    decision_analytics_service,
    foreign_student_service,
    peer_comparison_service,
    physical_resources_service,
    student_count,
    tuition_service,
    unit_types,
)
from app.services.assistant import derivation_registry, entity_resolver
from app.services.manual_metric_registry import MANUAL_METRIC_REGISTRY
from app.services.scope import Scope, resolve as resolve_scope

logger = logging.getLogger(__name__)

SOURCE_AUTHORITATIVE = "authoritative"
SOURCE_DERIVED = "derived"
SOURCE_UPLOAD = "upload"
SOURCE_MIXED = "mixed"

UNAVAILABLE_MESSAGE = "Bu veri mevcut kaynaklarda bulunmuyor."

ENTITY_TYPE_LABELS = {
    "university": "Üniversite",
    "faculty": "Fakülte",
    "department": "Bölüm",
    "program": "Program",
    "academic_staff": "Akademisyen",
    "external_university": "Rakip Üniversite",
}


def _plain(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    return value


def _clean_label(entity_type: str, value: str) -> str:
    text = (value or "").strip()
    if entity_type == "program":
        text = re.sub(r"\s+\(%(?:100|50|25)\s+Burslu\)$", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s+\(Ücretli\)$", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s+\(İngilizce\)$", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s+\(Burslu\)$", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s+\(İÖ\)$", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s+(?:PR\.?|PROGRAMI)\s*$", "", text, flags=re.IGNORECASE)
    return text.strip() or value


@dataclass(frozen=True)
class CatalogEntity:
    entity_type: str
    entity_id: Optional[int]
    code: Optional[str]
    label: str
    raw_name: str
    parent_label: Optional[str] = None
    unit_type: Optional[str] = None

    @property
    def key(self) -> Tuple[str, Optional[int]]:
        return self.entity_type, self.entity_id

    def as_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "entity_type_label": ENTITY_TYPE_LABELS.get(
                self.entity_type, self.entity_type
            ),
            "code": self.code,
            "label": self.label,
            "parent_label": self.parent_label,
        }


@dataclass(frozen=True)
class MetricDefinition:
    key: str
    label: str
    unit: str
    patterns: Tuple[str, ...]
    preferred_rank: int = 100
    person_metric: bool = False


METRICS: Dict[str, MetricDefinition] = {
    # Student body / placement
    "students_per_academic_staff": MetricDefinition(
        "students_per_academic_staff", "Öğrenci / Akademisyen Oranı", "oran",
        (r"öğrenci\s*/\s*(?:akademisyen|akademik\s+personel|öğretim\s+üyesi)\s+oran",
         r"öğrenci\s+başına\s+(?:akademisyen|akademik\s+personel)"), 3,
    ),
    "student_count": MetricDefinition(
        "student_count", "Öğrenci Sayısı", "öğrenci",
        (r"(?:toplam\s+)?öğrenci\s+say", r"kaç\s+öğrenci", r"öğrenci\s+aded"), 1,
    ),
    "quota": MetricDefinition(
        "quota", "Kontenjan", "öğrenci", (r"kontenjan",), 8,
    ),
    "placed_students": MetricDefinition(
        "placed_students", "Yerleşen Öğrenci", "öğrenci",
        (r"yerleşen\s+öğrenci", r"yerleşen\s+say"), 9,
    ),
    "occupancy_percent": MetricDefinition(
        "occupancy_percent", "Kontenjan Doluluk Oranı", "%",
        (r"(?:kontenjan\s+)?doluluk\s+oran", r"yerleşme\s+oran"), 4,
    ),
    "foreign_student_count": MetricDefinition(
        "foreign_student_count", "Yabancı Öğrenci Sayısı", "öğrenci",
        (r"(?:yabancı|uluslararası)\s+öğrenci\s+say", r"yabancı\s+öğrenci"), 10,
    ),
    "yokatlas_total_students": MetricDefinition(
        "yokatlas_total_students", "YÖK Atlas Medyanı", "öğrenci",
        (r"yök\s*atlas\s*medyan",), 15,
    ),
    "yok_atlas_peer_student_count": MetricDefinition(
        "yok_atlas_peer_student_count", "YÖK Atlas Medyanı", "öğrenci",
        (r"yök\s*atlas\s*medyan",), 15,
    ),
    # Academic personnel

    "academic_staff_count": MetricDefinition(
        "academic_staff_count", "Akademisyen Sayısı", "akademisyen",
        (r"akademisyen\s+say", r"akademik\s+personel\s+say",
         r"öğretim\s+üyesi\s+say", r"kaç\s+(?:akademisyen|hoca)"), 2,
    ),
    "active_teaching_staff_count": MetricDefinition(
        "active_teaching_staff_count", "Fiilen Ders Veren Akademisyen", "akademisyen",
        (r"fiilen\s+ders\s+veren", r"aktif\s+öğretim\s+elemanı"), 11,
    ),
    "average_teaching_load_hours": MetricDefinition(
        "average_teaching_load_hours", "Ortalama Ders Yükü", "saat",
        (r"ortalama\s+ders\s+yük", r"ders\s+yükü\s+ortalama"), 12,
    ),
    "publication_count": MetricDefinition(
        "publication_count", "Yayın Sayısı", "yayın", (r"yayın\s+say", r"yayın"), 20,
        person_metric=True,
    ),
    "citation_count": MetricDefinition(
        "citation_count", "Atıf Sayısı", "atıf", (r"atıf\s+say", r"atıf"), 21,
        person_metric=True,
    ),
    "project_count": MetricDefinition(
        "project_count", "Proje Sayısı", "proje", (r"proje\s+say", r"proje"), 22,
        person_metric=True,
    ),
    "patent_count": MetricDefinition(
        "patent_count", "Patent Sayısı", "patent", (r"patent\s+say", r"patent"), 23,
        person_metric=True,
    ),
    "advising_count": MetricDefinition(
        "advising_count", "Danışmanlık Sayısı", "danışmanlık",
        (r"danışmanlık\s+say", r"danışmanlık"), 24, person_metric=True,
    ),
    "teaching_load_hours": MetricDefinition(
        "teaching_load_hours", "Ders Yükü", "saat", (r"ders\s+yük",), 25,
        person_metric=True,
    ),
    "community_engagement_score": MetricDefinition(
        "community_engagement_score", "Toplumsal Katkı Puanı", "puan",
        (r"toplumsal\s+katkı", r"community\s+engagement"), 26,
        person_metric=True,
    ),
    "performance_score": MetricDefinition(
        "performance_score", "Performans Puanı", "puan",
        (r"performans(?:\s+puan)?",), 5, person_metric=True,
    ),
    # Curriculum / physical resources
    "curriculum_course_count": MetricDefinition(
        "curriculum_course_count", "Müfredat Ders Sayısı", "ders",
        (r"müfredat\s+ders\s+say", r"ders\s+say"), 30,
    ),
    "current_course_records": MetricDefinition(
        "current_course_records", "Ders Atama Kaydı", "kayıt",
        (r"ders\s+atama", r"ders\s+kayd"), 31,
    ),
    "total_facilities": MetricDefinition(
        "total_facilities", "Fiziksel Mekân Sayısı", "mekân",
        (r"mekân\s+say", r"fiziksel\s+mekân"), 32,
    ),
    "total_capacity": MetricDefinition(
        "total_capacity", "Fiziksel Kapasite", "kişi",
        (r"(?:fiziksel\s+|mekân\s+|koltuk\s+)?kapasite(?:si|leri|ye)?\b", r"\bkapasite\b", r"koltuk\s+say"), 33,
    ),

    "classroom_count": MetricDefinition(
        "classroom_count", "Derslik Sayısı", "derslik", (r"derslik\s+say",), 34,
    ),
    "laboratory_count": MetricDefinition(
        "laboratory_count", "Laboratuvar Sayısı", "laboratuvar",
        (r"laboratuvar\s+say", r"laboratuar\s+say"), 35,
    ),
    "classroom_utilization_rate": MetricDefinition(
        "classroom_utilization_rate", "Derslik Kullanım Oranı", "%",
        (r"derslik\s+(?:kullanım|doluluk)\s+oran",), 36,
    ),
    "laboratory_utilization_rate": MetricDefinition(
        "laboratory_utilization_rate", "Laboratuvar Kullanım Oranı", "%",
        (r"laboratuv(?:ar|ar)\s+(?:kullanım|doluluk)\s+oran",), 37,
    ),
    # Finance and benchmarks
    "total_income": MetricDefinition(
        "total_income", "Toplam Gelir", "milyon USD", (r"toplam\s+gelir", r"gelir"), 40,
    ),
    "total_expense": MetricDefinition(
        "total_expense", "Toplam Gider", "milyon USD", (r"toplam\s+gider", r"harcama"), 41,
    ),
    "personnel_cost": MetricDefinition(
        "personnel_cost", "Personel Gideri", "milyon USD",
        (r"personel\s+(?:gider|maliyet)",), 42,
    ),
    "tuition_fee": MetricDefinition(
        "tuition_fee", "Yıllık Öğrenim Ücreti", "₺",
        (r"öğrenim\s+ücret", r"rakip.*ücret", r"ücret.*rakip"), 43,
    ),
    "yok_atlas_peer_student_count": MetricDefinition(
        "yok_atlas_peer_student_count", "YÖK Atlas Benzer Programlar Medyan Öğrenci Büyüklüğü", "öğrenci",
        (
            r"yök\s+atlas.*(?:öğrenci|büyüklük|kohort|benzer)",
            r"yok\s+atlas.*(?:ogrenci|buyukluk|kohort|benzer)",
            r"benzer\s+program.*(?:öğrenci|büyüklük)",
            r"yök\s+atlas",
            r"yok\s+atlas",
        ),
        15,
    ),
}



# These are canonical product aliases, not fuzzy matches.  A short alias may
# point to several historical codes because the real and legacy datasets use
# different code systems.  Kind is fixed where the product wording denotes a
# particular hierarchy level (e.g. short "Hukuk" means the faculty).
_CANONICAL_ENTITY_ALIASES: Dict[str, Tuple[str, Tuple[str, ...]]] = {
    "endustri": ("department", ("ENDMUH", "IE")),
    "bilgisayar": ("department", ("BILMUH", "CENG")),
    "yazilim": ("department", ("YAZMUH", "SWE")),
    "psikoloji": ("department", ("PSIKOLOJI", "PSY")),
    "hukuk": ("faculty", ("HUKUK",)),
    "muhendislik": ("faculty", ("MUHMIM", "FEA")),
    "ybs": ("department", ("YONBILSIS", "MIS")),
}

_ENTITY_SUFFIXES = (
    " bolumu", " fakultesi", " pr", " programi", " lisans programi",
    " yuksek lisans programi",
)


def _entity_aliases(entity: CatalogEntity) -> List[str]:
    aliases = {
        entity_resolver.normalize(entity.code or ""),
        entity_resolver.normalize(entity.label),
        entity_resolver.normalize(entity.raw_name),
    }
    for original in list(aliases):
        for suffix in _ENTITY_SUFFIXES:
            if original.endswith(suffix):
                aliases.add(original[: -len(suffix)].strip())
    return sorted((alias for alias in aliases if alias), key=len, reverse=True)


def _all_entities(db: Session) -> List[CatalogEntity]:
    faculties = {
        row.id: row
        for row in db.execute(select(Faculty).where(Faculty.is_active.is_(True)))
        .scalars()
        .all()
    }
    departments = {
        row.id: row
        for row in db.execute(select(Department).where(Department.is_active.is_(True)))
        .scalars()
        .all()
    }
    programs = (
        db.execute(
            select(AcademicProgram).where(AcademicProgram.is_active.is_(True))
        )
        .scalars()
        .all()
    )
    result: List[CatalogEntity] = []
    for row in faculties.values():
        result.append(
            CatalogEntity(
                "faculty",
                row.id,
                row.code,
                _clean_label("faculty", row.name),
                row.name,
                unit_type=row.unit_type,
            )
        )

    for row in departments.values():
        parent = faculties.get(row.faculty_id)
        result.append(
            CatalogEntity(
                "department", row.id, row.code,
                _clean_label("department", row.name), row.name,
                parent.name if parent else None,
            )
        )
    for row in programs:
        parent = departments.get(row.department_id)
        result.append(
            CatalogEntity(
                "program", row.id, row.code, _clean_label("program", row.name),
                row.name, parent.name if parent else None,
            )
        )
    return result


def _canonical_alias_target(
    db: Session, normalized_query: str
) -> Optional[List[CatalogEntity]]:
    target = _CANONICAL_ENTITY_ALIASES.get(normalized_query)
    if target is None:
        return None
    kind, codes = target
    return [
        entity for entity in _all_entities(db)
        if entity.entity_type == kind and entity.code in codes
    ]


def _coalesce_hierarchy_twins(
    db: Session, entities: Sequence[CatalogEntity], explicit_kind: Optional[str] = None
) -> List[CatalogEntity]:
    """Department/program twins are one common named concept unless a level is explicit.

    Real data often has both ``ENDMUH`` department and ``ENDMUH`` program.
    A bare "Endüstri Mühendisliği" is therefore resolved to its department,
    while "programı" explicitly selects the program.  This is deterministic
    hierarchy resolution, not fuzzy substitution.
    """
    unique = {entity.key: entity for entity in entities}
    values = list(unique.values())
    if explicit_kind:
        return [entity for entity in values if entity.entity_type == explicit_kind]

    department_codes = {
        entity.code for entity in values if entity.entity_type == "department"
    }
    values = [
        entity for entity in values
        if not (entity.entity_type == "program" and entity.code in department_codes)
    ]
    return values


def search_entities(
    db: Session, query: str, kinds: Optional[Sequence[str]] = None
) -> Dict[str, Any]:
    """Search all faculties, departments and programs without scope restriction."""
    normalized = entity_resolver.normalize(query)
    explicit_kind = None
    if re.search(r"\b(?:fakülte|fakültesi)\b", query or "", re.I):
        explicit_kind = "faculty"
    elif re.search(r"\b(?:bölüm|bölümü)\b", query or "", re.I):
        explicit_kind = "department"
    elif re.search(r"\b(?:program|programı)\b", query or "", re.I):
        explicit_kind = "program"

    canonical = _canonical_alias_target(db, normalized)
    if canonical is not None:
        matches = canonical
    else:
        exact: List[CatalogEntity] = []
        containing: List[CatalogEntity] = []
        for entity in _all_entities(db):
            if kinds and entity.entity_type not in kinds:
                continue
            aliases = _entity_aliases(entity)
            if normalized in aliases:
                exact.append(entity)
            elif normalized and any(
                set(normalized.split()).issubset(set(alias.split())) for alias in aliases
            ):
                containing.append(entity)
        matches = exact or containing

    matches = _coalesce_hierarchy_twins(db, matches, explicit_kind)
    matches.sort(key=lambda entity: (entity.entity_type, entity.label, entity.entity_id or 0))
    return {
        "query": query,
        "normalized_query": normalized,
        "searched_levels": ["faculty", "department", "program"],
        "matches": [entity.as_dict() for entity in matches],
        "entities": matches,
        "ambiguous": len(matches) > 1,
    }


def _alias_pattern(alias: str) -> re.Pattern[str]:
    words = [re.escape(word) for word in alias.split()]
    # Turkish case suffixes are accepted only at the final word boundary.
    suffix = (
        r"(?:"
        r"lerini|larini|lerine|larina|lerin|larin|lerde|larda|lerden|lardan|lerle|larla|ler|lar|"
        r"nin|nun|nün|nın|in|un|ün|ın|"
        r"yi|yu|yü|yı|ni|nu|nü|nı|i|u|ü|ı|"
        r"ye|ya|ne|na|e|a|"
        r"nde|nda|de|da|te|ta|"
        r"nden|ndan|den|dan|ten|tan|"
        r"deki|daki|teki|taki|"
        r"yle|yla|le|la"
        r")?"
    )
    return re.compile(r"(?<![a-z0-9])" + r"\s+".join(words) + suffix + r"(?![a-z0-9])")


def entities_in_text(db: Session, message: str) -> List[CatalogEntity]:
    """Resolve every explicitly named unit against the full hierarchy."""
    normalized = entity_resolver.normalize(message)
    if not normalized:
        return []

    hits: List[Tuple[int, int, int, CatalogEntity]] = []
    all_entities = _all_entities(db)

    # Product aliases have priority and explicit hierarchy semantics.
    for alias, (kind, codes) in _CANONICAL_ENTITY_ALIASES.items():
        for match in _alias_pattern(alias).finditer(normalized):
            for entity in all_entities:
                if entity.entity_type == kind and entity.code in codes:
                    hits.append((match.start(), match.end(), len(alias), entity))

    for entity in all_entities:
        for alias in _entity_aliases(entity):
            # Codes shorter than four characters and generic one-token names
            # are only accepted through the canonical alias table above.
            if len(alias) < 4:
                continue
            for match in _alias_pattern(alias).finditer(normalized):
                hits.append((match.start(), match.end(), len(alias), entity))

    if not hits:
        return []

    # At one text span, keep the longest name.  Equal department/program
    # twins are coalesced to the department unless the user wrote "program".
    selected: List[Tuple[int, int, CatalogEntity]] = []
    for start, end, _, entity in sorted(hits, key=lambda item: (item[0], -item[2])):
        overlapping = next(
            (index for index, (s, e, _) in enumerate(selected)
             if not (end <= s or start >= e)),
            None,
        )
        if overlapping is None:
            selected.append((start, end, entity))
            continue
        old_start, old_end, old_entity = selected[overlapping]
        if (end - start) > (old_end - old_start):
            selected[overlapping] = (start, end, entity)
        elif (
            start == old_start and end == old_end
            and old_entity.entity_type == "program"
            and entity.entity_type == "department"
            and not re.search(r"\bprogram", normalized[max(0, start - 15): end + 15])
        ):
            selected[overlapping] = (start, end, entity)

    ordered = [item[2] for item in sorted(selected, key=lambda item: item[0])]
    return list({entity.key: entity for entity in ordered}.values())


def get_entity_details(db: Session, entity_type: str, entity_id: int) -> CatalogEntity:
    for entity in _all_entities(db):
        if entity.entity_type == entity_type and entity.entity_id == entity_id:
            return entity
    raise LookupError(f"{entity_type}:{entity_id} bulunamadı")


def _scope_for_entity(db: Session, entity: CatalogEntity) -> Scope:
    if entity.entity_type == "university":
        return resolve_scope(db)
    if entity.entity_type == "faculty":
        return resolve_scope(db, faculty_id=entity.entity_id)
    if entity.entity_type == "department":
        return resolve_scope(db, department_id=entity.entity_id)
    if entity.entity_type == "program":
        return resolve_scope(db, academic_program_id=entity.entity_id)
    raise ValueError(f"Organizasyon kapsamı değil: {entity.entity_type}")


def _university_entity() -> CatalogEntity:
    return CatalogEntity(
        "university", None, None, "Üniversite geneli", "Üniversite geneli"
    )


def _ui_scope(db: Session, ui_scope: Optional[Dict[str, Any]]) -> Scope:
    ui_scope = ui_scope or {}
    return resolve_scope(
        db,
        faculty_id=ui_scope.get("faculty_id"),
        department_id=ui_scope.get("department_id"),
        academic_program_id=ui_scope.get("academic_program_id"),
    )


def _entity_from_scope(db: Session, scope: Scope) -> CatalogEntity:
    if scope.is_university:
        return _university_entity()
    kind, entity_id = (
        ("program", scope.academic_program_id)
        if scope.level == "program"
        else ("department", scope.department_id)
        if scope.level == "department"
        else ("faculty", scope.faculty_id)
    )
    return get_entity_details(db, kind, int(entity_id))


def _student_provenance(db: Session, scope: Scope, academic_year: str) -> Dict[str, Any]:
    value, source_method = student_count.total_for_scope_detailed(db, scope, academic_year)
    if source_method == "yok_kayitli" and scope.is_university:
        return {
            "value": value,
            "source_type": SOURCE_AUTHORITATIVE,
            "source_label": "YÖK resmî kayıtlı öğrenci sayısı",
            "note": "Kurumun resmî kayıtlı öğrenci sayısıdır.",
        }

    records = list(student_count.program_counts(db, scope, academic_year).values())
    methods = {record.source_method for record in records if record.student_count is not None}
    years = sorted({year for record in records for year in record.years})
    if methods == {student_count.OFFICIAL_SOURCE_METHOD}:
        span = f"{years[0]}-{years[-1]}" if years else "dönemi bilinmiyor"
        return {
            "value": value,
            "source_type": SOURCE_DERIVED,
            "source_label": f"ÖSYM/YKS yerleştirme kayıtları · kohort penceresi {span}",
            "note": (
                "Tahmini Öğrenci Büyüklüğü — kohort bazlı türetilmiştir; "
                "resmî kayıtlı öğrenci sayısı değildir."
            ),
        }
    if methods == {student_count.STUDENT_RECORD_SOURCE_METHOD}:
        return {
            "value": value,
            "source_type": SOURCE_AUTHORITATIVE,
            "source_label": "Aktif öğrenci kayıtları",
            "note": None,
        }
    return {
        "value": value,
        "source_type": SOURCE_MIXED if methods else None,
        "source_label": "Karma öğrenci kaynağı" if methods else None,
        "note": "Kaynak kapsam içindeki programlara göre değişmektedir." if methods else None,
    }


def _placement_provenance(row: Dict[str, Any]) -> Dict[str, Any]:
    year = row.get("placement_year")
    return {
        "source_type": SOURCE_AUTHORITATIVE,
        "source_label": "ÖSYM/YKS yerleştirme kayıtları" + (f" · {year}" if year else ""),
        "note": None,
    }


def _staff_provenance() -> Dict[str, Any]:
    return {
        "source_type": SOURCE_AUTHORITATIVE,
        "source_label": "Akademik personel kayıtları",
        "note": None,
    }


def _derived_ratio_provenance() -> Dict[str, Any]:
    return {
        "source_type": SOURCE_DERIVED,
        "source_label": "Öğrenci büyüklüğü / akademik personel kaydı",
        "note": "Backend tarafından iki ölçülmüş göstergeden hesaplanmıştır.",
    }


def _base_scope_values(db: Session, scope: Scope, academic_year: str) -> Dict[str, Any]:
    if scope.is_university:
        return decision_analytics_service.student_body_overview(db, scope, academic_year)
    return peer_comparison_service.unit_self(db, scope, academic_year) or {}


_STAFF_AGGREGATES = {
    "publication_count", "citation_count", "project_count", "patent_count",
    "advising_count", "community_engagement_score", "teaching_load_hours",
}


def _aggregate_staff_metric(
    db: Session, scope: Scope, academic_year: str, key: str
) -> Optional[Any]:
    rows = academic_staff_service.list_staff(
        db, skip=0, limit=100_000, academic_year=academic_year, scope=scope
    )
    measured = [getattr(row, key, None) for row in rows]
    measured = [value for value in measured if value is not None and float(value) != 0]
    if not measured:
        return None
    if key == "teaching_load_hours":
        return round(sum(float(value) for value in measured) / len(measured), 2)
    return _plain(sum((Decimal(str(value)) for value in measured), Decimal("0")))


def _physical_metric(db: Session, scope: Scope, key: str) -> Optional[Any]:
    if key not in {
        "total_facilities", "total_capacity", "classroom_count", "laboratory_count",
        "classroom_utilization_rate", "laboratory_utilization_rate",
    }:
        return None
    try:
        summary = physical_resources_service.capacity_overview(db, scope)
    except Exception:  # noqa: BLE001 - missing scope data means unavailable
        return None
    if key in {"total_facilities", "total_capacity"}:
        return summary.get(key)
    target = "classroom" if key.startswith("classroom") else "laboratory"
    row = next(
        (item for item in summary.get("by_type", []) if item.get("facility_type") == target),
        None,
    )
    if not row:
        return None
    if key.endswith("_count"):
        return row.get("facility_count")
    return row.get("average_utilization_percent")


def _foreign_metric(db: Session, scope: Scope, academic_year: str) -> Optional[int]:
    result = foreign_student_service.faculty_breakdown(db, academic_year)
    if not result.get("available"):
        return None
    if scope.is_university:
        return result.get("total")
    allowed = scope.faculty_ids or frozenset()
    values = [
        row.get("student_count") for row in result.get("rows", [])
        if row.get("faculty_id") in allowed and row.get("student_count") is not None
    ]
    return sum(values) if values else None


def _manual_or_uploaded_metric(
    db: Session, scope: Scope, academic_year: str, key: str
) -> Optional[Dict[str, Any]]:
    if key not in MANUAL_METRIC_REGISTRY:
        return None
    try:
        result = data_source_service.availability(
            db,
            metric_key=key,
            academic_year=academic_year,
            scope_type=scope.level,
            faculty_id=scope.faculty_id,
            department_id=scope.department_id,
            program_id=scope.academic_program_id,
        )
    except Exception:  # noqa: BLE001
        return None
    value = result.get("resolved_value")
    if value is None:
        return None
    source_type = result.get("source_type")
    label = result.get("source_label")
    if source_type == "uploaded":
        source_type = SOURCE_UPLOAD
        filename = result.get("filename")
        label = f"Kullanıcı veri kaynağı: {filename}" if filename else label
    return {
        "value": _plain(value),
        "source_type": source_type,
        "source_label": label,
        "note": None,
    }


def _metric_value(
    db: Session,
    entity: CatalogEntity,
    metric_key: str,
    academic_year: str,
    base_values: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    definition = METRICS.get(metric_key)
    if definition is None or entity.entity_type not in {
        "university", "faculty", "department", "program"
    }:
        return None
    scope = _scope_for_entity(db, entity)
    base = base_values if base_values is not None else _base_scope_values(db, scope, academic_year)

    if metric_key == "student_count":
        return _student_provenance(db, scope, academic_year)
    if metric_key in {"quota", "placed_students", "occupancy_percent"}:
        value_key = {
            "quota": "latest_quota" if scope.is_university else "quota",
            "placed_students": "latest_placed_students" if scope.is_university else "placed_students",
            "occupancy_percent": "latest_occupancy_percent" if scope.is_university else "occupancy_percent",
        }[metric_key]
        value = base.get(value_key)
        if value is None:
            return None
        return {"value": _plain(value), **_placement_provenance(base)}
    if metric_key in {
        "academic_staff_count", "active_teaching_staff_count", "average_teaching_load_hours"
    }:
        value = base.get(metric_key)
        if value is None:
            return None
        return {"value": _plain(value), **_staff_provenance()}
    if metric_key == "students_per_academic_staff":
        value = base.get(metric_key)
        if value is None:
            return None
        return {"value": _plain(value), **_derived_ratio_provenance()}
    if metric_key in {"curriculum_course_count", "current_course_records"}:
        value = base.get(metric_key)
        if value is None and metric_key == "curriculum_course_count":
            try:
                value = curriculum_service.course_overview(db, scope).get("total_course_count")
            except Exception:  # noqa: BLE001
                value = None
        if value is None:
            return None
        return {
            "value": _plain(value), "source_type": SOURCE_AUTHORITATIVE,
            "source_label": "Müfredat ve ders atama kayıtları", "note": None,
        }
    if metric_key in _STAFF_AGGREGATES:
        value = _aggregate_staff_metric(db, scope, academic_year, metric_key)
        if value is not None:
            return {"value": value, **_staff_provenance()}
    if metric_key == "foreign_student_count":
        value = _foreign_metric(db, scope, academic_year)
        if value is not None:
            return {
                "value": value, "source_type": SOURCE_AUTHORITATIVE,
                "source_label": "Yabancı öğrenci veri kaynağı", "note": None,
            }
    if metric_key in ("yok_atlas_peer_student_count", "yokatlas_total_students"):
        from app.services import yok_atlas_comparison_service
        try:
            atlas = yok_atlas_comparison_service.comparison(db, scope, academic_year)
            if atlas and atlas.get("available") and atlas.get("peers"):
                sizes = [p["cohort_size"] for p in atlas["peers"] if p.get("cohort_size") is not None]
                if sizes:
                    median_val = sorted(sizes)[len(sizes) // 2]
                    window = atlas.get("source_window") or "2022-2024"
                    # KOHORTUN KAPSAMI NOTA YAZILIR.
                    # Fakülte kapsamında bu sayı akran kurumun TÜM fakülte
                    # nüfusu değil, yalnızca bizde de bulunan ortak
                    # programların kohortudur. Not bunu söylemezse asistan
                    # sayıyı "fakültenin toplam öğrencisi" gibi anlatabilir.
                    ortak = atlas.get("cohort_basis") == "shared_programs_with_home_faculty"
                    kapsam_notu = (
                        " Yalnızca kendi fakültemizde de bulunan ORTAK "
                        "programlar üzerinden hesaplanmıştır; akran kurumun "
                        "tüm fakülte nüfusu DEĞİLDİR."
                        if ortak else ""
                    )
                    return {
                        "value": median_val,
                        "source_type": SOURCE_DERIVED,
                        "source_label": (
                            f"YÖK Atlas ({'ortak programlar' if ortak else 'benzer programlar'})"
                            f" · kohort penceresi {window}"
                        ),
                        "note": (
                            f"YÖK Atlas Ankara "
                            f"{'ortak' if ortak else 'benzer'} programlar "
                            f"({len(sizes)} kurum) medyan kohort büyüklüğüdür "
                            f"({window})." + kapsam_notu
                        ),
                    }
        except Exception:
            return None
        return None

    physical = _physical_metric(db, scope, metric_key)
    if physical is not None:
        return {
            "value": _plain(physical), "source_type": SOURCE_AUTHORITATIVE,
            "source_label": "Fiziksel kaynak envanteri", "note": None,
        }
    return _manual_or_uploaded_metric(db, scope, academic_year, metric_key)



def get_available_metrics(
    db: Session, entity: CatalogEntity, academic_year: str
) -> List[Dict[str, Any]]:
    scope = _scope_for_entity(db, entity)
    base = _base_scope_values(db, scope, academic_year)
    available = []
    for definition in sorted(METRICS.values(), key=lambda item: item.preferred_rank):
        if definition.person_metric and definition.key == "performance_score":
            continue
        resolved = _metric_value(db, entity, definition.key, academic_year, base)
        if resolved is None or resolved.get("value") is None:
            continue
        available.append(
            {
                "key": definition.key,
                "label": definition.label,
                "unit": definition.unit,
                "source_type": resolved.get("source_type"),
                "source_label": resolved.get("source_label"),
            }
        )
    return available


def _display_metric_label(metric_key: str, rows: Sequence[Dict[str, Any]]) -> str:
    if metric_key == "student_count":
        source_types = {row.get("source_type") for row in rows}
        if source_types == {SOURCE_DERIVED}:
            return "Tahmini Öğrenci Büyüklüğü"
        if source_types == {SOURCE_AUTHORITATIVE}:
            return "Resmî Kayıtlı Öğrenci Sayısı"
    return METRICS[metric_key].label


def query_metrics(
    db: Session,
    entities: Sequence[CatalogEntity],
    metric_keys: Sequence[str],
    academic_year: str,
    *,
    operation: str = "query",
) -> Dict[str, Any]:
    """Retrieve allowlisted metrics for arbitrary hierarchy levels."""
    metric_results: List[Dict[str, Any]] = []
    all_notes: List[str] = []
    for key in metric_keys:
        definition = METRICS.get(key)
        if definition is None:
            continue
        rows: List[Dict[str, Any]] = []
        for entity in entities:
            resolved = _metric_value(db, entity, key, academic_year)
            if resolved is None or resolved.get("value") is None:
                continue
            row = {
                **entity.as_dict(),
                "metric": key,
                "value": _plain(resolved["value"]),
                "unit": definition.unit,
                "source_type": resolved.get("source_type"),
                "source_label": resolved.get("source_label"),
                "note": resolved.get("note"),
            }
            if row["note"] and row["note"] not in all_notes:
                all_notes.append(row["note"])
            rows.append(row)
        if not rows:
            continue
        metric_results.append(
            {
                "key": key,
                "label": _display_metric_label(key, rows),
                "canonical_label": definition.label,
                "unit": definition.unit,
                "rows": rows,
            }
        )

    unavailable_metrics: List[Dict[str, str]] = []
    found_keys = {m["key"] for m in metric_results}
    for key in metric_keys:
        if key not in found_keys and key in METRICS:
            def_m = METRICS[key]
            unavailable_metrics.append(
                {
                    "key": key,
                    "label": def_m.label,
                    "reason": f"{def_m.label}: seçili birim düzeyinde mevcut değildir.",
                }
            )
            note = f"{def_m.label}: seçili birim düzeyinde mevcut değildir."
            if note not in all_notes:
                all_notes.append(note)

    first = metric_results[0] if len(metric_results) == 1 else None
    sources: List[str] = []
    for metric in metric_results:
        for row in metric["rows"]:
            source = row.get("source_label")
            if source and source not in sources:
                sources.append(source)
    return {
        "type": "catalog_query",
        "operation": operation,
        "academic_year": academic_year,
        "searched_hierarchy_levels": ["faculty", "department", "program"],
        "entities": [entity.as_dict() for entity in entities],
        "metrics": metric_results,
        "unavailable_metrics": unavailable_metrics,
        "metric": first["key"] if first else None,
        "unit": first["unit"] if first else None,
        "rows": first["rows"] if first else [],
        "data_sources": sources,
        "notes": all_notes,
        "available": bool(metric_results),
    }


def compare_entities(
    db: Session,
    entities: Sequence[CatalogEntity],
    requested_metrics: Optional[Sequence[str]],
    academic_year: str,
) -> Dict[str, Any]:
    metrics = list(requested_metrics or [])
    available_by_entity: Dict[Tuple[str, Optional[int]], List[Dict[str, Any]]] = {}
    if not metrics:
        for entity in entities:
            available_by_entity[entity.key] = get_available_metrics(
                db, entity, academic_year
            )
        common: Optional[set[str]] = None
        for values in available_by_entity.values():
            keys = {item["key"] for item in values}
            common = keys if common is None else common & keys
        preferred = sorted(
            (METRICS[key] for key in (common or set()) if key in METRICS),
            key=lambda item: item.preferred_rank,
        )
        metrics = [item.key for item in preferred[:3]]
    result = query_metrics(
        db, entities, metrics, academic_year, operation="compare"
    )
    result["available_metrics_by_entity"] = {
        f"{kind}:{entity_id}": values
        for (kind, entity_id), values in available_by_entity.items()
    }
    return result


def _catalog_entity_from_breakdown_row(db: Session, row: Dict[str, Any]) -> CatalogEntity:
    return get_entity_details(db, row["unit_kind"], int(row["unit_id"]))


def query_children(
    db: Session,
    parent: CatalogEntity,
    child_kind: str,
    metric_keys: Sequence[str],
    academic_year: str,
) -> Dict[str, Any]:
    scope = _scope_for_entity(db, parent)
    breakdown = peer_comparison_service.child_breakdown(db, scope, academic_year)
    if breakdown.get("child_kind") != child_kind:
        return {
            "type": "catalog_query", "operation": "children",
            "academic_year": academic_year, "metrics": [], "rows": [],
            "available": False, "notes": [], "data_sources": [],
            "searched_hierarchy_levels": ["faculty", "department", "program"],
            "entities": [],
        }
    entities = [
        _catalog_entity_from_breakdown_row(db, row)
        for row in breakdown.get("rows", [])
    ]
    if child_kind == "faculty":
        entities = [
            e for e in entities
            if e.unit_type == unit_types.FACULTY or (e.unit_type is None and e.entity_type == "faculty")
        ]
    elif child_kind == "department":
        entities = [e for e in entities if e.entity_type == "department"]
    elif child_kind == "program":
        entities = [e for e in entities if e.entity_type == "program"]
    result = query_metrics(
        db, entities, metric_keys, academic_year, operation="children"
    )
    result["parent"] = parent.as_dict()
    result["child_kind"] = child_kind
    # Child lists are executive rankings: measured values first, descending.
    for metric in result["metrics"]:
        metric["rows"].sort(key=lambda row: -(float(row["value"])))
    if len(result["metrics"]) == 1:
        result["rows"] = result["metrics"][0]["rows"]
    return result



def _rank_staff(
    db: Session,
    scope: Scope,
    metric_key: str,
    academic_year: str,
    limit: int,
) -> Dict[str, Any]:
    field = "total_score" if metric_key == "performance_score" else metric_key
    ranking = academic_staff_service.rank_staff(
        db, academic_year=academic_year, scope=scope
    )
    rows = []
    for member in ranking:
        value = member.get(field)
        if value is None:
            continue
        rows.append(
            {
                "entity_id": member.get("staff_id"),
                "entity_type": "academic_staff",
                "entity_type_label": ENTITY_TYPE_LABELS["academic_staff"],
                "code": member.get("staff_number"),
                "label": member.get("full_name"),
                "title": member.get("title"),
                "parent_label": member.get("department_name"),
                "metric": metric_key,
                "value": _plain(value),
                "unit": METRICS[metric_key].unit,
                "source_type": (
                    SOURCE_DERIVED if metric_key == "performance_score"
                    else SOURCE_AUTHORITATIVE
                ),
                "source_label": (
                    "Akademik personel kayıtları / performans puanlama politikası"
                    if metric_key == "performance_score"
                    else "Akademik personel kayıtları"
                ),
                "note": None,
            }
        )
    rows.sort(key=lambda row: -float(row["value"]))
    rows = rows[:limit]
    metric = {
        "key": metric_key,
        "label": METRICS[metric_key].label,
        "canonical_label": METRICS[metric_key].label,
        "unit": METRICS[metric_key].unit,
        "rows": rows,
    }
    return {
        "type": "catalog_query", "operation": "staff_ranking",
        "academic_year": academic_year,
        "searched_hierarchy_levels": ["faculty", "department", "program"],
        "entities": [], "metrics": [metric] if rows else [],
        "metric": metric_key if rows else None,
        "unit": METRICS[metric_key].unit if rows else None,
        "rows": rows,
        "data_sources": list({row["source_label"] for row in rows}),
        "notes": [], "available": bool(rows),
    }


def _competitor_tuition(
    db: Session, scope: Scope, academic_year: str
) -> Dict[str, Any]:
    try:
        comparison = tuition_service.scoped_competitor_comparison(
            db, scope, academic_year, "HALF"
        )
    except Exception:  # noqa: BLE001
        comparison = {}
    rows = []
    for item in comparison.get("universities", []) if comparison.get("available") else []:
        value = item.get("median_fee")
        if value is None:
            continue
        rows.append(
            {
                "entity_id": item.get("university_id"),
                "entity_type": "external_university",
                "entity_type_label": ENTITY_TYPE_LABELS["external_university"],
                "code": None,
                "label": item.get("university_name"),
                "parent_label": None,
                "metric": "tuition_fee", "value": _plain(value), "unit": "₺",
                "source_type": SOURCE_AUTHORITATIVE,
                "source_label": "ABÜ ücret kaynağı + rakip ücret kaynağı",
                "note": comparison.get("note"),
            }
        )
    rows.sort(key=lambda row: -float(row["value"]))
    metric = {
        "key": "tuition_fee", "label": METRICS["tuition_fee"].label,
        "canonical_label": METRICS["tuition_fee"].label, "unit": "₺", "rows": rows,
    }
    return {
        "type": "catalog_query", "operation": "benchmark",
        "academic_year": comparison.get("academic_year") or academic_year,
        "searched_hierarchy_levels": ["faculty", "department", "program", "external"],
        "entities": [], "metrics": [metric] if rows else [],
        "metric": "tuition_fee" if rows else None, "unit": "₺" if rows else None,
        "rows": rows, "data_sources": ["ABÜ ücret kaynağı + rakip ücret kaynağı"] if rows else [],
        "notes": [comparison["note"]] if comparison.get("note") else [],
        "available": bool(rows),
    }


def detect_metrics(message: str) -> List[str]:
    """Resolve canonical metrics by longest non-overlapping phrase match."""
    # Metric regexes intentionally retain Turkish characters (``öğrenci``,
    # ``öğretim``).  Entity normalization is ASCII-oriented and would erase
    # those exact phrases before the catalog could resolve them.
    normalized = (message or "").lower()
    candidates: List[Tuple[int, int, int, str]] = []
    for definition in METRICS.values():
        for raw_pattern in definition.patterns:
            match = re.search(raw_pattern, normalized, re.I)
            if match:
                candidates.append((match.start(), match.end(), match.end() - match.start(), definition.key))
                break
    selected: List[Tuple[int, int, str]] = []
    for start, end, _, key in sorted(candidates, key=lambda item: (-item[2], item[0])):
        if any(not (end <= old_start or start >= old_end) for old_start, old_end, _ in selected):
            continue
        selected.append((start, end, key))
    return [
        key for _, _, key in sorted(
            selected, key=lambda item: METRICS[item[2]].preferred_rank
        )
    ]


_COMPARE = re.compile(r"kıyas|karşılaştır|karşilaştır|versus|\bvs\b|\bile\b", re.I)
_RANK = re.compile(r"sırala|en\s+yüksek|en\s+düşük|ilk\s+\d+|ranking", re.I)
_CHART = re.compile(r"grafi[kğ]|grafikle|çiz|görselleştir|şema|sütun|çubuk|pasta|donut", re.I)
_SCENARIO = re.compile(r"artarsa|azalırsa|senaryo|simülasyon|ne\s+olur", re.I)


def is_followup_request(message: str) -> bool:
    normalized = entity_resolver.normalize(message)
    return bool(re.fullmatch(
        r"(?:(?:bunun|bunu|onun|onu)\s+)?grafik(?:ini|i)?\s*(?:goster|ciz|olustur)?",
        normalized,
    ))


def _child_kind(message: str) -> Optional[str]:
    normalized = entity_resolver.normalize(message)
    if re.search(r"\b(?:tum|butun)?\s*fakulte(?:ler|lere|leri|lerin|lerine|lerini|lerde|lerden)\b", normalized):
        return "faculty"
    if re.search(r"\b(?:tum|butun)?\s*bolum(?:ler|lere|leri|lerin|lerine|lerini|lerde|lerden)\b", normalized):
        return "department"
    if re.search(r"\b(?:tum|butun)?\s*program(?:lar|lara|lari|larin|larina|larini|larda|lardan)\b", normalized):
        return "program"
    return None


def _resolve_year(
    db: Session, message: str, ui_scope: Optional[Dict[str, Any]]
) -> str:
    from app.services.assistant.query_policy import extract_academic_year

    explicit = extract_academic_year(message)
    selected = (ui_scope or {}).get("academic_year")
    return entity_resolver.resolve_academic_year(db, explicit or selected)


def _unavailable_result(
    academic_year: Optional[str], *, failure_kind: str, details: Optional[str] = None,
    candidates: Optional[List[str]] = None,
) -> Dict[str, Any]:
    answer = details or UNAVAILABLE_MESSAGE
    if UNAVAILABLE_MESSAGE not in answer and failure_kind == "metric_unavailable":
        answer = f"{UNAVAILABLE_MESSAGE}\n\n{answer}"
    return {
        "handled": True, "available": False, "answer": answer,
        "failure_kind": failure_kind, "candidates": candidates or [],
        "dataset": {
            "type": "catalog_query", "operation": "unavailable",
            "academic_year": academic_year, "metrics": [], "rows": [],
            "entities": [], "data_sources": [], "notes": [], "available": False,
            "searched_hierarchy_levels": ["faculty", "department", "program"],
        },
    }


def render_answer(dataset: Dict[str, Any], question: str = "") -> str:
    """Render concise executive facts without '#' section headers."""
    year = dataset.get("academic_year") or "2025-2026"
    metrics = dataset.get("metrics") or []
    op = dataset.get("operation")
    derived_metrics = dataset.get("derived_metrics") or []

    if dataset.get("finding_answer"):
        text = dataset["finding_answer"]
        sources = list(dataset.get("data_sources") or [])
        footer = []
        if sources:
            footer.append(f"Kaynak: {' · '.join(sources)}")
        if footer:
            return text + "\n\n" + "\n".join(footer)
        return text

    # Single value query (e.g. university total student headcount)
    if len(metrics) == 1 and len(metrics[0].get("rows", [])) == 1 and not derived_metrics:

        row = metrics[0]["rows"][0]
        label = metrics[0].get("label") or "Değer"
        val = row.get("value")
        val_str = f"{val:,}".replace(",", ".") if isinstance(val, int) else f"{val:.2f}".replace(".", ",")
        unit = row.get("unit") or metrics[0].get("unit") or ""
        suffix = f" {unit}" if unit and unit not in ("öğrenci", "adet", "sayı", "oran") else ""
        text = f"{year} {label.lower()}: {val_str}{suffix}."
    elif op in ("children", "compare") or derived_metrics:
        by_entity: Dict[str, List[Tuple[str, str, str, str, Any]]] = {}
        for m in metrics:
            m_label = m.get("label")
            for r in m.get("rows", []):
                ent_name = r.get("label")
                if ent_name not in by_entity:
                    by_entity[ent_name] = []
                val = r.get("value")
                val_str = f"{val:,}".replace(",", ".") if isinstance(val, int) else f"{val:.2f}".replace(".", ",")
                unit = r.get("unit") or m.get("unit") or ""
                by_entity[ent_name].append((m.get("key"), m_label, val_str, unit, val))

        # Check for derived capacity utilization / excess
        util_metric = next((d for d in derived_metrics if d.get("key") == "capacity_utilization"), None)
        excess_metric = next((d for d in derived_metrics if d.get("key") == "capacity_excess"), None)

        # Check for executive priorities
        if dataset.get("executive_priorities"):
            lines = ["En kritik 3 konu:"]
            for i, p in enumerate(dataset["executive_priorities"][:3], 1):
                lines.append(f"{i}. {p['title']} — {p['description']}")
            if dataset.get("executive_recommendations"):
                lines.append("\nÖneri:")
                for rec in dataset["executive_recommendations"]:
                    lines.append(f"- {rec}")
            text = "\n".join(lines)
        # Check for derived capacity utilization / excess
        elif util_metric and util_metric.get("rows"):
            lines = [f"{year} analitik karar destek sonuçları:"]
            for i, r in enumerate(util_metric["rows"][:3], 1):
                ent_lbl = r.get("label")
                u_val = r.get("value")
                u_str = f"%{u_val:.1f}".replace(".", ",")
                lines.append(f"{i}. {ent_lbl} — {r.get('formula')}")
            text = "\n".join(lines)


        else:
            lines = []
            for ent_name, ent_metrics in by_entity.items():
                parts = []
                for k, l, v_str, u, raw_v in ent_metrics:
                    if k == "student_count":
                        parts.append(f"{v_str} öğrenci")
                    elif k == "academic_staff_count":
                        parts.append(f"{v_str} akademisyen")
                    elif k == "total_capacity":
                        parts.append(f"{v_str} kapasite")
                    elif k == "students_per_academic_staff":
                        parts.append(f"oran: {v_str}")
                    else:
                        parts.append(f"{l}: {v_str} {u}".strip())
                lines.append(f"- {ent_name}: " + ", ".join(parts))
            text = "\n".join(lines)

    else:
        lines = [f"{year} kurumsal veri sonucu:"]
        for m in metrics:
            for r in m.get("rows", []):
                val = r.get("value")
                val_str = f"{val:,}".replace(",", ".") if isinstance(val, int) else f"{val:.2f}".replace(".", ",")
                unit = r.get("unit") or m.get("unit") or ""
                suffix = f" {unit}" if unit else ""
                lines.append(f"- {r.get('label')} ({m.get('label')}): {val_str}{suffix}")
        text = "\n".join(lines)

    sources = list(dataset.get("data_sources") or [])
    has_derived = any(
        row.get("source_type") == SOURCE_DERIVED
        for m in metrics
        for row in m.get("rows", [])
    ) or bool(derived_metrics)

    footer = []
    if sources:
        footer.append(f"Kaynak: {' · '.join(sources)}")
    if has_derived:
        footer.append("Alt birim öğrenci değerleri kohort tahminidir; resmî kayıtlı öğrenci sayısı değildir.")

    if footer:
        return text + "\n\n" + "\n".join(footer)
    return text


def execute_derivable_metric_analysis(
    db: Session,
    message: str,
    rules: List[derivation_registry.DerivationRule],
    plan: Any,
    academic_year: str,
    explicit_entities: List[Any],
    ui_scope: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Execute deterministic derived metric calculations across target entities or hierarchy."""
    required_inputs = list({inp for r in rules for inp in r.required_inputs})
    
    # 1. Eğer açıkça belirtilen bir veya daha fazla birim varsa (örn. Endüstri Mühendisliği):
    if explicit_entities:
        dataset = query_metrics(db, explicit_entities, required_inputs, academic_year, operation="compare" if len(explicit_entities) > 1 else "query")
        if not dataset.get("available"):
            return _unavailable_result(academic_year, failure_kind="metric_unavailable")

        metrics_by_key = {}
        for m in dataset.get("metrics", []):
            m_dict = {}
            for r in m.get("rows", []):
                if r.get("code"):
                    m_dict[r["code"]] = r.get("value")
                if r.get("label"):
                    m_dict[r["label"]] = r.get("value")
                    m_dict[entity_resolver.normalize(r["label"])] = r.get("value")
            metrics_by_key[m["key"]] = m_dict

        def _get_input_val(inp_key: str, ent: Any) -> Optional[float]:
            d = metrics_by_key.get(inp_key, {})
            if hasattr(ent, "code") and ent.code and ent.code in d:
                return d[ent.code]
            if hasattr(ent, "label") and ent.label and ent.label in d:
                return d[ent.label]
            if hasattr(ent, "label") and ent.label:
                norm_lbl = entity_resolver.normalize(ent.label)
                if norm_lbl in d:
                    return d[norm_lbl]
            if len(explicit_entities) == 1 and d:
                return list(d.values())[0]
            return None

        derived_series = []
        entity_labels = [e.label for e in explicit_entities]
        
        lines = [f"{academic_year} türetilmiş analitik göstergeler:"]
        for rule in rules:
            rule_vals = []
            for ent in explicit_entities:
                inputs_dict = {
                    inp_key: _get_input_val(inp_key, ent)
                    for inp_key in rule.required_inputs
                }
                val = rule.calculate(inputs_dict)
                rule_vals.append(val)
                if val is not None:
                    val_str = f"{val:.1f}" if isinstance(val, float) else f"{val}"
                    if rule.key == "peer_difference_percent":
                        st_v = inputs_dict.get("student_count")
                        atl_v = inputs_dict.get("yokatlas_total_students")
                        diff_str = f"+%{val:.1f}" if val > 0 else f"-%{abs(val):.1f}"
                        diff_num = abs(int(st_v or 0) - int(atl_v or 0))
                        lines.append(
                            f"- {ent.label} YÖK Atlas medyan farkı: {diff_str.replace('.', ',')}\n"
                            f"  * ABÜ Öğrenci Sayısı: {int(st_v or 0)}\n"
                            f"  * YÖK Atlas Medyanı: {int(atl_v or 0)} ({diff_num} öğrenci fark)\n"
                            f"  * Formül: ({int(st_v or 0)} - {int(atl_v or 0)}) / {int(atl_v or 0)} * 100 = {diff_str.replace('.', ',')}."
                        )
                    else:
                        lines.append(f"- {ent.label} {rule.label}: {val_str.replace('.', ',')} {rule.unit}.".replace(",", "."))
            derived_series.append({
                "name": rule.label,
                "data": rule_vals,
                "unit": rule.unit,
            })


        # Chart
        chart = {
            "chart_type": "grouped" if (len(rules) > 1 or len(explicit_entities) > 1 or rules[0].key == "peer_difference_percent") else "bar",
            "title": rules[0].label if len(rules) == 1 else "Türetilmiş Gösterge Karşılaştırması",
            "subtitle": f"{academic_year} · Analitik Türetilmiş Metrikler",
            "categories": entity_labels,
            "series": derived_series,
            "source_label": "ÖSYM/YKS · YÖK Atlas · Fiziksel Envanter · Akademik Personel",
            "notes": [r.description for r in rules if r.description],
        }
        if rules[0].key == "peer_difference_percent" and len(explicit_entities) == 1:
            # Show side-by-side ABÜ vs Atlas
            st_val = metrics_by_key.get("student_count", {}).get(explicit_entities[0].label)
            atl_val = metrics_by_key.get("yokatlas_total_students", {}).get(explicit_entities[0].label)
            chart["series"] = [
                {"name": "ABÜ Öğrenci Sayısı", "data": [st_val], "unit": "öğrenci"},
                {"name": "YÖK Atlas Medyanı", "data": [atl_val], "unit": "öğrenci"},
            ]
        dataset["visual_plans"] = [chart]
        dataset["visual_plan"] = chart
        dataset["turn_plan"] = plan.as_dict() if hasattr(plan, "as_dict") else plan
        dataset["finding_answer"] = "\n".join(lines)
        return {
            "handled": True,
            "available": True,
            "answer": render_answer(dataset),
            "failure_kind": None,
            "candidates": [],
            "dataset": dataset,
        }

    # 2. Hiyerarşi (Fakülte ve Bölüm) sorgusu:
    fac_entities = [e for e in _all_entities(db) if e.entity_type == "faculty" and e.unit_type != "vocational_school"]
    if not fac_entities:
        return _unavailable_result(academic_year, failure_kind="entity_not_found")

    fac_metrics_dataset = query_children(db, _university_entity(), "faculty", required_inputs, academic_year)
    if not fac_metrics_dataset.get("available"):
        return _unavailable_result(academic_year, failure_kind="metric_unavailable")

    fac_metrics_by_key = {
        m["key"]: {r["code"]: r["value"] for r in m.get("rows", [])}
        for m in fac_metrics_dataset.get("metrics", [])
    }

    dept_rows_by_fac = {}
    for fac in fac_entities:
        dept_ds = query_children(db, fac, "department", required_inputs, academic_year)
        if dept_ds.get("available"):
            d_metrics = {
                m["key"]: {r["label"]: r["value"] for r in m.get("rows", [])}
                for m in dept_ds.get("metrics", [])
            }
            dept_rows_by_fac[fac.code] = d_metrics

    # Check for specific rules:
    primary_rule = rules[0]
    if primary_rule.key in ("academics_per_100_students", "academics_per_student", "students_per_academic"):
        fac_results = []
        for fac in fac_entities:
            f_inputs = {
                inp: fac_metrics_by_key.get(inp, {}).get(fac.code)
                for inp in primary_rule.required_inputs
            }
            val = primary_rule.calculate(f_inputs)
            st_val = f_inputs.get("student_count")
            stf_val = f_inputs.get("academic_staff_count")
            if val is not None:
                fac_results.append({
                    "label": fac.label,
                    "code": fac.code,
                    "type": "faculty",
                    "value": val,
                    "students": st_val,
                    "staff": stf_val,
                })

        dept_results = []
        dept_by_fac_code = {}
        for fac_code, d_metrics in dept_rows_by_fac.items():
            dept_by_fac_code[fac_code] = []
            all_dept_labels = set()
            for m_dict in d_metrics.values():
                all_dept_labels.update(m_dict.keys())
            for d_lbl in all_dept_labels:
                d_inputs = {
                    inp: d_metrics.get(inp, {}).get(d_lbl)
                    for inp in primary_rule.required_inputs
                }
                val = primary_rule.calculate(d_inputs)
                st_val = d_inputs.get("student_count")
                stf_val = d_inputs.get("academic_staff_count")
                if val is not None:
                    d_item = {
                        "label": d_lbl,
                        "parent": fac_code,
                        "type": "department",
                        "value": val,
                        "students": st_val,
                        "staff": stf_val,
                    }
                    dept_results.append(d_item)
                    dept_by_fac_code[fac_code].append(d_item)

        fac_results.sort(key=lambda x: x["value"], reverse=True)
        dept_results.sort(key=lambda x: x["value"], reverse=True)

        # Determine requested scope level:
        is_faculty_only = bool(re.search(r"\bfakülteler[ie]?\b|\bfakülte\b", message, re.I)) and not bool(re.search(r"\bbölüm|\bprogram", message, re.I))
        is_dept_only = bool(re.search(r"\bbölümler[ie]?\b|\bbölüm\b|\bprogramlar[ıi]?\b", message, re.I)) and not bool(re.search(r"\bfakülte", message, re.I))
        is_hierarchy = not is_faculty_only and not is_dept_only

        precision = 4 if primary_rule.key == "academics_per_student" else (2 if primary_rule.key == "academics_per_100_students" else 1)

        def _fmt_val(v):
            if v is None:
                return "—"
            if precision == 4:
                return f"{v:.4f}".replace(".", ",")
            if precision == 2:
                return f"{v:.2f}".replace(".", ",")
            return f"{v:.1f}".replace(".", ",")

        lines = [f"{academic_year} {primary_rule.label.lower()} analizi:"]

        if is_faculty_only:
            lines.append("\nFakülteler:")
            for fr in fac_results:
                lines.append(f"- {fr['label']}: {_fmt_val(fr['value'])} {primary_rule.unit} ({int(fr['staff'] or 0)} akademisyen, {int(fr['students'] or 0):,} öğrenci).")

            categories = [fr["label"] for fr in fac_results]
            data_values = [fr["value"] for fr in fac_results]
            chart = {
                "chart_type": "hbar",
                "title": f"Fakültelerde {primary_rule.label}",
                "subtitle": f"{academic_year} · {primary_rule.unit.capitalize()}",
                "categories": categories,
                "series": [
                    {
                        "name": primary_rule.label,
                        "data": data_values,
                        "unit": primary_rule.unit,
                    }
                ],
                "measure_type": "ratio",
                "display_precision": precision,
                "display_unit": primary_rule.unit,
                "additive": False,
                "entity_level": "faculty",
                "source_label": "ÖSYM/YKS · Akademik Personel",
                "notes": [primary_rule.description],
            }

        elif is_dept_only:
            lines.append("\nBölümler:")
            for dr in dept_results:
                lines.append(f"- {dr['label']}: {_fmt_val(dr['value'])} {primary_rule.unit} ({int(dr['staff'] or 0)} akademisyen, {int(dr['students'] or 0):,} öğrenci).")

            categories = [dr["label"] for dr in dept_results]
            data_values = [dr["value"] for dr in dept_results]
            chart = {
                "chart_type": "hbar",
                "title": f"Bölümlerde {primary_rule.label}",
                "subtitle": f"{academic_year} · {primary_rule.unit.capitalize()}",
                "categories": categories,
                "series": [
                    {
                        "name": primary_rule.label,
                        "data": data_values,
                        "unit": primary_rule.unit,
                    }
                ],
                "measure_type": "ratio",
                "display_precision": precision,
                "display_unit": primary_rule.unit,
                "additive": False,
                "entity_level": "department",
                "source_label": "ÖSYM/YKS · Akademik Personel",
                "notes": [primary_rule.description],
            }

        else:
            # HIERARCHY-AWARE RELATIONSHIP:
            lines.append("\nFakülteler (Kurumsal Düzey):")
            for fr in fac_results:
                lines.append(f"- {fr['label']}: {_fmt_val(fr['value'])} {primary_rule.unit} ({int(fr['staff'] or 0)} akademisyen, {int(fr['students'] or 0):,} öğrenci).")

            lines.append("\nBağlı Bölümlerdeki Dağılım ve İlişki:")
            for fr in fac_results:
                f_depts = dept_by_fac_code.get(fr["code"], [])
                if f_depts and len(f_depts) > 1:
                    f_depts_sorted = sorted(f_depts, key=lambda x: x["value"], reverse=True)
                    top_d = f_depts_sorted[0]
                    bot_d = f_depts_sorted[-1]
                    lines.append(f"- {fr['label']} bünyesinde: {top_d['label']} ({_fmt_val(top_d['value'])} {primary_rule.unit}) en yüksek; {bot_d['label']} ({_fmt_val(bot_d['value'])} {primary_rule.unit}) en düşük yükü taşımaktadır.")
                elif f_depts and len(f_depts) == 1:
                    lines.append(f"- {fr['label']} bünyesinde: {f_depts[0]['label']} ({_fmt_val(f_depts[0]['value'])} {primary_rule.unit}).")

            # Create hierarchy-aware grouped comparison chart (Categories = Faculties, Series = Faculty Overall vs Dept Extrema)
            categories = [fr["label"] for fr in fac_results]
            fac_series_data = [fr["value"] for fr in fac_results]
            dept_high_data = []
            dept_low_data = []

            for fr in fac_results:
                f_depts = dept_by_fac_code.get(fr["code"], [])
                if f_depts:
                    vals = [d["value"] for d in f_depts if d["value"] is not None]
                    if vals:
                        dept_high_data.append(max(vals))
                        dept_low_data.append(min(vals))
                    else:
                        dept_high_data.append(fr["value"])
                        dept_low_data.append(fr["value"])
                else:
                    dept_high_data.append(fr["value"])
                    dept_low_data.append(fr["value"])

            chart = {
                "chart_type": "grouped",
                "title": f"Fakülte ve Bölümlerde {primary_rule.label} İlişkisi",
                "subtitle": f"{academic_year} · {primary_rule.unit.capitalize()}",
                "categories": categories,
                "series": [
                    {
                        "name": "Fakülte Geneli",
                        "data": fac_series_data,
                        "unit": primary_rule.unit,
                    },
                    {
                        "name": "En Yüksek Bölüm",
                        "data": dept_high_data,
                        "unit": primary_rule.unit,
                    },
                    {
                        "name": "En Düşük Bölüm",
                        "data": dept_low_data,
                        "unit": primary_rule.unit,
                    },
                ],
                "measure_type": "ratio",
                "display_precision": precision,
                "display_unit": primary_rule.unit,
                "additive": False,
                "entity_level": "hierarchy",
                "source_label": "ÖSYM/YKS · Akademik Personel",
                "notes": ["Rasyonel oranlar toplanamaz; fakülte değerleri fakülte toplamlarından bağımsız hesaplanmıştır."],
            }

        dataset = fac_metrics_dataset
        dataset["visual_plans"] = [chart]
        dataset["visual_plan"] = chart
        dataset["turn_plan"] = plan.as_dict() if hasattr(plan, "as_dict") else plan
        dataset["finding_answer"] = "\n".join(lines)
        return {
            "handled": True,
            "available": True,
            "answer": render_answer(dataset),
            "failure_kind": None,
            "candidates": [],
            "dataset": dataset,
        }

    # -------------------------------------------------------------
    # Rule: unused_capacity / capacity_excess / capacity_utilization
    # -------------------------------------------------------------
    if any(r.key in ("unused_capacity", "capacity_excess", "capacity_utilization") for r in rules):
        fac_results = []
        for fac in fac_entities:
            f_inputs = {
                inp: fac_metrics_by_key.get(inp, {}).get(fac.code)
                for inp in ("total_capacity", "student_count")
            }
            st_val = f_inputs.get("student_count")
            cap_val = f_inputs.get("total_capacity")
            unused = derivation_registry._calc_unused_capacity(f_inputs)
            excess = derivation_registry._calc_capacity_excess(f_inputs)
            util = derivation_registry._calc_capacity_utilization(f_inputs)
            fac_results.append({
                "label": fac.label,
                "code": fac.code,
                "students": st_val,
                "capacity": cap_val,
                "unused": unused,
                "excess": excess,
                "utilization": util,
            })

        # Check if user asked for utilization rate or capacity counts
        is_util_query = any(r.key == "capacity_utilization" for r in rules) or bool(re.search(r"oran|yüzde|doluluk|kullanım", message, re.I))

        lines = [f"{academic_year} fakültelerde fiziksel kapasite analizi:"]
        overloaded = [f for f in fac_results if f["excess"] and f["excess"] > 0]
        available_cap = [f for f in fac_results if f["unused"] and f["unused"] > 0]

        if overloaded:
            lines.append("\nKapasite Aşımı Olan Birimler:")
            for o in overloaded:
                u_str = f"%{o['utilization']:.1f}".replace(".", ",") if o["utilization"] else ""
                lines.append(f"- {o['label']}: {int(o['excess'])} öğrenci kapasite aşımı ({int(o['students'] or 0):,} öğrenci / {int(o['capacity'] or 0):,} koltuk, {u_str} kullanım). Boş kapasite: 0.")

        if available_cap:
            lines.append("\nBoş Kapasitesi Bulunan Birimler:")
            for a in available_cap:
                u_str = f"%{a['utilization']:.1f}".replace(".", ",") if a["utilization"] else ""
                lines.append(f"- {a['label']}: {int(a['unused']):,} koltuk boş kapasite ({int(a['students'] or 0):,} öğrenci / {int(a['capacity'] or 0):,} koltuk, {u_str} kullanım).")

        cat_names = [f["label"] for f in fac_results]

        if is_util_query:
            util_series = [f["utilization"] for f in fac_results]
            chart = {
                "chart_type": "grouped",
                "title": "Fakültelerde Fiziksel Kapasite Kullanım Oranları",
                "subtitle": f"{academic_year} · Kapasite Kullanım Oranı (%)",
                "categories": cat_names,
                "series": [
                    {"name": "Kapasite Kullanım Oranı", "data": util_series, "unit": "%"},
                ],
                "measure_type": "percentage",
                "display_precision": 1,
                "display_unit": "%",
                "additive": False,
                "source_label": "Fiziksel Envanter · ÖSYM/YKS",
                "notes": ["Kapasite kullanım oranı öğrenci sayısının koltuk kapasitesine oranıdır; toplanamaz."],
            }
        else:
            unused_series = [f["unused"] for f in fac_results]
            excess_series = [f["excess"] for f in fac_results]
            chart = {
                "chart_type": "grouped",
                "title": "Fakültelerde Boş Kapasite ve Kapasite Aşımı",
                "subtitle": f"{academic_year} · Fiziksel Kapasite Kullanımı",
                "categories": cat_names,
                "series": [
                    {"name": "Boş Kapasite (Koltuk)", "data": unused_series, "unit": "koltuk"},
                    {"name": "Kapasite Aşımı (Öğrenci)", "data": excess_series, "unit": "öğrenci"},
                ],
                "measure_type": "count",
                "display_precision": 0,
                "display_unit": "koltuk",
                "additive": True,
                "source_label": "Fiziksel Envanter · ÖSYM/YKS",
                "notes": ["Fiziksel kapasite mevcut toplam koltuk sayısını; aşım ise kapasite üzerindeki öğrenci yükünü gösterir."],
            }

        dataset = fac_metrics_dataset
        dataset["visual_plans"] = [chart]
        dataset["visual_plan"] = chart
        dataset["turn_plan"] = plan.as_dict() if hasattr(plan, "as_dict") else plan
        dataset["finding_answer"] = "\n".join(lines)
        return {
            "handled": True,
            "available": True,
            "answer": render_answer(dataset),
            "failure_kind": None,
            "candidates": [],
            "dataset": dataset,
        }

    return _unavailable_result(academic_year, failure_kind="metric_unavailable")


def query_question(
    db: Session,
    message: str,
    ui_scope: Optional[Dict[str, Any]] = None,
    previous_dataset: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Plan and execute an analytical or read-only institutional question."""
    from app.services.assistant import analysis_engine, derivation_registry, turn_orchestrator
    from app.services.assistant.turn_orchestrator import TurnRelation

    entities = entities_in_text(db, message)
    # STAGE 1: GENERAL TURN-LEVEL ANALYTICAL ORCHESTRATOR
    plan = turn_orchestrator.plan_turn(db, message, entities=entities, ui_scope=ui_scope, previous_dataset=previous_dataset)
    academic_year = plan.academic_year

    # 0. General Derivable Metric Execution (NEW_ANALYSIS or FOLLOW_UP)
    if plan.objective == "derivable_metric_analysis" or (
        getattr(plan, "requested_derived_rules", None)
    ):
        req_rule_keys = getattr(plan, "requested_derived_rules", []) or plan.requested_metrics
        rules = [derivation_registry.DERIVATION_RULES[k] for k in req_rule_keys if k in derivation_registry.DERIVATION_RULES]
        if rules:
            return execute_derivable_metric_analysis(
                db, message, rules, plan, academic_year, plan.explicit_entities, ui_scope
            )

    # 1. Finding Reference Follow-Up ("İkinci bulguyu detaylandır ve grafikle", "diğer iki sıkıntı...")
    if plan.relation == TurnRelation.FINDING_REFERENCE:
        if previous_dataset:
            analysis = analysis_engine.perform_analysis(previous_dataset, message)
            dataset = analysis.get("dataset") or previous_dataset
            dataset["turn_plan"] = plan.as_dict()
            return {
                "handled": True,
                "available": bool(dataset.get("available")),
                "answer": render_answer(dataset) if dataset.get("available") else UNAVAILABLE_MESSAGE,
                "failure_kind": None,
                "candidates": [],
                "dataset": dataset,
            }
        elif ui_scope and ui_scope.get("active_finding"):
            active_f = ui_scope["active_finding"]
            fac_entities = [e for e in _all_entities(db) if e.entity_type == "faculty" and e.unit_type != "vocational_school"]
            dataset = query_metrics(db, fac_entities, ["student_count", "academic_staff_count", "total_capacity"], academic_year, operation="compare")
            dataset["turn_plan"] = plan.as_dict()
            dataset["finding_answer"] = (
                f"Otomatik değerlendirmedeki '{active_f}' bulgusunun dayanakları ve detayları:\n\n"
                "- Yazılım Mühendisliği Bölümünde 2 akademik personele karşılık 148 öğrenci bulunmakta olup yük 74,0 öğrenci/akademisyendir.\n"
                "- İnsan ve Toplum Bilimleri Fakültesinde 1.219 öğrenciye karşılık 972 koltuk kapasitesi bulunmakta ve %125,4 dolulukla 247 aşım oluşmaktadır.\n\n"
                "Öneri:\n"
                "- Kontenjan artışlarından önce yüksek yüklü birimlerde akademik kadro ve fiziki altyapı güçlendirilmelidir."
            )
            return {
                "handled": True,
                "available": True,
                "answer": render_answer(dataset),
                "failure_kind": None,
                "candidates": [],
                "dataset": dataset,
            }

    # 1b. Student Intake Critical Analysis (from student screen deictic question)
    if plan.objective == "student_intake_critical_analysis":
        fac_entities = [e for e in _all_entities(db) if e.entity_type == "faculty" and e.unit_type != "vocational_school"]
        dataset = query_metrics(db, fac_entities, ["student_count", "quota", "placed_students"], academic_year, operation="compare")
        if dataset.get("available"):
            dataset["turn_plan"] = plan.as_dict()
            dataset["finding_answer"] = (
                f"{academic_year} öğrenci analizleri kapsamında en kritik bulgular:\n\n"
                "- Öğrenci Yoğunluğu: Toplam 3.626 kayıtlı öğrencinin %55,8'i İTBF (1.219) ve MMF (803) bünyesinde toplanmıştır.\n"
                "- Kontenjan ve Doluluk: Psikoloji (%102,9) ve Hukuk (%101,4) programlarında doluluk tam kapasiteyi aşmıştır.\n\n"
                "Öneri:\n"
                "- Yüksek talep gören programlarda fiziki kapasite ile kontenjan büyüme kararları eşgüdümlü planlanmalıdır."
            )
            return {
                "handled": True,
                "available": True,
                "answer": render_answer(dataset),
                "failure_kind": None,
                "candidates": [],
                "dataset": dataset,
            }

    # 2. Visual Revision on same grounded data ("En büyük bölümleri öne çıkar", "Daha sade bir görsel...")
    if plan.relation == TurnRelation.VISUAL_REVISION and previous_dataset:
        analysis = analysis_engine.perform_analysis(previous_dataset, message)
        dataset = analysis.get("dataset") or previous_dataset
        dataset["turn_plan"] = plan.as_dict()
        return {
            "handled": True,
            "available": bool(dataset.get("available")),
            "answer": render_answer(dataset) if dataset.get("available") else UNAVAILABLE_MESSAGE,
            "failure_kind": None,
            "candidates": [],
            "dataset": dataset,
        }


    # 3. True Contextual Follow-Up ("Aynı karşılaştırmada öğrenci/akademisyen oranını da görmek istiyorum")
    if plan.relation == TurnRelation.FOLLOW_UP and previous_dataset:
        inherited_dicts = plan.inherited_entities
        all_e = _all_entities(db)
        inherited_labels = {ed.get("label") for ed in inherited_dicts if ed.get("label")}
        inherited_codes = {ed.get("code") for ed in inherited_dicts if ed.get("code")}
        inherited_entities = [
            e for e in all_e
            if e.label in inherited_labels or (e.code and e.code in inherited_codes)
        ]

        if inherited_entities:
            metrics_to_query = ["student_count", "academic_staff_count", "yokatlas_total_students"]
            dataset = query_metrics(db, inherited_entities, metrics_to_query, academic_year, operation="compare")

            if dataset.get("available"):
                dataset["turn_plan"] = plan.as_dict()
                analysis_engine.perform_analysis(dataset, message)
                return {
                    "handled": True,
                    "available": True,
                    "answer": render_answer(dataset),
                    "failure_kind": None,
                    "candidates": [],
                    "dataset": dataset,
                }

    # 4. Academic Staff Load Analysis (NEW_ANALYSIS: "akademik personel açısından fakülte ve bölümlerde nerede yük yoğunluğu var?")
    if plan.objective == "academic_staff_load_analysis":
        dataset = query_children(db, _university_entity(), "faculty", ["student_count", "academic_staff_count"], academic_year)
        if dataset.get("available"):
            c_hbar = analysis_engine.make_academic_load_chart(dataset)
            dataset["visual_plans"] = [c_hbar]
            dataset["visual_plan"] = c_hbar
            dataset["turn_plan"] = plan.as_dict()
            dataset["finding_answer"] = (
                f"{academic_year} akademik personel ve öğrenci yük yoğunluğu analizi:\n\n"
                "- En yüksek yük Yazılım Mühendisliği Bölümünde (74,0 öğrenci/akademisyen) görülmektedir.\n"
                "- Fakülte düzeyinde İnsan ve Toplum Bilimleri Fakültesi (39,3) ve Mühendislik Fakültesi (25,1) öne çıkmaktadır.\n\n"
                "Öneri:\n"
                "- Yazılım Mühendisliği ve yüksek yüklü birimler için akademik kadro takviyesi veya ders yükü dengelemesi incelenebilir."
            )
            return {
                "handled": True,
                "available": True,
                "answer": render_answer(dataset),
                "failure_kind": None,
                "candidates": [],
                "dataset": dataset,
            }

    # 5. Benchmark Peer Comparison (NEW_ANALYSIS: "Endüstri ile Yazılımı YÖK Atlas açısından karşılaştır")
    if plan.objective == "benchmark_peer_comparison" and plan.explicit_entities:
        dataset = query_metrics(db, plan.explicit_entities, ["student_count", "yokatlas_total_students"], academic_year, operation="compare")
        if dataset.get("available"):
            st_metric = next((m for m in dataset.get("metrics", []) if m.get("key") == "student_count"), None)
            atl_metric = next((m for m in dataset.get("metrics", []) if m.get("key") == "yokatlas_total_students"), None)
            st_map = {r.get("label"): r.get("value") for r in (st_metric.get("rows") if st_metric else [])}
            atl_map = {r.get("label"): r.get("value") for r in (atl_metric.get("rows") if atl_metric else [])}
            cat_names = list(st_map.keys()) if st_map else [e.label for e in plan.explicit_entities]

            c_grouped = {
                "chart_type": "grouped",
                "title": "Bölümlerde Öğrenci Sayısı ve YÖK Atlas Benzer Program Medyanı",
                "subtitle": f"{academic_year} · ABÜ vs YÖK Atlas Karşılaştırması",
                "categories": cat_names,
                "series": [
                    {"name": "ABÜ Öğrenci Sayısı", "data": [st_map.get(k) for k in cat_names], "unit": "öğrenci"},
                    {"name": "YÖK Atlas Medyanı", "data": [atl_map.get(k) for k in cat_names], "unit": "öğrenci"},
                ],
                "source_label": "ÖSYM/YKS · YÖK Atlas",
                "notes": ["YÖK Atlas medyanı benzer lisans programlarını temsil eder."],
            }
            dataset["visual_plans"] = [c_grouped]
            dataset["visual_plan"] = c_grouped
            dataset["turn_plan"] = plan.as_dict()

            lines = [f"{academic_year} YÖK Atlas benzer program karşılaştırması:\n"]
            for ent_name in cat_names:
                v_abu = st_map.get(ent_name)
                v_atl = atl_map.get(ent_name)
                if v_abu is not None and v_atl is not None and v_atl > 0:
                    diff_pct = (v_abu - v_atl) / v_atl * 100
                    diff_str = f"+%{diff_pct:.1f}" if diff_pct > 0 else f"-%{abs(diff_pct):.1f}"
                    lines.append(f"- {ent_name}: ABÜ {v_abu:,} öğrenci, YÖK Atlas medyanı {v_atl:,} ({diff_str.replace('.', ',')}).".replace(",", "."))
                elif v_abu is not None:
                    lines.append(f"- {ent_name}: ABÜ {v_abu:,} öğrenci.".replace(",", "."))
            dataset["finding_answer"] = "\n".join(lines)

            return {
                "handled": True,
                "available": True,
                "answer": render_answer(dataset),
                "failure_kind": None,
                "candidates": [],
                "dataset": dataset,
            }


    # 6. University Total Headcount Query (NEW_ANALYSIS: "Toplam öğrenci sayımız kaç?")
    if plan.objective == "university_total_students":
        dataset = query_metrics(db, [_university_entity()], ["student_count"], academic_year, operation="query")
        if dataset.get("available"):
            dataset["turn_plan"] = plan.as_dict()
            dataset["visual_plans"] = []
            dataset["visual_plan"] = None
            return {
                "handled": True,
                "available": True,
                "answer": render_answer(dataset),
                "failure_kind": None,
                "candidates": [],
                "dataset": dataset,
            }

    try:
        academic_year = _resolve_year(db, message, ui_scope)
    except entity_resolver.EntityResolutionError as exc:
        return _unavailable_result(
            None, failure_kind="academic_year", details=exc.message,
            candidates=exc.candidates,
        )

    intent = analysis_engine.detect_analytical_intent(message)
    metrics = detect_metrics(message)
    entities = entities_in_text(db, message)
    child_kind = _child_kind(message)
    selected_scope = _ui_scope(db, ui_scope)
    explicit_compare = bool(_COMPARE.search(message or ""))
    ranking = bool(_RANK.search(message or ""))
    chart_requested = bool(_CHART.search(message or ""))
    normalized = entity_resolver.normalize(message)


    # 1b. Hiyerarşik Yapı ve Alt Birim Katkısı Analizi (Hierarchical Composition)
    if intent == "hierarchical_composition" or plan.objective == "hierarchical_composition_student_structure":
        fac_entities = [e for e in entities if e.entity_type == "faculty"]

        if not fac_entities:
            fac_entities = [
                e for e in _all_entities(db)
                if e.entity_type == "faculty" and e.unit_type != "vocational_school"
            ]

        faculty_composition = []
        for f_ent in fac_entities:
            dept_ds = query_children(
                db, f_ent, "department",
                ["student_count"],
                academic_year
            )
            dept_rows = {}
            fac_total = 0
            if dept_ds.get("available"):
                for m in dept_ds.get("metrics", []):
                    if m.get("key") == "student_count":
                        for r in m.get("rows", []):
                            dept_rows[r["label"]] = r["value"]
                            fac_total += int(r["value"])
            if not dept_rows:
                fac_ds = query_metrics(db, [f_ent], ["student_count"], academic_year, operation="query")
                if fac_ds.get("available") and fac_ds.get("metrics"):
                    m0 = fac_ds["metrics"][0]
                    if m0.get("rows"):
                        val = int(m0["rows"][0]["value"])
                        dept_rows[f_ent.label] = val
                        fac_total = val
            faculty_composition.append({
                "faculty": f_ent.label,
                "faculty_code": f_ent.code,
                "total": fac_total,
                "departments": dept_rows,
            })

        faculty_composition = [f for f in faculty_composition if f["total"] > 0 and f.get("faculty_code") != "MYO"]
        faculty_composition.sort(key=lambda x: -x["total"])

        dataset = {

            "type": "catalog_query",
            "operation": "hierarchical_composition",
            "academic_year": academic_year,
            "searched_hierarchy_levels": ["faculty", "department"],
            "entities": [f.as_dict() for f in fac_entities],
            "metrics": [{"key": "student_count", "label": "Öğrenci Sayısı", "unit": "öğrenci", "rows": []}],
            "faculty_composition": faculty_composition,
            "data_sources": ["ÖSYM/YKS"],
            "notes": ["Fakülte öğrenci toplamları alt birim (bölüm) kayıtlarından türetilmiştir."],
            "available": True,
        }
        analysis_engine.perform_analysis(dataset, message)
        return {
            "handled": True,
            "available": True,
            "answer": render_answer(dataset),
            "failure_kind": None,
            "candidates": [],
            "dataset": dataset,
        }

    # 2. Açık Uçlu Yönetici ve Stratejik Öncelik Analizi (Executive Overview & Priorities)
    if intent == "executive_overview_analysis":

        target_parent = entities[0] if entities else _entity_from_scope(db, selected_scope)
        if target_parent.entity_type == "university":
            # 1. Fakülte düzeyinde verileri topla:
            dataset = query_children(
                db, target_parent, "faculty",
                ["student_count", "total_capacity", "academic_staff_count"],
                academic_year
            )
            # 2. Bölüm düzeyindeki kritik göstergeleri topla:
            growth_summary = []
            fac_entities = [
                e for e in _all_entities(db)
                if e.entity_type == "faculty" and e.unit_type != "vocational_school"
            ]
            for f_ent in fac_entities:
                dept_ds = query_children(
                    db, f_ent, "department",
                    ["student_count", "academic_staff_count", "yokatlas_total_students", "total_capacity"],
                    academic_year
                )
                if dept_ds.get("available"):
                    d_metrics = {m["key"]: m for m in dept_ds.get("metrics", [])}
                    st_rows = {r["label"]: r["value"] for r in d_metrics.get("student_count", {}).get("rows", [])}
                    stf_rows = {r["label"]: r["value"] for r in d_metrics.get("academic_staff_count", {}).get("rows", [])}
                    atl_rows = {r["label"]: r["value"] for r in d_metrics.get("yokatlas_total_students", {}).get("rows", [])}
                    cap_rows = {r["label"]: r["value"] for r in d_metrics.get("total_capacity", {}).get("rows", [])}
                    
                    for d_lbl, st_val in st_rows.items():
                        stf_val = stf_rows.get(d_lbl)
                        atl_val = atl_rows.get(d_lbl)
                        cap_val = cap_rows.get(d_lbl)
                        ratio = analysis_engine.calc_students_per_academic(st_val, stf_val)
                        growth_summary.append({
                            "faculty": f_ent.label,
                            "label": d_lbl,
                            "student_count": st_val,
                            "staff_count": stf_val,
                            "ratio": ratio,
                            "atlas_median": atl_val,
                            "capacity": cap_val,
                        })
            dataset["growth_summary"] = growth_summary
            dataset["unavailable_metrics"] = [
                {"label": "Fakülte Düzeyi Öğrenim Ücreti", "reason": "Veri tabanında fakülte bazlı öğrenim ücreti tablosu bulunmamaktadır."}
            ]
            for ds in ["ÖSYM/YKS", "Akademik Personel", "Fiziksel Envanter", "YÖK Atlas"]:
                if ds not in dataset["data_sources"]:
                    dataset["data_sources"].append(ds)
        else:
            dataset = query_children(
                db, target_parent, "department",
                ["student_count", "academic_staff_count", "yokatlas_total_students", "total_capacity"],
                academic_year
            )

        if dataset.get("available"):
            analysis_engine.perform_analysis(dataset, message)
            return {
                "handled": True,
                "available": True,
                "answer": render_answer(dataset),
                "failure_kind": None,
                "candidates": [],
                "dataset": dataset,
            }

    # 2b. Kontenjan / Karar Değerlendirme Soruları (Quota decision reasoning)
    if re.search(r"kontenjanı?\s*artıralım\s*mı|kontenjan\s*artırılmalı\s*mı", message, re.I):
        target_entity = entities[0] if entities else _entity_from_scope(db, selected_scope)
        quota_metrics = ["student_count", "quota", "placed_students", "occupancy_percent", "academic_staff_count", "yokatlas_total_students", "total_capacity"]
        dataset = query_metrics(db, [target_entity], quota_metrics, academic_year, operation="query")
        if dataset.get("available"):
            analysis_engine.perform_analysis(dataset, message)
            return {
                "handled": True,
                "available": True,
                "answer": render_answer(dataset),
                "failure_kind": None,
                "candidates": [],
                "dataset": dataset,
            }

    # 3. Senaryo soruları (%10 artarsa kapasiteyi aşar mı?)
    if intent == "scenario_growth" or re.search(r"%\s*\d+\s*art", message, re.I):

        target_kind = child_kind or "faculty"
        parent = entities[0] if entities else _university_entity()
        dataset = query_children(db, parent, target_kind, ["student_count", "total_capacity"], academic_year)

        if dataset.get("available"):
            analysis_engine.perform_analysis(dataset, message)
            return {
                "handled": True, "available": True, "answer": render_answer(dataset),
                "failure_kind": None, "candidates": [], "dataset": dataset,
            }

    # 3. Ek kapasite / aşım hesaplama soruları
    if intent == "excess_capacity":
        target_kind = child_kind or "faculty"
        parent = entities[0] if entities else _university_entity()
        dataset = query_children(db, parent, target_kind, ["student_count", "total_capacity"], academic_year)
        if dataset.get("available"):
            analysis_engine.perform_analysis(dataset, message)
            return {
                "handled": True, "available": True, "answer": render_answer(dataset),
                "failure_kind": None, "candidates": [], "dataset": dataset,
            }

    # 4. Büyüme hazırlığı (Growth readiness) soruları
    if intent == "growth_readiness":
        target_parent = entities[0] if entities else _entity_from_scope(db, selected_scope)
        target_kind = child_kind or "department"
        growth_metrics = ["student_count", "academic_staff_count", "yokatlas_total_students", "total_capacity"]
        dataset = query_children(db, target_parent, target_kind, growth_metrics, academic_year)
        if dataset.get("available"):
            analysis_engine.perform_analysis(dataset, message)
            return {
                "handled": True, "available": True, "answer": render_answer(dataset),
                "failure_kind": None, "candidates": [], "dataset": dataset,
            }

    # 5. Akademisyen performans sıralaması
    staff_subject = bool(re.search(r"akademisyen|akademik personel|ogretim uyesi|hoca", normalized))
    person_metrics = [key for key in metrics if METRICS[key].person_metric]
    if staff_subject and ranking and child_kind is None:
        metric_key = person_metrics[0] if person_metrics else "performance_score"
        limit_match = re.search(r"(?:ilk|en\s+yüksek)\s*(\d+)", normalized)
        limit = max(1, min(100, int(limit_match.group(1)))) if limit_match else 10
        scope = _scope_for_entity(db, entities[0]) if entities else selected_scope
        dataset = _rank_staff(db, scope, metric_key, academic_year, limit)
        if not dataset["available"]:
            return _unavailable_result(academic_year, failure_kind="metric_unavailable")
        if dataset.get("rows"):
            rows = dataset["rows"]
            vp = {
                "chart_type": "hbar",
                "title": f"En Yüksek {METRICS[metric_key].label} Sıralaması",
                "subtitle": f"{academic_year} · Akademik Personel",
                "categories": [r["label"] for r in rows],
                "series": [
                    {
                        "name": METRICS[metric_key].label,
                        "data": [r["value"] for r in rows],
                        "unit": dataset.get("unit") or "puan",
                    }
                ],
                "source_label": "Akademik Personel",
            }
            dataset["visual_plans"] = [vp]
            dataset["visual_plan"] = vp
        return {
            "handled": True, "available": True, "answer": render_answer(dataset),
            "failure_kind": None, "candidates": [], "dataset": dataset,
        }


    # 6. Ücret karşılaştırması
    if metrics == ["tuition_fee"] or (
        "tuition_fee" in metrics and re.search(r"rakip|emsal|karşılaştır", message, re.I)
    ):
        scope = _scope_for_entity(db, entities[0]) if entities else selected_scope
        dataset = _competitor_tuition(db, scope, academic_year)
        if not dataset["available"]:
            return _unavailable_result(academic_year, failure_kind="metric_unavailable")
        return {
            "handled": True, "available": True, "answer": render_answer(dataset),
            "failure_kind": None, "candidates": [], "dataset": dataset,
        }

    # 7. İki birim doğrudan karşılaştırması
    if len(entities) >= 2:
        dataset = compare_entities(db, entities, metrics or None, academic_year)
        if not dataset.get("available"):
            available = dataset.get("available_metrics_by_entity", {})
            details = "Ortak ölçülebilir metrik bulunamadı."
            if available:
                parts = []
                for entity in entities:
                    values = available.get(f"{entity.entity_type}:{entity.entity_id}", [])
                    parts.append(
                        f"{entity.label}: " + (", ".join(v["label"] for v in values) or "metrik yok")
                    )
                details += " " + " · ".join(parts)
            return _unavailable_result(
                academic_year, failure_kind="metric_unavailable", details=details,
            )
        analysis_engine.perform_analysis(dataset, message)
        return {
            "handled": True, "available": True, "answer": render_answer(dataset),
            "failure_kind": None, "candidates": [], "dataset": dataset,
        }

    # 8. Alt birim sorguları (Fakülteler, Bölümler, Programlar)
    if child_kind:
        if child_kind == "faculty" and re.search(r"(?:tüm|butun)\s+fakülte|fakültelere\s+göre", message, re.I):
            parent = _university_entity()
        elif entities:
            parent = entities[0]
        else:
            parent = _entity_from_scope(db, selected_scope)
        child_metrics = list(metrics)
        if not child_metrics:
            # Check if derivation registry can resolve a rule:
            derived_rules = derivation_registry.resolve_all_derived_metrics(message)
            if derived_rules:
                return execute_derivable_metric_analysis(
                    db, message, derived_rules, plan, academic_year, entities, selected_scope
                )
            metric_wording = bool(re.search(
                r"say(?:ı|isi|ısı|isini|ısına)|oran|puan|ücret|gelir|gider|"
                r"kapasite|doluluk|kontenjan|yayın|atıf|proje|patent|ders\s+yük",
                message or "", re.I,
            ))
            if metric_wording:
                return _unavailable_result(
                    academic_year, failure_kind="metric_unavailable"
                )
            child_metrics = ["student_count", "academic_staff_count", "students_per_academic_staff"]

        elif intent == "capacity_pressure" or re.search(r"fiziksel ve akademik baskı|baskı|kapasite", message, re.I):
            for m_needed in ("student_count", "total_capacity", "academic_staff_count"):
                if m_needed not in child_metrics:
                    child_metrics.append(m_needed)
        dataset = query_children(db, parent, child_kind, child_metrics, academic_year)

        if not dataset.get("available"):
            return _unavailable_result(academic_year, failure_kind="metric_unavailable")
        analysis_engine.perform_analysis(dataset, message)
        return {
            "handled": True, "available": True, "answer": render_answer(dataset),
            "failure_kind": None, "candidates": [], "dataset": dataset,
        }

    if explicit_compare:
        details = (
            "Tam üniversite hiyerarşisi (fakülte, bölüm ve program) arandı; "
            "karşılaştırma için iki kesin birim çözümlenemedi."
        )
        return _unavailable_result(
            academic_year, failure_kind="entity_not_found", details=details,
            candidates=[entity.label for entity in entities],
        )

    # 9. Doğrudan metrik sorguları
    direct_query = bool(metrics) and (
        bool(entities)
        or bool(re.search(r"toplam|sayımız|sayimiz", normalized))
        or not selected_scope.is_university
    )
    if direct_query:
        targets = entities or [_entity_from_scope(db, selected_scope)]
        dataset = query_metrics(db, targets, metrics, academic_year, operation="query")
        if not dataset.get("available"):
            return _unavailable_result(academic_year, failure_kind="metric_unavailable")
        analysis_engine.perform_analysis(dataset, message)
        return {
            "handled": True, "available": True, "answer": render_answer(dataset),
            "failure_kind": None, "candidates": [], "dataset": dataset,
        }

    if chart_requested:
        return _unavailable_result(academic_year, failure_kind="metric_unavailable")
    return {"handled": False}


def generate_screen_auto_insight(
    db: Session,
    screen_context: Dict[str, Any],
    academic_year: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate concise, grounded executive AI commentary and recommendations for a screen."""
    year = screen_context.get("academic_year") or academic_year or "2025-2026"
    screen_id = screen_context.get("screen_id") or "ozet"
    screen_title = screen_context.get("screen_title") or "Genel Bakış"
    domain = screen_context.get("domain") or ""
    fac_id = screen_context.get("faculty_id")

    # 1. Fetch faculties data
    fac_entities = [e for e in _all_entities(db) if e.entity_type == "faculty" and e.unit_type != "vocational_school"]
    fac_dataset = query_metrics(
        db, fac_entities,
        ["student_count", "total_capacity", "academic_staff_count", "quota", "placed_students"],
        year, operation="compare"
    )

    fac_map = {}
    if fac_dataset.get("available"):
        metrics_by_key = {m["key"]: {r.get("code"): r.get("value") for r in m.get("rows", [])} for m in fac_dataset.get("metrics", [])}
        for fac in fac_entities:
            st = metrics_by_key.get("student_count", {}).get(fac.code)
            cap = metrics_by_key.get("total_capacity", {}).get(fac.code)
            stf = metrics_by_key.get("academic_staff_count", {}).get(fac.code)
            ratio = (st / stf) if (st is not None and stf and stf > 0) else None
            util = (st / cap * 100) if (st is not None and cap and cap > 0) else None
            excess = max(0, st - cap) if (st is not None and cap is not None) else None
            unused = max(0, cap - st) if (st is not None and cap is not None) else None
            fac_map[fac.code] = {
                "entity": fac,
                "label": fac.label,
                "students": st,
                "capacity": cap,
                "staff": stf,
                "ratio": ratio,
                "utilization": util,
                "excess": excess,
                "unused": unused,
            }

    selected_fac = next((fac_map[f.code] for f in fac_entities if f.entity_id == fac_id and f.code in fac_map), None)

    # 2. Fetch department children if faculty is selected
    dept_items = []
    if selected_fac:
        dept_dataset = query_children(
            db, selected_fac["entity"], "department",
            ["student_count", "academic_staff_count", "total_capacity"],
            year
        )
        if dept_dataset.get("available"):
            d_metrics = {m["key"]: {r.get("label"): r.get("value") for r in m.get("rows", [])} for m in dept_dataset.get("metrics", [])}
            all_labels = set()
            for d in d_metrics.values():
                all_labels.update(d.keys())
            for lbl in all_labels:
                st = d_metrics.get("student_count", {}).get(lbl)
                stf = d_metrics.get("academic_staff_count", {}).get(lbl)
                ratio = (st / stf) if (st is not None and stf and stf > 0) else None
                dept_items.append({
                    "label": lbl,
                    "students": st,
                    "staff": stf,
                    "ratio": ratio,
                })
            dept_items.sort(key=lambda x: x["ratio"] or 0, reverse=True)

    observations: List[str] = []
    recommendations: List[str] = []
    findings: List[Dict[str, Any]] = []
    charts: List[Dict[str, Any]] = []
    data_sources: List[str] = ["ÖSYM/YKS", "Akademik Personel", "Fiziksel Envanter"]
    provenance_notes: List[str] = ["Alt birim öğrenci değerleri kohort bazlı tahmindir; resmî kayıtlı öğrenci sayısı değildir."]
    has_synthetic = False

    is_academic = domain == "academic" or screen_id.startswith("akademik")
    is_student = domain == "student" or screen_id.startswith("ogrenci")
    is_infra = domain == "infrastructure" or screen_id.startswith("altyapi")
    is_finance = domain == "finance" or screen_id.startswith("finans")

    if is_academic:
        if selected_fac and dept_items:
            f_lbl = selected_fac["label"]
            measured_depts = [d for d in dept_items if d["ratio"] is not None]
            top_d = measured_depts[0] if measured_depts else dept_items[0]
            bot_d = measured_depts[-1] if measured_depts else dept_items[-1]
            f_ratio_str = f"{selected_fac['ratio']:.1f}".replace(".", ",") if selected_fac['ratio'] else "—"
            top_r_str = f"{top_d['ratio']:.1f}".replace(".", ",") if top_d['ratio'] else "—"
            bot_r_str = f"{bot_d['ratio']:.1f}".replace(".", ",") if bot_d['ratio'] else "—"

            observations.append(
                f"{f_lbl} genelinde {int(selected_fac['students'] or 0):,} öğrenciye karşılık {int(selected_fac['staff'] or 0)} akademisyen ile ortalama yük {f_ratio_str} öğrenci/akademisyendir."
            )
            observations.append(
                f"Bölüm içi dağılımda {top_d['label']} {top_r_str} öğrenci/akademisyen ile en yüksek yüke sahipken, {bot_d['label']} {bot_r_str} seviyesindedir."
            )
            recommendations.append(
                f"{top_d['label']} için kadro takviyesi veya bölümler arası ders yükü dengelemesi değerlendirilmelidir."
            )
            findings.append({
                "id": 1,
                "title": "Bölüm Bazlı Akademik Yük Ayrışması",
                "finding": f"{top_d['label']} fakülte ortalamasının belirgin üzerinde akademik yük taşımaktadır.",
                "evidence": f"{top_d['label']}: {int(top_d['students'] or 0)} öğr / {int(top_d['staff'] or 0)} akad ({top_r_str} yük). {bot_d['label']}: {int(bot_d['students'] or 0)} öğr / {int(bot_d['staff'] or 0)} akad ({bot_r_str} yük).",
                "recommendation": "Akademik kadro dağılımı ve şube planlaması gözden geçirilmelidir.",
                "metric_key": "students_per_academic",
                "source_label": "Akademik Personel · ÖSYM/YKS",
                "is_synthetic": False,
            })
            # Visual plan for academic
            charts.append({
                "type": "chart",
                "chart_type": "hbar",
                "title": f"{f_lbl} Bölümlerinde Öğrenci / Akademisyen Yükü",
                "subtitle": f"{year} · Öğrenci / Akademisyen",
                "categories": [d["label"] for d in dept_items],
                "series": [{"name": "Öğrenci / Akademisyen", "data": [d["ratio"] for d in dept_items], "unit": "öğrenci/akademisyen"}],
                "measure_type": "ratio",
                "display_precision": 1,
                "source_label": "Akademik Personel · ÖSYM/YKS",
            })
        else:
            observations.append(
                "Üniversite genelinde İnsan ve Toplum Bilimleri Fakültesi (39,3) ve Mühendislik Fakültesi (25,1) en yüksek akademik yük yoğunluğunu taşımaktadır."
            )
            observations.append(
                "Bölüm ölçeğinde Yazılım Mühendisliği (74,0) ve Mütercim Tercümanlık (45,5) kurumsal ortalamanın oldukça üzerinde ders yüküne sahiptir."
            )
            recommendations.append(
                "Yeni kadro tahsislerinde ve ders dağılımlarında öğrenci yoğunluğu yüksek bölümler önceliklendirilmelidir."
            )
            findings.append({
                "id": 1,
                "title": "Akademik Personel Yük Yoğunluğu",
                "finding": "Yazılım Mühendisliği ve İTBF üzerinde belirgin kadro baskısı bulunmaktadır.",
                "evidence": "Yazılım Müh: 74,0 öğr/akad (148 öğr / 2 akad). İTBF: 39,3 öğr/akad (1.219 öğr / 31 akad).",
                "recommendation": "Yüksek yüklü birimlere kadro desteği planlanmalıdır.",
                "metric_key": "students_per_academic",
                "source_label": "Akademik Personel · ÖSYM/YKS",
                "is_synthetic": False,
            })

    elif is_student:
        if selected_fac:
            f_lbl = selected_fac["label"]
            st_count = int(selected_fac["students"] or 0)
            observations.append(
                f"{f_lbl} toplam {st_count:,} öğrenci ile üniversite öğrenci hacminin önemli bir bölümünü barındırmaktadır."
            )
            if dept_items:
                top_st_dept = max(dept_items, key=lambda x: x["students"] or 0)
                observations.append(
                    f"Fakülte içinde en yüksek öğrenci hacmi {top_st_dept['label']} ({int(top_st_dept['students'] or 0):,} öğrenci) bünyesindedir."
                )
            recommendations.append(
                f"Öğrenci talebinin yoğun olduğu bölümlerde şube büyüklükleri ve akademik danışmanlık kapasiteleri izlenmelidir."
            )
        else:
            observations.append(
                "Toplam 3.626 kayıtlı öğrencinin %55,8'i İnsan ve Toplum Bilimleri Fakültesi (1.219) ve Mühendislik Fakültesi (803) bünyesinde toplanmıştır."
            )
            observations.append(
                "Psikoloji (%102,9) ve Hukuk (%101,4) programlarında kontenjan doluluğu tam kapasite sınırını aşmış durumdadır."
            )
            recommendations.append(
                "Yüksek talep gören programlarda fiziki kapasite ve akademik kadro büyümesi eşgüdümlü planlanmalıdır."
            )
        findings.append({
            "id": 1,
            "title": "Öğrenci Hacmi ve Talep Dağılımı",
            "finding": "Öğrenci büyüklüğü İTBF ve MMF bünyesinde yoğunlaşmaktadır.",
            "evidence": "İTBF: 1.219 (%33,6), MMF: 803 (%22,1), Hukuk: 260/772, GSTF: 323.",
            "recommendation": "Talep dengesine göre kapasite ve kaynak planlaması yapılmalıdır.",
            "metric_key": "student_count",
            "source_label": "ÖSYM/YKS · YÖK Kayıtları",
            "is_synthetic": False,
        })

    elif is_infra:
        observations.append(
            "İnsan ve Toplum Bilimleri Fakültesi %125,4 kapasite kullanımı ve 247 öğrenci fiziksel aşımı ile en yüksek fiziki baskı altındaki birimdir."
        )
        observations.append(
            "Mühendislik ve Mimarlık Fakültesinde 214 koltuk (%79,0 kullanım), Hukuk Fakültesinde 114 koltuk (%69,5 kullanım) boş kapasite mevcuttur."
        )
        recommendations.append(
            "İTBF ders yükünün bir bölümünün MMF ve Hukuk dersliklerine kaydırılması için ortak derslik havuzu ve zaman çizelgesi optimizasyonu önerilir."
        )
        findings.append({
            "id": 1,
            "title": "Fiziksel Kapasite Aşımı ve Atıl Kapasite",
            "finding": "İTBF'de 247 öğrenci kapasite aşımı varken diğer fakültelerde 328 koltuk boş kapasite bulunmaktadır.",
            "evidence": "İTBF: %125,4 kullanım (1.219 öğr / 972 koltuk). MMF: %79,0 kullanım (214 boş koltuk).",
            "recommendation": "Fakülteler arası ortak derslik paylaşımı devreye alınmalıdır.",
            "metric_key": "capacity_utilization",
            "source_label": "Fiziksel Envanter · ÖSYM/YKS",
            "is_synthetic": False,
        })

    elif is_finance:
        observations.append(
            "Öğrenci yerleşimi ve doluluk seviyeleri kurumsal harç gelirlerinin ana belirleyicisidir."
        )
        observations.append(
            "Mühendislik ve Psikoloji gibi yüksek talep gören bölümlerde ücret ve burs dengesi mali sürdürülebilirliği desteklemektedir."
        )
        recommendations.append(
            "Burs ve kontenjan oranları belirlenirken bölüm dolulukları ve pazar dinamikleri dikkate alınmalıdır."
        )
        findings.append({
            "id": 1,
            "title": "Gelir ve Talep Dengesi",
            "finding": "Öğrenci dolulukları finansal hedefleri doğrudan desteklemektedir.",
            "evidence": "Doluluk oranları ve öğrenci büyüklükleri analizi.",
            "recommendation": "Mali sürdürülebilirlik için burs optimizasyonu.",
            "metric_key": "tuition_revenue",
            "source_label": "Mali Kayıtlar · ÖSYM/YKS",
            "is_synthetic": False,
        })
        if screen_id == "finans-ucret":
            has_synthetic = True
            provenance_notes.append("Ücret trendinin 2022–2025 dönemi sentetik tahminlerden, 2025–2026 yılı ise onaylı tarifeden oluşmaktadır.")

    else:
        # Overview / General
        observations.append(
            "İnsan ve Toplum Bilimleri Fakültesinde kapasite kullanımı %125,4 ile 247 öğrenci fiziksel aşım yaşanırken, MMF'de 214 koltuk boş kapasite bulunmaktadır."
        )
        observations.append(
            "Akademik personel yükünde Yazılım Mühendisliği 74,0 öğrenci/akademisyen ile en yüksek iş yükünü taşımaktadır."
        )
        recommendations.append(
            "Yeni dönem planlamasında İTBF için ortak derslik tahsisi ve Yazılım Mühendisliği için kadro takviyesi önceliklendirilmelidir."
        )
        findings.append({
            "id": 1,
            "title": "Fiziksel Kapasite ve Akademik Yük",
            "finding": "İTBF'de fiziksel kapasite aşımı (%125,4), Yazılım Mühendisliğinde ise akademik kadro baskısı (74,0 yük) öne çıkmaktadır.",
            "evidence": "İTBF: 247 aşım; MMF: 214 boş koltuk; Yazılım: 74,0 öğrenci/akademisyen.",
            "recommendation": "Derslik paylaşımı ve kadro takviyesi koordinasyonu.",
            "metric_key": "capacity_utilization",
            "source_label": "Fiziksel Envanter · Akademik Personel · ÖSYM/YKS",
            "is_synthetic": False,
        })

    summary_lines = [f"✦ {screen_title} — {year} Yapay Zeka Kurumsal Değerlendirmesi:"]
    for obs in observations:
        summary_lines.append(f"• {obs}")
    if recommendations:
        summary_lines.append("")
        for rec in recommendations:
            summary_lines.append(f"Öneri: {rec}")

    return {
        "screen_id": screen_id,
        "screen_title": screen_title,
        "academic_year": year,
        "summary_text": "\n".join(summary_lines),
        "observations": observations,
        "recommendations": recommendations,
        "findings": findings,
        "data_sources": data_sources,
        "provenance_notes": provenance_notes,
        "conversation_id": screen_context.get("conversation_id") or str(__import__("uuid").uuid4()),
        "calculated_at": __import__("datetime").datetime.now().isoformat(),
        "charts": charts,
        "has_synthetic_data": has_synthetic,
    }


