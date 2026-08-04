# Entegrasyon Kararları

Birleştirme sırasında verilen her kararın gerekçesi. "Neden böyle yapıldı"
sorusunun cevabı burada; "ne yapıldı" sorusununki `TEAM_MODULE_MAP.md` içinde.

---

## 1. Ana backend: Habib'in FastAPI + SQLAlchemy yapısı

Otomatik kabul edilmedi; dört adayın hepsi incelendi.

| Aday | Teknoloji | Kalıcı veri | Katman ayrımı | Test | Endpoint |
|---|---|---|---|---|---|
| **Habib** | FastAPI + SQLAlchemy 2.0 + SQLite | Evet | models/schemas/routers/services/core | **412 test geçiyor** | 65 |
| Begüm | FastAPI + SQLAlchemy | Evet (ayrı DB) | Var | Yok | 15 |
| Eda | FastAPI + düz Python sınıfları | **Hayır** (bellekte liste) | Kısmi | Yok | 16 |
| Halil | stdlib `http.server` | JSON dosyası | Yok (`db.py` + `render.py`) | Yok | HTML üretiyor |

**Karar:** Habib'in yapısı ana backend. Gerekçeler:

1. Tek kalıcı, ilişkisel veritabanı olan aday.
2. Tek test edilmiş aday (412 test). Diğerlerinde hiç test yok.
3. Katman ayrımı diğer modüllerin taşınabileceği bir iskelet sunuyor.
4. `MoneyType` ile Decimal para bütünlüğü zaten çözülmüş — mali modülleri
   taşırken yeniden çözmek gerekmedi.
5. `lifespan` + `init_db()` deseni tüm modeller için tek noktadan tablo
   oluşturmayı sağlıyor.

Eda ve Halil'in backend'leri **veri katmanı olmadığı için** olduğu gibi
taşınamazdı; hesaplama mantıkları çıkarılıp servis katmanına aktarıldı.

---

## 2. Ana arayüz: Halil'in `full-frontend/`

| Aday | Teknoloji | Ekran | Tasarım sistemi |
|---|---|---|---|
| **Halil** | Vanilla JS SPA, hash router, 1974 satır | **15** | Var — CSS değişkenleri, gece modu, SVG grafik yardımcıları |
| Habib | Vanilla JS, 6 sekme | 6 | Basit |
| Begüm | Tek HTML dosyası | 1 | Yok |
| Eda | Tek HTML dosyası | 1 | Yok |

**Karar:** Halil'in arayüzü ana kabuk. Tek gerçek tasarım sistemi olan ve
15 ekranı önceden düşünülmüş tek aday. `style.css` **değiştirilmedi**; eklenen
bileşenler ayrı bir `integration.css` dosyasına yazıldı ki hangi stilin
Halil'den geldiği, hangisinin entegrasyonda eklendiği ayırt edilebilsin.

Arayüz backend ile **aynı sunucudan** servis ediliyor (`StaticFiles` mount).
Ayrı bir frontend sunucusu gerekmiyor, CORS yapılandırması gerekmiyor, tek
komutla açılıyor.

`StaticFiles` mount'u `main.py`'nin **en sonunda** yapılıyor: kök yolu (`/`)
kapsadığı için daha önce bağlansaydı `/api` ve `/docs` isteklerini de yakalar
ve 404 döndürürdü.

---

## 3. Kanonik modeller

Tek `Base`, tek `engine`, tek `SessionLocal`, tek `get_db` — hepsi
`app/database.py` içinde. İkinci bir `database.py` bırakılmadı.

### 3.1 Aynı kavram için farklı isimler

