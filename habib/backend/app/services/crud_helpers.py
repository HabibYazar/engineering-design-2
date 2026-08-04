"""Router'ların ortak kullandığı yardımcı CRUD fonksiyonları."""

from typing import Any, Optional, Type, TypeVar

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import Base

# ModelType: Base'den türeyen herhangi bir model anlamına gelir.
# Bu sayede aynı yardımcı fonksiyonlar dört model için de kullanılabiliyor.
ModelType = TypeVar("ModelType", bound=Base)


def get_object_or_404(
    db: Session,
    model: Type[ModelType],
    object_id: int,
    label: str,
) -> ModelType:
    """Verilen id'ye ait kaydı getirir, bulunamazsa 404 hatası fırlatır."""
    # Aynı "bulunamadı" kontrolünü her router'da tekrar yazmamak için ortak fonksiyon.
    obj: Optional[ModelType] = db.get(model, object_id)
    if obj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{label} bulunamadı (id={object_id}).",
        )
    return obj


def ensure_code_is_unique(
    db: Session,
    model: Type[ModelType],
    code: str,
    label: str,
    exclude_id: Optional[int] = None,
) -> None:
    """Aynı code değerine sahip başka bir kayıt varsa 409 hatası fırlatır."""
    # exclude_id, güncelleme sırasında kaydın kendi kodunu çakışma saymamak için kullanılır.
    statement = select(model).where(model.code == code)
    if exclude_id is not None:
        statement = statement.where(model.id != exclude_id)

    existing: Optional[ModelType] = db.execute(statement).scalars().first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"'{code}' kodu zaten başka bir {label} kaydında kullanılıyor.",
        )


def ensure_parent_exists(
    db: Session,
    model: Type[ModelType],
    parent_id: int,
    label: str,
) -> ModelType:
    """Foreign key ile bağlanılacak üst kaydın var olduğunu doğrular."""
    # Örneğin bölüm eklerken gönderilen faculty_id gerçekten var mı diye kontrol eder.
    # Geçersizse veritabanı hatası beklemek yerine anlaşılır bir 404 döndürüyoruz.
    parent: Optional[ModelType] = db.get(model, parent_id)
    if parent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"İlişkili {label} bulunamadı (id={parent_id}).",
        )
    return parent


def apply_updates(obj: Any, update_data: dict) -> None:
    """Güncelleme şemasından gelen alanları model nesnesine aktarır."""
    # Sadece istemcinin gönderdiği alanlar güncellenir; diğerleri olduğu gibi kalır.
    for field, value in update_data.items():
        setattr(obj, field, value)
