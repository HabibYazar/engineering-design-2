# API Genel Bakışı

Birleştirilmiş üründe **181 endpoint**, **121 yol** ve **193 şema** vardır.
Canlı ve denenebilir sürüm: <http://127.0.0.1:8000/docs>

---

## Ortak kurallar

| Konu | Kural |
|---|---|
| Önek | Tüm modüller `/api/...` |
| Sayfalama | `skip` (varsayılan 0) + `limit` (varsayılan 100) |
| Silme | Kayıt silinmez; `is_active=False` (soft delete) |
| Bulunamadı | `404` — mesajda mevcut seçenekler de listelenir |
| Tekil alan çakışması | `409` |
| Şema / iş kuralı hatası | `422` |
| Kimlik doğrulama | `401` (kullanıcı yok ve parola yanlış **aynı** mesajı döner) |
| Yetki yok / hesap pasif | `403` |
| Oluşturma | `201` |
| Para alanları | Decimal, metin olarak taşınır (`"486.00"`); milyon TL |
| Eksik ölçüm | `null` — asla `0` değil |

### Modül dışı yollar

| Metot | Yol | Açıklama |
|---|---|---|
| `GET` | `/` | Web arayüzü (SPA) |
| `GET` | `/api` | Backend karşılama JSON'u |
| `GET` | `/health` | Sağlık kontrolü |
| `GET` | `/docs` | Swagger |
| `GET` | `/openapi.json` | OpenAPI şeması |
| `GET` | `/assets/*` | Arayüz dosyaları |

---

## Arayüz — endpoint eşlemesi

Hangi ekranın hangi endpoint'leri çağırdığı:

| Ekran (`#/rota`) | Çağırdığı endpoint'ler |
|---|---|
| `#/login` | `POST /api/auth/login` |
| `#/dashboard` | `/api/student-analytics/overview`, `/api/student-analytics/trends`, `/api/student-analytics/by-department`, `/api/finance/{yıl}/summary`, `/api/finance/{yıl}/departments`, `/api/physical-resources/capacity/overview`, `/api/kpi/scorecard`, `/api/academic-staff/overview`, `/api/early-warning/alerts`, `/api/faculties`, `/api/departments` |
| `#/assistant` | `/api/assistant/status`, `/sample-questions`, `/prepare-context`, `/architecture` |
| `#/students` | `/api/student-analytics/overview`, `/by-program`, `/alerts`, `/api/education-analytics/overview` |
| `#/staff` | `/api/academic-staff/overview`, `/ranking`, `/compare/{grup}`, `/trend` |
| `#/physical` | `/api/physical-resources/capacity/overview`, `/by-type`, `/by-department`, `/per-person`, `/underutilized`, `/overcrowded`, `/forecast` |
| `#/finance` | `/api/finance/periods`, `/{yıl}/summary`, `/{yıl}/departments`, `/trend` |
| `#/sustainability` | `/api/program-sustainability/scores`, `/categories`, `/weights` |
| `#/kpi` | `/api/kpi/scorecard`, `/dimensions`, `/faculty-comparison`, `/attention`, `/api/kpi` |
| `#/rankings` | `/api/ranking-evaluations/frameworks`, `/assessments`, `/benchmarks/institutions` |
| `#/scenarios` | `/api/scenarios`, `/baselines/active`, `/preview` |
| `#/alerts` | `/api/early-warning/summary`, `/alerts`, `/rules`, `/rules/pending` |
| `#/structure` | `/api/faculties`, `/departments`, `/programs`, `/administrative-units` (GET + POST) |
| `#/data-import` | `/api/data-integration/resources`, `/templates/{tür}`, `/import/{tür}`, `/jobs` |
| `#/users` | `/api/auth/roles`, `/users` (GET, POST, DELETE) |

Arayüzün tüm backend çağrıları `frontend/assets/api.js` üzerinden geçer.

---