| Kavram | Bulunan isimler | Kanonik | Karar gerekçesi |
|---|---|---|---|
| Akademik program | `AcademicProgram` (Habib), program kodları (diğerleri) | **`AcademicProgram`** | İlişkileri ve testleri olan tek uygulama |
| Akademik personel | `Staff` (Eda, düz sınıf) | **`AcademicStaff`** | "Staff" idari personeli de çağrıştırıyor; tablo adı `academic_staff` |
| Öğrenci | `Student` (Habib), Modül 3 aynı tabloyu kullanıyor | **`Student`** | Begüm'ün 3 ek kolonu bu modele eklendi (birleşim) |
| Öğrenci kaydı | `StudentAcademicRecord` (Habib) | **`StudentAcademicRecord`** | Tek uygulama |
| Fiziksel mekân | `Facility` + `Classroom` (Eda, iki ayrı sınıf) | **`PhysicalFacility`** | `Classroom` alanları `Facility`'nin alt kümesiydi; iki tablo aynı derslik için iki farklı doluluk saklamaya yol açardı |
| Kullanıcı | `User` (Eda) | **`SystemUser`** | `users` çok genel bir tablo adı; ileride öğrenci/personel kullanıcılarıyla karışırdı |
| Mali dönem | JSON içinde `years` sözlüğü (Halil) | **`FinancialPeriod`** | — |
| Gelir/gider kalemi | JSON içinde `revenue`/`expenditure` sözlüğü (Halil) | **`FinancialEntry`** | `kind` + `category` + `UniqueConstraint` |
| Bölüm bütçesi | JSON içinde `departments` listesi (Halil) | **`DepartmentBudget`** | Bölüm adı serbest metindi → foreign key |
| KPI | JSON içinde `kpis` listesi (Halil) | **`StrategicKpi`** | — |
| KPI fakülte kırılımı | `faculties: [4.2, 4.0, 3.8, 4.1]` (sırasız dizi) | **`KpiFacultyValue`** | Dizi sırasına bağlıydı; fakülte eklenince tüm geçmiş veri kayıyordu |

### 3.2 Çift tablo bırakılmadı

`tests_integration/test_integration_all_modules.py::test_no_duplicate_tables_for_same_concept`
testi `staff`, `classrooms`, `facilities`, `users`, `students_m3` tablolarının
var olmadığını doğrular. Toplam **29 tablo** vardır.

### 3.3 Birleşim (union) yaklaşımı

Begüm'ün servisleri Habib'in `Student` modelinde olmayan üç alana ihtiyaç
duyuyordu. İki seçenek vardı:

- **A)** Begüm'ün servislerini bu alanları kullanmayacak şekilde yeniden yaz →
  iş mantığı değişirdi, mezun istihdam oranı ve burs analizi kaybolurdu.
- **B)** Kolonları kanonik modele ekle → mevcut veriyi bozmaz, eski kayıtlarda
  `NULL` kalır.

**B seçildi.** Üç kolon da `nullable=True`; 412 birim testi etkilenmedi.

`is_employed` bilinçli olarak `Optional[bool]`: "istihdam edilmiyor" ile
"istihdam bilgisi bize ulaşmadı" farklı şeylerdir ve oran yalnızca bilgisi
olan mezunlar üzerinden hesaplanır.

---

## 4. Endpoint kararları

### 4.1 Çakışma: `/api/student-analytics`

Modül 2 (Habib) ve Modül 3 (Begüm) **aynı prefix'i** kullanıyordu ve ikisi de
`/overview` yolunu **farklı response modelleriyle** açıyordu.

FastAPI'de aynı (yol, metot) ikilisi iki kez kaydedilirse ikincisi sessizce
gölgede kalır — hangi modülün cevap verdiği belirsizleşirdi.

