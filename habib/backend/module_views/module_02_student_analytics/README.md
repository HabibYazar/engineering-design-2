# Modül 2 — Strategic Education and Student Analytics

> Bu klasör sunum amaçlıdır. Dosyalar `app/` altındaki orijinallerin birebir kopyasıdır.

## Amaç

Üniversite, fakülte, bölüm ve program düzeyinde öğrenci sayılarını, kayıtları,
mezuniyetleri, akademik başarıyı, program dolulukları, burslu ve uluslararası öğrenci
oranlarını, öğrenci kaybını ve yıllara göre eğilimleri analiz eder; eşik dışına çıkan
metrikler için **erken uyarı** üretir.

## Ana Dosyalar

```
models/
  student.py                        Öğrenci (8 index: numara, program, durum, yıl...)
  student_academic_record.py        Dönemlik performans + unique(öğrenci, yıl, dönem)
  program_enrollment_snapshot.py    Yıllık kontenjan/yerleşme/taban puan
  comparable_university_program.py  Diğer üniversitelerin programları
schemas/
  students.py                       4 kaynağın Create/Update/Response + çapraz doğrulama
  student_analytics.py              Analitik cevapları, TrendMetric / AlertSeverity enum'ları
routers/
  students.py                       Öğrenci + akademik kayıt CRUD
  student_analytics.py              8 analitik endpoint + 2 CRUD grubu
services/
  student_analytics_service.py      Overview, program/bölüm/fakülte kırılımı, talep, karşılaştırma
  student_trend_service.py          Yıl bazlı toplu sorgular, değişim yüzdeleri
  student_alert_service.py          8 uyarı kuralı, şiddet seviyeleri, Türkçe öneriler
seed_student_data.py                120 öğrenci, 240 kayıt, 8 snapshot, 7 karşılaştırma
```

## Veri Akışı

```
Router (yalnızca parametre iletir)
   │
   ▼
student_analytics_service
   │  tek SQL sorgusu: SUM(CASE WHEN ... THEN 1 ELSE 0 END)
   │  ┌─────────────────────────────────────────────┐
   │  │ 11 ayrı COUNT yerine → 1 sorgu              │
   │  │ program kırılımı → GROUP BY (N+1 yok)       │
   │  └─────────────────────────────────────────────┘
   ▼
program sonuçları ──► bölüm sonuçları ──► fakülte sonuçları
   │                     (ağırlıklı toplama, SQL tekrar çalışmaz)
   ▼
student_alert_service ──► eşik karşılaştırması ──► Türkçe uyarı + öneri
```

## Veri Modeli

```
AcademicProgram (Modül 1)
   ├──< (N) Student ──< (N) StudentAcademicRecord
   └──< (N) ProgramEnrollmentSnapshot

ComparableUniversityProgram   (bağımsız — dış üniversite verisi)
```

## Önemli Endpointler

| Metot | Yol | Açıklama |
|---|---|---|
| GET | `/api/students` | 9 filtre + `search` (numara/ad/soyad) |
| POST/GET/PUT/DELETE | `/api/students/{id}` | CRUD (DELETE → soft delete) |
| POST/GET/PUT/DELETE | `/api/students/{id}/academic-records` | Dönemlik kayıtlar |
| GET | `/api/student-analytics/overview` | Genel özet |
| GET | `/api/student-analytics/by-program` | Program bazlı analitik |
| GET | `/api/student-analytics/by-department` | Bölüm bazlı (birleştirilmiş) |
| GET | `/api/student-analytics/by-faculty` | Fakülte bazlı (birleştirilmiş) |
| GET | `/api/student-analytics/trends?metric=` | 11 metrik için yıllık trend |
| GET | `/api/student-analytics/programs/{id}/demand` | Talep analizi + trend yorumu |
| GET | `/api/student-analytics/programs/{id}/comparisons` | Diğer üniversitelerle kıyas |
| GET | `/api/student-analytics/alerts` | Erken uyarılar |

