# Strategic University Management and Decision Support System — Backend

Üniversite yönetimi ve karar destek sistemi için geliştirilen FastAPI tabanlı backend altyapısı.

## Teknolojiler

| Paket | Görevi |
|---|---|
| FastAPI | Web API çatısı |
| Uvicorn | ASGI sunucusu |
| SQLAlchemy | Veritabanı ORM katmanı |
| Pydantic Settings | Ayar yönetimi |
| Pandas / OpenPyXL | Excel ve veri işleme (ileriki aşamalar için) |
| python-multipart | Dosya yükleme desteği |

Veritabanı: **SQLite** (`university_management.db`)

## Klasör Yapısı

```
backend/
├── main.py                          # FastAPI uygulamasının giriş noktası
├── seed_data.py                     # Modül 1 örnek verisi
├── seed_scenario_data.py            # Modül 9 örnek baseline ve senaryoları
├── seed_student_data.py             # Modül 2 örnek öğrenci verisi (deterministik)
├── seed_ranking_data.py             # Modül 10 THE/QS/YÖK çerçeve ve gösterge verisi
├── sample_data/                     # İçe aktarma için örnek CSV/XLSX/JSON dosyaları
├── tests/                           # pytest test paketi (izole test veritabanı kullanır)
├── app/
│   ├── database.py                  # SQLAlchemy engine, session ve Base tanımı
│   ├── core/
│   │   ├── config.py                # Pydantic Settings ile uygulama ayarları
│   │   └── decimal_types.py         # Para alanları için kayıpsız Decimal sütun tipi
│   ├── models/                      # Veritabanı modelleri
│   │   ├── faculty.py
│   │   ├── department.py
│   │   ├── academic_program.py
│   │   ├── administrative_unit.py
│   │   ├── import_job.py            # İçe aktarma geçmişi
│   │   ├── scenario.py              # Senaryo başlık kaydı
│   │   ├── scenario_input.py        # Senaryo girdi parametreleri
│   │   ├── scenario_result.py       # Simülasyon sonuçları
│   │   ├── scenario_baseline.py     # Referans (mevcut durum) verileri
│   │   ├── student.py               # Öğrenci
│   │   ├── student_academic_record.py       # Dönemlik akademik kayıt
│   │   ├── program_enrollment_snapshot.py   # Programın yıllık kayıt fotoğrafı
│   │   ├── comparable_university_program.py # Diğer üniversitelerin programları
│   │   ├── evaluation_framework.py  # THE / QS / YÖK çerçeveleri
│   │   ├── evaluation_dimension.py  # Çerçeve boyutları
│   │   ├── evaluation_indicator.py  # Göstergeler
│   │   ├── institutional_metric_value.py    # Kurumun gösterge verisi
│   │   ├── framework_assessment.py  # Hesaplanmış değerlendirme
│   │   ├── dimension_assessment.py  # Boyut kırılımı
│   │   ├── benchmark_institution.py # Karşılaştırma kurumları
│   │   └── benchmark_metric_value.py        # Karşılaştırma gösterge değerleri
│   ├── schemas/                     # Pydantic v2 şemaları (Create/Update/Response)
│   │   ├── faculty.py
│   │   ├── department.py
│   │   ├── academic_program.py
│   │   ├── administrative_unit.py
│   │   ├── data_integration.py      # Import raporu ve iş kaydı şemaları
│   │   ├── scenarios.py             # Senaryo, baseline ve simülasyon şemaları
│   │   ├── students.py              # Öğrenci ve alt kayıt şemaları
│   │   ├── student_analytics.py     # Analitik cevap şemaları
│   │   └── ranking_evaluations.py   # Modül 10 şemaları
│   ├── routers/                     # API endpoint'leri
│   │   ├── health.py
│   │   ├── faculties.py
│   │   ├── departments.py
│   │   ├── programs.py
│   │   ├── administrative_units.py
│   │   ├── data_integration.py      # Toplu veri aktarımı endpoint'leri
│   │   ├── scenarios.py             # Senaryo analizi endpoint'leri
│   │   ├── students.py              # Öğrenci ve akademik kayıt CRUD
│   │   ├── student_analytics.py     # Öğrenci analitiği endpoint'leri
│   │   └── ranking_evaluations.py   # THE/QS/YÖK değerlendirme endpoint'leri
│   └── services/
│       ├── crud_helpers.py          # Ortak 404 / 409 / foreign key kontrolleri
│       ├── file_parser.py           # CSV / XLSX / JSON okuma
│       ├── import_validators.py     # Satır doğrulama kuralları
│       ├── import_service.py        # Aktarım akışı ve transaction yönetimi
│       ├── scenario_engine.py       # Tüm hesaplama formülleri
│       ├── scenario_risk.py         # Risk tespiti ve seviyelendirme
│       ├── scenario_recommendations.py  # Türkçe öneri üretimi
│       ├── student_analytics_service.py # Öğrenci analitiği hesaplamaları
│       ├── student_trend_service.py     # Yıllara göre trend analizi
│       ├── student_alert_service.py     # Erken uyarı üretimi
│       ├── ranking_calculation_service.py    # Değerlendirme hesaplama motoru
│       ├── ranking_readiness_service.py      # Hazırlık katsayıları ve risk
│       ├── ranking_student_sync_service.py   # Modül 1/2 otomatik eşleştirme
│       ├── ranking_benchmark_service.py      # Karşılaştırma analizi
│       ├── ranking_recommendation_service.py # Türkçe stratejik öneriler
│       └── ranking_impact_service.py         # Senaryo etki analizi
├── requirements.txt
└── README.md
```

## Veri Modeli

```
Faculty (1) ──< (N) Department (1) ──< (N) AcademicProgram
                                              │
                                              ├──< (N) Student ──< (N) StudentAcademicRecord
                                              └──< (N) ProgramEnrollmentSnapshot

AdministrativeUnit           (bağımsız tablo)
ImportJob                    (bağımsız tablo — içe aktarma geçmişi)
ComparableUniversityProgram  (bağımsız tablo — dış üniversite verileri)

ScenarioBaseline     (bağımsız tablo — mevcut durum referansı, tek aktif kayıt)
Scenario (1) ──< (N) ScenarioInput
Scenario (1) ──< (N) ScenarioResult

EvaluationFramework (1) ──< (N) EvaluationDimension (1) ──< (N) EvaluationIndicator
                    │                                              │
                    │                                              ├──< (N) InstitutionalMetricValue
                    │                                              └──< (N) BenchmarkMetricValue
                    └──< (N) FrameworkAssessment (1) ──< (N) DimensionAssessment

BenchmarkInstitution (1) ──< (N) BenchmarkMetricValue
```

## Kurulum

Sanal ortamı oluştur (zaten `.venv` varsa bu adım atlanabilir):

```bash
python -m venv .venv
```

Sanal ortamı etkinleştir:

```bash
# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# Windows (CMD)
.venv\Scripts\activate.bat

# macOS / Linux
source .venv/bin/activate
```

Paketleri kur:

```bash
pip install -r requirements.txt
```

## Çalıştırma

`backend` klasörünün içindeyken:

```bash
uvicorn main:app --reload
```

Sunucu varsayılan olarak `http://127.0.0.1:8000` adresinde açılır.

## Örnek Verinin Yüklenmesi

Tabloları örnek kayıtlarla doldurmak için:

```bash
python seed_data.py
```

Script birden fazla kez çalıştırılabilir; aynı `code` değerine sahip kayıtlar tekrar eklenmez.

Eklenen veriler: `FEA` fakültesi, `SWE` ve `CENG` bölümleri, `SWE-BSC` ve `CENG-BSC` programları,
`ERASMUS` idari birimi.

Senaryo analizi (Modül 9) için örnek baseline ve senaryolar ayrı bir script ile yüklenir:

```bash
python seed_scenario_data.py
```

Bu script de tekrar çalıştırılabilir; aynı isimli baseline ve senaryolar yeniden eklenmez.

Öğrenci analitiği (Modül 2) için örnek veri:

```bash
python seed_student_data.py
```

120 öğrenci, 240 akademik kayıt, SWE/CENG için son 4 yılın snapshot'ları ve 7 karşılaştırma
programı ekler. **Deterministiktir** — `random.Random` sabit bir tohumla oluşturulduğu için her
çalıştırmada birebir aynı veri üretilir. `seed_data.py` çalıştırılmadan kullanılamaz (SWE-BSC ve
CENG-BSC programlarına ihtiyaç duyar).

THE/QS/YÖK değerlendirme (Modül 10) için çerçeve ve gösterge verisi:

```bash
python seed_ranking_data.py
```

3 çerçeve, 19 boyut, 40 gösterge, 57 gösterge verisi, 5 karşılaştırma kurumu, 40 karşılaştırma
değeri ve 9 hesaplanmış değerlendirme ekler. Deterministiktir ve tekrar çalıştırılabilir.

**Tam kurulum sırası:**

```bash
python seed_data.py           # fakülte, bölüm, program, idari birim
python seed_scenario_data.py  # senaryo baseline'ı ve örnek senaryolar
python seed_student_data.py   # öğrenciler, akademik kayıtlar, snapshot'lar
python seed_ranking_data.py   # THE/QS/YÖK çerçeveleri, göstergeler, değerlendirmeler
```

## Testler

```bash
pytest
```

Testler geçici bir dizindeki **izole test veritabanını** kullanır; `university_management.db`
dosyasına dokunulmaz (`tests/conftest.py` içinde `DATABASE_URL` ortam değişkeni yönlendirilir).

## Endpoint'ler

### Genel

| Metot | Yol | Açıklama |
|---|---|---|
| GET | `/` | Backend'in çalıştığını bildirir |
| GET | `/health` | Sistemin sağlık durumunu döndürür |
| GET | `/docs` | Otomatik Swagger dokümantasyonu |

### Modül 1 — University Structure and Core Data Management

Dört kaynağın da CRUD yapısı aynıdır:

| Metot | Yol | Açıklama |
|---|---|---|
| GET | `/api/{kaynak}` | Listeler (`skip`, `limit`, `is_active` parametreleri) |
| GET | `/api/{kaynak}/{id}` | Tek kayıt getirir |
| POST | `/api/{kaynak}` | Yeni kayıt oluşturur (201) |
| PUT | `/api/{kaynak}/{id}` | Kısmi günceller |
| DELETE | `/api/{kaynak}/{id}` | Kaydı silmez, `is_active=False` yapar |

