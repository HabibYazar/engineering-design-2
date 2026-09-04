"""Sistem sağlık kontrolü (health check) endpoint'i."""

from typing import Any, Dict

from fastapi import APIRouter

from app.core.config import settings

# APIRouter, endpoint'leri konu bazında gruplamamızı sağlar.
# tags değeri Swagger arayüzünde başlık olarak görünür.
router = APIRouter(tags=["Health"])


@router.get("/health")
def health_check() -> Dict[str, Any]:
    """Backend'in ayakta olduğunu bildiren sağlık durumu bilgisi döndürür."""
    # Bu endpoint genelde sunucu/izleme araçları tarafından düzenli olarak çağrılır.
    # Cevap dönüyorsa uygulamanın çalıştığı anlaşılır.
    return {
        "status": "healthy",
        "application": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "database": "sqlite",
    }
