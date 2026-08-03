"""Bağımsız demo giriş noktası — Modül 3, 7 ve 11.

Bu klasör tek başına indirilse bile çalışır; ana backend'e hiçbir bağımlılığı yoktur.

Çalıştırma:
    python main.py
    uvicorn main:app --reload

Adres:
    http://127.0.0.1:8000/docs

Uygulama ilk açılışta SQLite veritabanını oluşturur ve boşsa demo verisiyle doldurur.
Veriyi sıfırlamak için `demo.db` dosyasını silmek yeterlidir.
"""

import sys
from contextlib import asynccontextmanager
from pathlib import Path

# "python main.py" ve "uvicorn main:app" çağrılarının ikisinde de modül importlarının
# çalışması için bu klasör arama yoluna eklenir.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import FastAPI  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402

from database import SessionLocal, init_db  # noqa: E402
from module_03_ogrenci_analitigi.routers.student_analytics import (  # noqa: E402
    router as student_analytics_router,
)
from module_07_surdurulebilirlik.routers.sustainability import (  # noqa: E402
    router as sustainability_router,
)
from module_11_erken_uyari.routers.early_warning import (  # noqa: E402
    router as early_warning_router,
)
from seed_data import seed_if_empty  # noqa: E402

@asynccontextmanager
async def lifespan(_: FastAPI):
    """Uygulama açılışında tabloları oluşturur ve veritabanı boşsa demo verisini yükler."""
    init_db()
    db = SessionLocal()
    try:
        result = seed_if_empty(db)
        if result.get("skipped"):
            print("[Bilgi] Veritabaninda veri mevcut, seed atlandi.")
        else:
            print(
                f"[Bilgi] Demo verisi yuklendi: {result['programs']} program, "
                f"{result['students']} ogrenci, {result['snapshots']} yillik kayit, "
                f"{result['academic_records']} akademik kayit."
            )
    finally:
        db.close()
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Stratejik Üniversite Yönetimi ve Karar Destek Sistemi — Modül 3, 7, 11",
    description=(
        "**Modül 3** — Stratejik Eğitim ve Öğrenci Analitiği (PDF Bölüm 3)\n\n"
        "**Modül 7** — Akademik Program Sürdürülebilirlik Analizi (PDF Bölüm 7)\n\n"
        "**Modül 11** — Risk ve Erken Uyarı Sistemi (PDF Bölüm 11)\n\n"
        "Üç modül zincirleme çalışır: Modül 3 göstergeleri üretir, Modül 7 bu "
        "göstergelerden sürdürülebilirlik puanı hesaplar, Modül 11 her ikisini "
        "eşiklerle karşılaştırıp üst yönetime alarm üretir."
    ),
    version="1.0.0",
)

app.include_router(student_analytics_router)
app.include_router(sustainability_router)
app.include_router(early_warning_router)


STATIC_DIR = Path(__file__).resolve().parent / "static"


@app.get("/panel", tags=["Arayüz"], include_in_schema=False)
def panel() -> FileResponse:
    """Modül 3, 7 ve 11 göstergelerini tek panelde döndürür.

    Sayfa tek bir HTML dosyasıdır; veriyi bu servisin kendi endpoint'lerinden
    tarayıcıda çeker. Ayrı bir sunucuya, derleme adımına veya harici bir
    kütüphaneye ihtiyaç duymaz.
    """
    return FileResponse(STATIC_DIR / "panel.html", media_type="text/html")


@app.get("/", tags=["Health"])
def root() -> dict:
    """Servisin ayakta olduğunu bildirir."""
    return {
        "service": "Modül 3-7-11 — Öğrenci Analitiği, Sürdürülebilirlik, Erken Uyarı",
        "status": "calisiyor",
        "panel": "/panel",
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"])
def health() -> dict:
    """Sağlık kontrolü."""
    return {"status": "ok"}


@app.get("/demo-info", tags=["Health"])
def demo_info() -> dict:
    """Demo akışını ve endpoint listesini döndürür."""
    return {
        "demo_akisi": [
            "0. GET /panel — Modül 3 öğrenci analitiği arayüzü",
            "1. GET /health — servis ayakta",
            "2. GET /api/student-analytics/overview — üniversite geneli öğrenci göstergeleri",
            "3. GET /api/student-analytics/programs — program bazlı kırılım (drill-down)",
            "4. GET /api/student-analytics/admission-scores — taban puan / Ankara / Türkiye",
            "5. GET /api/student-analytics/demand-trends — 3 yıllık talep trendi",
            "6. GET /api/program-sustainability/weights — 11 kriter ve ağırlıkları",
            "7. GET /api/program-sustainability/scores — puan + kategori + veri tamlığı",
            "8. GET /api/program-sustainability/categories — kategori dağılımı",
            "9. POST /api/program-sustainability/scores — diğer modüllerin verisi eklenince",
            "10. GET /api/early-warning/alerts — üst yönetime giden alarmlar",
            "11. GET /api/early-warning/summary — alarm özeti",
            "12. GET /api/early-warning/rules/pending — diğer modülleri bekleyen kurallar",
            "13. POST /api/student-analytics/comparative — benzer üniversitelerle karşılaştırma (dış girdi ile)",
        ],
        "moduller": {
            "modul_03": "Stratejik Eğitim ve Öğrenci Analitiği (PDF Bölüm 3)",
            "modul_07": "Akademik Program Sürdürülebilirlik Analizi (PDF Bölüm 7)",
            "modul_11": "Risk ve Erken Uyarı Sistemi (PDF Bölüm 11)",
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
