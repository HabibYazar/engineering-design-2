# Modül 1 — University Structure and Core Data Management

> Bu klasör sunum amaçlıdır. Dosyalar `app/` altındaki orijinallerin birebir kopyasıdır.

## Amaç

Üniversitenin akademik ve idari yapısını tanımlar. Diğer bütün modüllerin üzerine inşa
edildiği **temel veri katmanıdır**: öğrenciler bir programa, programlar bir bölüme,
bölümler bir fakülteye bağlıdır.

## Ana Dosyalar

```
models/
  faculty.py                 Fakülte + departments ilişkisi (one-to-many)
  department.py              Bölüm + faculty_id FK, programs ilişkisi
  academic_program.py        Program + department_id FK, degree_level, quota
  administrative_unit.py     İdari birim (bağımsız tablo, FK yok)
schemas/
  faculty.py                 Create / Update / Response
  department.py              Create / Update / Response
  academic_program.py        Create / Update / Response + sayısal sınırlar
  administrative_unit.py     Create / Update / Response
routers/
  faculties.py               /api/faculties CRUD
  departments.py             /api/departments CRUD
  programs.py                /api/programs CRUD
  administrative_units.py    /api/administrative-units CRUD
services/
  crud_helpers.py            404 / 409 / foreign key kontrolleri (ortak)
seed_data.py                 FEA, SWE, CENG, SWE-BSC, CENG-BSC, ERASMUS
```

## Veri Akışı

```
İstek → Router → crud_helpers doğrulaması → SQLAlchemy model → SQLite
                      │
                      ├─ get_object_or_404()      kayıt yoksa 404
                      ├─ ensure_code_is_unique()  kod çakışırsa 409
                      └─ ensure_parent_exists()   üst kayıt yoksa 404
```

Router yalnızca isteği alır; tekrar eden doğrulamalar `crud_helpers.py` içinde toplanmıştır.
Bu sayede dört kaynak da aynı hata davranışını gösterir.

## Veri Modeli

```
Faculty (1) ──< (N) Department (1) ──< (N) AcademicProgram

AdministrativeUnit   (bağımsız — akademik hiyerarşiye bağlı değil)
```

## Önemli Endpointler

| Metot | Yol | Açıklama |
|---|---|---|
| GET | `/api/{kaynak}` | Listeler (`skip`, `limit`, `is_active`) |
| GET | `/api/{kaynak}/{id}` | Tek kayıt |
| POST | `/api/{kaynak}` | Oluşturur (**201**) |
| PUT | `/api/{kaynak}/{id}` | Kısmi günceller |
| DELETE | `/api/{kaynak}/{id}` | Silmez, `is_active=False` yapar |

Kaynaklar: `faculties` · `departments` · `programs` · `administrative-units`

Ek filtreler: `/api/departments?faculty_id=1` · `/api/programs?department_id=1`

## Temel Hesaplamalar

Bu modül hesaplama yapmaz; **veri bütünlüğü kuralları** uygular:

| Kural | Davranış |
|---|---|
| `code` benzersizliği | Hem veritabanı `unique` hem API ön kontrolü → **409** |
| Üst kayıt doğrulaması | `faculty_id` / `department_id` geçersizse → **404** |
| Alan doğrulaması | `duration_years` 1–10, `quota` ≥ 0, `name` ≥ 2 karakter → **422** |
| Soft delete | Kayıt silinmez; geçmiş veriler ve raporlar korunur |

## Diğer Modüllerle Bağlantılar

| Hedef | Bağlantı |
|---|---|
| **Modül 2** | `AcademicProgram` → `Student.academic_program_id` (FK) |
| **Modül 2** | `AcademicProgram` → `ProgramEnrollmentSnapshot.academic_program_id` (FK) |
| **Modül 10** | Program sayısı ve `degree_level` bilgisi doktora/lisans göstergelerini besler |
| **Modül 13** | 4 kaynak da CSV/XLSX/JSON ile toplu aktarılabilir (`faculty_code`, `department_code` ile eşleşme) |

## Sunumda Gösterilecek Noktalar

1. **Soft delete kararı** — `DELETE` isteği kaydı silmez, `is_active=False` yapar. Sebebi:
   bir fakülteye bağlı bölümler, programlar ve öğrenciler var; fiziksel silme geçmiş
   raporları bozardı. (`routers/faculties.py`, `deactivate_faculty`)

2. **Ortak yardımcılarla tekrarsız doğrulama** — `crud_helpers.py` içindeki dört fonksiyon
   dört kaynağın tamamına hizmet ediyor. Yeni bir kaynak eklendiğinde 404/409 mantığı
   yeniden yazılmıyor.

3. **Anlamlı HTTP kodları** — 409 kod çakışması, 404 bulunamayan üst kayıt, 422 şema
   doğrulaması. Kullanıcı ham veritabanı hatası yerine Türkçe açıklama görüyor.

4. **`ensure_code_is_unique` içindeki `exclude_id`** — güncelleme sırasında kaydın kendi
   kodunu çakışma saymamak için. Küçük ama sık atlanan bir ayrıntı.

5. **Temel katman olması** — bu modüldeki 4 tablo, sonraki 3 modülün tamamının dayandığı
   yapı. Program kodu (`SWE-BSC`) Modül 2, 10 ve 13'te eşleştirme anahtarı olarak kullanılıyor.
