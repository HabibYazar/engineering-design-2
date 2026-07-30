# Modül 3 — Stratejik Eğitim ve Öğrenci Analitiği

PDF **Bölüm 3 – Strategic Education and Student Analytics** karşılığı modül.

## Ana Sorumluluk

Öğrenci verisinden stratejik göstergeleri üretmek ve bunları hem üniversite geneli
(roll-up) hem de program bazında (drill-down) sunmak. Modül 7 ve Modül 11 bu modülün
ürettiği göstergeler üzerine kuruludur.

## PDF Bölüm 3 Gösterge Karşılığı

| PDF'te istenen | Nerede hesaplanıyor |
| :--- | :--- |
| Toplam öğrenci sayısı (üniversite + bölüm) | `get_university_overview`, `build_program_metrics` |
| Yeni kayıt / aktif / mezun sayıları | `current_status` kırılımı |
| Kontenjan ve doluluk oranı | `occupancy_rate` |
| Akademik performans ve mezuniyet oranı | `_graduation_stats`, `get_academic_performance_trend` |
| Hazırlık sınıfı öğrenci sayısı | `_student_composition` |
| Ortalama mezuniyet süresi | `_graduation_stats` |
| Öğrenci kaybı ve kayıt yenilememe oranları | `attrition_rate`, `non_renewal_rate` |
| Burslu öğrenci yüzdesi | `_student_composition` |
| Uluslararası öğrenci yüzdesi | `_student_composition` |
| Talep trendi + Ankara/Türkiye taban puan analizi | `get_demand_trends`, `get_admission_score_analysis` |

## Dosyalar

| Katman | Dosya | Açıklama |
| :--- | :--- | :--- |
| Model | `models/student.py` | Öğrenci künyesi, durum, burs, uyruk, mezuniyet yılları |
| Model | `models/student_academic_record.py` | Dönemlik ders yükü, GNO, kayıt yenileme |
| Model | `models/program_enrollment_snapshot.py` | Yıllık kontenjan, kayıt, taban puan, kayıp sayıları |
| Model | `models/academic_program.py` | Modül 1'in tablosunun yerel kopyası |
| Servis | `services/student_analytics_service.py` | Tüm gösterge hesaplamaları |
| Şema | `schemas/student_analytics.py` | Pydantic yanıt şemaları |
| Router | `routers/student_analytics.py` | 7 endpoint |

## Endpoint'ler

```
GET /api/student-analytics/academic-years
GET /api/student-analytics/overview?academic_year=2026-2027
GET /api/student-analytics/programs?academic_year=2026-2027
GET /api/student-analytics/programs/{program_code}
GET /api/student-analytics/admission-scores
GET /api/student-analytics/demand-trends
GET /api/student-analytics/performance-trends
```

## Oran Tanımları

- **Doluluk oranı** = o yılın kayıt sayısı / kontenjan
- **Öğrenci kaybı oranı** = o yıl terk eden / o yıl fiilen kayıtlı öğrenci gövdesi
- **Kayıt yenilememe oranı** = o yıl kaydını yenilemeyen / o yıl kayıtlı öğrenci gövdesi
- **Mezuniyet oranı** = mezun olanlar / beklenen mezuniyet yılı geçmiş kohort
  (hâlâ okuyan öğrenciler paydayı bozmasın diye dışarıda tutulur)
- **Ortalama mezuniyet süresi** = `actual_graduation_year - enrollment_year` ortalaması

## Durum

Çalışıyor — 7 endpoint, HTTP üzerinden doğrulandı.