## Örnek istek / cevaplar

### Giriş

```http
POST /api/auth/login
{ "username": "admin", "password": "demo1234" }
```

```json
{
  "token": "3f2c9b8a-...",
  "username": "admin",
  "full_name": "Sistem Yöneticisi",
  "role": "Admin",
  "permissions": ["view_all", "edit_all", "manage_users"],
  "message": "Giriş başarılı."
}
```

Parola veya özet bilgisi **hiçbir cevapta yer almaz**.

### Mali özet

```http
GET /api/finance/2025-2026/summary
```

```json
{
  "academic_year": "2025-2026",
  "total_revenue": "935.00",
  "total_expenditure": "933.00",
  "balance": "2.00",
  "balance_status": "fazla",
  "revenue_per_student_thousand_try": "233.75",
  "personnel_expense_share_percent": "46.62",
  "revenue_breakdown": [ { "category": "Öğrenim ücretleri", "amount": "742.00", "share_percent": "79.36" } ]
}
```

### Senaryo önizleme (veritabanına yazmaz)

```http
POST /api/scenarios/preview
{ "scenario_type": "tuition-change", "inputs": { "tuition_change_percent": 10 } }
```

### Veri aktarımı — önizleme

```http
POST /api/data-integration/import/faculties?preview=true
Content-Type: multipart/form-data
```

`preview=true` iken **hiçbir kayıt veritabanına yazılmaz**; dosya yalnızca
doğrulanır ve satır bazlı hata raporu döner.

### Asistan bağlamı (cevap üretmez)

```http
POST /api/assistant/prepare-context
{ "question": "Hangi programların doluluk oranı düşüyor?" }
```

```json
{
  "matched_topic": "öğrenci talebi",
  "context_items": [
    { "source_module": "Modül 2 — Öğrenci Analitiği", "label": "Toplam öğrenci", "value": "4000" }
  ],
  "notice": "Bu bir dil modeli cevabı DEĞİLDİR..."
}
```

---

## Endpoint listesi (etikete göre)


#### Academic Programs  (5 endpoint)

| Metot | Yol |
|---|---|
| `GET` | `/api/programs` |
| `POST` | `/api/programs` |
| `GET` | `/api/programs/{program_id}` |
| `PUT` | `/api/programs/{program_id}` |
| `DELETE` | `/api/programs/{program_id}` |

#### Administrative Units  (5 endpoint)

| Metot | Yol |
|---|---|
| `GET` | `/api/administrative-units` |
| `POST` | `/api/administrative-units` |
| `GET` | `/api/administrative-units/{unit_id}` |
| `PUT` | `/api/administrative-units/{unit_id}` |
| `DELETE` | `/api/administrative-units/{unit_id}` |

#### Akıllı Asistan (altyapı)  (4 endpoint)

| Metot | Yol |
|---|---|
| `GET` | `/api/assistant/architecture` |
| `POST` | `/api/assistant/prepare-context` |
| `GET` | `/api/assistant/sample-questions` |
| `GET` | `/api/assistant/status` |

#### Data Integration  (5 endpoint)

| Metot | Yol |
|---|---|
| `POST` | `/api/data-integration/import/{resource_type}` |
| `GET` | `/api/data-integration/jobs` |
| `GET` | `/api/data-integration/jobs/{job_id}` |
| `GET` | `/api/data-integration/resources` |
| `GET` | `/api/data-integration/templates/{resource_type}` |

#### Departments  (5 endpoint)

| Metot | Yol |
|---|---|
| `GET` | `/api/departments` |
| `POST` | `/api/departments` |
| `GET` | `/api/departments/{department_id}` |
| `PUT` | `/api/departments/{department_id}` |
| `DELETE` | `/api/departments/{department_id}` |

#### Faculties  (5 endpoint)

