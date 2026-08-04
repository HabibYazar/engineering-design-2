"""Entegrasyon testleri için pytest yapılandırması.

Neden ayrı bir dizin ve ayrı conftest: bu testler TAM ortak demo veri setine
(4000 öğrenci, 180 personel, 42 mekân, mali dönemler, KPI'lar, kullanıcılar)
ihtiyaç duyar. Bu veriyi tests/ altındaki birim testlerinin veritabanına
yüklemek, orada sayı bekleyen testleri bozardı.

Çalıştırma:
    pytest tests/               -> 412 birim testi (hızlı, modül içi)
    pytest tests_integration/   -> entegrasyon testleri (tam veri seti)
    pytest tests tests_integration  -> hepsi

ÖNEMLİ: Testler ASLA gerçek university_management.db dosyasına dokunmaz;
geçici bir dizindeki izole veritabanı kullanılır.
"""

import os
import pathlib
import shutil
import sys
import tempfile

# --- Test veritabanı yönlendirmesi (app.database import edilmeden ÖNCE) ---
_TEST_DIR: str = tempfile.mkdtemp(prefix="integration_tests_")
_TEST_DB_PATH: pathlib.Path = pathlib.Path(_TEST_DIR) / "test_integration.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH}"

# Seed script'leri ve main.py backend kökünde; import edilebilmesi için yol eklenir.
_BACKEND_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from typing import Iterator  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.database import SessionLocal, init_db  # noqa: E402
from main import app  # noqa: E402


def pytest_sessionfinish(session, exitstatus) -> None:
    """Test oturumu bitince geçici veritabanı dizinini temizler."""
    shutil.rmtree(_TEST_DIR, ignore_errors=True)


@pytest.fixture(scope="session", autouse=True)
def full_demo_database() -> Iterator[None]:
    """Ortak demo veri setinin tamamını izole test veritabanına yükler.

    Üretimde kullanılan seed_all_demo_data.py'nin ta kendisi çağrılır; ayrı bir
    test verisi yazılsaydı "testte çalışıyor ama demoda çalışmıyor" durumu
    ortaya çıkabilirdi.
    """
    init_db()

    import seed_all_demo_data

    seed_all_demo_data.main()
    yield


@pytest.fixture(scope="session")
def client(full_demo_database: None) -> Iterator[TestClient]:
    """Uygulama boyunca paylaşılan test istemcisi."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db_session() -> Iterator[Session]:
    """Doğrudan veritabanı doğrulaması için oturum."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
