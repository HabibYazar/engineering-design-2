"""Uygulama ayarlarının tek merkezden yönetildiği modül."""

from pydantic import field_validator
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

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def _bos_veritabani_varsayilana_dusur(cls, v):
        """BOŞ bir DATABASE_URL varsayılanı EZMEMELİ.

        `.env` dosyalarında "DATABASE_URL=" satırı, değeri boş METİN yapar
        ve pydantic bunu geçerli bir değer sayıp varsayılanın üstüne
        yazar. Sonuç, uygulamanın açılışta "Could not parse SQLAlchemy
        URL" ile düşmesidir — üstelik hata mesajı sebebi söylemez.

        Şablonun kendisi "boş bırakırsanız SQLite kullanılır" diyordu;
        bu doğrulayıcı o vaadi gerçek yapar.
        """
        if v is None or (isinstance(v, str) and not v.strip()):
            return "sqlite:///./university_management.db"
        return v

    # ----------------------------------------------------------------------
    # Akıllı asistan — Gemini (tek sağlayıcı)
    # ----------------------------------------------------------------------
    # Yerel Ollama ve Groq kaldırıldı. Tanınmayan bir sağlayıcı adı
    # yazılırsa sistem sessizce başkasına düşmez, açıkça "sağlayıcı yok"
    # durumuna geçer.
    #
    # TAKAS AÇIKÇA KAYDEDİLİR: sorular ve onlara eşlik eden kurum verisi
    # Google'ın sunucularına gider.
    ASSISTANT_ENABLED: bool = True
    LLM_PROVIDER: str = "gemini"

    # Anahtar KODA YAZILMAZ; .env dosyasından okunur ve .env Git'e girmez.
    GEMINI_API_KEY: str = ""
    # OpenAI UYUMLU uç. Projenin araç katmanı bu sözleşmeye göre yazılı;
    # Google'ın kendi `generateContent` şeması araç döngüsünün baştan
    # yazılmasını gerektirirdi.
    GEMINI_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    # Bu ad bir TERCİHTİR: hesapta yoksa sağlayıcı tanınan bir modele
    # düşer (`gemini_modelleri.py` hesabın listesini gösterir).
    GEMINI_MODEL: str = "gemini-3-flash-preview"
    # Tek HTTP isteğinin sınırı. Turun tamamı ayrıca
    # chat_service.MAX_USER_TURN_SECONDS ile sınırlıdır.
    #
    # 25 → 120. Bu değer pratikte her çağrıda `chat_service` tarafından
    # o turun kalan bütçesiyle EZİLİR; yine de tabanın tur sınırından
    # düşük kalması, ezme mantığı bir gün kaldırılırsa sessiz bir üst
    # sınır bırakırdı. Tur sınırıyla hizalandı.
    GEMINI_TIMEOUT_SECONDS: int = 120
    # Sıcaklık 0: hesabı araçlar yapıyor, modelin işi sonucu aktarmak.
    GEMINI_TEMPERATURE: float = 0.0
    # Gemini 3 bir DÜŞÜNME modeli: düşünme adımları da bu bütçeden
    # harcanır. 4096 uzun konuşmalarda modelin cevabı yazmadan bütçeyi
    # bitirmesine yol açıyordu (finish_reason="length", boş içerik).
    # KONTROLLÜ ARTIŞ: 8192 → 12288.
    # Karmaşık sorularda (çok metrikli karşılaştırma, grafik, eğilim)
    # cevap uzuyor ve düşünme adımları da AYNI bütçeden harcanıyor.
    # 8.192'de model bazen cevabı yazmadan sınıra dayanıyordu
    # (finish_reason="length", boş içerik). Artış yalnızca ÜST SINIRDIR:
    # model daha az token yazarsa daha az harcanır, dolayısıyla tipik
    # gecikmeyi artırmaz. Zaman aşımı ve retry zinciri değişmedi.
    GEMINI_MAX_TOKENS: int = 12288

    # DÜŞÜNME SEVİYESİ — ÖLÇÜLEN GECİKMENİN ASIL SEBEBİ.
    # ------------------------------------------------------------------
    # Bu ayar EKSİKTİ: istek gövdesinde `reasoning_effort` hiç
    # gönderilmiyordu. Google'ın OpenAI uyumluluk sözleşmesine göre
    # (ai.google.dev/gemini-api/docs/openai) parametre verilmezse model
    # KENDİ VARSAYILAN seviyesini kullanır ve `medium`, Gemini 2.5
    # karşılığıyla 8.192 tokenlık bir düşünme bütçesine denk gelir.
    #
    # Bunun anlamı şuydu: GEMINI_MAX_TOKENS de 8.192. Yani model, tek
    # bir turda bütün üretim bütçesini DÜŞÜNMEYE harcayıp cevabı hiç
    # yazmadan sınıra dayanabiliyordu. Gözlenen tablo tam olarak buydu —
    # "ROUND 3 TIMEOUT duration=40.4", model 40 saniye boyunca cevap
    # yazmıyor. Yukarıdaki GEMINI_MAX_TOKENS yorumu aynı olayın daha
    # önce 4096'da yaşandığını zaten kaydetmiş; o zaman bütçe
    # büyütülerek yamanmış, sebep bulunmamıştı.
    #
    # "low" seçildi: Gemini 3 için düşünme KAPATILAMAZ (sözleşme bunu
    # açıkça söyler), ama seviye düşürülebilir. Bu kokpitte hesabı
    # araçlar yapıyor; modelin işi sonucu aktarmak. Uzun iç muhakeme
    # kaliteyi artırmıyor, cevabın yerini yiyor.
    #
    # Geçerli değerler: "minimal" | "low" | "medium" | "high".
    # Boş bırakılırsa parametre gönderilmez (modelin varsayılanı).
    GEMINI_REASONING_EFFORT: str = "low"

    # MERKEZİ VERİ TABANI — `abu_kds.db` (SALT OKUNUR).
    # ------------------------------------------------------------------
    # Ekip 24 Excel + 9 CSV + 3 PDF + 2 metin belgesini tek bir SQLite
    # dosyasında birleştirdi: 62 tablo, 36.020 satır. Asistanın kurumsal
    # soruları bu dosyadan cevaplanır.
    #
    # Yol PROJEYE GÖREDİR; kullanıcıya özgü mutlak yol yazılmaz. Boş
    # bırakılırsa `integration/data/abu_kds/abu_kds.db` aranır. .env ile
    # başka bir konum verilebilir (örneğin ortak bir ağ sürücüsü).
    #
    # Dosya HİÇBİR KOŞULDA yazılmaz: bağlantı `mode=ro` ile açılır,
    # migration/seed/INSERT/UPDATE yapılmaz.
    ABU_KDS_DB_PATH: str = ""

    # KOTA DOLDUĞUNDA DENENECEK ALTERNATİF BULUT MODELLERİ.
    # ------------------------------------------------------------------
    # Virgülle ayrılmış Gemini model adları. Birincil model günlük ya da
    # dakikalık kotaya takıldığında sırayla denenir.
    #
    # BUNLAR YALNIZCA BULUT GEMINI MODELLERİDİR. Projede yerel model
    # yoktur; Ollama ve yerel çıkarım kaldırıldı ve geri getirilmez.
    # Kota, ağ üstündeki bir sınırdır — yerel bir modele düşmek başka
    # bir sistemin cevabını Gemini cevabı gibi göstermek olurdu.
    #
    # Boş bırakılırsa alternatif denenmez; sistem doğrudan eldeki
    # yapılandırılmış veriden deterministik cevaba geçer.
    GEMINI_FALLBACK_MODELS: str = ""

    # Bir soru için sağlayıcıya gönderilebilecek TOPLAM istem tokenı
    # (tüm araç turlarının toplamı). Sınıra yaklaşınca asistan araç
    # sunmayı bırakır ve elindeki veriyle cevabı yazar.
    #
    # 3.000 idi; o değer Groq'un 8.000 TPM sınırı için ölçülmüştü.
    # Gemini'de darboğaz token değil İSTEK sayısı (dakikada 5), ama
    # 3.000 tavanı sabit yükün (yönerge + araç şemaları ≈ 3.200) hemen
    # ardından araçları kapatıyor ve İKİNCİ araç turunu imkânsız
    # kılıyordu — grafik çizdirmek tam olarak ikinci turu gerektirir.
    ASSISTANT_MAX_PROMPT_TOKENS: int = 30000

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
