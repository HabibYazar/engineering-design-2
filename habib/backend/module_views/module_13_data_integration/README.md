# Modül 13 — Data Integration

> Bu klasör sunum amaçlıdır. Dosyalar `app/` ve `sample_data/` altındaki orijinallerin
> birebir kopyasıdır.

## Amaç

Kullanıcının CSV, Excel veya JSON dosyası yükleyerek **11 farklı kaynak** için toplu veri
aktarımı yapmasını sağlar. Diğer üç modülün tamamını besleyen **ortak veri giriş altyapısıdır**.

## Ana Dosyalar

```
models/
  import_job.py             İçe aktarma geçmişi (ön izlemeler ve hatalar dahil)
schemas/
  data_integration.py       ResourceType enum (11 kanonik + 3 takma ad), rapor şemaları
routers/
  data_integration.py       5 endpoint: import, templates, jobs, resources
services/
  file_parser.py            CSV/XLSX/JSON okuma, uzantı tespiti, FileParseError
  import_validators.py      ResourceSpec/ParentSpec — bildirimsel kaynak tanımları
  import_service.py         Aktarım akışı, çakışma tespiti, savepoint'li transaction
sample_data/                36 örnek dosya (4 modülün tüm kaynakları, 3 biçimde)
```

## Veri Akışı

```
Yüklenen dosya
     │
     ▼
file_parser.parse_file()
     ├─ uzantı tespiti → desteklenmiyorsa 415
     ├─ boş/bozuk dosya → 400
     └─ sütun başlıklarını normalize et (Faculty Code = faculty_code = FACULTY-CODE)
     │
     ▼
import_validators.validate_row()   ← ResourceSpec'i okuyarak çalışır
     ├─ zorunlu alanlar        ├─ tam sayı sınırları
     ├─ kod normalizasyonu     ├─ ondalık sınırları (virgüllü yazım kabul)
     ├─ metin alanları         ├─ enum değerleri
     ├─ akademik yıl biçimi    └─ boolean çok biçimli (true/1/evet/yes)
     │
     ▼
import_service.run_import()
     ├─ mevcut anahtarlar TEK sorguda belleğe            (N+1 yok)
     ├─ üst kayıt kod→id eşlemeleri TEK sorguda          (çoklu parent destekli)
     ├─ dosya içi + veritabanı çakışma tespiti
     ├─ her satır için SAVEPOINT (begin_nested)
     └─ tek COMMIT  /  beklenmedik hatada ROLLBACK
     │
     ▼
ImportResult + ImportJob kaydı
```

## Desteklenen Kaynaklar

| Modül | Kaynak | Anahtar | Üst kayıt |
|---|---|---|---|
| 1 | `faculties` | `code` | — |
| 1 | `departments` | `code` | `faculty_code` |
| 1 | `programs` | `code` | `department_code` |
| 1 | `administrative-units` | `code` | — |
| 2 | `students` | `student_number` | `academic_program_code` |
| 2 | `student-academic-records` | öğrenci+yıl+dönem | `student_number` |
| 2 | `program-enrollment-snapshots` | program+yıl | `academic_program_code` |
| 2 | `comparable-university-programs` | üniversite+program+yıl | — |
| 10 | `institutional-metric-values` | gösterge+yıl+dönem | `indicator_code` |
| 10 | `benchmark-institutions` | `name` | — |
| 10 | `benchmark-metric-values` | kurum+gösterge+yıl+dönem | **iki üst kayıt** |

Alt çizgili yazımlar (`institutional_metric_values` vb.) takma ad olarak da kabul edilir.

## Önemli Endpointler

| Metot | Yol | Açıklama |
|---|---|---|
| POST | `/api/data-integration/import/{resource_type}?preview=` | Yükleme + aktarım |
| GET | `/api/data-integration/templates/{resource_type}` | Boş CSV şablonu (indirilebilir) |
| GET | `/api/data-integration/jobs` | İçe aktarma geçmişi |
| GET | `/api/data-integration/jobs/{id}` | İş detayı |
| GET | `/api/data-integration/resources` | Desteklenen türler + takma adlar |

## Temel Hesaplamalar

Bu modül hesaplama değil, **veri kalitesi kontrolü** yapar. Rapor sayaçları:

