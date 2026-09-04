"""Genel manuel gösterge tanımı, çözümleme ve CRUD uçları."""

from typing import Optional

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.manual_metrics import (
    ManualMetricAvailability,
    ManualMetricCreate,
    ManualMetricEntryResponse,
    ManualMetricUpdate,
)
from app.services import manual_metric_service as service
from app.services.manual_metric_registry import list_definitions


router = APIRouter(prefix="/api/manual-metrics", tags=["Manuel Veri Girişi"])


@router.get("/definitions", summary="Manuel girişe açık metrik tanımları")
def definitions(
    screen_key: Optional[str] = Query(default=None),
    scope_type: Optional[str] = Query(default=None),
) -> list[dict]:
    """Formlar ve ekranlar bu kontrollü kayıt defterinden beslenir."""
    return [
        definition.public_dict()
        for definition in list_definitions(screen_key=screen_key, scope_type=scope_type)
    ]


@router.get(
    "/availability",
    response_model=ManualMetricAvailability,
    summary="Metrik için yetkili/manüel/boş çözümleme",
)
def get_availability(
    metric_key: str = Query(min_length=1),
    academic_year: str = Query(pattern=r"^\d{4}-\d{4}$"),
    scope_type: str = Query(pattern=r"^(university|faculty|department|program)$"),
    faculty_id: Optional[int] = Query(default=None, ge=1),
    department_id: Optional[int] = Query(default=None, ge=1),
    program_id: Optional[int] = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> ManualMetricAvailability:
    return ManualMetricAvailability(
        **service.availability(
            db,
            metric_key=metric_key,
            academic_year=academic_year,
            scope_type=scope_type,
            faculty_id=faculty_id,
            department_id=department_id,
            program_id=program_id,
        )
    )


@router.get(
    "/entries",
    response_model=list[ManualMetricEntryResponse],
    summary="Tam kapsam ve dönem için manuel kayıtlar",
)
def entries(
    academic_year: str = Query(pattern=r"^\d{4}-\d{4}$"),
    scope_type: str = Query(pattern=r"^(university|faculty|department|program)$"),
    faculty_id: Optional[int] = Query(default=None, ge=1),
    department_id: Optional[int] = Query(default=None, ge=1),
    program_id: Optional[int] = Query(default=None, ge=1),
    metric_key: Optional[str] = Query(default=None),
    screen_key: Optional[str] = Query(default=None),
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> list[ManualMetricEntryResponse]:
    return [
        ManualMetricEntryResponse(**row)
        for row in service.list_entries(
            db,
            academic_year=academic_year,
            scope_type=scope_type,
            faculty_id=faculty_id,
            department_id=department_id,
            program_id=program_id,
            metric_key=metric_key,
            screen_key=screen_key,
            include_inactive=include_inactive,
        )
    ]


@router.post(
    "",
    response_model=ManualMetricEntryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Manuel metrik kaydı oluştur",
)
def create(
    payload: ManualMetricCreate,
    x_session_token: Optional[str] = Header(default=None, alias="X-Session-Token"),
    db: Session = Depends(get_db),
) -> ManualMetricEntryResponse:
    return ManualMetricEntryResponse(
        **service.create_entry(db, payload, x_session_token)
    )


@router.put(
    "/{entry_id}",
    response_model=ManualMetricEntryResponse,
    summary="Manuel metrik kaydını düzenle",
)
def update(
    entry_id: int,
    payload: ManualMetricUpdate,
    x_session_token: Optional[str] = Header(default=None, alias="X-Session-Token"),
    db: Session = Depends(get_db),
) -> ManualMetricEntryResponse:
    return ManualMetricEntryResponse(
        **service.update_entry(db, entry_id, payload, x_session_token)
    )


@router.delete("/{entry_id}", summary="Manuel metrik kaydını pasifleştir")
def delete(
    entry_id: int,
    x_session_token: Optional[str] = Header(default=None, alias="X-Session-Token"),
    db: Session = Depends(get_db),
) -> dict:
    return service.delete_entry(db, entry_id, x_session_token)