| Metot | Yol |
|---|---|
| `GET` | `/api/faculties` |
| `POST` | `/api/faculties` |
| `GET` | `/api/faculties/{faculty_id}` |
| `PUT` | `/api/faculties/{faculty_id}` |
| `DELETE` | `/api/faculties/{faculty_id}` |

#### Health  (1 endpoint)

| Metot | Yol |
|---|---|
| `GET` | `/health` |

#### Modül 11 — Erken Uyarı  (4 endpoint)

| Metot | Yol |
|---|---|
| `GET` | `/api/early-warning/alerts` |
| `GET` | `/api/early-warning/rules` |
| `GET` | `/api/early-warning/rules/pending` |
| `GET` | `/api/early-warning/summary` |

#### Modül 14 — Kullanıcı ve Yetkilendirme  (10 endpoint)

| Metot | Yol |
|---|---|
| `POST` | `/api/auth/login` |
| `POST` | `/api/auth/logout` |
| `POST` | `/api/auth/permissions/check` |
| `GET` | `/api/auth/roles` |
| `POST` | `/api/auth/session` |
| `GET` | `/api/auth/users` |
| `POST` | `/api/auth/users` |
| `GET` | `/api/auth/users/{user_id}` |
| `PATCH` | `/api/auth/users/{user_id}` |
| `DELETE` | `/api/auth/users/{user_id}` |

#### Modül 3 — Öğrenci Analitiği  (8 endpoint)

| Metot | Yol |
|---|---|
| `GET` | `/api/education-analytics/academic-years` |
| `GET` | `/api/education-analytics/admission-scores` |
| `POST` | `/api/education-analytics/comparative` |
| `GET` | `/api/education-analytics/demand-trends` |
| `GET` | `/api/education-analytics/overview` |
| `GET` | `/api/education-analytics/performance-trends` |
| `GET` | `/api/education-analytics/programs` |
| `GET` | `/api/education-analytics/programs/{program_code}` |

#### Modül 4 — Akademik Personel  (9 endpoint)

| Metot | Yol |
|---|---|
| `GET` | `/api/academic-staff` |
| `POST` | `/api/academic-staff` |
| `GET` | `/api/academic-staff/compare/{group_by}` |
| `GET` | `/api/academic-staff/overview` |
| `GET` | `/api/academic-staff/ranking` |
| `GET` | `/api/academic-staff/trend` |
| `GET` | `/api/academic-staff/{staff_id}` |
| `PATCH` | `/api/academic-staff/{staff_id}` |
| `DELETE` | `/api/academic-staff/{staff_id}` |

#### Modül 5 — Fiziksel Kaynaklar  (12 endpoint)

| Metot | Yol |
|---|---|
| `GET` | `/api/physical-resources/capacity/by-department` |
| `GET` | `/api/physical-resources/capacity/by-type` |
| `GET` | `/api/physical-resources/capacity/forecast` |
| `GET` | `/api/physical-resources/capacity/overcrowded` |
| `GET` | `/api/physical-resources/capacity/overview` |
| `GET` | `/api/physical-resources/capacity/per-person` |
| `GET` | `/api/physical-resources/capacity/underutilized` |
| `GET` | `/api/physical-resources/facilities` |
| `POST` | `/api/physical-resources/facilities` |
| `GET` | `/api/physical-resources/facilities/{facility_id}` |
| `PATCH` | `/api/physical-resources/facilities/{facility_id}` |
| `DELETE` | `/api/physical-resources/facilities/{facility_id}` |

#### Modül 6 — Finansal Analiz  (9 endpoint)

| Metot | Yol |
|---|---|
| `GET` | `/api/finance/periods` |
| `POST` | `/api/finance/periods` |
| `GET` | `/api/finance/trend` |
| `PATCH` | `/api/finance/{academic_year}` |
| `GET` | `/api/finance/{academic_year}/departments` |
| `PUT` | `/api/finance/{academic_year}/departments` |
| `POST` | `/api/finance/{academic_year}/entries` |
| `DELETE` | `/api/finance/{academic_year}/entries/{entry_id}` |
| `GET` | `/api/finance/{academic_year}/summary` |