Kaynaklar: `faculties`, `departments`, `programs`, `administrative-units`

Ek filtreler:

- `/api/departments?faculty_id=1` — fakülteye göre bölümler
- `/api/programs?department_id=1` — bölüme göre programlar

### Hata Kodları

| Kod | Anlamı |
|---|---|
| 404 | Kayıt bulunamadı ya da `faculty_id` / `department_id` geçersiz |
| 409 | Aynı `code` değeri başka bir kayıtta zaten kullanılıyor |
| 422 | Gönderilen veri şema doğrulamasından geçmedi |

---

## Modül 13 — Data Integration (Toplu Veri Aktarımı)

CSV, Excel veya JSON dosyası yükleyerek dört kaynağa da toplu veri aktarılabilir.

### Endpoint'ler

| Metot | Yol | Açıklama |
|---|---|---|
| POST | `/api/data-integration/import/{resource_type}?preview=` | Dosya yükleyip aktarım yapar |
| GET | `/api/data-integration/templates/{resource_type}` | Boş CSV şablonu indirir |
| GET | `/api/data-integration/jobs` | İçe aktarma geçmişini listeler |
| GET | `/api/data-integration/jobs/{job_id}` | Tek bir işin detayını verir |
| GET | `/api/data-integration/resources` | Desteklenen kaynak ve biçimleri listeler |

`resource_type`: `faculties` · `departments` · `programs` · `administrative-units`
Desteklenen biçimler: `.csv` · `.xlsx` · `.json`

### Ön İzleme Modu

`preview=true` gönderildiğinde dosya okunur ve doğrulanır ama **veritabanına hiçbir kayıt yazılmaz**.
Cevapta kaç satırın geçerli / hatalı / çakışmalı olduğu, satır bazında hata mesajları ve ilk 10
geçerli kayıt (`preview_rows`) döner. Kullanıcı raporu inceleyip dosyayı düzelttikten sonra
`preview=false` ile gerçek aktarımı yapar.

### Beklenen Sütunlar

| Kaynak | Sütunlar |
|---|---|
| faculties | `name`, `code`, `description`, `is_active` |
| departments | `faculty_code`, `name`, `code`, `description`, `is_active` |
| programs | `department_code`, `name`, `code`, `degree_level`, `duration_years`, `quota`, `description`, `is_active` |
| administrative-units | `name`, `code`, `description`, `is_active` |

Bölüm aktarımında `faculty_code`, program aktarımında `department_code` kullanılarak ilgili üst
kayıt bulunur ve foreign key otomatik çözülür. Sütun başlıkları büyük/küçük harf ve boşluk
farklarına toleranslıdır (`Faculty Code`, `faculty-code`, `FACULTY_CODE` hepsi kabul edilir).

### Doğrulama Kuralları

| Kural | Davranış |
|---|---|
| `name` ve `code` zorunlu | Boşsa satır hatalı sayılır |
| `code` normalizasyonu | Boşluklar kırpılır, büyük harfe çevrilir (` swe ` → `SWE`) |
| Dosya içi tekrar | Aynı `code` ikinci kez geçerse çakışma |
| Veritabanı çakışması | `code` zaten varsa çakışma, mevcut kayıt **ezilmez** |
| Geçersiz `faculty_code` / `department_code` | Satır bazında hata |
| `duration_years` | 1 veya daha büyük tam sayı |
| `quota` | 0 veya daha büyük tam sayı |
| `is_active` | `true/false`, `1/0`, `yes/no`, `evet/hayır` kabul edilir; boşsa `true` |

### Sonuç Raporu

```json
{
  "resource_type": "faculties",
  "file_name": "faculties.csv",
  "file_type": "csv",
  "preview": false,
  "total_rows": 6,
  "valid_rows": 3,
  "imported_rows": 1,
  "error_rows": 3,
  "conflict_rows": 2,
  "status": "partial",
  "preview_rows": [{ "name": "Valid Faculty", "code": "VALID1" }],
  "errors": [
    { "row": 2, "field": "name", "value": "", "message": "name alanı zorunludur.", "issue_type": "error" },
    { "row": 6, "field": "code", "value": "FEA", "message": "'FEA' kodu veritabanında zaten mevcut.", "issue_type": "conflict" }
  ],
  "job_id": 12,
  "message": "1 satır aktarıldı, 3 satır hatalı, 2 satır çakışmalı olduğu için atlandı."
}
```

Sayaçların ilişkisi:

```
total_rows    = valid_rows + error_rows
imported_rows = valid_rows - conflict_rows      (preview modunda her zaman 0)
```

- **error_rows** — satır doğrulamadan geçemedi (eksik alan, hatalı sayı, geçersiz üst kod)
- **conflict_rows** — doğrulamayı geçti ama `code` çakıştı (dosya içi veya veritabanı)
- **valid_rows** — doğrulamayı geçen satırlar (çakışanlar dahil)

`status` değerleri: `preview` · `completed` · `partial` · `skipped` · `failed`
(`skipped` = hiçbir satır aktarılmadı ama sistemsel bir hata yok; `failed` = dosya okunamadı
veya veritabanı hatası oluştu.)

### Hata Kodları

| Kod | Durum |
|---|---|
| 415 | Desteklenmeyen dosya biçimi (`.txt`, `.pdf`, `.xls` …) |
| 400 | Boş dosya, sadece başlık içeren dosya, bozuk CSV/XLSX/JSON |
| 422 | Geçersiz `resource_type` |
| 404 | Olmayan `job_id` |

Satır bazındaki hatalar HTTP hatası üretmez — istek 200 döner, sorunlar rapordaki `errors`
listesinde bildirilir. Bunun sebebi: 100 satırlık bir dosyada 2 satır hatalıysa isteğin tamamını
reddetmek yerine 98 satırı aktarıp kullanıcıya sadece düzeltmesi gerekenleri göstermek.

### Transaction Davranışı

Aktarım şu şekilde çalışır:

1. Dosya okunur, tüm satırlar önce **bellekte** doğrulanır — veritabanına henüz dokunulmaz.
2. Mevcut `code` değerleri ve üst kayıt (`code → id`) eşlemesi **tek sorguda** belleğe alınır.
   Satır başına sorgu atılmadığı için büyük dosyalarda performans korunur.
3. Aktarılabilir her satır için `db.begin_nested()` ile bir **SAVEPOINT** açılır. Bir satırda
   beklenmedik bir veritabanı hatası olursa yalnızca o satır geri alınır, önceki satırlar korunur
   ve işlem devam eder.
4. Tüm satırlar işlendikten sonra **tek bir `commit`** yapılır.
5. Beklenmeyen bir hatada (bağlantı kopması, disk hatası) `rollback` ile **tüm işlem geri alınır**;
   rapor `status: "failed"` döner ve yarım veri kalmaz.
6. Kısmi aktarım olduğunda `status: "partial"` ile kaç satırın aktarıldığı açıkça bildirilir.

`preview=true` modunda 3–6. adımlar hiç çalışmaz.

### Import Geçmişi

Her aktarım — ön izlemeler ve başarısız dosya okumaları dahil — `import_jobs` tablosuna kaydedilir.
`GET /api/data-integration/jobs` en yeniden eskiye listeler; `resource_type`, `preview`, `skip`,
`limit` parametreleriyle filtrelenebilir.

### Örnek Kullanım

```bash
# Şablon indir
curl -O -J http://127.0.0.1:8000/api/data-integration/templates/faculties

# Önce ön izleme yap (veritabanına yazmaz)
curl -X POST "http://127.0.0.1:8000/api/data-integration/import/faculties?preview=true" \
     -F "file=@sample_data/faculties_sample.csv"

# Rapor uygunsa gerçek aktarımı yap
curl -X POST "http://127.0.0.1:8000/api/data-integration/import/faculties?preview=false" \
     -F "file=@sample_data/faculties_sample.csv"

# Geçmişi görüntüle
curl http://127.0.0.1:8000/api/data-integration/jobs
```

### Örnek Dosyalar

`sample_data/` klasöründe her kaynak için CSV, Excel ve JSON örnekleri bulunur. Üç biçim de **aynı
kayıtları** içerir; bu yüzden birini aktardıktan sonra diğerini yüklerseniz tüm satırlar çakışma
olarak raporlanır — bu beklenen davranıştır.

`faculties_with_errors_sample.csv` bilinçli olarak hatalı satırlar içerir (eksik alan, geçersiz
`is_active`, dosya içi tekrar, veritabanında var olan kod) ve hata raporunu denemek için kullanılır.

---

## Modül 2 — Strategic Education and Student Analytics

Üniversite, fakülte, bölüm ve program düzeyinde öğrenci sayılarını, kayıtları, mezuniyetleri,
akademik başarıyı, program dolulukları, burslu ve uluslararası öğrenci oranlarını, öğrenci kaybını
ve yıllara göre eğilimleri analiz eder; eşik dışına çıkan metrikler için erken uyarı üretir.

### Veri Modelleri

| Model | Görevi |
|---|---|
| `Student` | Öğrenci kaydı; durum, burs, uyruk, GPA, kayıt/mezuniyet yılları |
| `StudentAcademicRecord` | Dönemlik performans (ders, kredi, GPA, kayıt yenileme) |
| `ProgramEnrollmentSnapshot` | Programın yıllık kontenjan, yerleşme ve taban puan fotoğrafı |
| `ComparableUniversityProgram` | Diğer üniversitelerin benzer programları (karşılaştırma) |

`Student.current_status` değerleri: `newly-enrolled` · `active` · `graduated` · `suspended` ·
`dropped-out` · `non-renewed`
`Student.gender` değerleri: `male` · `female` · `other` · `unspecified`
`StudentAcademicRecord.semester` değerleri: `fall` · `spring` · `summer`

### CRUD Endpoint'leri

**Öğrenci**

| Metot | Yol | Açıklama |
|---|---|---|
| POST | `/api/students` | Öğrenci oluşturur (201) |
| GET | `/api/students` | Listeler (aşağıdaki filtrelerle) |
| GET | `/api/students/{id}` | Detay |
| PUT | `/api/students/{id}` | Kısmi günceller |
| DELETE | `/api/students/{id}` | Silmez, `is_active=false` yapar |

