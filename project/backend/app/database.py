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


def _add_missing_columns() -> None:
    """Var olan SQLite tablolarına modelde sonradan eklenen sütunları ekler.

    NEDEN GEREKLİ
    -------------
    `create_all` var olan bir tabloyu DEĞİŞTİRMEZ; yalnızca eksik tabloları
    oluşturur. Bir modele yeni sütun eklendiğinde, kullanıcının elindeki
    veritabanı dosyası eski şemada kalır ve ilk sorguda "no such column"
    hatası verir. Projede migration aracı yok; bu küçük denetim, kullanıcının
    veritabanını silmek zorunda kalmasını önlüyor.

    Yalnızca EKLEME yapar: sütun siler, tür değiştirir veya veri taşımaz.
    Bu yüzden idempotenttir ve her açılışta güvenle çağrılabilir.
    """
    if not settings.DATABASE_URL.startswith("sqlite"):
        return

    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as connection:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue  # create_all zaten oluşturdu
            present = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in present:
                    continue
                if column.server_default is None and not column.nullable:
                    # Varsayılanı olmayan zorunlu sütun sonradan eklenemez;
                    # sessizce atlanır ve sorun görünür kalır.
                    continue
                default = ""
                if column.server_default is not None:
                    default = f" DEFAULT {column.server_default.arg}"
                nullable = "" if column.nullable else " NOT NULL"
                connection.execute(
                    text(
                        f"ALTER TABLE {table.name} "
                        f"ADD COLUMN {column.name} "
                        f"{column.type.compile(engine.dialect)}{default}{nullable}"
                    )
                )


def init_db() -> None:
    """Tanımlı modellere göre veritabanı tablolarını oluşturur."""
    # Modelleri burada import etmemizin sebebi: create_all sadece Base'e kayıtlı
    # tabloları oluşturur, bir model hiç import edilmezse SQLAlchemy onu görmez.
    # Import fonksiyon içinde yapıldı ki modeller ile database.py arasında döngüsel import olmasın.
    import app.models  # noqa: F401

    # create_all zaten var olan tabloları tekrar oluşturmaz, bu yüzden her açılışta çağrılabilir.
    Base.metadata.create_all(bind=engine)
    _add_missing_columns()
