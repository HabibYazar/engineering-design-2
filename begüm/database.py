"""Bağımsız demo için ortak veritabanı katmanı (SQLite).

Ana projede bu dosyanın karşılığı `app.database`'dir. Bu klasör tek başına
indirilip çalıştırılabilsin diye burada yerel bir kopya tutuluyor; tablo ve
kolon adları ana projedekiyle birebir aynıdır, dolayısıyla entegrasyon
aşamasında modeller olduğu gibi taşınabilir.
"""

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

BASE_DIR = Path(__file__).resolve().parent
DATABASE_URL = f"sqlite:///{BASE_DIR / 'demo.db'}"

# check_same_thread=False: FastAPI istekleri farklı thread'lerde çalışabildiği için
# SQLite'ın varsayılan tek-thread kısıtı gevşetiliyor.
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Tüm ORM modellerinin türetildiği taban sınıf."""


def get_db() -> Iterator[Session]:
    """FastAPI bağımlılığı — istek başına bir oturum açar ve sonunda kapatır."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Modelleri kaydedip eksik tabloları oluşturur."""
    # Import, tabloların Base.metadata'ya kaydolması için gereklidir.
    from module_03_ogrenci_analitigi import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
