"""Uygulama ayarlarının tek merkezden yönetildiği modül."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Uygulamanın tüm yapılandırma değerlerini tutan ayar sınıfı."""

    # Ayarları kod içine dağıtmak yerine burada topluyoruz.
    # Böylece veritabanı adresi veya proje adı değişince tek dosyayı düzenlemek yeterli oluyor.
    APP_NAME: str = "Strategic University Management and Decision Support System"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True

    # Geliştirme aşamasında ayrı bir veritabanı sunucusu kurmaya gerek kalmasın diye SQLite kullanıyoruz.
    # Dosya adı sabit tutuldu; ileride PostgreSQL'e geçilirse sadece bu satır değişecek.
    DATABASE_URL: str = "sqlite:///./university_management.db"

    # .env dosyası varsa ayarlar oradan okunur; bu sayede gizli bilgiler koda yazılmaz.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


# Ayar nesnesini bir kez oluşturup her yerde aynı örneği kullanıyoruz.
settings: Settings = Settings()