#### Modül 7 — Program Sürdürülebilirliği  (5 endpoint)

| Metot | Yol |
|---|---|
| `GET` | `/api/program-sustainability/categories` |
| `GET` | `/api/program-sustainability/scores` |
| `POST` | `/api/program-sustainability/scores` |
| `GET` | `/api/program-sustainability/scores/{program_code}` |
| `GET` | `/api/program-sustainability/weights` |

#### Modül 8 — Performans Yönetimi  (11 endpoint)

| Metot | Yol |
|---|---|
| `GET` | `/api/kpi` |
| `POST` | `/api/kpi` |
| `GET` | `/api/kpi/attention` |
| `GET` | `/api/kpi/dimensions` |
| `GET` | `/api/kpi/faculty-comparison` |
| `GET` | `/api/kpi/scorecard` |
| `GET` | `/api/kpi/{kpi_id}` |
| `PATCH` | `/api/kpi/{kpi_id}` |
| `DELETE` | `/api/kpi/{kpi_id}` |
| `PUT` | `/api/kpi/{kpi_id}/faculty-values/{faculty_id}` |
| `POST` | `/api/kpi/{kpi_id}/measurements` |

#### Ranking Evaluations  (38 endpoint)

| Metot | Yol |
|---|---|
| `GET` | `/api/ranking-evaluations/assessments` |
| `POST` | `/api/ranking-evaluations/assessments/calculate` |
| `GET` | `/api/ranking-evaluations/assessments/latest/{framework_code}` |
| `GET` | `/api/ranking-evaluations/assessments/{assessment_id}` |
| `GET` | `/api/ranking-evaluations/assessments/{assessment_id}/dimensions` |
| `GET` | `/api/ranking-evaluations/assessments/{assessment_id}/missing-data` |
| `GET` | `/api/ranking-evaluations/benchmarks/comparison` |
| `GET` | `/api/ranking-evaluations/benchmarks/institutions` |
| `POST` | `/api/ranking-evaluations/benchmarks/institutions` |
| `GET` | `/api/ranking-evaluations/benchmarks/institutions/{institution_id}` |
| `PUT` | `/api/ranking-evaluations/benchmarks/institutions/{institution_id}` |
| `DELETE` | `/api/ranking-evaluations/benchmarks/institutions/{institution_id}` |
| `POST` | `/api/ranking-evaluations/benchmarks/values` |
| `GET` | `/api/ranking-evaluations/dashboard-summary` |
| `GET` | `/api/ranking-evaluations/dimensions` |
| `POST` | `/api/ranking-evaluations/dimensions` |
| `GET` | `/api/ranking-evaluations/dimensions/{dimension_id}` |
| `PUT` | `/api/ranking-evaluations/dimensions/{dimension_id}` |
| `DELETE` | `/api/ranking-evaluations/dimensions/{dimension_id}` |
| `GET` | `/api/ranking-evaluations/frameworks` |
| `POST` | `/api/ranking-evaluations/frameworks` |
| `GET` | `/api/ranking-evaluations/frameworks/{framework_id}` |
| `PUT` | `/api/ranking-evaluations/frameworks/{framework_id}` |
| `DELETE` | `/api/ranking-evaluations/frameworks/{framework_id}` |
| `POST` | `/api/ranking-evaluations/impact-preview` |
| `GET` | `/api/ranking-evaluations/indicators` |
| `POST` | `/api/ranking-evaluations/indicators` |
| `GET` | `/api/ranking-evaluations/indicators/{indicator_id}` |
| `PUT` | `/api/ranking-evaluations/indicators/{indicator_id}` |
| `DELETE` | `/api/ranking-evaluations/indicators/{indicator_id}` |
| `GET` | `/api/ranking-evaluations/metrics` |
| `POST` | `/api/ranking-evaluations/metrics` |
| `POST` | `/api/ranking-evaluations/metrics/sync-student-data` |
| `GET` | `/api/ranking-evaluations/metrics/{metric_id}` |
| `PUT` | `/api/ranking-evaluations/metrics/{metric_id}` |
| `DELETE` | `/api/ranking-evaluations/metrics/{metric_id}` |
| `GET` | `/api/ranking-evaluations/recommendations/{assessment_id}` |
| `GET` | `/api/ranking-evaluations/trends/{framework_code}` |

