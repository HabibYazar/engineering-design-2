"""Birinci hafta demosu için alternatif FastAPI giriş noktası.

Bu dosya main.py'nin YERİNE GEÇMEZ; onun yanında bağımsız bir giriş noktasıdır.
main.py, app/ paketi, tests/, sample_data/ ve mevcut seed dosyaları değiştirilmemiştir.
Buradaki uygulama mevcut model, şema, router ve servis dosyalarını doğrudan kullanır;
hiçbir kod kopyalanmamıştır.

Etkinleştirilen bileşenler:
    Modül 1  - health, faculties, departments, programs, administrative_units
    Modül 13 - data_integration

Diğer modüllerin (2, 9, 10) router'ları bilinçli olarak BAĞLANMAZ; bu yüzden
/docs ve /openapi.json çıktısında görünmezler.

Çalıştırma:
    uvicorn demo_week1:app --reload
"""

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, List

from fastapi import FastAPI
from sqlalchemy import inspect

from app.database import engine, init_db

# Router'lar mevcut paketten doğrudan alınır; yeniden yazılmaz.
from app.routers import (
    administrative_units,
    data_integration,
    departments,
    faculties,
    health,
    programs,
)

# Demo akışının çalışması için veritabanında bulunması gereken tablolar.
# Modül 1'in dört kaynağı ve Modül 13'ün içe aktarma geçmişi.
REQUIRED_TABLES: List[str] = [
    "faculties",
    "departments",
    "academic_programs",
    "administrative_units",
    "import_jobs",
]


def verify_demo_tables() -> Dict[str, bool]:
    """Demo için gereken tabloların oluştuğunu doğrular.

    init_db() projedeki tüm tabloları oluşturur (main.py ile aynı davranış).
    Bu fonksiyon yalnızca DEMO için gerekli olanların gerçekten hazır olduğunu
    kontrol eder; biri eksikse demo sırasında anlaşılmaz bir hata almak yerine
    açılışta net bir mesaj alınır.
    """
    existing = set(inspect(engine).get_table_names())
    return {table: table in existing for table in REQUIRED_TABLES}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Uygulama açılırken veritabanını hazırlar ve demo tablolarını doğrular."""
    # Veritabanı başlatma yöntemi main.py ile birebir aynıdır.
    init_db()

    status = verify_demo_tables()
    missing = [table for table, exists in status.items() if not exists]
    if missing:
        raise RuntimeError(
            "Demo için gereken tablolar oluşturulamadı: " + ", ".join(missing)
        )

    print("[week1-demo] Veritabani hazir. Demo tablolari dogrulandi:")
    for table in REQUIRED_TABLES:
        print(f"[week1-demo]   - {table}: OK")

    yield
    # Kapanışta özel bir temizlik gerekmiyor.


app = FastAPI(
    title="Week 1 Demo - Core Data and Data Integration",
    description=(
        "Engineering Design 2 first-week demonstration covering Module 1 and Module 13."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# --- Modül 1: Üniversite yapısı ve temel veri yönetimi ---
app.include_router(health.router)
app.include_router(faculties.router)
app.include_router(departments.router)
app.include_router(programs.router)
app.include_router(administrative_units.router)

# --- Modül 13: Veri entegrasyonu (CSV / XLSX / JSON) ---
app.include_router(data_integration.router)

# NOT: Modül 2 (students, student_analytics), Modül 9 (scenarios) ve
# Modül 10 (ranking_evaluations) router'ları bu demoda BAĞLANMAZ.


@app.get("/", tags=["Health"])
def read_root() -> Dict[str, Any]:
    """Demo uygulamasının çalıştığını ve hangi modülleri kapsadığını bildirir."""
    return {
        "message": "Week 1 demo is running",
        "application": app.title,
        "version": app.version,
        "enabled_modules": [
            "Module 1 - University Structure and Core Data Management",
            "Module 13 - Data Integration",
        ],
        "disabled_modules": [
            "Module 2 - Strategic Education and Student Analytics",
            "Module 9 - What-if Scenario Analysis",
            "Module 10 - THE, QS and YOK Evaluation and Monitoring Management",
        ],
        "docs_url": "/docs",
        "openapi_url": "/openapi.json",
    }


@app.get("/demo-info", tags=["Health"])
def demo_info() -> Dict[str, Any]:
    """Demo kapsamındaki endpoint'leri ve örnek dosyaları listeler."""
    # Sunum sırasında hangi adımın hangi dosyayı kullandığını hatırlatmak için.
    return {
        "module_1_resources": [
            "/api/faculties",
            "/api/departments",
            "/api/programs",
            "/api/administrative-units",
        ],
        "module_13_endpoints": [
            "/api/data-integration/import/{resource_type}",
            "/api/data-integration/templates/{resource_type}",
            "/api/data-integration/jobs",
            "/api/data-integration/resources",
        ],
        "demo_sample_files": {
            "faculties": "sample_data/faculties_sample.csv",
            "faculties_xlsx": "sample_data/faculties_sample.xlsx",
            "departments": "sample_data/departments_sample.csv",
            "programs": "sample_data/programs_sample.csv",
            "administrative_units": "sample_data/administrative_units_sample.csv",
            "error_demo": "sample_data/faculties_with_errors_sample.csv",
        },
        "required_tables": verify_demo_tables(),
    }
