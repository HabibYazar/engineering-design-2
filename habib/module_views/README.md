# Modül Görünümleri (module_views)

Bu klasör iki amaca hizmet eder:

1. **Sunum ve kod inceleme** — beş modülün dosyaları modül bazlı klasörlere ayrılmıştır.
2. **Bağımsız çalışan demo** — `main.py` sayesinde bu klasör tek başına indirilip
   çalıştırılabilir. Demo yalnızca **Modül 1** ve **Modül 13** kopyalarını kullanır ve
   ana backend'e (`backend/app`) **hiçbir bağımlılığı yoktur**.

---

## 🚀 Bağımsız Demo — Hızlı Başlangıç

`module_views` klasörünün içindeyken:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

Ardından tarayıcıdan: **http://127.0.0.1:8000/docs**

### Alternatif çalıştırma yolları

```powershell
# Otomatik yeniden yükleme ile
uvicorn main:app --reload

# Paket kontrolü + veritabanı hazırlığı + seed + çalıştırma (tek komut)
powershell -ExecutionPolicy Bypass -File .\run_demo.ps1
```

### Demoda bulunan endpoint'ler (16 yol)

| Grup | Endpoint |
|---|---|
| Health | `GET /` · `GET /health` · `GET /demo-info` |
| Faculties | `GET,POST /api/faculties` · `GET,PUT,DELETE /api/faculties/{faculty_id}` |
| Departments | `GET,POST /api/departments` · `GET,PUT,DELETE /api/departments/{department_id}` |
| Academic Programs | `GET,POST /api/programs` · `GET,PUT,DELETE /api/programs/{program_id}` |
| Administrative Units | `GET,POST /api/administrative-units` · `GET,PUT,DELETE /api/administrative-units/{unit_id}` |
| Data Integration | `POST /api/data-integration/import/{resource_type}` · `GET .../templates/{resource_type}` · `GET .../jobs` · `GET .../jobs/{job_id}` · `GET .../resources` |

**Demoda bulunmayanlar:** Student Analytics (Modül 2), Scenario Analysis (Modül 9),
Ranking Evaluations (Modül 10). Bu modüllerin dosyaları demoda **hiç yüklenmez**.

### Demo akışı

| Adım | İşlem | Kullanılan dosya |
|---|---|---|
| 1 | `GET /health` — sistemin çalıştığını göster | — |
| 2 | `GET /api/faculties` — seed'den gelen FEA | `module_01_core_data/seed_data.py` |
| 3 | `POST /api/faculties` — yeni fakülte (201) | — |
| 4 | `POST /api/departments` — fakülteye bağlı bölüm | — |
| 5 | `POST /api/programs` — bölüme bağlı program | — |
| 6 | `POST /api/administrative-units` — idari birim | — |
| 7 | Import **preview=true** | `sample_data/faculties_sample.csv` (veya `.xlsx`) |
| 8 | Import **preview=false** (sırayla) | `faculties` → `departments` → `programs` → `administrative_units` örnekleri |
| 9 | `GET /api/faculties` — aktarılan veriyi göster | — |
| 10 | Hatalı dosyayla doğrulama hataları | `sample_data/faculties_with_errors_sample.csv` |

> **Sıra önemli:** `departments_sample.csv` içindeki `MED` kodu, `faculties_sample.csv`
> aktarıldıktan sonra oluşur; `programs_sample.csv` ise `EE`/`IE` kodlarına bağlıdır.

### Veritabanı

Demo veritabanı `module_views/demo_module_views.db` dosyasında oluşur — ana projenin
`university_management.db` dosyasına dokunulmaz. Sıfırlamak için dosyayı silmek yeterli.

### Demoyu kapatma

Sunucunun çalıştığı konsolda **CTRL+C**.

---

## ⚠️ Önemli Notlar

- Modül klasörlerindeki tüm dosyalar `app/`, `sample_data/` ve kök dizindeki
  **orijinallerin birebir kopyalarıdır**. İçerikleri değiştirilmemiş, başlarına açıklama
  eklenmemiştir.
- **Ana uygulamanın çalışan kodu her zaman orijinal konumundadır** (`backend/app`,
  `backend/main.py`). Bu klasördeki kopyalar üzerinde değişiklik yapmak ana uygulamayı
  etkilemez.
- Kopyaların import yolları hâlâ `app.*` biçimindedir (birebir kopya oldukları için).
  `main.py` bunu çözmek için `sys.modules` üzerinde **sanal bir `app` paketi** kurar ve
  alt modüllerini bu klasördeki kopyalara yönlendirir. Kaynak kodların iş mantığına
  dokunulmaz.
- `main.py` içinde ayrıca demo için **eksik ortak bileşenler** üretilir:
  `Base`, `engine`, `SessionLocal`, `get_db`, `init_db`, `/health` endpoint'i,
  `validate_academic_year` yardımcısı ve Modül 13 doğrulayıcısının import ettiği
  8 yer tutucu tablo tanımı. Bu yer tutucular hiçbir iş mantığı, şema, servis veya
  endpoint içermez.
