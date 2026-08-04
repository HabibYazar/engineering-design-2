# Ekip ve Modül Haritası

Hangi kodun kimden geldiği, birleştirmede nereye taşındığı ve neyin arşive
alındığı. Sahiplik tahminle değil, dosya içerikleri, README'ler ve import
yolları incelenerek belirlenmiştir.

---

## 1. Ekip envanteri

| Kişi / Klasör | Modüller | Backend | Frontend | Veri Kaynağı | Test | Başlangıçta çalışıyor mu? | Entegrasyon kararı |
|---|---|---|---|---|---|---|---|
| **habib/** | 1, 2, 9, 10, 13 | FastAPI + SQLAlchemy 2.0 + SQLite | `module_views/static/` (vanilla JS demo) | `seed_data.py`, `seed_student_data.py`, `seed_scenario_data.py`, `seed_ranking_data.py` + 36 örnek CSV/XLSX/JSON | 412 pytest testi | Evet — 65 endpoint, 122 şema, 412/412 test geçiyor | **Ana backend olarak seçildi.** Tüm yapı korundu. |
| **begüm/** | 3, 7, 11 | FastAPI (ayrı `main.py` + kendi `database.py`) | `panel.html` (tek dosya) | `seed_data.py` + `config/weights.json`, `config/rules.json` | Yok | Kısmen — kendi başına çalışıyor, ayrı veritabanı kullanıyor | Servisler kanonik backend'e taşındı, prefix çakışması giderildi |
| **eda/** | 4, 5, 14 | FastAPI + **düz Python sınıfları** (veritabanı yok) | `frontend.html` | `seed_data.py` içinde modül seviyesi Python listeleri | Yok | Hayır — `/ranking` endpoint'i `FileNotFoundError` veriyor, `/capacity` iki router'da çakışıyor | SQLAlchemy modellerine dönüştürüldü, iki hata düzeltildi |
| **halilhan/** | 6, 8, 12 (arayüz) | **stdlib `http.server`** + JSON dosyası (`data.json`, `kpis.json`) | `full-frontend/` — vanilla JS SPA, 15 ekran, 1974 satır | `seed_data.json`, `seed_kpis.json` | Yok | Evet ama izole — kendi HTTP sunucusu, tüm arayüz verisi hard-code | Backend SQLAlchemy'ye taşındı; **arayüz ana shell olarak seçildi** |

### Modül 12 hakkında

`halilhan/frontend/index.html` Modül 12'ye ait bir arayüz taslağıdır ancak
karşılık gelen bir backend uygulaması ekip deposunda **bulunmamaktadır**. Bu
yüzden Modül 12 birleştirilmiş ürüne dâhil edilmemiştir; sahte bir ekran
üretilmemiştir. Dosya `integration/archive_before_merge/halilhan_module12_frontend_original/`
altında korunmaktadır.

---

## 2. Entegrasyonda kullanılan parçalar

### Habib — ana backend (değiştirilmeden alındı)

`habib/backend/` → `integration/backend/`

| Kaynak | Hedef | Not |
|---|---|---|
| `app/models/` (16 dosya) | aynı yol | Kanonik modeller |
| `app/schemas/` (11 dosya) | aynı yol | — |
| `app/routers/` (10 dosya) | aynı yol | — |
| `app/services/` (20 dosya) | aynı yol | — |
| `app/core/` | aynı yol | `MoneyType`, `Settings` |
| `app/database.py` | aynı yol | **Tek `Base`, `engine`, `SessionLocal`, `get_db`** |
| `tests/` (8 dosya, 412 test) | aynı yol | Değiştirilmedi |
| `sample_data/` (36 dosya) | aynı yol | Modül 13 örnek dosyaları |
| 4 seed script'i | aynı yol | Değiştirilmedi |

**Sonradan eklenen kolonlar** (Begüm'ün servisleri çalışsın diye, birleşim yaklaşımı):

| Model | Eklenen kolon | Sebep |
|---|---|---|
| `Student` | `status_change_year` | Modül 3 kohort analizi |
| `Student` | `is_employed` | Modül 3 mezun istihdam oranı (üçlü mantık: True/False/bilinmiyor) |
| `ProgramEnrollmentSnapshot` | `full_scholarship_minimum_admission_score` | Modül 3 burs politikası analizi |

### Begüm — Modül 3, 7, 11

| Kaynak dosya | Hedef dosya | Yapılan değişiklik |
|---|---|---|
| `module_03_ogrenci_analitigi/schemas/student_analytics.py` | `app/schemas/education_analytics.py` | Yalnızca import yolları |
| `module_03_ogrenci_analitigi/services/student_analytics_service.py` | `app/services/education_analytics_service.py` | Yalnızca import yolları |
| `module_03_ogrenci_analitigi/routers/student_analytics.py` | `app/routers/education_analytics.py` | Import + **prefix `/api/student-analytics` → `/api/education-analytics`** |
| `module_07_surdurulebilirlik/schemas/sustainability.py` | `app/schemas/sustainability.py` | Yalnızca import yolları |
| `module_07_surdurulebilirlik/services/sustainability_service.py` | `app/services/sustainability_service.py` | Import + `CONFIG_PATH` |
| `module_07_surdurulebilirlik/routers/sustainability.py` | `app/routers/sustainability.py` | Yalnızca import yolları |
| `module_11_erken_uyari/schemas/early_warning.py` | `app/schemas/early_warning.py` | Yalnızca import yolları |
| `module_11_erken_uyari/services/rule_engine.py` | `app/services/early_warning_rule_engine.py` | Import + `CONFIG_PATH` |
| `module_11_erken_uyari/routers/early_warning.py` | `app/routers/early_warning.py` | Yalnızca import yolları |
| `module_07_surdurulebilirlik/config/weights.json` | `app/config/sustainability_weights.json` | Ad benzersizleştirildi |
| `module_11_erken_uyari/config/rules.json` | `app/config/early_warning_rules.json` | Ad benzersizleştirildi |

**İş mantığına dokunulmadı.** Toplam 18 satır değişti; hepsi import veya yol
satırıdır. Türkçe yorumlar korunmuştur.

### Eda — Modül 4, 5, 14

Eda'nın kodu düz Python sınıflarıydı (veritabanı yok), 51 dosyanın 35'i boştu.
Toplam 540 satır kod vardı. Hesaplama mantığı korunarak SQLAlchemy'ye taşındı.

| Kaynak | Hedef | Taşınan mantık |
|---|---|---|
| `module_04/models/staff.py` (düz sınıf) | `app/models/academic_staff.py` | Alanlar; bölüm serbest metin → foreign key |
| `module_04/services/scores_calculator.py` | `app/services/academic_staff_service.py` | Ağırlıklı puan formülü **birebir**, `compare_by`, `trend_by_year` |
| `module_04/routes/staff_routes.py` | `app/routers/academic_staff.py` | 6 endpoint → 6 endpoint (+CRUD) |
| `config/weightConfig.json` | `app/config/academic_staff_weights.json` | Ağırlıklar aynen |
| `module_05/models/facility.py` + `classroom.py` | `app/models/physical_facility.py` | **İki sınıf tek tabloda birleştirildi** |
| `module_05/services/capacity_service.py` | `app/services/physical_resources_service.py` | 8 analiz fonksiyonu; eşikler (%50/%90) korundu |
| `module_05/routes/classroom_routes.py` + `capacity_routes.py` | `app/routers/physical_resources.py` | **Tek router** (çakışma giderildi) |
| `module_14/models/user.py` | `app/models/system_user.py` | Düz metin parola → PBKDF2 özet |
| `module_14/services/auth_service.py` | `app/services/auth_service.py` | login/logout/session/permission akışı korundu |
| `module_14/routes/auth_routes.py` | `app/routers/auth.py` | 7 endpoint |

**Bulunan ve düzeltilen 2 hata** — ayrıntı `INTEGRATION_DECISIONS.md` içinde.

### Halil — Modül 6, 8 + ana arayüz

| Kaynak | Hedef | Taşınan mantık |
|---|---|---|
| `finance/backend/db.py` (JSON dosyası) | `app/models/financial_period.py` | 3 model: `FinancialPeriod`, `FinancialEntry`, `DepartmentBudget` |
| `finance/backend/render.py` (HTML üretimi) | `app/services/finance_service.py` | **Tüm oran formülleri birebir**: denge, öğrenci/mezun başına maliyet, personel payı, araştırma payı, burs yükü, bütçe gerçekleşme (%100/%108 eşikleri) |
| `finance/backend/server.py` | `app/routers/finance.py` | 7 endpoint |
| `finance/backend/seed_data.json` | `shared_demo_data/05_finance.json` | Yapı korundu, 12 bölüme ölçeklendi, Türkçeleştirildi |
| `kpi/backend/db.py` | `app/models/strategic_kpi.py` | 2 model; `evaluate()` durum mantığı **birebir** |
| `kpi/backend/render.py` | `app/services/kpi_service.py` | Karne, boyut özeti, fakülte karşılaştırması |
| `kpi/backend/server.py` | `app/routers/kpi.py` | 8 endpoint |
| `kpi/backend/seed_kpis.json` | `shared_demo_data/06_kpis.json` | 14 KPI, 10 boyut korundu |
| **`full-frontend/assets/style.css`** | `frontend/assets/style.css` | **Değiştirilmeden alındı** — tasarım dili |
| **`full-frontend/assets/app.js`** | `frontend/assets/app.js` | Kabuk, yönlendirici, grafik yardımcıları korundu; oturum gerçek API'ye bağlandı, sahte sohbet kaldırıldı |
| `full-frontend/assets/views-*.js` | `frontend/assets/views-*.js` | Ekran düzeni ve isimlendirme korundu, **hard-code veri kaldırıldı**, gerçek API'ye bağlandı |

---

## 3. Halil'in arayüzünden alınan tasarım parçaları

Ana kabuk ve tasarım dili tamamen Halil'in çalışmasından gelmektedir:

- Yan menü (gruplu gezinme), üst bar, kullanıcı rozeti
- Renk paleti ve **gece modu** (`data-theme="dark"` + `localStorage`)
- Kart (`.card`), KPI kutusu (`.tile`), tablo, `chip` durum rozetleri
- SVG grafik yardımcıları: `lineChart()`, `donuts()`, `hbars()`, `meters()`
- Responsive yapı, mobil menü açma/kapama, sayfa geçiş animasyonu (`.enter`)
- Giriş ekranı düzeni
- Hash tabanlı yönlendirici ve `VIEWS` kayıt deseni

`integration/frontend/assets/integration.css` dosyası **ek** olarak yazılmıştır;
Halil'in `style.css` dosyası değiştirilmemiştir. Entegrasyonda ihtiyaç duyulan
yeni bileşenler (yükleniyor göstergesi, hata kutusu, bildirim, filtre çubuğu,
ağaç görünümü) oradadır.

---

## 4. Diğer ekip üyelerinden korunan ekranlar

Halil'in arayüzünde 15 ekran vardı; bunların 14'ü korundu (Modül 12 ekranı
backend'i olmadığı için çıkarıldı). Diğer üyelerin arayüzlerinde bulunup
Halil'de olmayan **işlevler** ilgili ekranlara eklendi:

| Kaynak | Eklenen işlev | Hangi ekrana |
|---|---|---|
| Begüm — `panel.html` | Program sürdürülebilirlik skoru + veri tamlığı sütunu | Program Sürdürülebilirliği |
| Begüm — `panel.html` | Kural bazlı uyarı listesi; ölçülen değer + eşik + kaynak gösterimi | Erken Uyarı |
| Begüm — `panel.html` | "Henüz çalıştırılamayan kurallar" listesi | Erken Uyarı |
| Eda — `frontend.html` | Kapasite projeksiyonu (büyüme yüzdesi girişi) | Fiziksel Kaynaklar |
| Eda — `frontend.html` | Personel karşılaştırma (bölüm/fakülte/unvan) | Akademik Personel |
| Habib — `module_views/static/` | Modül 13 önizleme + satır bazlı hata raporu | Veri Aktarımı |
| Habib — `module_views/static/` | Senaryo önizleme + risk listesi + puan kırılımı | Senaryo Analizi |

Tekrar eden ekran bırakılmamıştır: Modül 2 ve Modül 3'ün her ikisi de öğrenci
analitiği üretir; iki ayrı sekme yerine **tek "Öğrenci Analitiği" ekranında**
iki modülün çıktıları ayrı kartlarda (modül rozetiyle) gösterilir.

---

## 5. Arşivlenen parçalar

Hiçbir dosya silinmemiştir. `integration/archive_before_merge/` (90 dosya):

| Klasör / dosya | Kaynak | Neden arşivlendi |
|---|---|---|
| `begum_main_original.py` | `begüm/main.py` | Ayrı FastAPI uygulaması; tek backend'e geçildi |
| `begum_database_original.py` | `begüm/database.py` | İkinci `Base`/`engine`; ortak `app/database.py` kullanılıyor |
| `begum_seed_data_original.py` | `begüm/seed_data.py` | Ortak seed'e taşındı |
| `begum_panel_original.html` | `begüm/panel.html` | İşlevleri ana arayüze taşındı |
| `begum_legacy_konsol_demo/` | `begüm/` konsol demoları | Arayüzle değiştirildi |
| `eda_main_original.py` | `eda/main.py` | Ayrı FastAPI uygulaması |
| `eda_module_04_original/` | `eda/module_04_academic_staff/` | SQLAlchemy'ye taşındı |
| `eda_module_05_original/` | `eda/module_05_physical_resources/` | SQLAlchemy'ye taşındı |
| `eda_module_14_original/` | `eda/module_14_user_authorization/` | SQLAlchemy'ye taşındı |
| `eda_seed_data_original.py` | `eda/seed_data.py` | Ortak seed'e taşındı |
| `halilhan_finance_original/` | `halilhan/finance/` | stdlib HTTP sunucusu → FastAPI |
| `halilhan_kpi_original/` | `halilhan/kpi/` | stdlib HTTP sunucusu → FastAPI |
| `halilhan_full_frontend_original/` | `halilhan/full-frontend/` | Hard-code verili orijinal hâli |
| `halilhan_module12_frontend_original/` | `halilhan/frontend/` | Modül 12 — backend'i yok |
| `root_ogrenci_analitigi_paneli.html` | depo kökü | Sahipsiz tek dosya panel |

Ekip üyelerinin **orijinal klasörleri de yerinde durmaktadır**
(`habib/`, `begüm/`, `eda/`, `halilhan/`). Arşiv, birleştirmede kaynak olarak
kullanılan dosyaların birleştirme öncesi hâlinin ikinci bir kopyasıdır.
