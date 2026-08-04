# Modül 10 — THE, QS ve YÖK Değerlendirme ve İzleme Yönetimi

> Bu klasör sunum amaçlıdır. Dosyalar `app/` altındaki orijinallerin birebir kopyasıdır.

> ### ⚠️ ÖNEMLİ
> **Bu modül gerçek THE, QS veya YÖK sıralaması ÜRETMEZ ve resmi sıralama tahmini YAPMAZ.**
> Skorlar kurumun kendi verisine dayanan **iç performans izleme**, **veri hazırlık**,
> **iç uyum** ve **iyileştirme takibi** amaçlıdır. Seed'deki ağırlıklar resmi metodolojinin
> kopyası değil, ondan esinlenen yapılandırılabilir değerlerdir. Karşılaştırma kurumları
> tamamen **DEMO** verisidir.

## Amaç

Üniversitenin THE, QS ve YÖK değerlendirme başlıklarındaki durumunu izler; hangi verinin
eksik olduğunu, hangi göstergede zayıf kalındığını ve hangi iyileştirmenin en çok kazanç
sağlayacağını gösterir.

## Ana Dosyalar

```
models/  (8 tablo)
  evaluation_framework.py         THE/QS/YÖK — anahtar: code + methodology_year
  evaluation_dimension.py         Boyutlar (ağırlıklı)
  evaluation_indicator.py         Göstergeler (hesaplama türü, yön, sınırlar)
  institutional_metric_value.py   Kurumun yıllık verisi + origin (automatic/manual/imported)
  framework_assessment.py         Hesaplanmış değerlendirme
  dimension_assessment.py         Boyut kırılımı
  benchmark_institution.py        Karşılaştırma kurumları (demo)
  benchmark_metric_value.py       Karşılaştırma gösterge değerleri
schemas/
  ranking_evaluations.py          11 enum + Create/Update/Response + detay raporlar
routers/
  ranking_evaluations.py          23 yol / 33 operasyon
services/
  ranking_calculation_service.py    Hesaplama motoru (etkin değer → skor → boyut → çerçeve)
  ranking_readiness_service.py      Hazırlık katsayıları, uyum formülü, risk eşikleri
  ranking_student_sync_service.py   Modül 1/2'den 17 metriğin otomatik üretimi
  ranking_benchmark_service.py      5 kapsamlı karşılaştırma
  ranking_recommendation_service.py Dinamik Türkçe öneriler
  ranking_impact_service.py         What-if etki analizi (kayıt yazmaz)
seed_ranking_data.py                3 çerçeve, 19 boyut, 40 gösterge, 57 veri, 5 kurum
```

## Veri Akışı

```
Modül 1/2 verisi ──► ranking_student_sync_service ──┐
                                                     ├──► InstitutionalMetricValue
Elle giriş / CSV import ─────────────────────────────┘         (origin ile ayrıştırılır)
                                                                       │
                                                                       ▼
                                              ranking_calculation_service
                                              ├─ resolve_effective_value()   calculation_type
                                              ├─ normalize_score()           0-100, direction
                                              ├─ evaluate_dimension()        ağırlıklı
                                              └─ evaluate_framework()        ağırlıklı
                                                                       │
                        ┌──────────────────────────────────────────────┤
                        ▼                                              ▼
            ranking_readiness_service                        build_missing_data_summary
            ├─ readiness (veri hazırlık)                     eksik/kısmi/geçersiz + kayıp
            ├─ compliance = perf × ready / 100
            └─ risk (hazırlık tabanıyla)
                        │
                        ▼
            ranking_recommendation_service ──► Türkçe öneri + expected_score_gain
```

## Veri Modeli

```
EvaluationFramework (1) ──< (N) EvaluationDimension (1) ──< (N) EvaluationIndicator
        │                                                          │
        │                                                          ├──< InstitutionalMetricValue
        │                                                          └──< BenchmarkMetricValue
        └──< (N) FrameworkAssessment (1) ──< (N) DimensionAssessment

BenchmarkInstitution (1) ──< (N) BenchmarkMetricValue
```

## Önemli Endpointler

| Metot | Yol | Açıklama |
|---|---|---|
| GET/POST | `/api/ranking-evaluations/frameworks` | Çerçeveler (ağırlık dengesiyle) |
| GET/POST | `/api/ranking-evaluations/dimensions` | Boyutlar |
| GET/POST | `/api/ranking-evaluations/indicators` | Göstergeler |
| GET/POST | `/api/ranking-evaluations/metrics` | Gösterge verisi (hesaplanmış skorla) |
| POST | `/api/ranking-evaluations/metrics/sync-student-data` | Modül 1/2'den otomatik doldurur |
| POST | `/api/ranking-evaluations/assessments/calculate` | Hesaplar (`persist=false` deneme) |
| GET | `/api/ranking-evaluations/assessments/latest/{code}` | En güncel değerlendirme |
| GET | `/api/ranking-evaluations/assessments/{id}/missing-data` | Eksik veri analizi |
| GET | `/api/ranking-evaluations/recommendations/{id}` | Stratejik öneriler |
| GET | `/api/ranking-evaluations/benchmarks/comparison` | 5 kapsamlı karşılaştırma |
| GET | `/api/ranking-evaluations/trends/{code}` | Yıllara göre gelişim |
| POST | `/api/ranking-evaluations/impact-preview` | Senaryo etkisi (kayıt yazmaz) |
| GET | `/api/ranking-evaluations/dashboard-summary` | Genel bakış paneli |

