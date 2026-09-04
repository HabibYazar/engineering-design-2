"""Pytest ortak yapılandırması ve fixture'ları.

ÖNEMLİ: Testler ASLA gerçek university_management.db dosyasına dokunmaz.
Bu dosya, app.database modülü import edilmeden ÖNCE DATABASE_URL ortam
değişkenini geçici bir dizindeki test veritabanına yönlendirir. Böylece
geliştirme verisi korunur.
"""

import os
import pathlib
import shutil
import tempfile

# --- Test veritabanı yönlendirmesi (import sırasından ÖNCE olmalı) ---
# app.core.config içindeki Settings sınıfı DATABASE_URL'i ortam değişkeninden
# okur. Bu satırlar app.database import edilmeden çalıştığı için engine
# doğrudan test veritabanına bağlanır.
_TEST_DIR: str = tempfile.mkdtemp(prefix="ranking_tests_")
_TEST_DB_PATH: pathlib.Path = pathlib.Path(_TEST_DIR) / "test_university_management.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH}"

from decimal import Decimal  # noqa: E402
from typing import Dict, Iterator  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.database import SessionLocal, init_db  # noqa: E402
from app.models import (  # noqa: E402
    AcademicProgram,
    EvaluationFramework,
    EvaluationIndicator,
    FrameworkAssessment,
)
from main import app  # noqa: E402

# Testlerde kullanılan ortak akademik yıl.
TEST_ACADEMIC_YEAR: str = "2025-2026"
TEST_PERIOD: str = "annual"


def pytest_sessionfinish(session, exitstatus) -> None:
    """Test oturumu bitince geçici veritabanı dizinini temizler."""
    shutil.rmtree(_TEST_DIR, ignore_errors=True)


@pytest.fixture(scope="session", autouse=True)
def seeded_database() -> Iterator[None]:
    """Tüm modüllerin seed verisini izole test veritabanına yükler."""
    init_db()

    # Seed script'leri import edilirken app.database zaten test veritabanına
    # bağlı olduğu için veriler doğru yere yazılır.
    import seed_data
    import seed_ranking_data
    import seed_scenario_data
    import seed_student_data

    seed_data.seed()
    seed_scenario_data.seed()
    seed_student_data.seed()
    seed_ranking_data.seed()

    yield


@pytest.fixture(scope="session")
def client(seeded_database: None) -> Iterator[TestClient]:
    """Uygulama boyunca paylaşılan test istemcisi."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db_session() -> Iterator[Session]:
    """Doğrudan veritabanı erişimi gereken testler için oturum."""
    session: Session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


# Seed verisinin metodoloji yılı. Testlerde oluşturulan geçici çerçeveler
# farklı yıllar kullanır; fixture bu yıla sabitlenerek karışıklık önlenir.
SEED_METHODOLOGY_YEAR: int = 2026


@pytest.fixture(scope="session")
def framework_ids(seeded_database: None) -> Dict[str, int]:
    """Seed'den gelen çerçevelerin kod -> id eşlemesi."""
    session: Session = SessionLocal()
    try:
        return {
            framework.code: framework.id
            for framework in session.execute(
                select(EvaluationFramework).where(
                    EvaluationFramework.methodology_year == SEED_METHODOLOGY_YEAR
                )
            )
            .scalars()
            .all()
        }
    finally:
        session.close()


@pytest.fixture(scope="session")
def indicator_ids(db_session_factory=None) -> Dict[str, int]:
    """Gösterge kodu -> id eşlemesi."""
    session: Session = SessionLocal()
    try:
        return {
            indicator.code: indicator.id
            for indicator in session.execute(select(EvaluationIndicator)).scalars().all()
        }
    finally:
        session.close()


@pytest.fixture(scope="session")
def program_ids() -> Dict[str, int]:
    """Modül 1'den gelen akademik program kodu -> id eşlemesi."""
    session: Session = SessionLocal()
    try:
        return {
            program.code: program.id
            for program in session.execute(select(AcademicProgram)).scalars().all()
        }
    finally:
        session.close()


@pytest.fixture(scope="session")
def the_assessment_id(client: TestClient) -> int:
    """THE çerçevesi için kaydedilmiş bir değerlendirme id'si üretir."""
    response = client.post(
        "/api/ranking-evaluations/assessments/calculate",
        json={"framework_code": "THE", "academic_year": TEST_ACADEMIC_YEAR},
    )
    return response.json()["assessments"][0]["assessment_id"]


@pytest.fixture()
def unique_suffix() -> str:
    """Testler arasında çakışmayan benzersiz bir son ek üretir."""
    # Aynı oturumda çalışan testlerin birbirinin kayıtlarını bozmaması için
    # her çağrıda artan bir sayaç kullanılır.
    global _COUNTER
    _COUNTER += 1
    return f"t{_COUNTER:04d}"


_COUNTER: int = 0


def make_framework_payload(suffix: str, **overrides) -> dict:
    """Test için geçerli bir çerçeve gövdesi üretir."""
    payload = {
        "code": "THE",
        "name": f"Test Framework {suffix}",
        # Seed 2026 kullandığı için testler farklı yıllarla çakışmayı önler.
        "methodology_year": 2050 + (_COUNTER % 40),
        "description": "Test amaçlı çerçeve",
        "is_active": True,
    }
    payload.update(overrides)
    return payload


def make_indicator_payload(dimension_id: int, suffix: str, **overrides) -> dict:
    """Test için geçerli bir gösterge gövdesi üretir."""
    payload = {
        "dimension_id": dimension_id,
        "code": f"test-indicator-{suffix}",
        "name": f"Test Indicator {suffix}",
        "unit": "%",
        "calculation_type": "percentage",
        "weight": "50.00",
        "direction": "higher_is_better",
        "minimum_value": "0",
        "target_value": "50",
        "maximum_value": "100",
        "data_source": "Test birimi",
        "required_for_readiness": True,
        "is_active": True,
    }
    payload.update(overrides)
    return payload


def build_indicator(**overrides) -> EvaluationIndicator:
    """Hesaplama motoru testleri için bellekte gösterge nesnesi üretir.

    Veritabanına eklenmez; normalize_score ve resolve_effective_value saf
    fonksiyonlar olduğu için kalıcı kayda gerek yoktur.
    """
    indicator = EvaluationIndicator(
        id=overrides.pop("id", 1),
        dimension_id=overrides.pop("dimension_id", 1),
        code=overrides.pop("code", "test-indicator"),
        name=overrides.pop("name", "Test Indicator"),
        unit=overrides.pop("unit", None),
        calculation_type=overrides.pop("calculation_type", "raw"),
        weight=overrides.pop("weight", Decimal("100")),
        direction=overrides.pop("direction", "higher_is_better"),
        minimum_value=overrides.pop("minimum_value", None),
        target_value=overrides.pop("target_value", None),
        maximum_value=overrides.pop("maximum_value", None),
        data_source=overrides.pop("data_source", None),
        required_for_readiness=overrides.pop("required_for_readiness", True),
        is_active=overrides.pop("is_active", True),
    )
    for key, value in overrides.items():
        setattr(indicator, key, value)
    return indicator
