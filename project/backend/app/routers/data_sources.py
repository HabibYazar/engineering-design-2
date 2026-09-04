"""Kullanıcı dosyaları için aşamalı veri kaynağı API'si."""

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Header, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.data_sources import SourceImportRequest, SourceSelection, SourceValidationRequest
from app.services import data_source_service as service
from app.services.manual_metric_registry import list_definitions


router = APIRouter(prefix="/api/data-sources", tags=["Yüklenen Veri Kaynakları"])


@router.get("/definitions")
def definitions(screen_key: Optional[str] = None, scope_type: Optional[str] = None) -> list[dict]:
    return [item.public_dict() for item in list_definitions(screen_key=screen_key, scope_type=scope_type)]


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload(
    file: UploadFile = File(...),
    scope_type: str = Form(pattern=r"^(university|faculty|department|program)$"),
    faculty_id: Optional[int] = Form(default=None),
    department_id: Optional[int] = Form(default=None),
    program_id: Optional[int] = Form(default=None),
    academic_year: Optional[str] = Form(default=None),
    notes: Optional[str] = Form(default=None),
    x_session_token: Optional[str] = Header(default=None, alias="X-Session-Token"),
    db: Session = Depends(get_db),
) -> dict:
    content = await file.read(service.MAX_UPLOAD_BYTES + 1)
    source = service.create_source(
        db, original_filename=file.filename or "upload", content=content,
        scope_type=scope_type, faculty_id=faculty_id, department_id=department_id,
        program_id=program_id, academic_year=academic_year, notes=notes,
        session_token=x_session_token,
    )
    return service.source_to_dict(source)


@router.post("/{source_id}/inspect")
def inspect(source_id: int, payload: SourceSelection, db: Session = Depends(get_db)) -> dict:
    return service.inspect_source(db, source_id, payload.selected_sheet, payload.selected_table)


@router.post("/{source_id}/validate")
def validate(source_id: int, payload: SourceValidationRequest, db: Session = Depends(get_db)) -> dict:
    return service.validate_source(db, source_id, payload.mapping, payload.selected_sheet, payload.selected_table)


@router.post("/{source_id}/import")
def import_data(
    source_id: int, payload: SourceImportRequest,
    x_session_token: Optional[str] = Header(default=None, alias="X-Session-Token"),
    db: Session = Depends(get_db),
) -> dict:
    return service.import_source(
        db, source_id, payload.mapping, payload.selected_sheet, payload.selected_table,
        payload.confirm, x_session_token,
    )


@router.get("/availability")
def get_availability(
    metric_key: str, academic_year: str = Query(pattern=r"^\d{4}-\d{4}$"),
    scope_type: str = Query(pattern=r"^(university|faculty|department|program)$"),
    faculty_id: Optional[int] = Query(default=None, ge=1),
    department_id: Optional[int] = Query(default=None, ge=1),
    program_id: Optional[int] = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> dict:
    return service.availability(
        db, metric_key=metric_key, academic_year=academic_year, scope_type=scope_type,
        faculty_id=faculty_id, department_id=department_id, program_id=program_id,
    )


@router.get("")
def list_all(include_deleted: bool = Query(default=False), db: Session = Depends(get_db)) -> list[dict]:
    return service.list_sources(db, include_deleted=include_deleted)


@router.get("/{source_id}")
def detail(source_id: int, db: Session = Depends(get_db)) -> dict:
    return service.source_to_dict(service.get_source(db, source_id), include_validation=True)


@router.delete("/{source_id}")
def delete(
    source_id: int,
    x_session_token: Optional[str] = Header(default=None, alias="X-Session-Token"),
    db: Session = Depends(get_db),
) -> dict:
    return service.delete_source(db, source_id, x_session_token)
