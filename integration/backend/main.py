"""Uygulamanın giriş noktası: FastAPI nesnesinin oluşturulduğu dosya."""

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict

from fastapi import FastAPI

from app.core.config import settings
from app.database import init_db
from app.routers import (
    academic_staff,
    administrative_units,
    auth,
    data_integration,
    departments,
    early_warning,
    education_analytics,
    faculties,
    health,
    physical_resources,
    programs,
    ranking_evaluations,
    scenarios,
    student_analytics,
    students,
    sustainability,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Uygulama açılırken ve kapanırken çalışacak işlemleri yönetir."""
    # Sunucu başlarken veritabanı dosyasını ve tabloları hazırlıyoruz.
    # Böylece ilk istek geldiğinde veritabanı kullanıma hazır oluyor.
    init_db()
    yield
    # Kapanışta özel bir temizlik gerekmiyor; ileride gerekirse buraya eklenebilir.


# FastAPI uygulaması: title ve version değerleri otomatik dokümantasyonda (/docs) görünür.
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Üniversite yönetimi ve karar destek sistemi için geliştirilen backend API.",
    lifespan=lifespan,
)

# Router'ları uygulamaya bağlıyoruz.
# Sağlık kontrolü kök seviyede (/health), modül endpoint'leri ise /api altında toplandı.
app.include_router(health.router)

# Modül 1 - University Structure and Core Data Management
app.include_router(faculties.router)
app.include_router(departments.router)
app.include_router(programs.router)
app.include_router(administrative_units.router)

# Modül 13 - Data Integration (CSV / Excel / JSON toplu veri aktarımı)
app.include_router(data_integration.router)

# Modül 9 - What-if Scenario Analysis (senaryo simülasyonu ve karar desteği)
app.include_router(scenarios.router)

# Modül 2 - Strategic Education and Student Analytics (öğrenci analitiği)
app.include_router(students.router)
app.include_router(student_analytics.router)

# Modül 10 - THE, QS ve YÖK Değerlendirme ve İzleme Yönetimi
# NOT: Bu modül gerçek THE/QS/YÖK sıralaması üretmez; iç performans izleme,
# veri hazırlık ve uyum göstergeleri hesaplar.
app.include_router(ranking_evaluations.router)

# Modül 3 - Öğrenci Analitiği (Begüm)
# NOT: Prefix entegrasyonda /api/student-analytics -> /api/education-analytics olarak
# değiştirildi. Sebep: Modül 2 aynı prefix'i farklı response modelleriyle kullanıyordu;
# iki router aynı yolu paylaşsaydı ikinci kayıt sessizce gölgede kalırdı.
app.include_router(education_analytics.router)

# Modül 7 - Program Sürdürülebilirliği (Begüm)
app.include_router(sustainability.router)

# Modül 11 - Erken Uyarı Sistemi (Begüm)
app.include_router(early_warning.router)

# Modül 4 - Akademik Personel Performansı (Eda)
app.include_router(academic_staff.router)

# Modül 5 - Fiziksel Kaynak ve Kapasite Yönetimi (Eda)
# NOT: Orijinal kodda /capacity iki ayrı router'da tanımlıydı ve biri
# gölgede kalıyordu; entegrasyonda tek router'da toplandı.
app.include_router(physical_resources.router)

# Modül 14 - Kullanıcı Yönetimi ve Yetkilendirme (Eda)
app.include_router(auth.router)


@app.get("/")
def read_root() -> Dict[str, Any]:
    """Backend'in çalıştığını doğrulayan karşılama mesajı döndürür."""
    # Tarayıcıdan hızlıca kontrol edebilmek için basit bir kök endpoint.
    return {
        "message": "Backend is running",
        "application": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs_url": "/docs",
    }
