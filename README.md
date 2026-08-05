# Stratejik Üniversite Yönetimi ve Karar Destek Sistemi

Engineering Design 2 dönem projesi. Dört ekip üyesinin ayrı ayrı geliştirdiği
13 modül, tek çalışan bir ürün hâline getirilmiştir: tek backend, tek
veritabanı, tek web arayüzü, tek veri seti.

---

## Hızlı başlangıç

Windows / PowerShell:

```powershell
.\run_project.ps1
```

Bu komut sanal ortamı kurar, bağımlılıkları yükler, ortak demo verisini
veritabanına yazar ve sunucuyu başlatarak tarayıcıyı açar.

Sunum öncesi tam doğrulama için:

```powershell
.\run_project.ps1 -FreshDatabase -RunTests
```

Manuel çalıştırma (herhangi bir işletim sisteminde):

```bash
python -m venv .venv
.venv/bin/pip install -r integration/backend/requirements.txt   # Windows: .venv\Scripts\pip
cd integration/backend
python seed_all_demo_data.py
python -m uvicorn main:app --port 8000
```

Açıldıktan sonra:

| Adres | İçerik |
|---|---|
| <http://127.0.0.1:8000> | Web arayüzü (16 ekran) |
| <http://127.0.0.1:8000/docs> | Swagger API dokümantasyonu (195 endpoint) |
| <http://127.0.0.1:8000/health> | Sağlık kontrolü |

### Demo hesapları

Parola hepsinde `demo1234`.

| Kullanıcı | Rol | Kapsam |
|---|---|---|
| `admin` | Admin | Tüm kurum + kullanıcı yönetimi |
| `dekan.muh` | Dekan | Mühendislik ve Mimarlık Fakültesi |
| `dekan.iibf` | Dekan | İktisadi ve İdari Bilimler Fakültesi |
| `baskan.ceng` | Bölüm Başkanı | Bilgisayar Mühendisliği |
| `baskan.isl` | Bölüm Başkanı | İşletme |
| `ogretim.uyesi` | Öğretim Üyesi | Yalnızca görüntüleme |

Parolalar veritabanında düz metin saklanmaz; PBKDF2-HMAC-SHA256 ile
saltlanarak özetlenir.

---

## Klasör yapısı

```
engineering-design-2-main/
├── run_project.ps1                Tek komutla kurulum + çalıştırma
├── README.md                      Bu dosya
│
├── integration/                   BİRLEŞTİRİLMİŞ ÜRÜN
│   ├── backend/                   FastAPI + SQLAlchemy + SQLite
│   │   ├── app/
│   │   │   ├── models/            SQLAlchemy modelleri (tüm modüller)
│   │   │   ├── schemas/           Pydantic v2 şemaları
│   │   │   ├── routers/           HTTP endpoint'leri
│   │   │   ├── services/          İş mantığı
│   │   │   │   └── assistant/     Asistan altyapısı (LLM BAĞLI DEĞİL)
│   │   │   ├── config/            JSON yapılandırma (ağırlıklar, kurallar)
│   │   │   └── core/              Ayarlar, Decimal tipleri
│   │   ├── tests/                 412 birim testi
│   │   ├── tests_integration/     57 entegrasyon testi
│   │   ├── main.py                Uygulama giriş noktası
│   │   ├── seed_all_demo_data.py  Ortak veriyi yükleyen tek script
│   │   └── .env.example           Ortam değişkeni şablonu
│   │
│   ├── frontend/                  Vanilla JS SPA (CDN yok, derleme yok)
│   │   ├── index.html
│   │   └── assets/
│   │       ├── api.js             Backend istemcisi
│   │       ├── app.js             Yönlendirici, oturum, kabuk
│   │       ├── views-*.js         16 ekran
│   │       ├── style.css          Halil'in tasarım sistemi
│   │       └── integration.css    Entegrasyonda eklenen bileşenler
│   │
│   ├── shared_demo_data/          TEK DOĞRULUK KAYNAĞI (10 JSON dosyası)
│   ├── tests_ui/                  Arayüz entegrasyon testi (jsdom)
│   └── archive_before_merge/      Birleştirme öncesi orijinal dosyalar
│
├── docs/                          Dokümantasyon
├── habib/  begüm/  eda/  halilhan/   Ekip üyelerinin orijinal çalışmaları
└── .venv/                         Sanal ortam (Git'e girmez)
```

**Önemli:** Ekip üyelerinin orijinal klasörleri silinmedi. Birleştirmede
kullanılan dosyaların birleştirme öncesi hâli ayrıca
`integration/archive_before_merge/` altında saklanmaktadır.

---

## Modüller

