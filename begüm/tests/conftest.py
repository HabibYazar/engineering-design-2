"""Modül 3/7/11 testleri için ortak sabitler.

Gerçek `demo.db`'ye dokunulmaz: her test oturumu kendi geçici SQLite dosyasını
kullanır ve `seed_data.py` ile aynı deterministik veri kümesini üretir (sabit
`RANDOM_SEED` sayesinde), böylece testler README'deki bilinen demo rakamlarıyla
(3.124 öğrenci, 27 alarm vb.) karşılaştırılabilir.

`main.app`'in `lifespan`'ı kasıtlı olarak tetiklenmez (TestClient `with` bloğu
içinde KULLANILMAZ); aksi halde açılış rutini gerçek `demo.db`'ye yazardı.
Bunun yerine `get_db` bağımlılığı test veritabanına yönlendirilir.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base, get_db
from seed_data import seed_if_empty


@pytest.fixture(scope="session")
def test_session_factory(tmp_path_factory):
    """Test oturumu boyunca yaşayan, `demo.db`'den bağımsız bir SQLite motoru kurar."""
    from module_03_ogrenci_analitigi import models  # noqa: F401  (Base.metadata'ya kayıt için)

    db_path = tmp_path_factory.mktemp("db") / "test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture(scope="session", autouse=True)
def seeded_data(test_session_factory):
    """Test veritabanını bir kez, `seed_data.py`'nin sabit tohumuyla doldurur."""
    db = test_session_factory()
    try:
        seed_if_empty(db)
    finally:
        db.close()


@pytest.fixture()
def client(test_session_factory):
    """`get_db`'yi test veritabanına yönlendiren, lifespan'ı tetiklemeyen bir TestClient."""
    from main import app

    def override_get_db():
        db = test_session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
