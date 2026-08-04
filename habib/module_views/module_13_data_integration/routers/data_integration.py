"""Toplu veri aktarımı (Data Integration) endpoint'leri.

Bu router yalnızca isteği alır, servis katmanını çağırır ve HTTP cevabını üretir.
Dosya okuma, doğrulama ve veritabanı işlemleri app/services altındaki modüllerdedir.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ImportJob
from app.schemas.data_integration import (
    ImportJobResponse,
    ImportResult,
    ResourceType,
)
from app.services.file_parser import FileParseError
from app.services.import_service import (
    build_csv_template,
    get_resource_aliases,
    get_supported_resources,
    run_import,
)
from app.services.crud_helpers import get_object_or_404

router = APIRouter(prefix="/api/data-integration", tags=["Data Integration"])


@router.post(
    "/import/{resource_type}",
    response_model=ImportResult,
    summary="CSV / Excel / JSON dosyasından toplu veri aktarımı",
)
async def import_resource(
    resource_type: ResourceType,
    file: UploadFile = File(..., description="CSV, XLSX veya JSON dosyası"),
    preview: bool = Query(
        default=False,
        description="true ise veritabanına yazılmaz, sadece doğrulama raporu döner",
    ),
    db: Session = Depends(get_db),
) -> ImportResult:
    """Yüklenen dosyayı doğrular ve preview=false ise veritabanına aktarır."""
    # resource_type bir Enum olduğu için geçersiz değerler FastAPI tarafından
    # bu fonksiyona hiç girmeden 422 ile reddedilir.

    # Dosya içeriğini bir kez okuyup byte olarak servise veriyoruz;
    # servis katmanının FastAPI'ye bağımlı olmaması için UploadFile'ı içeri taşımıyoruz.
    content: bytes = await file.read()

    try:
        return run_import(
            db=db,
            resource_type=resource_type.value,
            file_name=file.filename or "unknown",
            content=content,
            preview=preview,
        )
    except FileParseError as error:
        # Servis katmanındaki teknik hatayı burada HTTP cevabına çeviriyoruz.
        # 415: desteklenmeyen biçim, 400: boş/bozuk dosya.
        raise HTTPException(status_code=error.status_code, detail=error.message) from error


@router.get(
    "/templates/{resource_type}",
    response_class=PlainTextResponse,
    summary="Kaynak için boş CSV şablonu indir",
)
def download_template(resource_type: ResourceType) -> PlainTextResponse:
    """İlgili kaynak için beklenen sütun başlıklarını içeren CSV şablonu döndürür."""
    csv_content: str = build_csv_template(resource_type.value)
    file_name: str = f"{resource_type.value}_template.csv"

    # Content-Disposition başlığı tarayıcıya bu cevabı dosya olarak indirmesini söyler.
    return PlainTextResponse(
        content=csv_content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )


@router.get(
    "/jobs",
    response_model=List[ImportJobResponse],
    summary="Geçmiş içe aktarma işlerini listele",
)
def list_import_jobs(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    resource_type: Optional[ResourceType] = Query(default=None),
    preview: Optional[bool] = Query(default=None, description="Sadece ön izlemeler / gerçek aktarımlar"),
    db: Session = Depends(get_db),
) -> List[ImportJob]:
    """İçe aktarma geçmişini en yeniden eskiye doğru listeler."""
    statement = select(ImportJob)

    if resource_type is not None:
        statement = statement.where(ImportJob.resource_type == resource_type.value)
    if preview is not None:
        statement = statement.where(ImportJob.preview == preview)

    # En son yapılan işlem en üstte görünsün diye id'ye göre tersten sıralıyoruz.
    statement = statement.order_by(ImportJob.id.desc()).offset(skip).limit(limit)
    return list(db.execute(statement).scalars().all())


@router.get(
    "/jobs/{job_id}",
    response_model=ImportJobResponse,
    summary="Belirli bir içe aktarma işinin detayı",
)
def get_import_job(job_id: int, db: Session = Depends(get_db)) -> ImportJob:
    """Tek bir içe aktarma işini id ile getirir."""
    return get_object_or_404(db, ImportJob, job_id, "İçe aktarma işi")


@router.get("/resources", summary="Desteklenen kaynak türleri ve dosya biçimleri")
def list_supported_resources() -> dict:
    """Arayüzün seçenekleri dinamik doldurabilmesi için desteklenen değerleri döndürür."""
    # Kanonik isimler listelenir; alt çizgili takma adlar ayrı alanda gösterilir
    # ki seçim listesi aynı kaynağı iki kez göstermesin.
    return {
        "resource_types": get_supported_resources(),
        "aliases": get_resource_aliases(),
        "file_formats": ["csv", "xlsx", "json"],
    }