#### Scenario Analysis  (17 endpoint)

| Metot | Yol |
|---|---|
| `POST` | `/api/scenarios` |
| `GET` | `/api/scenarios` |
| `POST` | `/api/scenarios/baselines` |
| `GET` | `/api/scenarios/baselines` |
| `GET` | `/api/scenarios/baselines/active` |
| `POST` | `/api/scenarios/baselines/sync-student-data` |
| `GET` | `/api/scenarios/baselines/{baseline_id}` |
| `PUT` | `/api/scenarios/baselines/{baseline_id}` |
| `DELETE` | `/api/scenarios/baselines/{baseline_id}` |
| `POST` | `/api/scenarios/preview` |
| `GET` | `/api/scenarios/{scenario_id}` |
| `PUT` | `/api/scenarios/{scenario_id}` |
| `DELETE` | `/api/scenarios/{scenario_id}` |
| `GET` | `/api/scenarios/{scenario_id}/inputs` |
| `GET` | `/api/scenarios/{scenario_id}/results` |
| `GET` | `/api/scenarios/{scenario_id}/results/latest` |
| `POST` | `/api/scenarios/{scenario_id}/simulate` |

#### Student Analytics  (18 endpoint)

| Metot | Yol |
|---|---|
| `GET` | `/api/student-analytics/alerts` |
| `GET` | `/api/student-analytics/by-department` |
| `GET` | `/api/student-analytics/by-faculty` |
| `GET` | `/api/student-analytics/by-program` |
| `POST` | `/api/student-analytics/comparable-programs` |
| `GET` | `/api/student-analytics/comparable-programs` |
| `GET` | `/api/student-analytics/comparable-programs/{comparison_id}` |
| `PUT` | `/api/student-analytics/comparable-programs/{comparison_id}` |
| `DELETE` | `/api/student-analytics/comparable-programs/{comparison_id}` |
| `GET` | `/api/student-analytics/overview` |
| `POST` | `/api/student-analytics/program-snapshots` |
| `GET` | `/api/student-analytics/program-snapshots` |
| `GET` | `/api/student-analytics/program-snapshots/{snapshot_id}` |
| `PUT` | `/api/student-analytics/program-snapshots/{snapshot_id}` |
| `DELETE` | `/api/student-analytics/program-snapshots/{snapshot_id}` |
| `GET` | `/api/student-analytics/programs/{program_id}/comparisons` |
| `GET` | `/api/student-analytics/programs/{program_id}/demand` |
| `GET` | `/api/student-analytics/trends` |

#### Students  (10 endpoint)

| Metot | Yol |
|---|---|
| `POST` | `/api/students` |
| `GET` | `/api/students` |
| `GET` | `/api/students/{student_id}` |
| `PUT` | `/api/students/{student_id}` |
| `DELETE` | `/api/students/{student_id}` |
| `POST` | `/api/students/{student_id}/academic-records` |
| `GET` | `/api/students/{student_id}/academic-records` |
| `GET` | `/api/students/{student_id}/academic-records/{record_id}` |
| `PUT` | `/api/students/{student_id}/academic-records/{record_id}` |
| `DELETE` | `/api/students/{student_id}/academic-records/{record_id}` |

---

**TOPLAM 181 endpoint | 121 yol | 193 sema**
