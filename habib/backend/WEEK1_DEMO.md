# 1. Hafta Demosu — Modül 1 + Modül 13

**Uygulama:** Week 1 Demo - Core Data and Data Integration · v1.0.0

Bu demo yalnızca iki modülü gösterir:

- **Modül 1** — University Structure and Core Data Management (fakülte, bölüm, program, idari birim)
- **Modül 13** — Data Integration (CSV / XLSX / JSON toplu veri aktarımı)

Modül 2, 9 ve 10 endpoint'leri bu demoda **görünmez**.

> **Not:** `demo_week1.py` alternatif bir giriş noktasıdır. `main.py`, `app/`, `tests/`,
> `sample_data/` ve mevcut seed dosyaları **değiştirilmemiştir**. Demo, mevcut model, şema,
> router ve servis dosyalarını doğrudan kullanır; hiçbir kod kopyalanmamıştır.

---

## 1. Kurulum

Sanal ortam yoksa oluştur ve bağımlılıkları kur (yalnızca ilk kez):

```powershell
cd "C:\Users\habib\OneDrive\Desktop\Yaz Okulu 2026\EngineeringDesign2\backend"
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Sanal ortam zaten varsa bu adım atlanabilir — çalıştırma betiği `.venv`'i otomatik bulur.

## 2. Çalıştırma

```powershell
powershell -ExecutionPolicy Bypass -File .\run_week1_demo.ps1
```

Betik sırayla şunları yapar:

| Adım | İşlem |
|---|---|
| 1 | Python yorumlayıcısını bulur (`.venv\Scripts\python.exe`, yoksa sistem `python`) |
| 2 | Gerekli paketlerin kurulu olduğunu doğrular |
| 3 | `demo_week1.py`, `seed_data.py` ve örnek dosyaların varlığını kontrol eder |
| 4 | **Veritabanını hazırlar** ve Modül 1 örnek verilerini yükler (`seed_data.py`) |
| 5 | Tarayıcıyı ~4 saniye sonra `http://127.0.0.1:8000/docs` adresinde açar |
| 6 | `uvicorn demo_week1:app --reload --port 8000` ile uygulamayı başlatır |

**Beklenen konsol çıktısı (özet):**

```
==> Preparing database and loading Module 1 sample data
Seed tamamlandi. Eklenen: 6, zaten mevcut: 0
    OK - Database ready (university_management.db)
    OK - Module 1 records: FEA / SWE / CENG / SWE-BSC / CENG-BSC / ERASMUS

==> Starting the demo application
[week1-demo] Veritabani hazir. Demo tablolari dogrulandi:
[week1-demo]   - faculties: OK
[week1-demo]   - departments: OK
[week1-demo]   - academic_programs: OK
[week1-demo]   - administrative_units: OK
[week1-demo]   - import_jobs: OK
INFO:     Uvicorn running on http://127.0.0.1:8000
```

`seed_data.py` **idempotenttir** — betiği tekrar çalıştırmak kayıtları çoğaltmaz
(`Eklenen: 0, zaten mevcut: 6` yazar).

### Demo verisini sıfırdan başlatmak isterseniz

```powershell
Remove-Item .\university_management.db
powershell -ExecutionPolicy Bypass -File .\run_week1_demo.ps1
```

## 3. Kullanılacak Örnek Veri Dosyaları

Hepsi mevcut `sample_data/` klasöründedir; yeni dosya oluşturulmamıştır.

| Dosya | İçerik | Demo adımı |
|---|---|---|
| `sample_data/faculties_sample.csv` | 5 fakülte: MED, LAW, EDU, ARTS, ECON | 7, 8 |
| `sample_data/faculties_sample.xlsx` | Aynı 5 fakülte (Excel biçimi) | 7 (alternatif) |
| `sample_data/departments_sample.csv` | 3 bölüm: EE, IE (FEA'ya), BMS (MED'e) | 8 |
| `sample_data/programs_sample.csv` | 3 program: EE-BSC, EE-MSC, IE-BSC | 8 |
| `sample_data/administrative_units_sample.csv` | 3 birim: STDAFF, INTL, CAREER | 8 |
| `sample_data/faculties_with_errors_sample.csv` | Bilinçli 6 hatalı/çakışmalı satır | 10 |