| # | Modül | Geliştiren | Endpoint öneki | Ekran |
|---|---|---|---|---|
| 1 | Üniversite Yapısı ve Temel Veri Yönetimi | Habib | `/api/faculties`, `/api/departments`, `/api/programs`, `/api/administrative-units` | Üniversite Yapısı |
| 2 | Stratejik Eğitim ve Öğrenci Analitiği | Habib | `/api/students`, `/api/student-analytics` | Öğrenci Analitiği |
| 3 | Öğrenci Analitiği | Begüm | `/api/education-analytics` | Öğrenci Analitiği |
| 4 | Akademik Personel Performansı | Eda | `/api/academic-staff` | Akademik Personel |
| 5 | Fiziksel Kaynak ve Kapasite | Eda | `/api/physical-resources` | Fiziksel Kaynaklar |
| 6 | Stratejik Finansal Analiz | Halil | `/api/finance` | Finansal Analiz |
| 7 | Program Sürdürülebilirliği | Begüm | `/api/program-sustainability` | Program Sürdürülebilirliği |
| 8 | Kurumsal Performans Yönetimi | Halil | `/api/kpi` | Performans ve KPI |
| 9 | What-if Senaryo Analizi | Habib | `/api/scenarios` | Senaryo Analizi |
| 10 | THE / QS / YÖK Değerlendirme | Habib | `/api/ranking-evaluations` | THE · QS · YÖK |
| 11 | Erken Uyarı Sistemi | Begüm | `/api/early-warning` | Erken Uyarı |
| 13 | Veri Entegrasyonu | Habib | `/api/data-integration` | Veri Aktarımı |
| — | Akademik Başarı Analizi | Entegrasyon | `/api/academic-success` | Akademik Başarı |
| — | Sanayi ve Bölgesel Katkı | Entegrasyon | `/api/engagement` | Sanayi ve Bölgesel Katkı |
| 14 | Kullanıcı ve Yetkilendirme | Eda | `/api/auth` | Kullanıcı ve Yetki |

Modül 12 için ekip deposunda backend kodu bulunmamaktadır; ayrıntı
[`docs/KNOWN_LIMITATIONS.md`](docs/KNOWN_LIMITATIONS.md) dosyasındadır.

Ayrıntılı dosya eşlemesi: [`docs/TEAM_MODULE_MAP.md`](docs/TEAM_MODULE_MAP.md)

---

## Testler

```bash
cd integration/backend
python -m pytest tests tests_integration -q     # 469 test
```

Arayüz testi (sunucu çalışırken, ayrı bir terminalde):

```bash
npm install jsdom
node integration/tests_ui/test_frontend.js       # 43 kontrol
```

| Test kümesi | Adet | Kapsam |
|---|---|---|
| Birim testleri (`tests/`) | 412 | Modül içi iş mantığı, doğrulama, hesaplama |
| Entegrasyon testleri (`tests_integration/`) | 57 | Router çakışması, model birleşimi, hesaplama doğruluğu, 5 yıllık mali toplamlar, senaryo formülleri, oran sınırları, seed idempotanslığı |
| Arayüz testleri (`tests_ui/`) | 43 | 16 ekranın gerçek veriyle dolması, USD gösterimi, senaryo karşılaştırması, hata gösterimi |

---

## Bilinmesi gerekenler

- **Yapay zekâ asistanı bağlı değil.** Arayüzdeki "Akıllı Asistan" ekranı
  altyapının hazır kısmını gösterir ve **cevap üretmez**. Hiçbir dil modeline
  bağlantı yoktur, hiçbir API anahtarı kullanılmaz. Ayrıntı:
  [`docs/ASSISTANT_ARCHITECTURE.md`](docs/ASSISTANT_ARCHITECTURE.md)
- **Modül 10 gerçek sıralama üretmez.** THE, QS veya YÖK sıralamalarını
  hesaplamaz; kurum içi performans ve veri hazırlık göstergeleri üretir.
- **Tek para birimi USD'dir.** Sistemde TL veya birimsiz tutar bulunmaz;
  her parasal değer `$` işaretiyle ve birimiyle gösterilir.
- **Veri seti kurgusaldır.** `integration/shared_demo_data/` altındaki
  varsayımlardan üretilir ve gerçek bir kurumun verisi değildir. 5 mali dönem,
  5 yıllık başarı ve iş birliği verisi içerir.
- Bilinen sınırlamaların tamamı:
  [`docs/KNOWN_LIMITATIONS.md`](docs/KNOWN_LIMITATIONS.md)

---

## Dokümantasyon

| Dosya | İçerik |
|---|---|
| [`docs/TEAM_MODULE_MAP.md`](docs/TEAM_MODULE_MAP.md) | Hangi dosya kimden geldi, nereye taşındı |
| [`docs/INTEGRATION_PLAN.md`](docs/INTEGRATION_PLAN.md) | Birleştirme planı ve aşamalar |
| [`docs/INTEGRATION_DECISIONS.md`](docs/INTEGRATION_DECISIONS.md) | Verilen kararlar ve gerekçeleri |
| [`docs/SHARED_DATA_DICTIONARY.md`](docs/SHARED_DATA_DICTIONARY.md) | Ortak veri sözlüğü |
| [`docs/API_OVERVIEW.md`](docs/API_OVERVIEW.md) | Endpoint listesi |
| [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md) | Sunum senaryosu |
| [`docs/FIXED_CALCULATION_BUGS.md`](docs/FIXED_CALCULATION_BUGS.md) | Bulunan ve düzeltilen hesaplama hataları |
| [`docs/KNOWN_LIMITATIONS.md`](docs/KNOWN_LIMITATIONS.md) | Bilinen sınırlamalar |
| [`docs/ASSISTANT_ARCHITECTURE.md`](docs/ASSISTANT_ARCHITECTURE.md) | Asistan mimarisi |