## Temel Hesaplamalar

**1. Etkin değer** (`calculation_type`)

| Tür | Formül |
|---|---|
| `raw` / `manual` | doğrudan `value` |
| `percentage` | `numerator / denominator × 100` |
| `ratio` | `numerator / denominator` |
| `score` | doğrudan 0-100 |
| `boolean` | ≠0 → 100, =0 → 0 |

**2. Normalizasyon (0-100)**

```
higher_is_better: value ≥ target → 100 | ≤ minimum → 0 | arada doğrusal
lower_is_better : value ≤ target → 100 | ≥ maximum → 0 | arada ters doğrusal
target_is_best  : hedefte 100, sınırlara yaklaştıkça 0
```

Sınır eksikse **hata verilmez**; açıklanabilir fallback uygulanır ve `calculation_notes`
alanına not düşülür.

**3. Hazırlık katsayıları** (`ranking_readiness_service.py`)

| Durum | Katsayı |
|---|---|
| `available` | 1.00 |
| `estimated` | 0.75 |
| `partial` | 0.50 |
| `missing` / `invalid` | 0.00 |

**4. Boyut ve çerçeve**

```
dimension.performance = Σ(skor × ağırlık) / Σ(skoru hesaplanabilen ağırlık)
framework.performance = Σ(boyut perf × boyut ağırlığı) / Σ(boyut ağırlığı)
framework.readiness   = Σ(boyut hazırlığı × boyut ağırlığı) / Σ(boyut ağırlığı)

compliance = performance × readiness / 100
```

**5. Risk** — uyum skoruna göre 75/50/25 eşikleri. **Hazırlık tabanı:** `readiness < 50` →
en az `high`, `readiness < 25` → her zaman `critical`.

**6. Eksik veri kaybı**

```
kayıp = boyut ağırlık payı × göstergenin boyut içindeki payı × (1 − hazırlık katsayısı) × 100
```

**7. Öneri kazancı**

```
expected_score_gain = (100 − mevcut skor) × gösterge payı × boyut payı
```

## Diğer Modüllerle Bağlantılar

| Bağlantı | Nasıl |
|---|---|
| **Modül 1** | Program `degree_level` → doktora/lisans göstergeleri |
| **Modül 2** | 17 öğrenci metriği → `auto_source_key` eşleşmesiyle gösterge verisi |
| **Modül 9** | `impact-preview` Modül 9 motorunu **kullanmaz**; bağımsız çalışır |
| **Modül 13** | 3 yeni `resource_type`; `benchmark-metric-values` iki üst kayıt çözer |

## Sunumda Gösterilecek Noktalar

1. **Performans ve veri hazırlığı ayrı ölçülüyor** — bir kurum az veriyle yüksek performans
   gösteriyor olabilir. `compliance = performance × readiness / 100` bu ikisini birleştirir:
   performansı 80 ama verisinin yarısı hazır bir çerçevenin gerçek uyum düzeyi 40'tır.

2. **Eksik veri gizlenmiyor, ölçülüyor** — veri olmayan göstergeler performans paydasına
   dahil edilmiyor (aksi halde veri toplayamayan kurum "kötü performanslı" görünürdü),
   ama readiness skorunda ve eksik veri raporunda puan kaybıyla birlikte raporlanıyor.

3. **Metodoloji sürümlenebilir** — çerçeve anahtarı `code + methodology_year`. THE 2025 ve
   THE 2026 aynı anda saklanabilir; geçmiş değerlendirmeler hangi metodolojiyle
   hesaplandıysa o haliyle korunur. Ağırlıklar veritabanından okunduğu için metodoloji
   değişikliği **kod değişikliği gerektirmez**.

4. **Manuel veri otomatik veriyi ezmez** — `origin` alanı (`automatic` / `manual` /
   `imported`) sayesinde senkronizasyon yalnızca kendi ürettiği kayıtları günceller.
   Doğrulanmış insan verisi korunur; `overwrite_manual=true` ile bilinçli olarak değiştirilebilir.

5. **Veri odaklı what-if analizi** — her gösterge `impact_numerator_variable` /
   `impact_denominator_variable` alanlarıyla senaryo değişkenlerine bağlı. Yeni bir gösterge
   eklendiğinde etki analizi **kod değişikliği olmadan** çalışır. Analiz veritabanına
   hiçbir kayıt yazmaz: veriler bellekte kopyalanıp motor yeniden çalıştırılır.

6. **Sıralama yalnızca yeterli veri varsa** — karşılaştırmada `rank`/`percentile` en az 3
   kurum verisi varsa hesaplanır; aksi halde açık uyarı döner. Az veriden sıralama üretmek
   yanıltıcı olurdu.