Listeleme filtreleri: `academic_program_id`, `department_id`, `faculty_id`, `current_status`,
`is_international`, `preparatory_school`, `enrollment_year`, `is_active`, `search`, `skip`, `limit`.
`search` parametresi `student_number`, `first_name` ve `last_name` üzerinde büyük/küçük harf
duyarsız arama yapar.

**Akademik kayıtlar**

| Metot | Yol |
|---|---|
| POST | `/api/students/{student_id}/academic-records` |
| GET | `/api/students/{student_id}/academic-records` |
| GET | `/api/students/{student_id}/academic-records/{record_id}` |
| PUT | `/api/students/{student_id}/academic-records/{record_id}` |
| DELETE | `/api/students/{student_id}/academic-records/{record_id}` |

**Program snapshot ve karşılaştırma**

| Metot | Yol |
|---|---|
| POST/GET | `/api/student-analytics/program-snapshots` |
| GET/PUT/DELETE | `/api/student-analytics/program-snapshots/{snapshot_id}` |
| POST/GET | `/api/student-analytics/comparable-programs` |
| GET/PUT/DELETE | `/api/student-analytics/comparable-programs/{comparison_id}` |

### Analitik Endpoint'leri

| Metot | Yol | Açıklama |
|---|---|---|
| GET | `/api/student-analytics/overview` | Genel öğrenci özeti |
| GET | `/api/student-analytics/by-program` | Program bazlı analitik |
| GET | `/api/student-analytics/by-department` | Bölüm bazlı (program sonuçları birleştirilir) |
| GET | `/api/student-analytics/by-faculty` | Fakülte bazlı (bölüm sonuçları birleştirilir) |
| GET | `/api/student-analytics/trends` | Yıllara göre metrik gelişimi |
| GET | `/api/student-analytics/programs/{id}/demand` | Programın talep analizi |
| GET | `/api/student-analytics/programs/{id}/comparisons` | Diğer üniversitelerle karşılaştırma |
| GET | `/api/student-analytics/alerts` | Erken uyarılar |

Ortak filtreler: `faculty_id`, `department_id`, `academic_program_id`, `academic_year`.

`trends` için `metric` parametresi: `total-students` · `newly-enrolled` · `graduates` ·
`occupancy-rate` · `graduation-rate` · `attrition-rate` · `non-renewal-rate` ·
`scholarship-percentage` · `international-percentage` · `average-gpa` · `minimum-admission-score`

### Hesaplama Formülleri

Tüm formüller `app/services/student_analytics_service.py` içindedir. **Bütün yüzdeler
`ROUND_HALF_UP` ile iki ondalık basamağa yuvarlanır** ve her bölme `percentage()` / `ratio()`
yardımcılarından geçer — payda sıfırsa hata fırlatmak yerine `0.00` döner.

```
occupancy_rate = enrolled_student_count / quota × 100

graduation_rate = graduated / (graduated + active + dropped_out) × 100

attrition_rate = dropped_out / total_students × 100

non_renewal_rate = non_renewed / total_students × 100

scholarship_student_percentage =
    (scholarship_rate_percent > 0 olan öğrenci sayısı) / total_students × 100

international_student_percentage =
    (is_international = true olan öğrenci sayısı) / total_students × 100

average_graduation_duration_years =
    AVG(actual_graduation_year − enrollment_year)      -- yalnızca mezun öğrenciler

average_gpa = AVG(current_gpa)

passed_course_ratio     = SUM(passed_course_count) / SUM(registered_course_count) × 100
credit_efficiency_ratio = SUM(earned_credits) / SUM(attempted_credits)
```

**Mezuniyet oranının paydası neden `graduated + active + dropped_out`?**
Kaydını yenilemeyen (`non-renewed`) öğrenciler henüz kesin ayrılmış sayılmadığı için paydaya dahil
edilmez; bunlar ayrı bir metrikte (`non_renewal_rate`) izlenir.

**Bölüm ve fakülte düzeyinde birleştirme:** Doluluk oranı basit ortalama ile değil, **kontenjan
toplamı üzerinden ağırlıklı** hesaplanır. Aksi halde 10 kişilik bir program ile 200 kişilik bir
program eşit ağırlık alırdı. GPA ortalaması da öğrenci sayısıyla ağırlıklandırılır.

### Kapasite ve Talep Trendi

```
demand_trend:
  Son 3 yılın doluluk oranı ve taban puanı birlikte değerlendirilir.
  ├─ ikisi de sürekli yükseliyorsa  → increasing
  ├─ ikisi de sürekli düşüyorsa     → decreasing
  └─ diğer bütün durumlarda         → stable
```

Tek ölçüte bakmak yanıltıcı olurdu: kontenjan artırılınca doluluk düşebilir ama taban puan
yükselmeye devam edebilir. Taban puan verisi eksikse ölçüt kararsız kabul edilir ve `stable` döner.

Trend serilerinde genel yön, ilk ve son değer arasındaki fark **%5**'i aştığında `increasing` /
`decreasing`, aksi halde `stable` olur.

### Erken Uyarılar

| Kod | Koşul | Varsayılan eşik |
|---|---|---|
| `low_occupancy_rate` | Doluluk oranı eşiğin altında | %50 |
| `high_attrition_rate` | Öğrenci kaybı eşiği aşıyor | %15 |
| `high_non_renewal_rate` | Kayıt yenilememe eşiği aşıyor | %10 |
| `low_graduation_rate` | Mezuniyet oranı eşiğin altında | %40 |
| `low_average_gpa` | Ortalama GPA eşiğin altında | 2.00 |
| `low_international_percentage` | Uluslararası oran hedefin altında | %5 (parametre) |
| `declining_admission_score` | Taban puan 2 yıl üst üste düştü | — |
| `declining_student_demand` | Yerleşen öğrenci 3 yıl üst üste düştü | — |

**Şiddet seviyeleri** (`info` · `warning` · `high` · `critical`) eşikten sapmanın büyüklüğüne göre
belirlenir: eşiğin biraz altındaki bir değerle çok altındaki bir değeri aynı seviyede göstermek
yöneticiyi yanıltırdı. Sapma kritik aralığın tamamını geçtiyse `critical`, yarısını geçtiyse
`high`, aksi halde `warning` olur. Uluslararası oran uyarısı bilgilendirme amaçlı olduğu için her
zaman `info`, üç yıllık talep düşüşü ise stratejik olduğu için her zaman `critical` üretir.

Her uyarı `code`, `severity`, `entity_type`, `entity_id`, `entity_name`, `metric`,
`current_value`, `threshold`, `message` ve `recommendation` alanlarını içerir. Uyarılar en kritik
olan üstte olacak şekilde sıralanır. `severity` query parametresiyle filtrelenebilir.

### Doğrulama Kuralları

| Kural | Hata |
|---|---|
| `student_number` benzersiz (boşluk kırpılır, büyük harfe çevrilir) | 409 |
| `academic_program_id` geçerli olmalı | 404 |
| `scholarship_rate_percent` 0–100 | 422 |
| `current_gpa`, `semester_gpa`, `cumulative_gpa` 0–4 | 422 |
| `enrollment_year` 1950–2100 | 422 |
| `actual_graduation_year` ≥ `enrollment_year` | 422 |
| `passed_course_count + failed_course_count` ≤ `registered_course_count` | 422 |
| `earned_credits` ≤ `attempted_credits` | 422 |
| `semester` ∈ {fall, spring, summer} | 422 |
| `academic_year` `YYYY-YYYY` biçiminde ve yıllar ardışık | 422 |
| `quota` > 0, öğrenci sayıları ≥ 0, taban puan ≥ 0 | 422 |
| Aynı öğrenci + akademik yıl + dönem kaydı | 409 |
| Aynı program + akademik yıl snapshot'ı | 409 |
| Aynı üniversite + program + yıl karşılaştırması | 409 |

Tüm hata mesajları Türkçedir. Benzersizlik kuralları hem veritabanı seviyesinde
(`UniqueConstraint`) hem de API katmanında kontrol edilir; API katmanındaki ön kontrol sayesinde
kullanıcı ham bütünlük hatası yerine anlaşılır bir 409 mesajı görür.

### Performans

Analitik endpoint'leri **N+1 sorgu üretmez**:

- Bütün sayımlar SQL tarafında `SUM(CASE WHEN ... THEN 1 ELSE 0 END)` kalıbıyla yapılır. Genel
  bakışta 11 ayrı `COUNT` sorgusu yerine **tek sorgu** çalışır.
- Program kırılımı `GROUP BY academic_program_id` ile tek sorguda alınır; her program için ayrı
  sorgu atılmaz.
- Program/bölüm/fakülte adları tek `JOIN`'li sorguda çekilir.
- Bölüm ve fakülte analizleri, program sonuçları üzerine toplama yaparak üretilir — aynı SQL
  sorguları ikinci kez çalıştırılmaz.
- Snapshot geçmişi tek sorguda çekilip bellekte gruplanır (veri seti program×yıl kadar küçüktür).
- Seed script'i bile 120 öğrenci için 120 `SELECT` yerine mevcut numaraları tek sorguda alır.
- Öğrenci kayıtları hiçbir zaman toplu olarak Python belleğine çekilmez; listeleme
  endpoint'lerinde `skip`/`limit` zorunludur.

**Eklenen index'ler:**

| Tablo | Index |
|---|---|
| `students` | `student_number` (unique), `academic_program_id`, `current_status`, `enrollment_year`, `is_international`, `preparatory_school`, `is_active`, `actual_graduation_year` |
| `student_academic_records` | `student_id`, `academic_year`, unique(`student_id`, `academic_year`, `semester`) |
| `program_enrollment_snapshots` | `academic_program_id`, `academic_year`, unique(`academic_program_id`, `academic_year`) |
| `comparable_university_programs` | `university_name`, `program_name`, `city`, `academic_year`, `is_competitor` |

### Veri Entegrasyonu (Modül 13 Genişletmesi)

Dört yeni `resource_type` eklendi; CSV, XLSX ve JSON biçimlerinin üçü de desteklenir ve her biri
için şablon endpoint'i çalışır:

| resource_type | Anahtar sütun(lar) | Üst kayıt eşleşmesi |
|---|---|---|
| `students` | `student_number` | `academic_program_code` → AcademicProgram |
| `student-academic-records` | `student_number` + `academic_year` + `semester` | `student_number` → Student |
| `program-enrollment-snapshots` | `academic_program_code` + `academic_year` | `academic_program_code` → AcademicProgram |
| `comparable-university-programs` | `university_name` + `program_name` + `academic_year` | — |

```bash
curl -O -J http://127.0.0.1:8000/api/data-integration/templates/students
curl -X POST "http://127.0.0.1:8000/api/data-integration/import/students?preview=true" \
     -F "file=@sample_data/students_sample.csv"
```

Bu genişletme için `import_validators.py` **bildirimsel** hale getirildi: her kaynak artık hangi
sütunların metin / tam sayı / ondalık / boolean / sabit değer (enum) / akademik yıl olduğunu bir
`ResourceSpec` içinde tanımlar. Doğrulama fonksiyonu bu tanımı okuyarak çalışır, dolayısıyla yeni
bir kaynak eklemek yeni kod yazmayı değil, tek bir tanım satırı eklemeyi gerektirir. Mevcut dört
kaynağın (fakülte, bölüm, program, idari birim) davranışı ve şablon sütunları **hiç değişmedi**.

Çakışma tespiti de bileşik anahtarları destekleyecek şekilde genelleştirildi; artık "aynı öğrencinin
aynı dönemi" veya "aynı programın aynı yılı" gibi çok alanlı benzersizlikler de dosya içi ve
veritabanı çakışması olarak raporlanır.

`sample_data/` klasöründe dört kaynak için de CSV/XLSX/JSON örnekleri ve bilinçli olarak hatalı
satırlar içeren `students_with_errors_sample.csv` bulunur.

### Senaryo Modülüyle Entegrasyon (Modül 9)

**1. Öğrenci sayısını baseline'a senkronize etme**

```
POST /api/scenarios/baselines/sync-student-data
```

Aktif baseline'ın `student_count` alanını Modül 2'deki **aktif öğrenci sayısıyla** günceller
(`is_active = true` ve durumu `active` veya `newly-enrolled` olanlar; mezun ve ayrılanlar sayılmaz).
Eski ve yeni değeri birlikte döndürür. Aktif baseline yoksa **409** döner.

Sadece öğrenci sayısı senkronize edilir. Derslik/laboratuvar kapasitesi program snapshot
verilerinden türetilmeye **çalışılmaz**; snapshot'lar kontenjan bilgisidir, fiziksel kapasite
değildir ve bu iki kavramı karıştırmak yanlış kapasite riskleri üretirdi.

```json
{
  "baseline_id": 1,
  "baseline_name": "2026 University Baseline",
  "previous_student_count": 5000,
  "new_student_count": 83,
  "difference": -4917,
  "message": "Aktif baseline'ın öğrenci sayısı 5000 değerinden 83 değerine güncellendi (fark: -4917)."
}
```

**2. Canlı öğrenci verisiyle simülasyon**

`preview` ve `simulate` endpoint'lerine `use_live_student_data` query parametresi eklendi:

| Değer | Davranış |
|---|---|
| `false` (varsayılan) | `baseline.student_count` kullanılır — **mevcut davranış aynen korunur** |
| `true` | Başlangıç öğrenci sayısı Student tablosundaki aktif öğrenci sayısından alınır |

Her iki cevapta da yeni alanlar döner:

```json
{
  "student_data_source": "live-student-module",
  "live_active_student_count": 83
}
```

`student_data_source` `"baseline"` veya `"live-student-module"` olur. Canlı veri kullanıldığında
baseline kaydı **değiştirilmez**; hesaplama motoruna geçici bir `student_count_override` verilir,
böylece bir simülasyon kalıcı veriyi bozmaz.

### Swagger'da Denenebilecek Örnek İstekler

**Öğrenci oluşturma** — `POST /api/students`

```json
{
  "student_number": "S2026001",
  "first_name": "Elif",
  "last_name": "Yıldız",
  "gender": "female",
  "nationality": "Türkiye",
  "is_international": false,
  "scholarship_rate_percent": "50",
  "enrollment_year": 2026,
  "current_status": "newly-enrolled",
  "preparatory_school": true,
  "academic_program_id": 1,
  "current_gpa": null,
  "expected_graduation_year": 2030
}
```

**Akademik kayıt** — `POST /api/students/1/academic-records`

```json
{
  "academic_year": "2026-2027",
  "semester": "fall",
  "registered_course_count": 6,
  "passed_course_count": 5,
  "failed_course_count": 1,
  "earned_credits": 25,
  "attempted_credits": 30,
  "semester_gpa": "3.10",
  "cumulative_gpa": "3.10",
  "registration_renewed": true
}
```

**Program snapshot** — `POST /api/student-analytics/program-snapshots`

```json
{
  "academic_program_id": 1,
  "academic_year": "2025-2026",
  "quota": 80,
  "enrolled_student_count": 79,
  "minimum_admission_score": "441.90",
  "national_average_minimum_score": "389.80",
  "ankara_average_minimum_score": "406.20",
  "graduated_student_count": 49,
  "dropped_out_student_count": 3,
  "non_renewed_student_count": 2
}
```

**Karşılaştırma programı** — `POST /api/student-analytics/comparable-programs`

```json
{
  "university_name": "Orta Doğu Teknik Üniversitesi",
  "program_name": "Computer Engineering",
  "city": "Ankara",
  "academic_year": "2025-2026",
  "quota": 130,
  "enrolled_student_count": 130,
  "occupancy_rate": "100.00",
  "minimum_admission_score": "498.40",
  "is_competitor": true
}
```

**Analitik sorguları**

```bash
# Genel bakış
curl "http://127.0.0.1:8000/api/student-analytics/overview"

# Bir fakültenin program kırılımı
curl "http://127.0.0.1:8000/api/student-analytics/by-program?faculty_id=1"

# Bir programın doluluk trendi
curl "http://127.0.0.1:8000/api/student-analytics/trends?metric=occupancy-rate&start_year=2022&end_year=2025&academic_program_id=2"

# Talep analizi ve karşılaştırma
curl "http://127.0.0.1:8000/api/student-analytics/programs/1/demand"
curl "http://127.0.0.1:8000/api/student-analytics/programs/1/comparisons"

# Sadece kritik uyarılar
curl "http://127.0.0.1:8000/api/student-analytics/alerts?severity=critical"
```

### Örnek Cevaplar

`GET /api/student-analytics/overview`

```json
{
  "total_students": 120,
  "newly_enrolled_students": 8,
  "active_students": 75,
  "graduated_students": 17,
  "preparatory_school_students": 6,
  "dropped_out_students": 5,
  "non_renewed_students": 12,
  "scholarship_student_percentage": "33.33",
  "international_student_percentage": "16.67",
  "average_gpa": "2.47",
  "average_graduation_duration_years": "4.35",
  "passed_course_ratio": "88.43",
  "credit_efficiency_ratio": "0.88",
  "applied_filters": { "faculty_id": null, "department_id": null, "academic_program_id": null, "academic_year": null }
}
```

`GET /api/student-analytics/by-program` (tek kayıt)

```json
{
  "program_id": 1,
  "program_name": "Software Engineering Bachelor's Program",
  "program_code": "SWE-BSC",
  "department_id": 1,
  "department_name": "Software Engineering",
  "faculty_id": 1,
  "faculty_name": "Faculty of Engineering and Architecture",
  "quota": 80,
  "enrolled_student_count": 79,
  "occupancy_rate": "98.75",
  "active_student_count": 43,
  "graduate_count": 7,
  "graduation_rate": "13.21",
  "dropped_out_count": 3,
  "attrition_rate": "5.00",
  "non_renewed_count": 6,
  "non_renewal_rate": "10.00",
  "scholarship_student_percentage": "33.33",
  "international_student_percentage": "33.33",
  "average_gpa": "2.43",
  "average_graduation_duration_years": "4.29",
  "minimum_admission_score": "441.90",
  "demand_trend": "increasing",
  "total_students": 60
}
```

`GET /api/student-analytics/alerts` (tek uyarı)

```json
{
  "code": "declining_student_demand",
  "severity": "critical",
  "entity_type": "program",
  "entity_id": 2,
  "entity_name": "Computer Engineering Bachelor's Program",
  "metric": "enrolled_student_count",
  "current_value": "44",
  "threshold": "88",
  "message": "Computer Engineering Bachelor's Program programına yerleşen öğrenci sayısı 3 yıl üst üste düştü (88 → 44).",
  "recommendation": "Program için kapsamlı bir talep analizi yapılmalı; kontenjan azaltma, program birleştirme veya yeniden konumlandırma seçenekleri değerlendirilmelidir."
}
```

---

## Modül 10 — THE, QS ve YÖK Değerlendirme ve İzleme Yönetimi

> ### ⚠️ ÖNEMLİ UYARI
> **Bu modül gerçek THE, QS veya YÖK sıralaması ÜRETMEZ ve resmi sıralama tahmini YAPMAZ.**
> Üretilen skorlar yalnızca kurumun kendi verisine dayanan **iç performans izleme**
> (institutional performance monitoring), **veri hazırlık** (data readiness), **iç uyum**
> (internal compliance) ve **iyileştirme takibi** (improvement tracking) amaçlıdır.
> Seed verisindeki ağırlıklar ve eşikler resmi metodolojinin kopyası değil, ondan esinlenen
> yapılandırılabilir değerlerdir. Karşılaştırma kurumları tamamen **DEMO** verisidir.

### Amaç

Üniversitenin THE, QS ve YÖK değerlendirme başlıklarındaki durumunu izler; hangi verinin
eksik olduğunu, hangi göstergede zayıf kalındığını ve hangi iyileştirmenin en çok kazanç
sağlayacağını gösterir.

### Veri Modeli

| Model | Görevi |
|---|---|
| `EvaluationFramework` | THE / QS / YÖK çerçeveleri. Anahtar: `code + methodology_year` |
| `EvaluationDimension` | Çerçevenin ana başlıkları (ağırlıklı) |
| `EvaluationIndicator` | Ölçülebilir göstergeler (hesaplama türü, yön, sınırlar) |
| `InstitutionalMetricValue` | Kurumun yıllık gösterge verisi (value / numerator / denominator) |
| `FrameworkAssessment` | Hesaplanmış çerçeve değerlendirmesi |
| `DimensionAssessment` | Değerlendirmenin boyut kırılımı |
| `BenchmarkInstitution` | Karşılaştırma kurumları (demo) |
| `BenchmarkMetricValue` | Karşılaştırma kurumlarının gösterge değerleri |

