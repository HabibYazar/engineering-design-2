# Ortak Veri Sözlüğü

Demoda görünen **her sayı** `integration/shared_demo_data/` altındaki 8 JSON
dosyasından türer. Kod içine gömülü ikinci bir kopya yoktur.

Veriyi değiştirmek için: ilgili JSON dosyasını düzenleyin, veritabanını silin
(`*.db`), `python seed_all_demo_data.py` çalıştırın.

---

## 1. Kaynak dosyalar

| Dosya | İçerik | Besledi ği modüller |
|---|---|---|
| `00_assumptions.json` | Kurum bilgisi, ölçek, akademik yıllar, para birimi, tohum | Tümü (referans belge) |
| `01_university_structure.json` | 4 fakülte, 12 bölüm, 14 program, 8 idari birim | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 14 |
| `02_students.json` | Öğrenci üretim şartnamesi + kayıt görüntüsü parametreleri | 2, 3, 7, 9, 11 |
| `03_academic_staff.json` | Personel üretim şartnamesi | 4, 5 (kişi başına alan) |
| `04_physical_facilities.json` | 42 mekân (tek tek listelenmiş) | 5, 9 |
| `05_finance.json` | 4 mali dönem, gelir/gider kalemleri, 12 bölüm bütçesi | 6, 8, 9 |
| `06_kpis.json` | 14 KPI, 10 stratejik boyut, fakülte kırılımları | 8, 10 |
| `07_system_users.json` | 6 demo kullanıcısı ve rolleri | 14 |

**Neden bazıları şartname, bazıları liste?** 4000 öğrenci ve 180 personel tek
tek listelense dosya okunamaz hâle gelir ve bir oranı değiştirmek elle 4000
satır düzenlemek demek olurdu. Bunlar parametrelerden **deterministik** üretilir
(`random_seed: 20260804`) — her çalıştırmada aynı veri oluşur. 42 mekân ise
demoda tek tek gösterildiği için açıkça listelenmiştir.

---

## 2. Temel varsayımlar

| Alan | Değer | Kaynak |
|---|---|---|
| Kurum | Ankara Bilim Üniversitesi (kurgusal vakıf üniversitesi) | `00_assumptions.json` |
| Fakülte / Bölüm / Program | 4 / 12 / 14 | `01_university_structure.json` |
| Öğrenci | 4.000 | `02_students.json` |
| Akademik personel | 180 | `03_academic_staff.json` |
| Fiziksel mekân | 42 | `04_physical_facilities.json` |
| İzlenen KPI | 14 (10 boyut) | `06_kpis.json` |
| Sistem kullanıcısı | 6 | `07_system_users.json` |
| Akademik yıllar | 2022-2023 … 2026-2027 | `00_assumptions.json` |
| Güncel yıl | 2025-2026 | `00_assumptions.json` |
| Para birimi | TRY; mali tablolarda **milyon TL**, oranlarda **bin TL** | `00_assumptions.json` |
| Rastgelelik tohumu | 20260804 | `00_assumptions.json` |

---

## 3. Tablolar ve alanlar

Toplam **29 tablo**. Ortak alanlar: `id` (PK), `is_active` (soft delete),
`created_at`, `updated_at`.

### Modül 1 — Üniversite yapısı

| Tablo | Alanlar | İlişkiler | Kullanan modüller |
|---|---|---|---|
| `faculties` | `code` (unique), `name`, `description`, `is_active` | → `departments`, `system_users`, `kpi_faculty_values` | 1, 2, 3, 4, 8, 10, 14 |
| `departments` | `code` (unique), `faculty_id` (FK), `name`, `description` | ← `faculties`; → `academic_programs`, `academic_staff`, `physical_facilities`, `department_budgets` | 1, 2, 3, 4, 5, 6, 14 |
| `academic_programs` | `code` (unique), `department_id` (FK), `name`, `degree_level`, `duration_years`, `quota` | ← `departments`; → `students`, `program_enrollment_snapshots` | 1, 2, 3, 7, 9, 11 |
| `administrative_units` | `code` (unique), `name`, `description` | — | 1 |

### Modül 2 / 3 — Öğrenci