## Temel Hesaplamalar

```
occupancy_rate    = enrolled_student_count / quota × 100

graduation_rate   = graduated / (graduated + active + dropped_out) × 100
                    ↑ non-renewed paydaya girmez: henüz kesin ayrılmış sayılmaz

attrition_rate    = dropped_out / total_students × 100
non_renewal_rate  = non_renewed / total_students × 100

scholarship_%     = (scholarship_rate_percent > 0 olanlar) / total × 100
international_%   = (is_international = true olanlar) / total × 100

average_graduation_duration = AVG(actual_graduation_year − enrollment_year)

passed_course_ratio     = SUM(passed) / SUM(registered) × 100
credit_efficiency_ratio = SUM(earned_credits) / SUM(attempted_credits)
```

**Bölüm/fakülte birleştirmesi ağırlıklıdır:** doluluk kontenjan toplamı üzerinden, GPA
öğrenci sayısıyla ağırlıklandırılır. Basit ortalama alsaydık 10 kişilik bir program ile
200 kişilik bir program eşit ağırlık alırdı.

**Talep trendi:** Son 3 yılın doluluk oranı **ve** taban puanı birlikte değerlendirilir.
İkisi de yükseliyorsa `increasing`, ikisi de düşüyorsa `decreasing`, diğer durumlarda
`stable`. Tek ölçüte bakmak yanıltıcı olurdu (kontenjan artınca doluluk düşebilir ama puan
yükselmeye devam edebilir).

**8 erken uyarı kuralı:** düşük doluluk (%50), yüksek kayıp (%15), yüksek yenilememe (%10),
düşük mezuniyet (%40), düşük GPA (2.00), düşük uluslararası oran, taban puanın 2 yıl üst
üste düşmesi, talebin 3 yıl üst üste düşmesi.

## Diğer Modüllerle Bağlantılar

| Bağlantı | Nasıl |
|---|---|
| **Modül 1** | `Student.academic_program_id` → `AcademicProgram` (FK) |
| **Modül 9** | Aktif öğrenci sayısı → `POST /api/scenarios/baselines/sync-student-data` |
| **Modül 9** | `?use_live_student_data=true` ile simülasyon canlı sayıyı kullanır |
| **Modül 10** | 17 öğrenci metriği → gösterge verisi (`auto_source_key` eşleşmesi) |
| **Modül 13** | 4 kaynak da CSV/XLSX/JSON ile aktarılabilir |

## Sunumda Gösterilecek Noktalar

1. **N+1 sorgu bilinçli olarak önlendi** — `student_analytics_service.py` içinde 11 ayrı
   `COUNT` yerine tek sorguda `SUM(CASE WHEN ... THEN 1 ELSE 0 END)`; program kırılımı
   `GROUP BY` ile tek seferde. Öğrenci kayıtları hiçbir zaman toplu olarak belleğe çekilmez.

2. **Mezuniyet oranının paydası bir tasarım kararı** — `graduated + active + dropped_out`.
   Kaydını yenilemeyenler dahil edilmiyor çünkü henüz kesin ayrılmış sayılmıyorlar; onlar
   ayrı bir metrikte (`non_renewal_rate`) izleniyor.

3. **Ağırlıklı birleştirme** — bölüm ve fakülte skorları basit ortalama değil, kontenjan ve
   öğrenci sayısıyla ağırlıklı. (`build_department_analytics`, `build_faculty_analytics`)

4. **Talep trendinde iki ölçüt birlikte** — doluluk ve taban puan aynı yönde hareket
   etmedikçe trend `stable` kalıyor. Seed verisi bunu test edebilmek için SWE'yi yükselen,
   CENG'i düşen olarak kurgulanmış.

5. **Uyarı şiddeti sapma büyüklüğüne göre** — eşiğin biraz altındaki bir değerle çok
   altındaki aynı seviyede gösterilmiyor (`_severity_for_gap`). %49 doluluk `warning`,
   %20 doluluk `critical`.
