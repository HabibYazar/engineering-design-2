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

    # ----------------------------------------------------------------------
    # Akıllı asistan — yerel dil modeli (Ollama)
    # ----------------------------------------------------------------------
    # Model YEREL çalışır. Hiçbir internet servisine (OpenAI, Gemini, Claude)
    # istek gönderilmez. Adres varsayılan olarak 127.0.0.1'dir; dışarıya açık
    # bir adres yazılırsa veri kurum dışına çıkar.
    #
    # Bu değerler yalnızca burada tanımlıdır. Provider, servis ve router
    # katmanları settings üzerinden okur; hiçbir dosyada tekrar gömülmez.
    ASSISTANT_ENABLED: bool = True
    LLM_PROVIDER: str = "ollama"

    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434"
    OLLAMA_MODEL: str = "qwen3.5:9b"
    # Yerel modelde ilk üretim yavaş olabilir (model belleğe yüklenir).
    OLLAMA_TIMEOUT_SECONDS: int = 120
    OLLAMA_CONTEXT_LENGTH: int = 8192
    # Düşük sıcaklık: yönetim raporlarında yaratıcılık değil tutarlılık isteniyor.
    OLLAMA_TEMPERATURE: float = 0.2

    # Kullanıcı mesajı sınırları. Üst sınır olmadan tek bir istek modelin
    # bağlam penceresini doldurup sunucuyu dakikalarca meşgul edebilir.
    ASSISTANT_MAX_MESSAGE_LENGTH: int = 4000
    # Bellekte tutulacak en fazla konuşma sayısı ve konuşma başına mesaj sayısı.
    ASSISTANT_MAX_CONVERSATIONS: int = 100
    ASSISTANT_MAX_HISTORY_MESSAGES: int = 20

    # .env dosyası varsa ayarlar oradan okunur; bu sayede gizli bilgiler koda yazılmaz.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


# Ayar nesnesini bir kez oluşturup her yerde aynı örneği kullanıyoruz.
settings: Settings = Settings()