**Metodoloji sürümleme:** Çerçeve anahtarı `code + methodology_year` olduğu için THE 2025 ve
THE 2026 metodolojileri aynı anda saklanabilir. Geçmiş değerlendirmeler hangi metodolojiyle
hesaplandıysa o haliyle korunur.

**Gösterge kodu benzersizliği:** `EvaluationIndicator.code` sistem genelinde benzersizdir.
Bu, istenen "aynı boyut içinde benzersiz" kuralını kapsayan daha güçlü bir kısıttır ve
CSV/Excel içe aktarımında göstergeye tek bir metinle referans vermeyi mümkün kılar.
Seed kodları çerçeve ön ekiyle üretilir: `the-`, `qs-`, `yok-`.

**Projeye özel alanlar:** `auto_source_key` (Modül 1/2'den otomatik doldurma anahtarı),
`impact_numerator_variable` / `impact_denominator_variable` (senaryo etki analizi eşleşmesi).

### Seed İçeriği

| Çerçeve | Boyut | Gösterge |
|---|---|---|
| THE 2026 | Teaching Environment, Research Environment, Research Quality, International Outlook, Industry Income and Patents | 15 |
| QS 2026 | Academic Reputation, Citations per Faculty, Employer Reputation, Employment Outcomes, Faculty Student Ratio, International Faculty Ratio, International Student Ratio, International Research Network, Sustainability | 9 |
| YÖK 2026 | Eğitim ve Öğretim, Araştırma/Geliştirme/Proje/Yayın, Uluslararasılaşma, Sürdürülebilirlik, Topluma Hizmet ve Sosyal Sorumluluk | 16 |

Her çerçevenin boyut ağırlıkları 100 toplar. Seed verisi bilinçli olarak **eksik ve kısmi
gösterge örnekleri** içerir (`the-research-reputation`, `qs-sustainability-score`,
`yok-waste-recycling-ratio` eksik bırakılmıştır) — eksik veri analizi ve readiness hesabı
gerçek veriyle test edilebilsin diye.

### Hesaplama Mantığı

Zincir: **ham veri → etkin değer → 0-100 performans skoru → boyut skoru → çerçeve skoru →
uyum skoru → risk**

**1. Etkin değer** (`calculation_type`'a göre)

| Tür | Formül |
|---|---|
| `raw` / `manual` | doğrudan `value` |
| `percentage` | `numerator / denominator × 100` |
| `ratio` | `numerator / denominator` |
| `score` | doğrudan 0-100 skor |
| `boolean` | değer ≠ 0 → 100, değer = 0 → 0 |

Pay/payda ile elle girilen `value` çelişirse **hesaplanan değer esas alınır** ve
`calculation_notes` alanına açık bir not düşülür. Sessizce birini seçmek raporu okuyanı
yanıltırdı.

**2. Performans skoru (0-100 normalizasyon)**

```
higher_is_better:
    value >= target      -> 100
    value <= minimum     -> 0
    arada               -> (value - minimum) / (target - minimum) × 100

lower_is_better:
    value <= target      -> 100
    value >= maximum     -> 0
    arada               -> (maximum - value) / (maximum - target) × 100

target_is_best:
    value == target      -> 100
    value <  target      -> (value - minimum) / (target - minimum) × 100
    value >  target      -> (maximum - value) / (maximum - target) × 100
```

**Sınır eksikse hata verilmez**, açıklanabilir bir fallback uygulanır ve `calculation_notes`
alanına not eklenir:

| Durum | Fallback |
|---|---|
| `higher_is_better`, minimum yok | 0 kabul edilir |
| `higher_is_better`, target yok ama maximum var | maximum hedef kabul edilir |
| `higher_is_better`, hiç sınır yok | ham değer 0-100 aralığına kırpılır |
| `lower_is_better`, target yok | minimum (yoksa 0) hedef kabul edilir |
| `lower_is_better`, maximum yok | hedefin altı 100, üstü 0 (ikili değerlendirme) |
| `target_is_best`, minimum/maximum yok | oransal değerlendirme |
| minimum == target | eşik karşılaştırması |

**3. Readiness (veri hazırlık) skoru**

`required_for_readiness=True` göstergeler dikkate alınır. Katsayılar tek yerde tanımlıdır
(`app/services/ranking_readiness_service.py`):

| Veri durumu | Katsayı |
|---|---|
| `available` | 1.00 |
| `estimated` | 0.75 |
| `partial` | 0.50 |
| `missing` | 0.00 |
| `invalid` | 0.00 |

```
readiness = Σ(katsayı × 100 × gösterge ağırlığı) / Σ(gösterge ağırlığı)
```

**4. Boyut skoru**

```
performance = Σ(gösterge skoru × gösterge ağırlığı) / Σ(skoru hesaplanabilen göstergelerin ağırlığı)
weighted_score = performance × boyut ağırlığı / 100
```

Veri olmayan göstergeler **paydaya dahil edilmez**. Eksik veriyi 0 saymak, veri toplayamayan
bir kurumu "kötü performanslı" göstererek raporu yanıltırdı; eksiklik ayrıca readiness
skorunda ölçülür.

**5. Çerçeve skoru ve uyum**

```
performance = Σ(boyut performansı × boyut ağırlığı) / Σ(boyut ağırlığı)
readiness   = Σ(boyut hazırlığı × boyut ağırlığı) / Σ(boyut ağırlığı)

compliance  = performance × readiness / 100
```

Uyum formülünün mantığı: bir skorun ne kadar güvenilir olduğu, onu üreten verinin ne kadar
tam olduğuna bağlıdır. Performansı 80 olan ama verisinin yalnızca yarısı hazır bir çerçevenin
gerçek uyum düzeyi 40'tır.

**6. Risk seviyeleri**

Uyum skoru üzerinden:

| Aralık | Risk |
|---|---|
| 75 – 100 | `low` |
| 50 – 74.99 | `medium` |
| 25 – 49.99 | `high` |
| 0 – 24.99 | `critical` |

**Hazırlık tabanı:** Veri yetersizken risk yapay olarak düşük görünemez.

- `readiness < 50` → risk en az `high`
- `readiness < 25` → risk her zaman `critical`

**7. Eksik veri analizi**

Her eksik/kısmi/geçersiz gösterge için şunlar üretilir: gösterge ve boyut adı, çerçeve,
veri durumu, beklenen veri kaynağı ve **tahmini readiness kaybı**:

```
kayıp = boyut ağırlık payı × göstergenin boyut içindeki ağırlık payı × (1 − hazırlık katsayısı) × 100
```

### Modül 1/2 ile Otomatik Veri Eşleştirmesi

`POST /api/ranking-evaluations/metrics/sync-student-data` mevcut öğrenci verisinden şu
göstergeleri otomatik hesaplar:

`total_student_count` · `active_student_count` · `newly_enrolled_student_count` ·
`graduate_count` · `preparatory_student_count` · `international_student_count` ·
`international_student_ratio` · `scholarship_student_ratio` · `graduation_rate` ·
`attrition_rate` · `non_renewal_rate` · `average_graduation_duration` ·
`program_occupancy_rate` · `doctoral_student_count` · `doctoral_to_bachelor_ratio` ·
`active_program_count` · `students_per_program`

Sistemde akademik personel modeli bulunmadığı için **personel, yayın, atıf, araştırma geliri
gibi veriler uydurulmaz**; bunlar `InstitutionalMetricValue` üzerinden elle veya içe
aktarımla doldurulur.

**Öncelik kuralı:** Elle girilmiş (`manual`) ve içe aktarılmış (`imported`) veriler otomatik
senkronizasyonla **ezilmez** — doğrulanmış insan verisi önceliklidir. Bu davranış
`overwrite_manual=true` ile bilinçli olarak değiştirilebilir. Her kaydın kaynağı API
cevabında `origin` alanında görünür: `automatic` · `manual` · `imported`.

### Endpoint Tablosu

**Çerçeve yönetimi**

| Metot | Yol | Açıklama |
|---|---|---|
| GET | `/api/ranking-evaluations/frameworks` | Listeler (ağırlık dengesiyle) |
| POST | `/api/ranking-evaluations/frameworks` | Oluşturur (201) |
| GET | `/api/ranking-evaluations/frameworks/{id}` | Detay |
| PUT | `/api/ranking-evaluations/frameworks/{id}` | Günceller |
| DELETE | `/api/ranking-evaluations/frameworks/{id}` | Pasifleştirir (soft delete) |

**Boyut ve gösterge yönetimi**

| Metot | Yol |
|---|---|
| GET / POST | `/api/ranking-evaluations/dimensions` |
| GET / PUT / DELETE | `/api/ranking-evaluations/dimensions/{dimension_id}` |
| GET / POST | `/api/ranking-evaluations/indicators` |
| GET / PUT / DELETE | `/api/ranking-evaluations/indicators/{indicator_id}` |

**Gösterge verisi**

| Metot | Yol | Açıklama |
|---|---|---|
| GET | `/api/ranking-evaluations/metrics` | Hesaplanmış değer ve skorla listeler |
| POST | `/api/ranking-evaluations/metrics` | Oluşturur (201) |
| GET / PUT | `/api/ranking-evaluations/metrics/{metric_id}` | Detay / güncelleme |
| DELETE | `/api/ranking-evaluations/metrics/{metric_id}` | Siler (204) |
| POST | `/api/ranking-evaluations/metrics/sync-student-data` | Modül 1/2'den otomatik doldurur |

**Değerlendirme**

| Metot | Yol | Açıklama |
|---|---|---|
| POST | `/api/ranking-evaluations/assessments/calculate` | Hesaplar (`persist=false` ile deneme) |
| GET | `/api/ranking-evaluations/assessments` | Geçmiş değerlendirmeler |
| GET | `/api/ranking-evaluations/assessments/{id}` | Tam rapor |
| GET | `/api/ranking-evaluations/assessments/latest/{framework_code}` | En güncel değerlendirme |
| GET | `/api/ranking-evaluations/assessments/{id}/dimensions` | Boyut kırılımı |
| GET | `/api/ranking-evaluations/assessments/{id}/missing-data` | Eksik veri analizi |

**Karşılaştırma, trend, öneri, senaryo, panel**

| Metot | Yol | Açıklama |
|---|---|---|
| GET / POST | `/api/ranking-evaluations/benchmarks/institutions` | Karşılaştırma kurumları |
| GET / PUT / DELETE | `/api/ranking-evaluations/benchmarks/institutions/{id}` | Detay / güncelleme / pasifleştirme |
| POST | `/api/ranking-evaluations/benchmarks/values` | Karşılaştırma gösterge değeri |
| GET | `/api/ranking-evaluations/benchmarks/comparison` | Karşılaştırma raporu |
| GET | `/api/ranking-evaluations/trends/{framework_code}` | Yıllara göre gelişim |
| GET | `/api/ranking-evaluations/recommendations/{assessment_id}` | Stratejik öneriler |
| POST | `/api/ranking-evaluations/impact-preview` | Senaryo etkisi (kayıt yazmaz) |
| GET | `/api/ranking-evaluations/dashboard-summary` | Genel bakış paneli |

**Desteklenen filtreler:** `framework_code`, `framework_id`, `dimension_id`, `indicator_id`,
`academic_year`, `period`, `data_status`, `origin`, `is_active`, `required_for_readiness`,
`skip`, `limit`.

### Karşılaştırma (Benchmark)

`scope` parametresiyle beş kapsam desteklenir:

| Kapsam | Anlamı |
|---|---|
| `previous-years` | Kurumun kendi geçmiş yıl ortalaması |
| `national` | Türkiye ulusal ortalaması (`institution_type=national-average`) |
| `similar` | Benzer üniversiteler |
| `competitors` | Seçilmiş rakip üniversiteler |
| `all` | Tüm aktif karşılaştırma kurumları |

Her satırda `university_value`, `benchmark_average`, `difference`, `percentage_difference`,
`performance_status` (`above` / `near` / `below` / `unknown`) bulunur. `rank` ve `percentile`
**yalnızca en az 3 karşılaştırma kaydı varsa** hesaplanır; aksi halde açık bir `warning`
döndürülür. Ortalamaya ±%5 yakınlıktaki değerler `near` sayılır. `lower_is_better` yönlü
göstergelerde karşılaştırma yönü ters çevrilir.

### Stratejik Öneriler

Öneriler sabit cümleler değildir; mevcut değer, hedef ve fark kullanılarak dinamik üretilir.
Her öneri şu alanları içerir: `framework`, `dimension`, `indicator`, `indicator_code`,
`current_value`, `target_value`, `gap`, `urgency`, `expected_score_gain`, `recommendation`,
`required_data_or_action`.

`expected_score_gain`, gösterge hedefe ulaşırsa çerçeve performans skorunda beklenen artışı
puan cinsinden verir:

```
kazanç = (100 − mevcut skor) × göstergenin boyut içindeki payı × boyutun çerçeve içindeki payı
```

Öneri türleri: veri eksikliği toplama, veri doğrulama süreci kurma, uluslararası öğrenci
oranını artırma, uluslararası akademik personel oranını artırma, atıf etkisini yükseltme,
personel başına yayın artırma, araştırma geliri artırma, sanayi geliri artırma, patent
sayısını artırma, doktora mezunu sayısını artırma, öğrenci/personel oranını iyileştirme,
istihdam ve itibar göstergelerini yükseltme, sürdürülebilirlik ve topluma hizmet
raporlamasını güçlendirme.

Öneriler aciliyet (`critical` → `low`) ve beklenen kazanca göre sıralanır.

### Senaryo Etki Analizi (What-if)

`POST /api/ranking-evaluations/impact-preview` — Modül 9 senaryo motoruna **dokunmadan**
bağımsız çalışır. Aşağıdaki değişkenlerin **mutlak değişimini** (delta) alır:

`citation_count` · `publication_count` · `academic_staff_count` ·
`international_student_count` · `international_academic_staff_count` ·
`doctoral_graduate_count` · `research_income` · `industry_income` · `patent_count` ·
`total_student_count`

Her gösterge, `impact_numerator_variable` ve `impact_denominator_variable` alanlarıyla bu
değişkenlere bağlıdır; servis pay ve paydaya deltayı uygulayıp değeri yeniden hesaplar.

**Veritabanına hiçbir kayıt yazmaz** ve mevcut gösterge değerlerini değiştirmez: veriler
bellekte kopyalanır ve hesaplama motoru geçici anlık görüntülerle yeniden çalıştırılır.

Cevapta before/after değerleri, etkilenen göstergeler, boyut skoru değişimi, çerçeve
performans/hazırlık/uyum değişimi, risk değişimi ve Türkçe öneriler bulunur.

### Veri Entegrasyonu (Modül 13 Genişletmesi)

Üç yeni `resource_type` eklendi. CSV, XLSX ve JSON desteklenir; alt çizgili yazımlar da
takma ad olarak kabul edilir:

| Kanonik ad | Takma ad | Anahtar |
|---|---|---|
| `institutional-metric-values` | `institutional_metric_values` | `indicator_code` + `academic_year` + `period` |
| `benchmark-institutions` | `benchmark_institutions` | `name` |
| `benchmark-metric-values` | `benchmark_metric_values` | kurum + gösterge + yıl + dönem |

`benchmark-metric-values` **iki üst kayıt** çözümler (kurum adı ve gösterge kodu). Bunun için
import katmanına çoklu parent desteği (`ParentSpec`) eklendi; mevcut yedi kaynağın davranışı
ve şablon sütunları **değişmedi**.

İçe aktarım tek transaction içinde çalışır, satır bazlı hataları raporlar, geçersiz gösterge
kodlarını yakalar, dosya içi ve veritabanı çakışmalarını ayırt eder ve Decimal değerleri
güvenli parse eder (Türkçe Excel'den gelen virgüllü ondalık da kabul edilir).

```bash
curl -O -J "http://127.0.0.1:8000/api/data-integration/templates/institutional-metric-values"
curl -X POST "http://127.0.0.1:8000/api/data-integration/import/institutional-metric-values?preview=true" \
     -F "file=@sample_data/institutional_metric_values_sample.csv"
```

`sample_data/` klasöründe üç kaynak için de CSV/XLSX/JSON örnekleri ve bilinçli hatalı
satırlar içeren `institutional_metric_values_with_errors_sample.csv` bulunur.

### Swagger'da Denenebilecek Örnek İstekler

**Çerçeve oluşturma** — `POST /api/ranking-evaluations/frameworks`

```json
{
  "code": "THE",
  "name": "THE World University Rankings (2027 metodolojisi)",
  "methodology_year": 2027,
  "description": "İç izleme amaçlı çerçeve",
  "is_active": true
}
```

**Gösterge oluşturma** — `POST /api/ranking-evaluations/indicators`

```json
{
  "dimension_id": 4,
  "code": "the-international-collaboration-2027",
  "name": "International collaboration ratio",
  "unit": "%",
  "calculation_type": "percentage",
  "weight": "30.00",
  "direction": "higher_is_better",
  "minimum_value": "0",
  "target_value": "30",
  "maximum_value": "70",
  "data_source": "Uluslararası İlişkiler Ofisi",
  "required_for_readiness": true
}
```

**Gösterge verisi girme** — `POST /api/ranking-evaluations/metrics`

```json
{
  "indicator_id": 11,
  "academic_year": "2025-2026",
  "period": "annual",
  "numerator": "20",
  "denominator": "120",
  "data_status": "available",
  "origin": "manual",
  "source_reference": "Öğrenci Bilgi Sistemi raporu"
}
```

**Otomatik senkronizasyon** — `POST /api/ranking-evaluations/metrics/sync-student-data`

```json
{ "academic_year": "2025-2026", "period": "annual", "overwrite_manual": false }
```

**Değerlendirme hesaplama** — `POST /api/ranking-evaluations/assessments/calculate`

```json
{ "framework_code": "THE", "academic_year": "2025-2026", "period": "annual", "persist": true }
```

**Senaryo etkisi** — `POST /api/ranking-evaluations/impact-preview`

```json
{
  "academic_year": "2025-2026",
  "publication_count": "150",
  "citation_count": "2500",
  "academic_staff_count": "30",
  "international_student_count": "40",
  "research_income": "15000000"
}
```

**curl örnekleri**

```bash
# Çerçeveler
curl "http://127.0.0.1:8000/api/ranking-evaluations/frameworks"

# Öğrenci verisini senkronize et
curl -X POST "http://127.0.0.1:8000/api/ranking-evaluations/metrics/sync-student-data" \
     -H "Content-Type: application/json" -d '{"academic_year":"2025-2026"}'

# Tüm çerçeveleri hesapla
curl -X POST "http://127.0.0.1:8000/api/ranking-evaluations/assessments/calculate" \
     -H "Content-Type: application/json" -d '{"academic_year":"2025-2026"}'

# En güncel değerlendirmeler
curl "http://127.0.0.1:8000/api/ranking-evaluations/assessments/latest/THE"
curl "http://127.0.0.1:8000/api/ranking-evaluations/assessments/latest/QS"
curl "http://127.0.0.1:8000/api/ranking-evaluations/assessments/latest/YOK"

# Karşılaştırma ve trend
curl "http://127.0.0.1:8000/api/ranking-evaluations/benchmarks/comparison?academic_year=2025-2026&framework_code=THE&scope=competitors"
curl "http://127.0.0.1:8000/api/ranking-evaluations/trends/THE"

# Panel
curl "http://127.0.0.1:8000/api/ranking-evaluations/dashboard-summary"
```

### Örnek Cevap

`POST /api/ranking-evaluations/assessments/calculate` (kısaltılmış)

```json
{
  "academic_year": "2025-2026",
  "period": "annual",
  "persisted": true,
  "calculated_framework_count": 3,
  "assessments": [
    {
      "disclaimer": "Bu sonuç gerçek THE/QS/YÖK sıralaması değildir. Kurumun kendi verisine dayanan iç performans izleme, veri hazırlık ve uyum göstergesidir.",
      "assessment_id": 3,
      "framework": "THE",
      "methodology_year": 2026,
      "academic_year": "2025-2026",
      "readiness_score": "98.88",
      "performance_score": "69.01",
      "compliance_score": "68.24",
      "risk_level": "medium",
      "total_indicator_count": 15,
      "available_indicator_count": 11,
      "missing_indicator_count": 1,
      "dimensions": [ "..." ],
      "missing_data": { "missing_count": 1, "total_readiness_loss": "1.12", "items": [ "..." ] },
      "strongest_indicators": [ "..." ],
      "weakest_indicators": [ "..." ],
      "recommendations": [ "..." ],
      "calculation_notes": [ "..." ],
      "calculated_at": "2026-07-26T16:40:12"
    }
  ]
}
```

---

## Modül 9 — What-if Scenario Analysis (Senaryo Simülasyonu)

Üniversite yöneticisinin "öğrenci sayısını %10 artırırsak ne olur?", "enflasyon %50 olursa bütçe
tutar mı?" gibi soruları veri üzerinden yanıtlamasını sağlar. Sistem finans, personel ihtiyacı,
öğrenci başına maliyet ve fiziksel kapasite üzerindeki tahmini etkiyi hesaplar, riskleri tespit
eder ve Türkçe öneriler üretir.

### Çalışma Mantığı

```
ScenarioBaseline (mevcut durum)  +  ScenarioInput (değişiklikler)
                          ↓
                  scenario_engine  → sayısal sonuçlar
                          ↓
                  scenario_risk    → risk listesi + risk seviyesi
                          ↓
            scenario_recommendations → Türkçe öneri metni
                          ↓
                    ScenarioResult (kaydedilir)
```

### Baseline (Referans Veri)

Finans, personel ve fiziksel kapasite modülleri henüz hazır olmadığı için mevcut durum verileri
`ScenarioBaseline` tablosuna elle girilir. **Sistemde aynı anda yalnızca bir baseline aktif
olabilir**; yeni bir kayıt aktif yapıldığında önceki otomatik olarak pasifleşir. Simülasyonlar
her zaman aktif baseline'ı kullanır.

| Metot | Yol | Açıklama |
|---|---|---|
| POST | `/api/scenarios/baselines` | Yeni baseline oluşturur (aktifse diğerlerini pasifleştirir) |
| GET | `/api/scenarios/baselines` | Listeler (`skip`, `limit`, `is_active`) |
| GET | `/api/scenarios/baselines/active` | Aktif baseline'ı verir (yoksa 409) |
| GET | `/api/scenarios/baselines/{id}` | Detay |
| PUT | `/api/scenarios/baselines/{id}` | Kısmi günceller |
| DELETE | `/api/scenarios/baselines/{id}` | Silmez, `is_active=false` yapar |

### Senaryo ve Simülasyon

| Metot | Yol | Açıklama |
|---|---|---|
| POST | `/api/scenarios` | Senaryo oluşturur (`status=draft`) |
| GET | `/api/scenarios` | Listeler (`scenario_type`, `status`, `skip`, `limit`) |
| GET | `/api/scenarios/{id}` | Detay |
| PUT | `/api/scenarios/{id}` | Kısmi günceller |
| DELETE | `/api/scenarios/{id}` | Silmez, `status=archived` yapar |
| POST | `/api/scenarios/{id}/simulate` | Hesaplar, girdi + sonucu **kaydeder** (201) |
| GET | `/api/scenarios/{id}/results` | Geçmiş sonuçlar (en yeni önce) |
| GET | `/api/scenarios/{id}/results/latest` | En son sonuç |
| GET | `/api/scenarios/{id}/inputs` | Geçmiş girdi parametreleri |
| POST | `/api/scenarios/preview` | Hesaplar ama **hiçbir kayıt yazmaz** |

`scenario_type` değerleri: `student-enrollment` · `tuition-scholarship` · `academic-staffing` ·
`investment` · `research-strategy` · `economic-risk` · `combined`

`status` değerleri: `draft` (henüz çalıştırılmadı) · `simulated` (en az bir kez hesaplandı) ·
`archived`

### Girdi Parametreleri

Tüm alanlar isteğe bağlıdır ve varsayılanı `0`'dır. Yönetici yalnızca değiştirmek istediği
parametreyi göndererek "diğer her şey sabitken ne olur" sorusunu sorabilir.

| Alan | Tip | Açıklama |
|---|---|---|
| `student_change_percent` | yüzde | Öğrenci sayısındaki değişim |
| `tuition_change_percent` | yüzde | Öğrenim ücretindeki değişim |
| `scholarship_change_percent` | yüzde puanı | Mevcut burs oranına **eklenir** (%35 + %10 = %45) |
| `inflation_percent` | yüzde | Beklenen yıllık enflasyon |
| `exchange_rate_change_percent` | yüzde | Döviz kurundaki değişim |
| `research_funding_change_percent` | yüzde | Araştırma fonlarındaki değişim |
| `academic_staff_change` | adet | Akademik personel artışı/azalışı (negatif olabilir) |
| `classroom_capacity_change` | kişi | Derslik kapasitesi değişimi (negatif olabilir) |
| `laboratory_capacity_change` | kişi | Laboratuvar kapasitesi değişimi (negatif olabilir) |

### Hesaplama Formülleri

Tüm formüller `app/services/scenario_engine.py` içindedir. `growth(p)` = `(1 + p / 100)`.

**Öğrenci sayısı**

```
projected_student_count = baseline.student_count × growth(student_change_percent)
```
Sonuç en yakın tam sayıya yuvarlanır (yarım öğrenci olamaz).

**Gelirler**

```
gross_tuition_revenue      = projected_student_count
                             × annual_tuition_per_student
                             × growth(tuition_change_percent)

effective_scholarship_rate = baseline.scholarship_rate_percent + scholarship_change_percent

scholarship_deduction      = gross_tuition_revenue × (effective_scholarship_rate / 100)

projected_tuition_revenue  = gross_tuition_revenue − scholarship_deduction

projected_research_revenue = annual_research_revenue × growth(research_funding_change_percent)

projected_other_revenue    = annual_other_revenue                        (değişmez)

projected_revenue          = tuition + research + other
```

**Giderler**

```
average_staff_cost              = annual_personnel_expense / academic_staff_count

projected_personnel_expense     = annual_personnel_expense
                                  + (academic_staff_change × average_staff_cost)

projected_education_expense     = annual_education_expense
                                  × growth(student_change_percent)
                                  × growth(inflation_percent)

projected_rd_expense            = annual_rd_expense
                                  × growth(research_funding_change_percent)
                                  × growth(inflation_percent)

projected_building_energy_expense = annual_building_energy_expense
                                    × growth(inflation_percent)

projected_technology_expense    = annual_technology_expense
                                  × growth(inflation_percent)
                                  × growth(exchange_rate_change_percent)

projected_expenditure           = personel + eğitim + Ar-Ge + bina/enerji + teknoloji
```

Her gider kaleminin farklı bir değişkene bağlanmasının sebebi: eğitim gideri öğrenci sayısıyla,
Ar-Ge gideri araştırma bütçesiyle, teknoloji gideri ise ithal ürün ağırlıklı olduğu için kurla
birlikte hareket eder.

**Personel, oran ve maliyet**

```
projected_staff_count         = academic_staff_count + academic_staff_change
projected_student_staff_ratio = projected_student_count / projected_staff_count
projected_cost_per_student    = projected_expenditure / projected_student_count
```

**Kapasite**

```
projected_classroom_capacity   = classroom_capacity + classroom_capacity_change
projected_laboratory_capacity  = laboratory_capacity + laboratory_capacity_change
```

**Bütçe dengesi** (rapordaki `breakdown` bölümünde döner)

```
balance = revenue − expenditure        (pozitif = fazla, negatif = açık)
```

### Kapasite Durumu

| Durum | Koşul |
|---|---|
| `sufficient` | Öğrenci sayısı kapasitenin %90'ının altında |
| `tight` | Kapasitenin %90–100'ü dolu — aşılmadı ama erken uyarı |
| `insufficient` | Öğrenci sayısı kapasiteyi aşıyor |

### Risk Kuralları

| Risk kodu | Koşul | Şiddet |
|---|---|---|
| `budget_deficit` | `projected_expenditure > projected_revenue` | warning |
| `high_student_staff_ratio` | Öğrenci/öğretim üyesi oranı > 25 | warning |
| `classroom_capacity_exceeded` | Öğrenci sayısı > derslik kapasitesi | warning |
| `laboratory_capacity_exceeded` | Öğrenci sayısı > laboratuvar kapasitesi | warning |
| `scholarship_rate_invalid` | Toplam burs oranı 0–100 aralığı dışında | **critical** |
| `staff_count_invalid` | `projected_staff_count <= 0` | **critical** |
| `student_count_invalid` | `projected_student_count <= 0` | **critical** |

**Risk seviyesi:**

| Seviye | Koşul |
|---|---|
| `low` | Hiç risk yok |
| `medium` | 1 veya 2 uyarı |
| `high` | 3 veya daha fazla uyarı |
| `critical` | En az bir kritik matematiksel geçersizlik var (sayı adedine bakılmaz) |

Kritik durumlarda diğer hesaplanan sayılar da güvenilir olmadığı için seviye doğrudan `critical`
olur. Bu senaryolar HTTP hatası değil, `200/201` ile birlikte `risk_level: "critical"` döndürür —
yönetici senaryonun **neden** geçersiz olduğunu görebilsin diye. Sıfıra bölme durumlarında ilgili
oran `0.00` olarak döner, program çökmez.

### Öneri Sistemi

`scenario_recommendations.py` her risk koduna bir Türkçe öneri metni bağlar. Üretilen metin şu
sırayla oluşur:

1. Risk seviyesine göre bir başlık cümlesi
2. Tespit edilen her risk için numaralı öneri
3. Bütçe dengesindeki değişimi anlatan not
4. Öğrenci başına maliyetteki yüzdesel değişimi anlatan not

Örnek çıktı:

```
Senaryo uygulanabilir ancak izlenmesi gereken riskler var.
1. Laboratuvar açığı için laboratuvar yatırımı, grup sayısının artırılması veya
   laboratuvar kullanım saatlerinin genişletilmesi planlanmalıdır.
Bütçe dengesi 170,000,000.00 seviyesinden 221,500,000.00 seviyesine iyileşiyor.
Öğrenci başına maliyet 98,000.00 seviyesinden 90,363.64 seviyesine, yani %7.79 oranında azalıyor.
```

### Sayısal Hassasiyet (Decimal)

Para hesaplarının tamamı `Decimal` ile yapılır. Float kullanılsaydı `0.1 + 0.2 = 0.30000000000000004`
türü sapmalar milyonluk bütçelerde lira seviyesinde hataya dönüşürdü.

SQLite'ta `Numeric` sütunlar arka planda float olarak tutulduğu için `app/core/decimal_types.py`
içinde `MoneyType` adlı özel bir sütun tipi tanımlandı. Bu tip Decimal değerleri veritabanına
**metin olarak** yazar ve okurken tekrar Decimal'e çevirir — böylece yazılan değerin aynısının
geri okunduğu garanti edilir.

- Para ve oran alanları `ROUND_HALF_UP` ile 2 ondalık basamağa yuvarlanır.
- Öğrenci, personel ve kapasite değerleri tam sayıya yuvarlanır.
- Tüm bölme işlemleri `safe_divide()` üzerinden yapılır; payda sıfırsa `0` döner ve durum risk
  olarak raporlanır.

### Doğrulama Kuralları

| Kural | Nerede | Hata |
|---|---|---|
| Yüzde alanları −100 ile 1000 arasında | Pydantic şeması | 422 |
| Para alanları ≥ 0 | Pydantic şeması | 422 |
| `student_count`, `academic_staff_count`, kapasiteler > 0 | Pydantic şeması | 422 |
| Baseline burs oranı 0–100 | Pydantic şeması | 422 |
| `scenario_type` geçerli enum değeri | Pydantic şeması | 422 |
| Kapasite değişimi sonucu negatif olamaz | `scenario_engine` | 422 (Türkçe mesaj) |
| Aktif baseline bulunmalı | Router | 409 |
| Senaryo / baseline mevcut olmalı | Router | 404 |

Kapasite kuralı şema katmanında yakalanamaz çünkü sonucu baseline'a bağlıdır (`-600` derslik
değişimi baseline 5500 ise geçerli, 500 ise geçersizdir). Bu yüzden hesaplama motorunda kontrol
edilip 422'ye çevrilir.

### Swagger'da Denenebilecek Örnek İstekler

**Baseline oluşturma** — `POST /api/scenarios/baselines`

```json
{
  "name": "2026 University Baseline",
  "student_count": 5000,
  "annual_tuition_per_student": "180000",
  "scholarship_rate_percent": "35",
  "annual_research_revenue": "50000000",
  "annual_other_revenue": "25000000",
  "annual_personnel_expense": "320000000",
  "annual_education_expense": "70000000",
  "annual_rd_expense": "45000000",
  "annual_building_energy_expense": "30000000",
  "annual_technology_expense": "25000000",
  "academic_staff_count": 220,
  "classroom_capacity": 5500,
  "laboratory_capacity": 5200,
  "is_active": true
}
```

**Senaryo oluşturma** — `POST /api/scenarios`

```json
{
  "name": "Student Growth 10 Percent",
  "description": "Öğrenci sayısının %10 artmasının etkileri",
  "scenario_type": "student-enrollment"
}
```

**Öğrenci artışı simülasyonu** — `POST /api/scenarios/1/simulate`

```json
{ "student_change_percent": "10" }
```

**Ekonomik risk senaryosu** — `POST /api/scenarios/2/simulate`

```json
{
  "inflation_percent": "45",
  "exchange_rate_change_percent": "35"
}
```

**Personel alımı senaryosu** — `POST /api/scenarios/3/simulate`

```json
{ "academic_staff_change": 30 }
```

**Birleşik senaryo** — `POST /api/scenarios/4/simulate`

```json
{
  "student_change_percent": "15",
  "tuition_change_percent": "25",
  "scholarship_change_percent": "0",
  "academic_staff_change": 25,
  "inflation_percent": "35",
  "exchange_rate_change_percent": "20",
  "research_funding_change_percent": "10",
  "classroom_capacity_change": 500,
  "laboratory_capacity_change": 800
}
```

**Hızlı ön izleme (kayıt oluşturmaz)** — `POST /api/scenarios/preview`

```json
{ "student_change_percent": "8", "inflation_percent": "30" }
```

### Örnek Cevap

`POST /api/scenarios/1/simulate` → `{ "student_change_percent": "10" }`

```json
{
  "scenario_id": 1,
  "scenario_name": "Student Growth 10 Percent",
  "scenario_type": "student-enrollment",
  "baseline_id": 1,
  "baseline_name": "2026 University Baseline",
  "preview": false,
  "result": {
    "baseline_student_count": 5000,
    "projected_student_count": 5500,
    "baseline_revenue": "660000000.00",
    "projected_revenue": "718500000.00",
    "baseline_expenditure": "490000000.00",
    "projected_expenditure": "497000000.00",
    "baseline_staff_count": 220,
    "projected_staff_count": 220,
    "baseline_student_staff_ratio": "22.73",
    "projected_student_staff_ratio": "25.00",
    "baseline_cost_per_student": "98000.00",
    "projected_cost_per_student": "90363.64",
    "baseline_classroom_capacity": 5500,
    "projected_classroom_capacity": 5500,
    "baseline_laboratory_capacity": 5200,
    "projected_laboratory_capacity": 5200,
    "classroom_capacity_status": "tight",
    "laboratory_capacity_status": "insufficient"
  },
  "breakdown": {
    "projected_tuition_revenue": "643500000.00",
    "projected_research_revenue": "50000000.00",
    "projected_other_revenue": "25000000.00",
    "projected_personnel_expense": "320000000.00",
    "projected_education_expense": "77000000.00",
    "projected_rd_expense": "45000000.00",
    "projected_building_energy_expense": "30000000.00",
    "projected_technology_expense": "25000000.00",
    "effective_scholarship_rate_percent": "35.00",
    "scholarship_deduction": "346500000.00",
    "baseline_balance": "170000000.00",
    "projected_balance": "221500000.00"
  },
  "risks": [
    {
      "code": "laboratory_capacity_exceeded",
      "message": "Laboratuvar kapasitesi yetersiz: 5500 öğrenciye karşılık 5200 kapasite var. 300 kişilik açık oluşuyor.",
      "severity": "warning"
    }
  ],
  "risk_level": "medium",
  "recommendation": "Senaryo uygulanabilir ancak izlenmesi gereken riskler var.\n1. Laboratuvar açığı için ...",
  "result_id": 1,
  "calculated_at": "2026-07-26T13:20:11"
}
```

Örnek `/health` cevabı:

```json
{
  "status": "healthy",
  "application": "Strategic University Management and Decision Support System",
  "version": "0.1.0",
  "database": "sqlite"
}
```

## Ayarlar

Ayarlar `app/core/config.py` içindeki `Settings` sınıfında tanımlıdır. İstenirse `backend/.env`
dosyası oluşturularak değerler koda dokunmadan değiştirilebilir:

```
APP_NAME=Strategic University Management and Decision Support System
DEBUG=True
DATABASE_URL=sqlite:///./university_management.db
```

## Tasarım Notları

- **Soft delete:** Kayıtlar veritabanından silinmez, `is_active=False` yapılır. Böylece geçmiş
  veriler ve raporlar bozulmaz.
- **Kod benzersizliği:** `code` alanı hem veritabanı seviyesinde `unique`, hem de API katmanında
  kontrol edilir; çakışma durumunda anlaşılır bir 409 mesajı döner.
- **Foreign key doğrulaması:** Bölüm veya program eklerken üst kaydın varlığı önceden kontrol
  edilir, böylece ham veritabanı hatası yerine anlamlı bir 404 döndürülür.

- **Katmanlı yapı:** Router yalnızca isteği alıp servisi çağırır. Dosya okuma (`file_parser`),
  doğrulama (`import_validators`) ve aktarım (`import_service`) ayrı modüllerdedir; böylece her
  parça tek başına test edilebilir ve yeni bir dosya biçimi eklemek diğer katmanları etkilemez.

## Tamamlanan Modüller

| Modül | Ad | Durum |
|---|---|---|
| 1 | University Structure and Core Data Management | ✅ |
| 2 | Strategic Education and Student Analytics | ✅ |
| 9 | What-if Scenario Analysis | ✅ |
| 10 | THE, QS and YÖK Evaluation and Monitoring Management | ✅ |
| 13 | Data Integration | ✅ |

## Sonraki Adımlar

Sonraki modüllerde eklenecek modeller `app/models/`, şemalar `app/schemas/`, iş mantığı
`app/services/` ve endpoint'ler `app/routers/` altına aynı düzende eklenecektir.

Genişletme noktaları:

- Yeni bir kaynak için toplu aktarım desteği: `app/services/import_validators.py` içindeki
  `RESOURCE_SPECS` sözlüğüne bir `ResourceSpec` satırı eklemek yeterli.
- Yeni bir senaryo risk kuralı: `app/services/scenario_risk.py` içine bir kontrol, ardından
  `scenario_recommendations.py` içine karşılık gelen öneri metni.
- Yeni bir öğrenci erken uyarısı: `app/services/student_alert_service.py` içine bir eşik sabiti
  ve kontrol bloğu.
- Yeni bir trend metriği: `TrendMetric` enum'una bir değer ve `student_trend_service.py` içindeki
  ilgili toplu sorguya bir satır.
- Yeni bir değerlendirme çerçevesi veya metodoloji yılı: veritabanına `EvaluationFramework`
  kaydı eklemek yeterli; hesaplama motoru ağırlıkları veriden okuduğu için kod değişmez.
- Yeni bir otomatik gösterge eşleştirmesi: `ranking_student_sync_service.py` içine bir metrik
  hesabı, ardından göstergenin `auto_source_key` alanına aynı anahtar.
- Finans, personel ve fiziksel kapasite modülleri devreye girdiğinde `ScenarioBaseline` verileri
  elle girilmek yerine o modüllerden otomatik doldurulacak; hesaplama motoru değişmeyecek.
  Öğrenci sayısı için bu entegrasyon `POST /api/scenarios/baselines/sync-student-data` ile
  hâlihazırda çalışıyor.