**Önemli sıra:** `departments_sample.csv` içindeki `MED` kodu, `faculties_sample.csv`
aktarıldıktan sonra var olur. `programs_sample.csv` ise `departments_sample.csv`'den gelen
`EE` ve `IE` kodlarına bağlıdır. Bu yüzden içe aktarım sırası:
**fakülteler → bölümler → programlar** olmalıdır.

---

## 4. Demo Adımları

Tüm adımlar Swagger UI (`http://127.0.0.1:8000/docs`) üzerinden uygulanabilir.
Her endpoint'te **"Try it out"** düğmesine basıp **"Execute"** ile çalıştırın.

### Adım 1 — Sistemin çalıştığını göster

**`GET /health`**

**Beklenen sonuç:** `200 OK`

```json
{
  "status": "healthy",
  "application": "Strategic University Management and Decision Support System",
  "version": "0.1.0",
  "database": "sqlite"
}
```

> İsteğe bağlı: `GET /` demo kapsamını, `GET /demo-info` ise etkin endpoint'leri ve
> kullanılacak örnek dosyaları listeler.

---

### Adım 2 — Fakülteleri listele

**`GET /api/faculties`**

**Beklenen sonuç:** `200 OK` — seed'den gelen **1 fakülte**:

```json
[
  {
    "name": "Faculty of Engineering and Architecture",
    "code": "FEA",
    "id": 1,
    "is_active": true
  }
]
```

---

### Adım 3 — Yeni bir fakülte oluştur

**`POST /api/faculties`**

```json
{
  "name": "Faculty of Science",
  "code": "FSCI",
  "description": "Temel bilimler fakültesi",
  "is_active": true
}
```

**Beklenen sonuç:** `201 Created` — cevapta `id`, `created_at` ve `is_active: true`.

> **Hata senaryosu (isteğe bağlı gösterim):** Aynı gövdeyi ikinci kez gönderin →
> `409 Conflict`, mesaj: `'FSCI' kodu zaten başka bir Fakülte kaydında kullanılıyor.`

---

### Adım 4 — Bu fakülteye bağlı departman oluştur

**`POST /api/departments`** — `faculty_id` alanına Adım 3'te dönen `id` değerini yazın.

```json
{
  "faculty_id": 2,
  "name": "Physics",
  "code": "PHYS",
  "description": "Fizik bölümü",
  "is_active": true
}
```

**Beklenen sonuç:** `201 Created`

> **Hata senaryosu:** `faculty_id: 9999` gönderin → `404 Not Found`,
> mesaj: `İlişkili Fakülte bulunamadı (id=9999).`

---

### Adım 5 — Departmana bağlı akademik program oluştur

**`POST /api/programs`** — `department_id` alanına Adım 4'te dönen `id` değerini yazın.

```json
{
  "department_id": 3,
  "name": "Physics Bachelor's Program",
  "code": "PHYS-BSC",
  "degree_level": "Bachelor",
  "duration_years": 4,
  "quota": 60,
  "description": "Fizik lisans programı",
  "is_active": true
}
```

**Beklenen sonuç:** `201 Created`

> **Doğrulama gösterimi:** `duration_years: 20` gönderin → `422`, çünkü sınır 1–10.

---

### Adım 6 — İdari birim oluştur

**`POST /api/administrative-units`**

```json
{
  "name": "Quality Assurance Office",
  "code": "QUALITY",
  "description": "Kalite güvence ofisi",
  "is_active": true
}
```

**Beklenen sonuç:** `201 Created`

---

### Adım 7 — Modül 13 ile dosyayı ÖN İZLE (veritabanına yazmaz)

**`POST /api/data-integration/import/{resource_type}`**

| Parametre | Değer |
|---|---|
| `resource_type` | `faculties` |
| `preview` | `true` |
| `file` | `sample_data/faculties_sample.csv` (veya `.xlsx`) |

**Beklenen sonuç:** `200 OK`

```json
{
  "resource_type": "faculties",
  "file_name": "faculties_sample.csv",
  "file_type": "csv",
  "preview": true,
  "total_rows": 5,
  "valid_rows": 5,
  "imported_rows": 0,
  "error_rows": 0,
  "conflict_rows": 0,
  "status": "preview",
  "preview_rows": [ "... ilk 5 geçerli kayıt ..." ],
  "message": "Ön izleme: 5 satır aktarılmaya hazır. Veritabanına hiçbir kayıt yazılmadı."
}
```

**Vurgulanacak nokta:** `imported_rows: 0` ve `status: "preview"`. Bunu kanıtlamak için
Adım 2'yi tekrarlayın — fakülte sayısı **değişmemiş** olacak.