| Tablo | Alanlar | Not |
|---|---|---|
| `students` | `student_number` (unique), `first_name`, `last_name`, `gender`, `nationality`, `is_international`, `scholarship_rate_percent` (Decimal), `enrollment_year`, `current_status`, **`status_change_year`**, `preparatory_school`, `academic_program_id` (FK), `current_gpa` (Decimal), `expected_graduation_year`, `actual_graduation_year`, **`is_employed`** | Kalın alanlar entegrasyonda Modül 3 için eklendi |
| `student_academic_records` | `student_id` (FK), `academic_year`, `semester`, `gpa`, `earned_credits` | — |
| `program_enrollment_snapshots` | `academic_program_id` (FK), `academic_year`, `quota`, `enrolled_student_count`, `minimum_admission_score`, **`full_scholarship_minimum_admission_score`**, `national_average_minimum_score`, `ankara_average_minimum_score`, `graduated_student_count`, `dropped_out_student_count`, `non_renewed_student_count` | 5 yıl × 14 program = 70 kayıt |
| `comparable_university_programs` | Karşılaştırma programları | — |

**`current_status` değerleri:** `newly-enrolled`, `active`, `graduated`,
`suspended`, `dropped-out`, `non-renewed`.

**`is_employed` üçlü mantık:** `True` / `False` / `NULL` (bilgi ulaşmadı).
İstihdam oranı yalnızca `NULL` olmayanlar üzerinden hesaplanır.

### Modül 4 — Akademik personel

| Tablo | Alanlar |
|---|---|
| `academic_staff` | `staff_number` (unique), `first_name`, `last_name`, `title`, `department_id` (FK), `academic_year`, `publication_count`, `citation_count`, `teaching_load_hours`, `advising_count`, `project_count`, `patent_count`, `community_engagement_score` (0-10), `has_administrative_duty`, `has_industry_collaboration` |

Fakülte bilgisi ayrı kolonda **tutulmaz**; bölüm üzerinden türetilir.

**Puan formülü** (ağırlıklar `app/config/academic_staff_weights.json`):

```
puan = yayın×5 + atıf×2 + ders_yükü×1 + danışmanlık×3
     + proje×4 + patent×6 + topluma_katkı×2
```

Bantlar: ≥150 yüksek performans · ≥80 beklenen · <80 desteklenmesi gereken.

### Modül 5 — Fiziksel kaynaklar

| Tablo | Alanlar |
|---|---|
| `physical_facilities` | `code` (unique), `name`, `facility_type`, `department_id` (FK, **nullable** — ortak alanlar), `capacity` (≥1), `occupied`, `area_square_meters` (nullable) |

**`facility_type`:** `classroom`, `laboratory`, `office`, `library`, `other`.

**Eşikler:** doluluk <%50 atıl · ≥%90 aşırı dolu · arası yeterli.

`occupied > capacity` veri girişinde reddedilir.

### Modül 6 — Finans

| Tablo | Alanlar |
|---|---|
| `financial_periods` | `academic_year` (unique), `total_students`, `total_graduates` |
| `financial_entries` | `financial_period_id` (FK), `kind` (`revenue`/`expenditure`), `category`, `amount` (Decimal, milyon TL) · unique(dönem, tür, kalem) |
| `department_budgets` | `financial_period_id` (FK), `department_id` (FK), `student_count`, `revenue`, `expenditure`, `allocated_budget` (hepsi Decimal) · unique(dönem, bölüm) |

**Türetilen göstergeler** (saklanmaz, her istekte hesaplanır):
denge, öğrenci başına gelir/maliyet (bin TL), mezun başına maliyet (milyon TL),
personel gideri payı, araştırma geliri payı, burs yükü, bütçe gerçekleşme oranı.

**Bütçe durumu:** ≤%100 bütçe içinde · ≤%108 hafif aşım · >%108 bütçe aşımı ·
bütçe 0 ise **hesaplanmaz** (`null`, "bütçe tanımsız").

### Modül 8 — KPI

| Tablo | Alanlar |
|---|---|
| `strategic_kpis` | `name`, `dimension`, `unit`, `academic_year`, `current_value`, `target_value` (>0), `previous_value` (nullable), `university_average` (nullable), `on_track_threshold` (vars. 90), `at_risk_threshold` (vars. 70), `corrective_action` · unique(ad, yıl) |
| `kpi_faculty_values` | `kpi_id` (FK), `faculty_id` (FK), `value` · unique(kpi, fakülte) |

**Durum:** başarı ≥ `on_track_threshold` → hedefte · < `at_risk_threshold` →
riskli · arası → gecikmeli. Eşikler KPI başına yapılandırılabilir.

### Modül 9 — Senaryo

`scenario_baselines`, `scenarios`, `scenario_inputs`, `scenario_results`.
Tüm para ve oran alanları Decimal.

### Modül 10 — Değerlendirme

`evaluation_frameworks` (THE/QS/YÖK), `evaluation_dimensions`,
`evaluation_indicators`, `institutional_metric_values`, `framework_assessments`,
`dimension_assessments`, `benchmark_institutions`, `benchmark_metric_values`.

