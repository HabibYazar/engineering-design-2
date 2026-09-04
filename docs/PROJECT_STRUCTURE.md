# Proje Yapısı

## Backend — `project/backend/`

FastAPI uygulaması. Giriş noktası `main.py`; hem API'yi sunar hem de
`frontend/` klasörünü statik olarak yayınlar.

```
backend/
├── main.py                   uygulama girişi, router bağlama, statik dosyalar
├── requirements.txt          Python bağımlılıkları
├── .env.example              ortam değişkeni şablonu (gerçek anahtar YOK)
├── university_management.db  AKTİF VERİTABANI (SQLite)
├── app/
│   ├── models/               SQLAlchemy tabloları
│   ├── schemas/              Pydantic v2 şemaları
│   ├── routers/              HTTP uç noktaları
│   ├── services/             iş mantığı ve hesaplamalar
│   │   └── assistant/        Yapay Zeka Kokpiti (aşağıda)
│   ├── core/                 yapılandırma
│   └── database.py           oturum yönetimi
├── tests/                    birim testleri
├── tests_integration/        uçtan uca testler
├── import_*.py               tek seferlik veri aktarım betikleri
├── build_*.py                türetilmiş dosya üreticileri
└── seed_*.py                 örnek/demo veri yükleyicileri
```

Aktarım (`import_*`) ve üretim (`build_*`) betikleri **çalışma zamanında
kullanılmaz**. Veritabanı hazır teslim edildiği için çalıştırılmaları
gerekmez; kaynaktan tekrar üretim gerektiğinde kayıt olarak dururlar.

## Yapay Zeka Kokpiti — `project/backend/app/services/assistant/`

Asistan yalnızca bu projenin veritabanını okur; web erişimi yoktur.

```
assistant/
├── chat_service.py       tur akışı, süre ve çağrı bütçeleri
├── gemini_provider.py    Google Gemini bağlantısı
├── tool_registry.py      araç kaydı ve şemaları
├── tool_runner.py        araç çalıştırma, önbellek, süre sınırı
├── tool_selection.py     soruya göre araç seçimi
├── tools*.py             veri okuma araçları (salt okunur)
├── chart_tool.py         grafik üretimi (yalnız araç çıktısından)
└── query_policy.py       kurumsal soru kuralları
```

Bütçeler: kullanıcı mesajı başına en fazla **3 model çağrısı**, **2 veri
çağrısı**, çağrı başına **25 saniye**, mesaj başına toplam **45 saniye**.
Bütçe dolarsa elde bulunan verilerle cevap üretilir; kullanıcı boş ekranla
kalmaz.

## Frontend — `project/frontend/`

Derleme adımı olmayan vanilla JavaScript. Tarayıcı önbelleğini atlatmak
için varlıklar `?v=` sürüm etiketiyle çağrılır.

```
frontend/
├── index.html
└── assets/
    ├── kabuk.js                  uygulama kabuğu, gezinme
    ├── ekranlar.js               analiz ekranları
    ├── app.js                    API istemcisi
    ├── ai-screen-assistant.js    Yapay Zeka Kokpiti arayüzü
    ├── derslik-haritasi.js       derslik haritası
    └── derslik-harita-plan.js    kat planı çizimi
```

## Veri — `project/data/` ve `data_sources/`

- **`project/data/`** — uygulamanın çalışırken okuduğu dosyalar.
  Silinirse uygulama bozulur.
- **`data_sources/`** — ham ve yetkili kaynakların arşivi. Uygulama
  okumaz; denetim ve tekrar üretilebilirlik içindir.

Ayrıntılı liste: `docs/DATA_MANIFEST.csv`