**Karar:** Habib'in Modül 2'si `/api/student-analytics` prefix'ini korudu
(önce yazılmıştı, 12 endpoint'i ve testleri var). Begüm'ün Modül 3'ü
`/api/education-analytics` prefix'ine taşındı (8 endpoint).

Arayüzde ikisi de tek "Öğrenci Analitiği" ekranında, modül rozetleriyle
gösteriliyor. Kullanıcı için iki ayrı sekme yok.

### 4.2 Çakışma: `/capacity` (Eda kendi içinde)

Eda'nın `classroom_routes.py` ve `capacity_routes.py` dosyalarının ikisi de
`/capacity` yolunu tanımlıyordu ve `main.py` ikisini de ekliyordu.

**Karar:** Tek router (`app/routers/physical_resources.py`). Yollar
`/api/physical-resources/capacity/*` altında toplandı.

### 4.3 Diğer modüller

Modül 7 (`/api/program-sustainability`) ve Modül 11 (`/api/early-warning`)
çakışmıyordu; prefix'leri korundu.

### 4.4 Ortak API kuralları

Tüm modüllerde uygulanan kurallar:

| Durum | Kod |
|---|---|
| Kayıt bulunamadı | 404 |
| Tekil alan çakışması (kod, kullanıcı adı, sicil no) | 409 |
| Şema doğrulama hatası | 422 |
| İş kuralı ihlali (doluluk > kapasite, ters eşik) | 422 |
| Kimlik doğrulama başarısız | 401 |
| Yetki yok / hesap pasif | 403 |
| Oluşturma başarılı | 201 |

- Prefix: `/api/...`
- Sayfalama: `skip` / `limit`
- Silme: kayıt silinmez, `is_active=False` (soft delete) — tüm modüllerde
- Tarih alanları: `created_at` / `updated_at`, `DateTime`, `server_default=func.now()`
- Sabit yollar parametreli yoldan **önce** tanımlanır (`/overview` ile
  `/{staff_id}` çakışmasın diye)

### 4.5 Kök yol değişikliği

Önceden `GET /` JSON döndürüyordu. Artık arayüzü döndürüyor. JSON karşılama
`GET /api` adresine taşındı. `/health` ve `/docs` değişmedi.

---

## 5. Eda'nın kodunda bulunan ve düzeltilen hatalar

Bunlar entegrasyonda ortaya çıkan gerçek hatalardır; gizlenmemiştir.

### Hata 1 — `/ranking` endpoint'i hiç çalışmıyordu

`module_04/services/scores_calculator.py:8`:

```python
config_path = os.path.join(os.path.dirname(__file__), "..", "config", "weights.json")
```

Bu yol `module_04_academic_staff/config/weights.json` dosyasını arıyor. **Böyle
bir klasör yok** — ağırlıklar `eda/config/weightConfig.json` dosyasında. Endpoint
her çağrıldığında `FileNotFoundError` veriyordu.

**Çözüm:** Dosya `app/config/academic_staff_weights.json` olarak taşındı, yol
düzeltildi, `lru_cache` ile bir kez okunuyor.

### Hata 2 — `/capacity` sessizce gölgeleniyordu

Yukarıda 4.2'de açıklandı.

### Güçlendirme — düz metin parolalar

`module_14/services/auth_service.py` parolaları düz metin karşılaştırıyordu
(`user.password == password`) ve `seed_data.py` içinde `"1234"` olarak
saklanıyordu.

**Çözüm:** PBKDF2-HMAC-SHA256, 120.000 tur, kullanıcı başına rastgele salt.
`hmac.compare_digest` ile sabit süreli karşılaştırma. Kullanılan `hashlib` ve
`hmac` standart kütüphanededir; **yeni bağımlılık eklenmedi**.

Ayrıca kullanıcı bulunamadığında ve parola yanlış olduğunda **aynı 401 mesajı**
dönüyor — farklı mesaj hangi kullanıcı adlarının var olduğunu ele verirdi.

---

## 6. Halil'in kodunda yapılan bilinçli davranış değişiklikleri

### 6.1 Sabit öğrenci/personel sayıları kaldırıldı

`module_05/services/capacity_service.py`:

```python
TOTAL_STUDENTS = 3200
TOTAL_STAFF = 180
```

Bu sabitlerle hesaplanan "kişi başına alan" değeri gerçek sistem verisi gibi
görünüyordu. **Çözüm:** Sayılar `SELECT COUNT(*)` ile veritabanından okunuyor.
Entegrasyon testi bunu doğruluyor.

### 6.2 Yüzdeler metin yerine sayı

`render.py` doluluk oranını `"72.22%"` biçiminde **metin** döndürüyordu. Metin
alan üzerinde grafik çizilemez ve karşılaştırma yapılamaz. **Çözüm:** Sayısal
tip; biçimlendirme arayüzde (`fmt.pct`).

### 6.3 Float yerine Decimal

Mali tutarlar `float` idi. Dokuz gider kalemi toplandığında kuruş sapması
oluşuyor ve denge (gelir − gider) sıfır olması gereken yerde sıfırdan farklı
çıkabiliyordu. **Çözüm:** Projenin `MoneyType` altyapısı (Decimal → TEXT).

### 6.4 Sahte AI sohbeti kaldırıldı

`full-frontend/assets/app.js` içinde bir yüzen sohbet balonu vardı; önceden
yazılmış cevapları (`ASSISTANT_ANSWERS`) 800 ms gecikmeyle "Analyzing…"
yazarak gösteriyordu. Bu, kural tabanlı bir sistemi gerçek bir yapay zekâ gibi
sunuyordu.

**Çözüm:** Tamamen kaldırıldı. Yerine, dil modelinin bağlı olmadığını açıkça
söyleyen ve yalnızca gerçek veri toplayan bir asistan ekranı geldi.

---

## 7. Ortak veri seti kararı

Her modülün kendi seed'i vardı ve farklı sayıda fakülte/bölüm varsayıyordu.
Sunumda "Modül 5 bana 9 mekân diyor, Modül 2 bana 120 öğrenci diyor" gibi
tutarsızlıklar çıkıyordu.

**Karar:** `integration/shared_demo_data/` altındaki 8 JSON dosyası **tek
doğruluk kaynağı**. Ekranda görünen her sayı buradan türer.

**Mevcut seed script'leri değiştirilmedi.** `seed_all_demo_data.py` onları
çağırır ve ortak veriyi üzerine ekler. Böylece 412 birim testi bozulmadı.

Veri kod içine gömülmedi: 4000 öğrenci ve 180 personel tek tek listelenmek
yerine **parametre şartnamesinden deterministik olarak** üretilir
(`random_seed: 20260804`). "Uluslararası öğrenci oranını %12 yap" gibi bir
değişiklik tek satırda yapılabiliyor ve her çalıştırmada aynı veri oluşuyor.

---

## 8. Akıllı asistan: bilinçli olarak yapılmayanlar

Proje ekibi henüz bir dil modeli seçmemiştir. Bu entegrasyonda **hiçbir
sağlayıcı bağlanmamıştır**:

- Hiçbir LLM sağlayıcısı seçilmedi (OpenAI, Gemini, Claude, Ollama, Hugging Face…)
- Hiçbir API istemci paketi `requirements.txt` dosyasına eklenmedi
- Hiçbir API anahtarı istenmedi veya koda yazılmadı
- Sahte AI cevabı üretilmedi
- Kural tabanlı eşleştirme **gerçek yapay zekâ gibi sunulmadı**
- RAG, embedding, vector database kurulmadı
- Model adı uydurulmadı

Yapılan: sağlayıcıdan bağımsız arayüz (`base.py`), veri erişim katmanı
(`data_access.py`), bağlam derleyici (`context_builder.py`), sağlayıcı seçici
(`provider_factory.py`), şemalar (`schemas.py`) ve `.env.example`.

**Cevap üreten endpoint bilinçli olarak yoktur.** `/api/assistant/ask` benzeri
bir endpoint eklenip kural tabanlı metin döndürseydi kullanıcı bunu yapay zekâ
cevabı sanırdı. Entegrasyon testi böyle bir endpoint olmadığını doğrular.

Ayrıntı: `ASSISTANT_ARCHITECTURE.md`

---

## 9. Silinmeyen legacy kodlar

Hiçbir dosya silinmedi.

- Ekip üyelerinin orijinal klasörleri (`habib/`, `begüm/`, `eda/`, `halilhan/`)
  **yerinde duruyor**.
- Birleştirmede kaynak olarak kullanılan dosyaların birleştirme öncesi hâli
  ayrıca `integration/archive_before_merge/` altında (90 dosya).
- `habib/backend/module_views/` ve `habib/backend/demo_week1.py` gibi
  daha önceki demo giriş noktaları da korundu.

---

## 10. Git

Depoda başlangıçta **`.git` klasörü yoktu** — bu bir bulgudur, tahmin değil.
Depo bir arşiv olarak indirilmiş.

Bu yüzden Git başlatıldı ve istenen sıra uygulandı:

| Adım | Branch / commit |
|---|---|
| 1 | `.gitignore` yazıldı (`.venv/`, `__pycache__/`, `*.db`, `.env`) |
| 2 | `integration-backup-before-merge` — commit `7cc78b1` (433 dosya, birleştirme öncesi tam hâl) |
| 3 | `integration/main-product` — entegrasyon çalışması |

Branch adları istenen adlarla birebir aynıdır; çakışma olmadı.