- Kopyalar orijinal katman yapısını korur (`models/`, `schemas/`, `routers/`, `services/`).
  Bunun sebebi: aynı isimli dosyalar farklı katmanlarda bulunabiliyor (örneğin
  `models/faculty.py` ve `schemas/faculty.py`); düz kopyalama bu dosyaların birbirini
  ezmesine yol açardı.
- Seed script'leri her modül klasörünün kökündedir.
- Modül 2, 9 ve 10 klasörleri **yalnızca inceleme amaçlıdır**; bağımsız demo bu
  klasörlerden hiçbir dosya yüklemez.

## Bağımsız Demoda Yüklenen Python Dosyaları (19)

`GET /demo-info` bu listeyi çalışma zamanında da döndürür.

| Sanal modül adı | Gerçek dosya |
|---|---|
| `app.models.faculty` | `module_01_core_data/models/faculty.py` |
| `app.models.department` | `module_01_core_data/models/department.py` |
| `app.models.academic_program` | `module_01_core_data/models/academic_program.py` |
| `app.models.administrative_unit` | `module_01_core_data/models/administrative_unit.py` |
| `app.models.import_job` | `module_13_data_integration/models/import_job.py` |
| `app.schemas.faculty` | `module_01_core_data/schemas/faculty.py` |
| `app.schemas.department` | `module_01_core_data/schemas/department.py` |
| `app.schemas.academic_program` | `module_01_core_data/schemas/academic_program.py` |
| `app.schemas.administrative_unit` | `module_01_core_data/schemas/administrative_unit.py` |
| `app.schemas.data_integration` | `module_13_data_integration/schemas/data_integration.py` |
| `app.services.crud_helpers` | `module_01_core_data/services/crud_helpers.py` |
| `app.services.file_parser` | `module_13_data_integration/services/file_parser.py` |
| `app.services.import_validators` | `module_13_data_integration/services/import_validators.py` |
| `app.services.import_service` | `module_13_data_integration/services/import_service.py` |
| `app.routers.faculties` | `module_01_core_data/routers/faculties.py` |
| `app.routers.departments` | `module_01_core_data/routers/departments.py` |
| `app.routers.programs` | `module_01_core_data/routers/programs.py` |
| `app.routers.administrative_units` | `module_01_core_data/routers/administrative_units.py` |
| `app.routers.data_integration` | `module_13_data_integration/routers/data_integration.py` |

Ek olarak `module_01_core_data/seed_data.py` örnek veri yüklenirken çalıştırılır.
**Bu 20 dosya dışında hiçbir proje dosyası import edilmez.**

## Bağımsız Demo Dosyaları

| Dosya | Görevi |
|---|---|
| `main.py` | Bağımsız FastAPI giriş noktası + uyumluluk katmanı |
| `requirements.txt` | Yalnızca gerçekten kullanılan 7 paket |
| `run_demo.ps1` | Paket kontrolü → veritabanı → seed → uvicorn |
| `demo_module_views.db` | Demo SQLite veritabanı (çalıştırınca oluşur) |

## Modül Özet Tablosu

| Modül | Klasör | Ad | Ana Sorumluluk | Dosya | Model | Endpoint |
|---|---|---|---|---|---|---|
| 1 | `module_01_core_data/` | University Structure and Core Data Management | Fakülte, bölüm, program ve idari birim yönetimi | 14 | 4 | 20 |
| 2 | `module_02_student_analytics/` | Strategic Education and Student Analytics | Öğrenci sayıları, oranlar, trendler ve erken uyarılar | 12 | 4 | 21 |
| 9 | `module_09_scenario_analysis/` | What-if Scenario Analysis | Finans, personel ve kapasite senaryo simülasyonu | 10 | 4 | 15 |
| 10 | `module_10_ranking_evaluations/` | THE, QS and YÖK Evaluation and Monitoring | Değerlendirme çerçeveleri, veri hazırlık ve iç uyum izleme | 17 | 8 | 33 |
| 13 | `module_13_data_integration/` | Data Integration | CSV / XLSX / JSON toplu veri aktarımı | 42 | 1 | 5 |

**Toplam:** 95 dosya kopyalandı · 21 veritabanı tablosu · 65 endpoint yolu

## Katmanlı Mimari

Projenin tamamı aynı katman düzenini kullanır:

```
Router      →  yalnızca HTTP: isteği alır, servisi çağırır, cevabı döndürür
Service     →  tüm iş mantığı ve hesaplamalar
Schema      →  Pydantic v2 giriş/çıkış doğrulaması
Model       →  SQLAlchemy 2.0 veritabanı tabloları
```

**Kural:** Router içinde hesaplama yapılmaz. Bu ayrım sayesinde formüller veritabanı ve
HTTP katmanından bağımsız olarak test edilebilir.

