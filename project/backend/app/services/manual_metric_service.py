"""Manuel göstergelerin doğrulama, öncelik, kapsam ve CRUD servisi."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    AcademicStaff,
    Department,
    DepartmentBudget,
    FinancialEntry,
    FinancialPeriod,
    ManualMetricEntry,
    ManualMetricEntryAudit,
)
from app.schemas.manual_metrics import ManualMetricCreate, ManualMetricUpdate
from app.services import academic_staff_service, auth_service, finance_service
from app.services.manual_metric_registry import (
    MANUAL_METRIC_REGISTRY,
    ManualMetricDefinition,
    get_definition,
)
from app.services.scope import Scope, resolve


@dataclass(frozen=True)
class AuthoritativeMetric:
    value: Decimal
    source_label: str


FINANCE_CATEGORY_MATCH: dict[str, tuple[str, tuple[str, ...]]] = {
    "gross_tuition_revenue": ("revenue", ("öğrenim", "tuition")),
    "research_revenue": ("revenue", ("araştırma", "research", "ar-ge", "r&d")),
    "other_revenue": ("revenue", ("diğer", "other")),
    "scholarship_expense": ("expenditure", ("burs", "scholarship")),
    "academic_personnel_expense": (
        "expenditure", ("akademik personel", "academic personnel", "academic staff")
    ),
    "administrative_personnel_expense": (
        "expenditure", ("idari personel", "administrative personnel", "administrative staff")
    ),
    "education_operating_expense": (
        "expenditure", ("eğitim ve işletme", "education operating")
    ),
    "research_laboratory_expense": (
        "expenditure", ("araştırma ve laboratuvar", "research and laboratory")
    ),
    "facility_infrastructure_expense": (
        "expenditure", ("tesis ve altyapı", "facility and infrastructure")
    ),
    "technology_expense": ("expenditure", ("teknoloji", "technology")),
    "other_operating_expense": (
        "expenditure", ("diğer işletme", "other operating")
    ),
}


def _error(code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=code, detail=detail)


def definition_or_404(metric_key: str) -> ManualMetricDefinition:
    try:
        return get_definition(metric_key)
    except KeyError as exc:
        raise _error(status.HTTP_404_NOT_FOUND, f"'{metric_key}' manuel girişe açık bir metrik değil.") from exc


def validate_academic_year(academic_year: str) -> None:
    """Biçimin yanında iki yılın ardışık olduğunu da doğrular."""
    try:
        first, second = (int(part) for part in academic_year.split("-"))
    except (TypeError, ValueError) as exc:
        raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, "Akademik yıl YYYY-YYYY biçiminde olmalıdır.") from exc
    if second != first + 1 or first < 2000 or second > 2200:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Akademik yıl ardışık ve geçerli olmalıdır (ör. 2025-2026).",
        )


def exact_scope(
    db: Session,
    scope_type: str,
    faculty_id: Optional[int],
    department_id: Optional[int],
    program_id: Optional[int],
) -> Scope:
    """Kimlikleri çözer ve istemcinin söylediği kapsam türüyle birebir eşler."""
    scope = resolve(
        db,
        faculty_id=faculty_id,
        department_id=department_id,
        academic_program_id=program_id,
    )
    if scope.level != scope_type:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"scope_type='{scope_type}' gönderildi ancak kimlikler '{scope.level}' kapsamını çözüyor.",
        )
    return scope


def _scope_parts(scope: Scope) -> tuple[Optional[int], Optional[int], Optional[int]]:
    return scope.faculty_id, scope.department_id, scope.academic_program_id


def _identity(metric_key: str, academic_year: str, scope: Scope) -> str:
    faculty_id, department_id, program_id = _scope_parts(scope)
    return ":".join(
        [
            metric_key,
            academic_year,
            scope.level,
            str(faculty_id or 0),
            str(department_id or 0),
            str(program_id or 0),
        ]
    )


def _validate_definition_scope(definition: ManualMetricDefinition, scope: Scope) -> None:
    if scope.level not in definition.allowed_scopes:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"{definition.label} metriği '{scope.level}' kapsamında manuel girilemez.",
        )


def _validate_value(
    definition: ManualMetricDefinition,
    numeric_value: Optional[Decimal],
    text_value: Optional[str],
    unit: Optional[str],
) -> tuple[Optional[Decimal], Optional[str]]:
    if unit is not None and unit.strip() != definition.unit:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Bu metriğin birimi '{definition.unit}' olmalıdır.",
        )
    if definition.value_type == "number":
        if numeric_value is None:
            raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, "Sayısal değer zorunludur.")
        if not numeric_value.is_finite():
            raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, "Sayısal değer sonlu olmalıdır.")
        if definition.minimum is not None and numeric_value < definition.minimum:
            raise _error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"Değer {definition.minimum} değerinden küçük olamaz.",
            )
        if definition.maximum is not None and numeric_value > definition.maximum:
            raise _error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"Değer {definition.maximum} değerinden büyük olamaz.",
            )
        if abs(numeric_value) > Decimal("1000000000000000000"):
            raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, "Sayısal değer izin verilen sınırı aşıyor.")
        if definition.integer_only and numeric_value != numeric_value.to_integral_value():
            raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, "Bu metrik yalnızca tam sayı kabul eder.")
        if text_value not in (None, ""):
            raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, "Sayısal metrikte text_value kullanılamaz.")
        return numeric_value, None

    normalized = (text_value or "").strip()
    if not normalized:
        raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, "Metin değer boş olamaz.")
    if numeric_value is not None:
        raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, "Metin metrikte numeric_value kullanılamaz.")
    return None, normalized


def _query_for_scope(statement, scope: Scope):
    faculty_id, department_id, program_id = _scope_parts(scope)
    return statement.where(
        ManualMetricEntry.scope_type == scope.level,
        ManualMetricEntry.faculty_id.is_(None) if faculty_id is None else ManualMetricEntry.faculty_id == faculty_id,
        ManualMetricEntry.department_id.is_(None) if department_id is None else ManualMetricEntry.department_id == department_id,
        ManualMetricEntry.program_id.is_(None) if program_id is None else ManualMetricEntry.program_id == program_id,
    )


def _active_entry(db: Session, metric_key: str, academic_year: str, scope: Scope) -> Optional[ManualMetricEntry]:
    statement = select(ManualMetricEntry).where(
        ManualMetricEntry.metric_key == metric_key,
        ManualMetricEntry.academic_year == academic_year,
        ManualMetricEntry.is_active.is_(True),
    )
    return db.execute(_query_for_scope(statement, scope)).scalars().first()


def _academic_authoritative(
    db: Session, definition: ManualMetricDefinition, scope: Scope, academic_year: str
) -> Optional[AuthoritativeMetric]:
    rows = academic_staff_service.list_staff(
        db, skip=0, limit=100_000, academic_year=academic_year, scope=scope
    )
    if not rows:
        return None
    total = sum(Decimal(getattr(row, definition.key) or 0) for row in rows)
    # Bu alanlar eski içe aktarımlarda zorunlu 0 varsayılanıyla oluşturulmuş;
    # pozitif olmayan toplam "ölçülmüş sıfır" kanıtı değildir. NULL ile aynı
    # biçimde eksik sayılır ve manuel girişe izin verilir.
    if total <= 0:
        return None
    return AuthoritativeMetric(total, "Akademik personel içe aktarımı")


def _physical_authoritative(
    db: Session, definition: ManualMetricDefinition, scope: Scope
) -> Optional[AuthoritativeMetric]:
    from app.services import physical_resources_service

    if definition.key in {"facility_occupancy_rate", "facility_area_m2"}:
        try:
            overview = physical_resources_service.capacity_overview(db, scope)
        except HTTPException as exc:
            if exc.status_code == status.HTTP_404_NOT_FOUND:
                return None
            raise
        field = (
            "overall_occupancy_percent"
            if definition.key == "facility_occupancy_rate"
            else "total_area_square_meters"
        )
        value = overview.get(field)
        if value is None:
            return None
        return AuthoritativeMetric(
            Decimal(str(value)), "Fiziksel kaynak envanteri ve kullanım ölçümü"
        )

    target = "classroom" if definition.key.startswith("classroom") else "laboratory"
    try:
        rows = physical_resources_service.utilization_by_type(db, scope)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_404_NOT_FOUND:
            return None
        raise
    row = next((item for item in rows if item["facility_type"] == target), None)
    value = row and row.get("average_utilization_percent")
    if value is None:
        return None
    return AuthoritativeMetric(Decimal(str(value)), "Fiziksel kaynak kullanım ölçümü")


def _finance_source_exists(
    db: Session, definition: ManualMetricDefinition, scope: Scope, period: FinancialPeriod
) -> bool:
    if scope.is_program:
        return False
    category_spec = FINANCE_CATEGORY_MATCH.get(definition.key)
    if category_spec is not None:
        if not scope.is_university:
            return False
        kind, tokens = category_spec
        entries = db.execute(
            select(FinancialEntry).where(
                FinancialEntry.financial_period_id == period.id,
                FinancialEntry.kind == kind,
            )
        ).scalars()
        return any(
            any(token in row.category.casefold() for token in tokens)
            for row in entries
        )
    if definition.key == "personnel_cost":
        if not scope.is_university:
            return False
        entries = db.execute(
            select(FinancialEntry).where(
                FinancialEntry.financial_period_id == period.id,
                FinancialEntry.kind == "expenditure",
            )
        ).scalars()
        return any(
            any(token in row.category.lower() for token in finance_service.PERSONNEL_CATEGORY_KEYS)
            for row in entries
        )
    if scope.is_university:
        kind = "revenue" if definition.key == "total_income" else "expenditure"
        return db.execute(
            select(FinancialEntry.id).where(
                FinancialEntry.financial_period_id == period.id,
                FinancialEntry.kind == kind,
            )
        ).first() is not None
    return db.execute(
        select(DepartmentBudget.id).where(
            DepartmentBudget.financial_period_id == period.id,
            DepartmentBudget.department_id.in_(scope.department_ids or frozenset()),
        )
    ).first() is not None


def _finance_authoritative(
    db: Session, definition: ManualMetricDefinition, scope: Scope, academic_year: str
) -> Optional[AuthoritativeMetric]:
    period = db.execute(
        select(FinancialPeriod).where(
            FinancialPeriod.academic_year == academic_year,
            FinancialPeriod.is_active.is_(True),
        )
    ).scalars().first()
    if period is None or not _finance_source_exists(db, definition, scope, period):
        return None
    category_spec = FINANCE_CATEGORY_MATCH.get(definition.key)
    if category_spec is not None:
        kind, tokens = category_spec
        matched = [
            row.amount
            for row in db.execute(
                select(FinancialEntry).where(
                    FinancialEntry.financial_period_id == period.id,
                    FinancialEntry.kind == kind,
                )
            ).scalars()
            if any(token in row.category.casefold() for token in tokens)
        ]
        if not matched:
            return None
        return AuthoritativeMetric(
            sum(matched, Decimal("0")), "Yetkili mali dönem kalemi"
        )
    summary = finance_service.financial_summary(db, academic_year, scope)
    if definition.key == "total_income":
        value = summary["total_revenue"]
    elif definition.key == "total_expense":
        value = summary["total_expenditure"]
    else:
        matched = [
            Decimal(str(row["amount"]))
            for row in summary.get("expenditure_breakdown", [])
            if any(token in row["category"].lower() for token in finance_service.PERSONNEL_CATEGORY_KEYS)
        ]
        value = sum(matched, Decimal("0"))
    return AuthoritativeMetric(Decimal(str(value)), "Yetkili mali dönem kaydı")


def authoritative_value(
    db: Session, definition: ManualMetricDefinition, scope: Scope, academic_year: str
) -> Optional[AuthoritativeMetric]:
    if definition.screen_key == "academic":
        return _academic_authoritative(db, definition, scope, academic_year)
    if definition.screen_key == "infrastructure":
        return _physical_authoritative(db, definition, scope)
    if definition.screen_key == "finance":
        return _finance_authoritative(db, definition, scope, academic_year)
    return None


def authorize_mutation(db: Session, session_token: Optional[str], scope: Scope) -> Optional[str]:
    """Mevcut oturum varsa rol/kapsamı uygular; girişsiz demo akışını korur."""
    if not session_token:
        return None
    current = auth_service.get_session(session_token)
    if current is None:
        raise _error(status.HTTP_401_UNAUTHORIZED, "Oturum geçersiz veya süresi dolmuş.")
    role = current.get("role")
    allowed = role == "Admin"
    if role == "Dekan":
        allowed = scope.faculty_id is not None and scope.faculty_id == current.get("faculty_id")
    elif role == "Bölüm Başkanı":
        allowed = scope.department_id is not None and scope.department_id == current.get("department_id")
    if not allowed:
        raise _error(status.HTTP_403_FORBIDDEN, "Bu kapsamda manuel veri düzenleme yetkiniz yok.")
    return current.get("username")


def _snapshot(entry: ManualMetricEntry) -> str:
    return json.dumps(
        {
            "numeric_value": str(entry.numeric_value) if entry.numeric_value is not None else None,
            "text_value": entry.text_value,
            "source_note": entry.source_note,
            "note": entry.note,
            "unit": entry.unit,
            "is_active": entry.is_active,
        },
        ensure_ascii=False,
    )


def _audit(
    db: Session,
    entry: ManualMetricEntry,
    action: str,
    actor: Optional[str],
    old: Optional[str],
    new: Optional[str],
) -> None:
    db.add(
        ManualMetricEntryAudit(
            entry_id=entry.id,
            action=action,
            old_value_json=old,
            new_value_json=new,
            changed_by=actor,
        )
    )


def entry_to_dict(entry: ManualMetricEntry, scope_label: str) -> dict:
    return {
        "id": entry.id,
        "metric_key": entry.metric_key,
        "metric_label": entry.metric_label,
        "screen_key": entry.screen_key,
        "scope_type": entry.scope_type,
        "scope_label": scope_label,
        "faculty_id": entry.faculty_id,
        "department_id": entry.department_id,
        "program_id": entry.program_id,
        "academic_year": entry.academic_year,
        "numeric_value": entry.numeric_value,
        "text_value": entry.text_value,
        "unit": entry.unit,
        "source_note": entry.source_note,
        "note": entry.note,
        "source_type": "manual",
        "source_label": "Manuel veri",
        "editable": True,
        "created_by": entry.created_by,
        "updated_by": entry.updated_by,
        "is_active": entry.is_active,
        "created_at": entry.created_at,
        "updated_at": entry.updated_at,
    }


def create_entry(
    db: Session, payload: ManualMetricCreate, session_token: Optional[str] = None
) -> dict:
    definition = definition_or_404(payload.metric_key)
    if payload.screen_key != definition.screen_key:
        raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, "Metrik bu ekrana ait değil.")
    validate_academic_year(payload.academic_year)
    scope = exact_scope(
        db, payload.scope_type, payload.faculty_id, payload.department_id, payload.program_id
    )
    _validate_definition_scope(definition, scope)
    numeric_value, text_value = _validate_value(
        definition, payload.numeric_value, payload.text_value, payload.unit
    )
    actor = authorize_mutation(db, session_token, scope)
    authoritative = authoritative_value(db, definition, scope, payload.academic_year)
    if authoritative is not None:
        raise _error(
            status.HTTP_409_CONFLICT,
            f"Bu metrik için yetkili veri zaten mevcut ({authoritative.source_label}); manuel kayıt oluşturulamaz.",
        )
    if _active_entry(db, definition.key, payload.academic_year, scope) is not None:
        raise _error(status.HTTP_409_CONFLICT, "Bu metrik, kapsam ve dönem için etkin manuel kayıt zaten var.")

    faculty_id, department_id, program_id = _scope_parts(scope)
    entry = ManualMetricEntry(
        metric_key=definition.key,
        metric_label=definition.label,
        screen_key=definition.screen_key,
        identity_key=_identity(definition.key, payload.academic_year, scope),
        scope_type=scope.level,
        faculty_id=faculty_id,
        department_id=department_id,
        program_id=program_id,
        academic_year=payload.academic_year,
        numeric_value=numeric_value,
        text_value=text_value,
        unit=definition.unit,
        source_note=(payload.source_note or "").strip() or None,
        note=(payload.note or "").strip() or None,
        created_by=actor,
        updated_by=actor,
    )
    db.add(entry)
    try:
        db.flush()
        _audit(db, entry, "create", actor, None, _snapshot(entry))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _error(status.HTTP_409_CONFLICT, "Bu metrik, kapsam ve dönem için etkin kayıt zaten var.") from exc
    db.refresh(entry)
    return entry_to_dict(entry, scope.label)


def _get_active_or_404(db: Session, entry_id: int) -> ManualMetricEntry:
    entry = db.get(ManualMetricEntry, entry_id)
    if entry is None or not entry.is_active:
        raise _error(status.HTTP_404_NOT_FOUND, f"{entry_id} numaralı etkin manuel kayıt bulunamadı.")
    return entry


def _scope_for_entry(db: Session, entry: ManualMetricEntry) -> Scope:
    return exact_scope(
        db, entry.scope_type, entry.faculty_id, entry.department_id, entry.program_id
    )


def update_entry(
    db: Session, entry_id: int, payload: ManualMetricUpdate, session_token: Optional[str] = None
) -> dict:
    entry = _get_active_or_404(db, entry_id)
    definition = definition_or_404(entry.metric_key)
    scope = _scope_for_entry(db, entry)
    actor = authorize_mutation(db, session_token, scope)
    authoritative = authoritative_value(db, definition, scope, entry.academic_year)
    if authoritative is not None:
        raise _error(
            status.HTTP_409_CONFLICT,
            f"Yetkili veri artık mevcut ({authoritative.source_label}); manuel kayıt düzenlenemez.",
        )
    numeric_value = payload.numeric_value if "numeric_value" in payload.model_fields_set else entry.numeric_value
    text_value = payload.text_value if "text_value" in payload.model_fields_set else entry.text_value
    unit = payload.unit if "unit" in payload.model_fields_set else entry.unit
    numeric_value, text_value = _validate_value(definition, numeric_value, text_value, unit)
    old = _snapshot(entry)
    entry.numeric_value = numeric_value
    entry.text_value = text_value
    entry.unit = definition.unit
    if "source_note" in payload.model_fields_set:
        entry.source_note = (payload.source_note or "").strip() or None
    if "note" in payload.model_fields_set:
        entry.note = (payload.note or "").strip() or None
    entry.updated_by = actor
    entry.updated_at = datetime.now()
    _audit(db, entry, "update", actor, old, _snapshot(entry))
    db.commit()
    db.refresh(entry)
    return entry_to_dict(entry, scope.label)


def delete_entry(db: Session, entry_id: int, session_token: Optional[str] = None) -> dict:
    entry = _get_active_or_404(db, entry_id)
    scope = _scope_for_entry(db, entry)
    actor = authorize_mutation(db, session_token, scope)
    old = _snapshot(entry)
    entry.is_active = False
    entry.deleted_at = datetime.now()
    entry.updated_at = datetime.now()
    entry.updated_by = actor
    _audit(db, entry, "delete", actor, old, _snapshot(entry))
    db.commit()
    return {
        "id": entry.id,
        "metric_key": entry.metric_key,
        "is_active": False,
        "message": "Manuel veri silindi.",
    }


def list_entries(
    db: Session,
    *,
    academic_year: str,
    scope_type: str,
    faculty_id: Optional[int],
    department_id: Optional[int],
    program_id: Optional[int],
    metric_key: Optional[str] = None,
    screen_key: Optional[str] = None,
    include_inactive: bool = False,
) -> list[dict]:
    validate_academic_year(academic_year)
    scope = exact_scope(db, scope_type, faculty_id, department_id, program_id)
    statement = select(ManualMetricEntry).where(
        ManualMetricEntry.academic_year == academic_year
    )
    if not include_inactive:
        statement = statement.where(ManualMetricEntry.is_active.is_(True))
    if metric_key:
        definition_or_404(metric_key)
        statement = statement.where(ManualMetricEntry.metric_key == metric_key)
    if screen_key:
        statement = statement.where(ManualMetricEntry.screen_key == screen_key)
    rows = db.execute(
        _query_for_scope(statement, scope).order_by(ManualMetricEntry.metric_key)
    ).scalars()
    return [entry_to_dict(row, scope.label) for row in rows]


def availability(
    db: Session,
    *,
    metric_key: str,
    academic_year: str,
    scope_type: str,
    faculty_id: Optional[int],
    department_id: Optional[int],
    program_id: Optional[int],
) -> dict:
    definition = definition_or_404(metric_key)
    validate_academic_year(academic_year)
    scope = exact_scope(db, scope_type, faculty_id, department_id, program_id)
    _validate_definition_scope(definition, scope)
    scope_dict = {
        "scope_type": scope.level,
        "scope_label": scope.label,
        "faculty_id": scope.faculty_id,
        "department_id": scope.department_id,
        "program_id": scope.academic_program_id,
    }
    authoritative = authoritative_value(db, definition, scope, academic_year)
    if authoritative is not None:
        return {
            "definition": definition.public_dict(),
            "scope": scope_dict,
            "academic_year": academic_year,
            "status": "authoritative",
            "can_add": False,
            "reason": "Yetkili veri kaynağı mevcut; manuel veri öncelik kazanamaz.",
            "resolved_value": authoritative.value,
            "unit": definition.unit,
            "source_type": "authoritative",
            "source_label": authoritative.source_label,
            "editable": False,
            "manual_entry": None,
        }
    entry = _active_entry(db, metric_key, academic_year, scope)
    if entry is not None:
        response = entry_to_dict(entry, scope.label)
        return {
            "definition": definition.public_dict(),
            "scope": scope_dict,
            "academic_year": academic_year,
            "status": "manual",
            "can_add": False,
            "reason": None,
            "resolved_value": entry.numeric_value,
            "unit": entry.unit,
            "source_type": "manual",
            "source_label": "Manuel veri",
            "editable": True,
            "manual_entry": response,
        }
    return {
        "definition": definition.public_dict(),
        "scope": scope_dict,
        "academic_year": academic_year,
        "status": "unavailable",
        "can_add": True,
        "reason": "Bu metrik, kapsam ve dönem için veri bulunamadı.",
        "resolved_value": None,
        "unit": definition.unit,
        "source_type": None,
        "source_label": None,
        "editable": False,
        "manual_entry": None,
    }


def manual_context_rows(
    db: Session, scope: Scope, academic_year: str, screen_key: Optional[str] = None
) -> list[dict]:
    """Asistan bağlamı için yalnızca etkin ve tam kapsamdaki manuel satırlar."""
    statement = select(ManualMetricEntry).where(
        ManualMetricEntry.academic_year == academic_year,
        ManualMetricEntry.is_active.is_(True),
    )
    if screen_key:
        statement = statement.where(ManualMetricEntry.screen_key == screen_key)
    rows = db.execute(_query_for_scope(statement, scope)).scalars()
    result = []
    for entry in rows:
        definition = MANUAL_METRIC_REGISTRY.get(entry.metric_key)
        if definition is None:
            continue
        # Sonradan yetkili veri geldiyse manuel satır bağlama da sızmaz.
        if authoritative_value(db, definition, scope, academic_year) is not None:
            continue
        value = entry.numeric_value if entry.numeric_value is not None else entry.text_value
        result.append(
            {
                "metric_key": entry.metric_key,
                "label": entry.metric_label,
                "value": value,
                "unit": entry.unit,
                "source_type": "manual",
                "source_label": "Manuel veri",
                "entry_id": entry.id,
            }
        )
    return result