**Uyum puanı = performans × veri hazırlık / 100.** Ölçümü olmayan gösterge
performans paydasına girmez (veri fakiri kurum "kötü performanslı" gösterilmez)
ama hazırlık puanını düşürür ve eksik olarak raporlanır.

### Modül 13 — Veri entegrasyonu

`import_jobs`: `resource_type`, `file_name`, `is_preview`, `total_rows`,
`success_count`, `error_count`, `status`, `error_details`.

Desteklenen 11 kaynak türü, 3 format (CSV, XLSX, JSON).

### Modül 14 — Kullanıcı

| Tablo | Alanlar |
|---|---|
| `system_users` | `username` (unique), `full_name`, `password_salt`, `password_hash`, `role`, `faculty_id` (FK, nullable), `department_id` (FK, nullable), `last_login_at` |

**Parola asla düz metin saklanmaz.** PBKDF2-HMAC-SHA256, 120.000 tur,
kullanıcı başına 32 karakterlik rastgele salt.

**Roller ve yetkiler:**

| Rol | Yetkiler |
|---|---|
| Admin | `view_all`, `edit_all`, `manage_users` |
| Dekan | `view_all`, `edit_faculty` |
| Bölüm Başkanı | `view_department`, `edit_department` |
| Öğretim Üyesi | `view_own` |

---

## 4. Seed sırası

`seed_all_demo_data.py` foreign key bağımlılıklarına göre sıralanmıştır:

| # | Adım | Bağımlılık |
|---|---|---|
| 1 | Fakülteler | — |
| 2 | Bölümler | fakülte |
| 3 | Akademik programlar | bölüm |
| 4 | İdari birimler | — |
| 5 | Öğrenciler (4.000) | program |
| 6 | Kayıt görüntüleri (70) | program |
| 7 | Akademik personel (180) | bölüm |
| 8 | Fiziksel mekânlar (42) | bölüm (opsiyonel) |
| 9 | Mali dönemler (4) + kalemler (64) | — |
| 10 | Bölüm bütçeleri (12) | dönem + bölüm |
| 11 | KPI'lar (14) + fakülte kırılımı (36) | fakülte |
| 12 | Sistem kullanıcıları (6) | fakülte + bölüm |
| 13 | Modül 9 senaryo verisi | program |
| 14 | Modül 10 değerlendirme verisi | — |

**Toplam: 4.466 kayıt, ~4 saniye.**

### İdempotanslık

Her adım önce tekil anahtarla (`code`, `student_number`, `staff_number`,
`username`, `academic_year`) arar; varsa atlar. İkinci çalıştırmada **0 yeni
kayıt** oluşur. Script her adım için "Eklenen / Mevcut" sayılarını yazdırır.

---

## 5. Modüller arası tutarlılık

Aynı sayının iki ekranda farklı görünmemesi için uygulanan kurallar:

| Kural | Nasıl sağlanıyor |
|---|---|
| Öğrenci sayısı tek kaynak | Tüm modüller `students` tablosunu sayar |
| Fakülte/bölüm kimlikleri ortak | Tek `faculties` / `departments` tablosu, FK ile bağlı |
| Personel doğru bölümde | `academic_staff.department_id` FK |
| Mekân doğru birimde | `physical_facilities.department_id` FK |
| Bütçe doğru bölümde | `department_budgets.department_id` FK |
| KPI doğru fakültede | `kpi_faculty_values.faculty_id` FK |
| Kişi başına alan gerçek | `COUNT(*)` ile sayılır, sabit yok |
| Fakülte toplamı = bölümler toplamı | Pano fakülte satırını bölümlerden türetir |
| Dashboard = API | Pano ayrı hesap yapmaz, aynı endpoint'leri çağırır |

Bu kurallar `tests_integration/test_integration_all_modules.py` içinde
otomatik olarak doğrulanır.

---

## 6. Veri dürüstlüğü kuralları

`00_assumptions.json` içinde de yazılıdır ve kodda uygulanır:

1. Ölçümü girilmemiş gösterge **sıfır olarak değil, "veri yok" olarak**
   raporlanır (`null`).
2. Payda sıfır olduğunda oran **hesaplanmaz**; uydurma değer üretilmez.
3. Bütçesi tanımlanmamış bölüm için gerçekleşme oranı **boş bırakılır**.
4. Metrekare ölçümü olmayan grup için `0 m²` yerine `null` döner.
5. Bu veri seti **kurgusaldır** ve gerçek bir kurumun verisi olarak sunulamaz.