## Modüller Arası Bağlantı Haritası

```
                    ┌──────────────────────────────┐
                    │  Modül 1 - Üniversite Yapısı │
                    │  Faculty → Department →      │
                    │  AcademicProgram             │
                    └───────┬──────────────────────┘
                            │ akademik program
              ┌─────────────┴─────────────┐
              ▼                           ▼
   ┌──────────────────────┐   ┌────────────────────────┐
   │ Modül 2 - Öğrenci    │   │ Modül 13 - Veri        │
   │ Analitiği            │   │ Entegrasyonu           │
   │ Student, Records,    │◄──┤ 11 kaynak türü için    │
   │ Snapshots            │   │ CSV/XLSX/JSON import   │
   └────┬─────────────┬───┘   └───────────┬────────────┘
        │             │                   │ besler
        │ aktif       │ öğrenci           │
        │ öğrenci     │ göstergeleri      ▼
        ▼             ▼        ┌────────────────────────────┐
   ┌─────────────────────┐     │ Modül 10 - THE/QS/YÖK      │
   │ Modül 9 - Senaryo   │     │ Değerlendirme ve İzleme    │
   │ Analizi             │     │ Framework → Dimension →    │
   │ Baseline, Scenario, │     │ Indicator → MetricValue    │
   │ Input, Result       │     └────────────────────────────┘
   └─────────────────────┘
```

### Somut Entegrasyon Noktaları

| Kaynak | Hedef | Nasıl |
|---|---|---|
| Modül 1 → Modül 2 | `AcademicProgram` → `Student.academic_program_id` | Foreign key |
| Modül 1 → Modül 2 | `AcademicProgram` → `ProgramEnrollmentSnapshot` | Foreign key |
| Modül 2 → Modül 9 | Aktif öğrenci sayısı → `ScenarioBaseline.student_count` | `POST /api/scenarios/baselines/sync-student-data` |
| Modül 2 → Modül 9 | Canlı öğrenci sayısı → simülasyon başlangıcı | `?use_live_student_data=true` |
| Modül 1+2 → Modül 10 | 17 öğrenci metriği → gösterge verisi | `POST /api/ranking-evaluations/metrics/sync-student-data` |
| Modül 13 → 1, 2, 10 | Toplu veri aktarımı | 11 `resource_type` |

## Ortak Teknik Kararlar

| Karar | Gerekçe |
|---|---|
| **Decimal** (float değil) | Para ve oran hesaplarında ikili gösterim sapması milyonluk bütçelerde gerçek hataya dönüşür |
| **`MoneyType`** özel sütun tipi | SQLite `Numeric`'i float olarak saklar; Decimal'i metin olarak yazıp okuyarak kayıpsızlık garanti edilir |
| **Soft delete** | Kayıtlar silinmez, `is_active=False` yapılır — geçmiş raporlar bozulmaz |
| **`ROUND_HALF_UP`, 2 basamak** | Tüm yüzde ve para değerleri tutarlı biçimde yuvarlanır |
| **Sıfıra bölme koruması** | Her bölme güvenli yardımcıdan geçer; hata yerine 0 döner ve durum raporlanır |
| **Toplu SQL sorguları** | `GROUP BY` + `SUM(CASE WHEN...)` ile N+1 sorgu önlenir |
| **Yol sırası** | Sabit yollar (`/baselines`) parametreli yollardan (`/{id}`) önce tanımlanır |

## Sunumda Vurgulanacak Genel Noktalar

1. **Katmanlı mimari tutarlı biçimde uygulandı** — 5 modülün beşi de aynı Router/Service/
   Schema/Model ayrımını kullanıyor; hiçbir router içinde hesaplama yok.
2. **Modüller birbirini besliyor** — Modül 1'in yapısı Modül 2'yi, Modül 2'nin öğrenci
   verisi hem Modül 9 senaryolarını hem Modül 10 göstergelerini otomatik dolduruyor.
3. **Decimal hassasiyeti uçtan uca korunuyor** — özel `MoneyType` sütun tipi sayesinde
   veritabanına yazılan değer birebir geri okunuyor.
4. **Veri kalitesi ayrı bir boyut olarak ölçülüyor** — Modül 10 performansı ve veri
   hazırlığını ayrı hesaplayıp uyum skorunda birleştiriyor; eksik veri gizlenmiyor.
5. **940 otomatik test** — 412 pytest + 528 senaryo bazlı kontrol; her modül eklendikçe
   öncekilerin regresyonu doğrulandı.

## Test ve Çalıştırma

Bu klasör test kapsamına dahil **değildir**. Uygulama ve testler orijinal dosyalarla çalışır:

```bash
# Kurulum sırası
python seed_data.py
python seed_scenario_data.py
python seed_student_data.py
python seed_ranking_data.py

# Çalıştırma
uvicorn main:app --reload

# Testler (izole test veritabanı kullanır)
pytest
```
