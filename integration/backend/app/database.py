"""SQLAlchemy veritabanı bağlantısı ve oturum yönetimi."""

from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

# SQLite, varsayılan olarak bağlantının sadece onu açan thread'de kullanılmasına izin verir.
# FastAPI istekleri farklı thread'lerde çalışabildiği için bu kontrolü kapatıyoruz.
connect_args: dict = (
    {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
)

# engine: Veritabanına giden asıl bağlantıyı yöneten nesne. Uygulama boyunca tek bir tane olur.
engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)

# SessionLocal: Her istek için yeni bir veritabanı oturumu üretmemizi sağlayan fabrika.
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    """Tüm veritabanı modellerinin türeyeceği temel sınıf."""

    # İleride yazılacak modeller bu sınıftan miras alacak.
    # SQLAlchemy tabloları bu ortak taban üzerinden tanıyıp oluşturuyor.
    pass


def get_db() -> Generator[Session, None, None]:
    """İstek başına veritabanı oturumu açar ve iş bitince kapatır."""
    # FastAPI'nin Depends yapısı ile kullanılır.
    # try/finally sayesinde hata olsa bile bağlantı açık kalmaz.
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Tanımlı modellere göre veritabanı tablolarını oluşturur."""
    # Modelleri burada import etmemizin sebebi: create_all sadece Base'e kayıtlı
    # tabloları oluşturur, bir model hiç import edilmezse SQLAlchemy onu görmez.
    # Import fonksiyon içinde yapıldı ki modeller ile database.py arasında döngüsel import olmasın.
    import app.models  # noqa: F401

    # create_all zaten var olan tabloları tekrar oluşturmaz, bu yüzden her açılışta çağrılabilir.
    Base.metadata.create_all(bind=engine)