```
total_rows    = valid_rows + error_rows
imported_rows = valid_rows − conflict_rows        (preview modunda her zaman 0)
```

| Sayaç | Anlamı |
|---|---|
| `error_rows` | Satır doğrulamadan geçemedi (eksik alan, hatalı tip, geçersiz üst kod) |
| `conflict_rows` | Doğrulamayı geçti ama anahtar çakıştı (dosya içi veya veritabanı) |
| `valid_rows` | Doğrulamayı geçen satırlar (çakışanlar dahil) |

**Durum:** `preview` · `completed` · `partial` · `skipped` · `failed`

> `skipped` = hiçbir satır aktarılmadı ama sistemsel hata yok (hepsi zaten mevcut).
> `failed` yalnızca gerçek dosya/veritabanı hatalarına ayrılmıştır.

**HTTP kodları:** 415 desteklenmeyen biçim · 400 boş/bozuk dosya · 422 geçersiz
`resource_type` · 404 olmayan iş.

Satır bazındaki hatalar **HTTP hatası üretmez**; istek 200 döner ve sorunlar rapordaki
`errors` listesinde bildirilir. 100 satırlık bir dosyada 2 satır hatalıysa isteğin tamamını
reddetmek yerine 98 satır aktarılır.

## Transaction Davranışı

1. Tüm satırlar önce **bellekte** doğrulanır — veritabanına dokunulmaz.
2. Mevcut anahtarlar ve üst kayıt eşlemeleri **tek sorguda** alınır.
3. Her satır için `db.begin_nested()` ile **SAVEPOINT** açılır: bir satırda beklenmedik hata
   olursa yalnızca o satır geri alınır, önceki satırlar korunur.
4. Tüm satırlar işlendikten sonra **tek `commit`**.
5. Beklenmeyen hatada `rollback` ile **tüm işlem geri alınır**; yarım veri kalmaz.

## Diğer Modüllerle Bağlantılar

| Bağlantı | Nasıl |
|---|---|
| **Modül 1** | 4 kaynak; `faculty_code` / `department_code` ile FK çözümü |
| **Modül 2** | 4 kaynak; `academic_program_code` / `student_number` ile FK çözümü |
| **Modül 10** | 3 kaynak; `indicator_code` ve `benchmark_institution_name` ile FK çözümü |

## Sunumda Gösterilecek Noktalar

1. **Bildirimsel kaynak tanımı** — `import_validators.py` içindeki `RESOURCE_SPECS`, her
   kaynağın hangi sütununun metin/tam sayı/ondalık/boolean/enum olduğunu **veri olarak**
   tanımlar. Doğrulama fonksiyonu bu tanımı okuyarak çalışır; yeni kaynak eklemek yeni kod
   değil, tek bir `ResourceSpec` satırı gerektirir. 4 kaynaktan 11'e bu şekilde çıkıldı.

2. **Satır bazlı SAVEPOINT** — `db.begin_nested()` sayesinde bir satırın hatası diğerlerini
   etkilemiyor. Tek `commit` ile bütünlük korunuyor, beklenmedik hatada tamamı geri alınıyor.

3. **Çoklu üst kayıt desteği** — `benchmark-metric-values` hem kuruma hem göstergeye bağlı.
   `ParentSpec` listesi bunu genel olarak çözüyor; mevcut 8 kaynağın davranışı hiç değişmedi
   (testlerle doğrulandı).

4. **Ön izleme modu gerçek bir güvenlik ağı** — `preview=true` dosyayı okur, doğrular,
   satır bazında hata listesi ve ilk 10 geçerli kaydı döndürür ama **veritabanına hiçbir şey
   yazmaz**. Kullanıcı raporu görüp dosyayı düzeltebilir.

5. **Kullanıcı hatalarına toleranslı okuma** — sütun başlıkları büyük/küçük harf ve boşluk
   farklarına duyarsız; `is_active` alanı `true/1/yes/evet/aktif` gibi yazımları kabul eder;
   Türkçe Excel'den gelen virgüllü ondalık (`42,50`) doğru parse edilir.

6. **Her aktarım kayıt altında** — ön izlemeler ve başarısız dosya okumaları dahil her işlem
   `ImportJob` tablosuna yazılır; hangi dosyanın ne zaman hangi sonuçla yüklendiği geriye
   dönük izlenebilir.