> `sample_data/faculties_sample.xlsx` ile aynı adımı tekrarlayarak Excel desteğini de
> gösterebilirsiniz; cevapta `file_type: "xlsx"` görünür.

---

### Adım 8 — Dosyayı İÇE AKTAR

Aynı endpoint, `preview` = **`false`**. Sırayı koruyun:

| # | `resource_type` | Dosya | Beklenen |
|---|---|---|---|
| 8a | `faculties` | `sample_data/faculties_sample.csv` | `imported_rows: 5`, `status: "completed"` |
| 8b | `departments` | `sample_data/departments_sample.csv` | `imported_rows: 3`, `status: "completed"` |
| 8c | `programs` | `sample_data/programs_sample.csv` | `imported_rows: 3`, `status: "completed"` |
| 8d | `administrative-units` | `sample_data/administrative_units_sample.csv` | `imported_rows: 3`, `status: "completed"` |

**Vurgulanacak noktalar:**

- `ARTS` kodu dosyada `" arts "` olarak yazılmış → sistem boşlukları kırpıp büyük harfe
  çevirdiği için `ARTS` olarak kaydedilir.
- `is_active` sütununda `true`, `1`, `evet`, `yes`, `hayir` yazımlarının hepsi doğru
  yorumlanır.
- `departments_sample.csv` içindeki `MED` kodu 8a'da oluştuğu için 8b sorunsuz çalışır.

> **İçe aktarma geçmişi:** `GET /api/data-integration/jobs` — ön izlemeler dahil her
> işlemin kaydını gösterir (`preview`, `imported_rows`, `status`).

---

### Adım 9 — Aktarılan verilerin Modül 1 listelemede göründüğünü göster

| Endpoint | Beklenen sonuç |
|---|---|
| `GET /api/faculties?limit=100` | **7 fakülte**: FEA (seed) + FSCI (Adım 3) + MED, LAW, EDU, ARTS, ECON (Adım 8a) |
| `GET /api/departments?limit=100` | **6 bölüm**: SWE, CENG (seed) + PHYS (Adım 4) + EE, IE, BMS (Adım 8b) |
| `GET /api/programs?limit=100` | **6 program**: SWE-BSC, CENG-BSC (seed) + PHYS-BSC (Adım 5) + EE-BSC, EE-MSC, IE-BSC (Adım 8c) |
| `GET /api/administrative-units?limit=100` | **5 birim**: ERASMUS (seed) + QUALITY (Adım 6) + STDAFF, INTL, CAREER (Adım 8d) |

**Filtre gösterimi:** `GET /api/departments?faculty_id=1` → yalnızca FEA'ya bağlı bölümler
(SWE, CENG, EE, IE).

---

### Adım 10 — Hatalı dosyada doğrulama hatalarını göster

**`POST /api/data-integration/import/faculties`** · `preview` = `true` ·
`file` = **`sample_data/faculties_with_errors_sample.csv`**

**Beklenen sonuç:** `200 OK` (HTTP hatası değil — sorunlar rapor içinde bildirilir)

```json
{
  "total_rows": 6,
  "valid_rows": 3,
  "error_rows": 3,
  "conflict_rows": 2,
  "imported_rows": 0,
  "status": "preview",
  "errors": [
    { "row": 2, "field": "name",      "issue_type": "error",    "message": "name alanı zorunludur." },
    { "row": 3, "field": "code",      "issue_type": "error",    "message": "code alanı zorunludur." },
    { "row": 4, "field": "is_active", "issue_type": "error",    "message": "is_active alanı true/false, 1/0, yes/no veya evet/hayır olmalıdır." },
    { "row": 5, "field": "code",      "issue_type": "conflict", "message": "'VALID1' kodu dosya içinde birden fazla kez kullanılmış." },
    { "row": 6, "field": "code",      "issue_type": "conflict", "message": "'FEA' kodu veritabanında zaten mevcut." }
  ]
}
```

**Vurgulanacak noktalar:**

- Hatalar **satır numarasıyla** bildirilir → kullanıcı dosyayı düzeltebilir.
- İki ayrı sorun türü ayırt edilir: `error` (doğrulama) ve `conflict` (çakışma).
- Dosya içi tekrar (satır 5) ile veritabanı çakışması (satır 6) farklı mesaj verir.
- 3 satır hatalı olmasına rağmen istek `200` döner; 100 satırlık bir dosyada 2 hata
  yüzünden tüm aktarımı reddetmek yerine geçerli satırlar aktarılır.

