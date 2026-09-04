"""Uygulamanın giriş noktası: FastAPI nesnesinin oluşturulduğu dosya."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Dict

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.database import init_db
from app.routers import (
    academic_staff,
    academic_success,
    assistant,
    administrative_units,
    auth,
    data_integration,
    data_sources,
    departments,
    early_warning,
    education_analytics,
    engagement,
    faculties,
    finance,
    curriculum,
    decision_analytics,
    health,
    kpi,
    physical_resources,
    programs,
    ranking_evaluations,
    reference,
    scenarios,
    student_analytics,
    students,
    sustainability,
    tuition,
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
# Arayüzün ortak kullandığı Türkçe ad sözlüğü.
app.include_router(reference.router)

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

# Modül 6 - Stratejik Finansal Analiz (Halil)
app.include_router(finance.router)

# Modül 8 - Kurumsal Performans Yönetimi ve İzleme (Halil)
app.include_router(kpi.router)

# Yetkili tabloları değiştirmeyen, dosya tabanlı ikincil veri kaynakları.
app.include_router(data_sources.router)

# Akademik Başarı Analizi
# Üniversite -> fakülte -> bölüm -> program kırılımında ders geçme,
# başarısızlık, bırakma ve mezuniyet oranları.
app.include_router(academic_success.router)

# Üniversite-Sanayi İş Birliği ve Bölgesel Katkı
# Bu iki gösterge önceden elle girilen tek bir puandı; artık ölçülebilir
# alt bileşenlerden formülle hesaplanıyor.
app.include_router(engagement.router)

# Akıllı Asistan altyapısı.
# NOT: Bu router hiçbir dil modeline bağlı DEĞİLDİR ve cevap üretmez.
# Yalnızca bir soru için gereken kurumsal veriyi toplar ve altyapının
# durumunu bildirir. Ayrıntı: docs/ASSISTANT_ARCHITECTURE.md
app.include_router(assistant.router)

# Müfredat kataloğu ve akademisyen ders kayıtları (gerçek veri).
app.include_router(curriculum.router)
# Karar destek göstergeleri — yalnızca dolu tablolardan türetilir.
app.include_router(decision_analytics.router)
app.include_router(tuition.router)


@app.get("/api", include_in_schema=False)
def api_root() -> Dict[str, Any]:
    """Backend'in çalıştığını doğrulayan karşılama mesajı döndürür."""
    return {
        "message": "Backend is running",
        "application": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs_url": "/docs",
        "ui_url": "/",
    }


# --------------------------------------------------------------------------
# Web arayüzü
# --------------------------------------------------------------------------
# Arayüz backend ile aynı sunucudan servis edilir. Ayrı bir web sunucusu
# gerekmediği için CORS yapılandırmasına da ihtiyaç kalmıyor ve tek komutla
# çalışan bir demo elde ediliyor.
#
# Mount en sona konuldu: StaticFiles kök yolu ("/") kapsadığı için daha önce
# bağlanırsa /api ve /docs isteklerini de yakalar ve 404 döndürürdü.
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

class TazeHTML(StaticFiles):
    """HTML'i ASLA önbellekten servis ettirmez; sürümlü varlıklar kalır.

    NEDEN GEREKTİ
    -------------
    `index.html` betikleri `?v=` ile sürümler:

        <script src="assets/kabuk.js?v=121"></script>

    Bu desenin çalışması HTML'in TAZE olmasına bağlıdır. Ama
    `StaticFiles` yalnızca `etag`/`last-modified` gönderiyor,
    `Cache-Control` göndermiyordu; tarayıcı `index.html`i kendi
    önbelleğinden okuyup İÇİNDEKİ ESKİ SÜRÜM NUMARASIYLA eski betiği
    çekiyordu.

    Görünen sonuç: sunucudaki dosya güncellenmiş, sürüm artırılmış,
    ama ekran değişmiyor. Kenar çubuğu sadeleştirmesi tam olarak bu
    yüzden kullanıcıya ulaşmadı — dosya doğruydu, teslimat değildi.
    Ctrl+F5 sorunu geçici olarak çözer; bu başlık kalıcı çözer.

    Sürümlü varlıklara (`?v=`) dokunulmaz: onların önbelleğe alınması
    zaten istenen davranıştır ve sürüm değişince URL de değişir.
    """

    async def get_response(self, path: str, scope):  # type: ignore[override]
        yanit = await super().get_response(path, scope)
        if path.endswith((".html", "/")) or path in ("", "."):
            yanit.headers["Cache-Control"] = "no-cache, must-revalidate"
        return yanit


if FRONTEND_DIR.is_dir():
    app.mount(
        "/",
        TazeHTML(directory=str(FRONTEND_DIR), html=True),
        name="frontend",
    )
else:
    # Arayüz klasörü yoksa uygulama yine de çalışmalı; sessizce kaybolmak
    # yerine kök adreste durumu açıklıyoruz.
    @app.get("/", include_in_schema=False)
    def missing_frontend() -> Dict[str, Any]:
        """Arayüz klasörü bulunamadığında bilgilendirme döndürür."""
        return {
            "message": "Backend calisiyor ancak arayuz klasoru bulunamadi.",
            "expected_path": str(FRONTEND_DIR),
            "docs_url": "/docs",
        }
