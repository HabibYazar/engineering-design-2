# Modül 9 — What-if Scenario Analysis

> Bu klasör sunum amaçlıdır. Dosyalar `app/` altındaki orijinallerin birebir kopyasıdır.

## Amaç

Üniversite yöneticisinin *"öğrenci sayısını %10 artırırsak ne olur?"*, *"enflasyon %50 olursa
bütçe tutar mı?"* gibi soruları veri üzerinden yanıtlamasını sağlar. Finans, personel
ihtiyacı, öğrenci başına maliyet ve fiziksel kapasite üzerindeki tahmini etkiyi hesaplar,
riskleri tespit eder ve Türkçe öneriler üretir.

## Ana Dosyalar

```
models/
  scenario_baseline.py         Mevcut durum referansı (tek aktif kayıt kuralı)
  scenario.py                  Senaryo başlığı + inputs/results ilişkileri
  scenario_input.py            Girdi parametreleri (her simülasyonda yeni kayıt)
  scenario_result.py           20 metrik + kapasite durumu + risk + öneri
schemas/
  scenarios.py                 4 enum, baseline/senaryo/input şemaları, SimulationResponse
routers/
  scenarios.py                 15 endpoint (baseline, CRUD, simulate, preview, results)
services/
  scenario_engine.py           Tüm formüller, safe_divide, kapasite durumu
  scenario_risk.py             7 risk kuralı + low/medium/high/critical seviyelendirme
  scenario_recommendations.py  Risk kodu → Türkçe öneri + bütçe/maliyet notları
seed_scenario_data.py          2026 baseline + 4 örnek senaryo
```

## Veri Akışı

```
ScenarioBaseline (mevcut durum)  +  ScenarioInput (değişiklikler)
                          ↓
                  scenario_engine.calculate()
                  ├─ growth_factor(p) = 1 + p/100
                  ├─ safe_divide()  → payda 0 ise 0 döner, çökmez
                  └─ Decimal aritmetiği baştan sona
                          ↓
                  ScenarioComputation (saf veri nesnesi)
                          ↓
                  scenario_risk.evaluate()  → risk listesi + seviye
                          ↓
                  scenario_recommendations.build()  → Türkçe metin
                          ↓
                  ScenarioResult (kaydedilir)  /  preview → kaydedilmez
```

`scenario_engine.calculate()` **saf bir fonksiyondur**: veritabanına, FastAPI'ye veya HTTP'ye
bağımlı değildir. Bu yüzden formüller tek başına test edilebilir.

## Veri Modeli

```
ScenarioBaseline   (bağımsız — sistemde yalnızca BİR aktif kayıt)

Scenario (1) ──< (N) ScenarioInput
         (1) ──< (N) ScenarioResult
```

## Önemli Endpointler

| Metot | Yol | Açıklama |
|---|---|---|
| POST/GET | `/api/scenarios/baselines` | Baseline (aktifse diğerlerini pasifleştirir) |
| GET | `/api/scenarios/baselines/active` | Aktif baseline (yoksa **409**) |
| POST | `/api/scenarios/baselines/sync-student-data` | Modül 2'den öğrenci sayısını senkronize eder |
| POST/GET/PUT/DELETE | `/api/scenarios/{id}` | Senaryo CRUD (DELETE → `archived`) |
| POST | `/api/scenarios/{id}/simulate` | Hesaplar ve **kaydeder** (201) |
| GET | `/api/scenarios/{id}/results/latest` | En son sonuç |
| POST | `/api/scenarios/preview` | Hesaplar ama **hiçbir kayıt yazmaz** |

`?use_live_student_data=true` — başlangıç öğrenci sayısı Modül 2'deki aktif öğrenci
sayısından alınır. Varsayılan `false`: baseline kullanılır (mevcut davranış korunur).

## Temel Hesaplamalar

`growth(p) = (1 + p / 100)`

```
projected_student_count = baseline.student_count × growth(student_change_percent)

gross_tuition   = öğrenci × ücret × growth(tuition_change_percent)
effective_burs  = baseline.scholarship_rate + scholarship_change_percent
kesinti         = gross_tuition × effective_burs / 100
tuition_revenue = gross_tuition − kesinti

projected_revenue = tuition + research × growth(research_%) + other

average_staff_cost  = personnel_expense / academic_staff_count
personnel_expense'  = personnel_expense + (staff_change × average_staff_cost)
education_expense'  = education × growth(student_%) × growth(inflation)
rd_expense'         = rd × growth(research_%) × growth(inflation)
building_expense'   = building × growth(inflation)
technology_expense' = technology × growth(inflation) × growth(exchange_rate)

student_staff_ratio = projected_students / projected_staff
cost_per_student    = projected_expenditure / projected_students
```

Her gider kalemi farklı bir değişkene bağlı: eğitim öğrenci sayısıyla, Ar-Ge araştırma
bütçesiyle, teknoloji ithal ağırlıklı olduğu için kurla birlikte hareket eder.

**7 risk kuralı:** bütçe açığı · öğrenci/personel oranı > 25 · derslik kapasitesi aşımı ·
laboratuvar kapasitesi aşımı · burs oranı 0–100 dışı (**kritik**) · personel ≤ 0 (**kritik**) ·
öğrenci ≤ 0 (**kritik**).

**Risk seviyesi:** 0 risk → `low` · 1–2 → `medium` · 3+ → `high` · en az bir kritik
geçersizlik → `critical` (sayıya bakılmaz, çünkü diğer sayılar da güvenilmez olur).

## Diğer Modüllerle Bağlantılar

| Bağlantı | Nasıl |
|---|---|
| **Modül 2** | `sync-student-data` aktif öğrenci sayısını baseline'a yazar |
| **Modül 2** | `use_live_student_data=true` ile canlı sayı simülasyonu besler |
| **Modül 10** | Modül 10'un `impact-preview` servisi bu motoru **kullanmaz**; bağımsız çalışır (Modül 9 bozulmasın diye) |

## Sunumda Gösterilecek Noktalar

1. **Decimal ve özel `MoneyType` sütun tipi** — SQLite `Numeric`'i float olarak saklar.
   `app/core/decimal_types.py` Decimal'i **metin olarak** yazıp okurken geri çevirir; yazılan
   değerin aynısının okunduğu testle doğrulandı. `0.1 + 0.2` sapması milyonluk bütçede
   gerçek hataya dönüşürdü.

2. **Hesaplama motoru saf fonksiyon** — `calculate()` yalnızca baseline + input alır,
   dataclass döndürür. Router hiç hesap yapmaz. Bu ayrım 164 testin formülleri veritabanı
   olmadan doğrulamasını mümkün kıldı.

3. **`safe_divide` ile sıfıra bölme koruması** — personel sayısı 0'a düşen senaryoda program
   çökmüyor; oran `0.00` dönüyor ve durum `critical` risk olarak raporlanıyor.

4. **Kritik risklerde seviye atlaması** — burs > %100, personel ≤ 0 veya öğrenci ≤ 0
   olduğunda risk sayısına bakılmadan doğrudan `critical`. Bu senaryolar HTTP hatası değil,
   `200` + `risk_level: critical` döndürüyor; yönetici *neden* geçersiz olduğunu görsün diye.

5. **`preview` ve `student_count_override`** — ön izleme veritabanına yazmaz; canlı öğrenci
   verisi kullanılırken baseline nesnesi **mutasyona uğratılmaz**, motora geçici bir override
   verilir. Aksi halde bir simülasyon kalıcı veriyi bozardı.