> **Kapanış gösterimi:** Aynı dosyayı `preview=false` ile gönderin →
> `imported_rows: 1` (yalnızca `VALID1`), `status: "partial"`,
> `message: "1 satır aktarıldı, 3 satır hatalı, 2 satır çakışmalı olduğu için atlandı."`

---

### Ek Gösterim — Şablon indirme

**`GET /api/data-integration/templates/faculties`** → indirilebilir CSV:

```
name,code,description,is_active
```

Kullanıcının hangi sütunları göndereceğini tahmin etmesine gerek kalmaz.

---

## 5. Demoda Görünen / Görünmeyen Endpoint'ler

`/docs` sayfasında **yalnızca** şunlar bulunur (16 yol):

| Grup | Endpoint |
|---|---|
| Health | `GET /` · `GET /health` · `GET /demo-info` |
| Faculties | `GET,POST /api/faculties` · `GET,PUT,DELETE /api/faculties/{faculty_id}` |
| Departments | `GET,POST /api/departments` · `GET,PUT,DELETE /api/departments/{department_id}` |
| Programs | `GET,POST /api/programs` · `GET,PUT,DELETE /api/programs/{program_id}` |
| Administrative Units | `GET,POST /api/administrative-units` · `GET,PUT,DELETE /api/administrative-units/{unit_id}` |
| Data Integration | `POST /api/data-integration/import/{resource_type}` · `GET /api/data-integration/templates/{resource_type}` · `GET /api/data-integration/jobs` · `GET /api/data-integration/jobs/{job_id}` · `GET /api/data-integration/resources` |

**Görünmeyenler:** `/api/students`, `/api/student-analytics/*` (Modül 2),
`/api/scenarios/*` (Modül 9), `/api/ranking-evaluations/*` (Modül 10).

> **Bir ayrıntı:** İçe aktarma endpoint'indeki `resource_type` açılır listesi projedeki
> **11 kaynağı** gösterir (Modül 2 ve 10 kaynakları dahil), çünkü demo mevcut
> `data_integration` router'ını olduğu gibi kullanır — kod değiştirilmemiştir. 1. hafta
> akışında yalnızca Modül 1'in dört kaynağı kullanılır:
> `faculties`, `departments`, `programs`, `administrative-units`.

---

## 6. Uygulamayı Kapatma

| Yöntem | Nasıl |
|---|---|
| **Normal** | Uygulamanın çalıştığı PowerShell penceresinde **CTRL+C** |
| Pencere kapatıldıysa | `Get-Process python \| Stop-Process -Force` |
| Port meşgul kaldıysa | `Get-NetTCPConnection -LocalPort 8000 \| Select-Object OwningProcess` ardından `Stop-Process -Id <PID> -Force` |

CTRL+C sonrası betik arka plan işlerini (tarayıcı açma görevi) otomatik temizler ve
`Demo stopped` mesajını yazar.

---

## 7. Sorun Giderme

| Belirti | Çözüm |
|---|---|
| `ERROR: Required packages are missing` | `.venv\Scripts\Activate.ps1` ardından `pip install -r requirements.txt` |
| `run_week1_demo.ps1 cannot be loaded` | Komutu `-ExecutionPolicy Bypass` ile çalıştırın (yukarıdaki tam komut) |
| Port 8000 kullanımda | Betikteki `$Port = 8000` değerini değiştirin veya mevcut süreci kapatın |
| Tarayıcı açılmadı | Adresi elle girin: `http://127.0.0.1:8000/docs` |
| `409 Conflict` alıyorum | Aynı kod ikinci kez ekleniyor; bu **beklenen** davranıştır (Adım 3 notu) |
| Demo verisini sıfırlamak | `Remove-Item .\university_management.db` ardından betiği tekrar çalıştırın |

---

## 8. Demo Sonrası Ana Uygulamaya Dönüş

Demo `main.py`'yi etkilemez. Tüm modülleri (1, 2, 9, 10, 13) çalıştırmak için:

```powershell
python seed_data.py
python seed_scenario_data.py
python seed_student_data.py
python seed_ranking_data.py
uvicorn main:app --reload
```

Aynı `university_management.db` dosyası kullanılır; demo sırasında eklenen kayıtlar korunur.
