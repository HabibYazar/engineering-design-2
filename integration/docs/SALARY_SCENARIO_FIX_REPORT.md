# Maaş Senaryosu — Semantik ve Mali Sunum Düzeltmeleri

Bildirdiğiniz hata doğruydu ve altında **üç ayrı kök neden** vardı. Bunları
düzeltirken senaryo motorunda başka bir hata daha ortaya çıktı.

**Önizleme:** `integration/docs/preview/salary_panel_preview.html`
(`node integration/tools_build_preview.js salary` ile üretilir)

---

## 1. Mali etkinin düzeltilmesi

### Önce (hatalı)

```
Ek brüt gelir            +612.000 USD    ← maaş artışı GELİR sayılmış
Ek operasyonel etki    -1.224.000 USD    ← 612.000 iki kez sayılmış
Net bütçe değişimi       -612.000 USD
```

### Sonra (doğru)

```
Mevcut net bütçe        2.900.000 USD
Akademik personel gideri  -612.000 USD
Senaryo net bütçesi     2.288.000 USD
```

| Gösterge | Taban | Senaryo | Değişim |
|---|---|---|---|
| Akademik personel gideri | 6.120.000 | 6.732.000 | +612.000 |
| İdari personel gideri | 2.090.000 | 2.090.000 | değişmedi |
| Toplam personel gideri | 8.210.000 | 8.332.000 | +612.000 |
| Toplam kurum harcaması | 33.060.000 | 33.672.000 | +612.000 |
| Toplam gelir | 35.960.000 | 35.960.000 | **0** |
| Net bütçe | 2.900.000 | 2.288.000 | −612.000 |

Bütün değerler senaryo motorundan gelir; hiçbiri sabit yazılmadı.

### Kök neden 1 — parasal kalemin YÖNÜ bilinmiyordu

Şelale kuralı "değişimi olan parasal metrikleri" alıyor, hangisinin gelir
hangisinin gider olduğunu **bilmiyordu**. `ScopedMetric` iki yeni alan
kazandı:

```python
flow: "inflow" | "outflow" | "balance" | "unit_price"
is_total: bool
```

Bir kalem bunları kendisi bildirebilir; bildirmezse `metric_semantics`
anahtar ve etiketten sınıflandırır. `unit_price` ayrı bir değer olmak
zorundaydı: "ortalama akademik maaş" bir bütçe akışı değildir, toplanamaz.

### Kök neden 2 — toplam kalemler katkı sayılıyordu

"Toplam gider etkisi" ile "akademik personel gideri" **aynı 612.000 USD'yi**
taşır. İkisi birden katkı sayılırsa tutar iki kez hesaplanır. Artık şelale
yalnızca `is_total=False` kalemleri kullanıyor ve **katkıların toplamı net
bütçe değişimine eşit olmak zorunda**. Eşitlenemezse fark uydurulmuş bir
kalem adıyla değil, açıkça *«Diğer kalemlerin etkisi»* olarak yazılıyor ve
o sütunun kaynak adresi boş bırakılıyor.

### Kök neden 3 — işaret kayboluyordu

Bir gider **artışı** kaynakta pozitiftir (+612.000) ama bütçeyi **azaltır**.
Doğrulama katmanı (ui_spec ↔ structured_result karşılaştırması) çubuğu
kaynağa göre "düzeltip" yukarı çeviriyordu. `ChartSeries.value_signs`
eklendi: her değerin kaynağa uygulanacak işareti açıkça taşınıyor.

---

## 2. Gerçek kademeli şelale

`waterfall_chart` artık bağımsız sütunlar değil, kümülatif kademeler çiziyor:

* İlk ve son sütun `kind="total"` — **mutlak seviye**, sıfırdan çizilir ve
  kümülatif düzeyi kendi değerine ayarlar.
* Ara sütunlar o seviyeden başlar, yukarı/aşağı iner.
* **Bütün** sütunlar bağlantı çizgileriyle bağlı (önceden toplam
  sütunlarından sonra çizgi kesiliyordu).
* Toplam sütunları işaretsiz yazılır: "2.900.000", "+2.900.000" değil — bir
  seviye artış değildir.

Öğrenci senaryosunda da aynı yapı çalışıyor:

```
Üniversite net bütçesi (mevcut)          2.900.000
Bu programdaki artışın ek gelir etkisi    +329.840
Diğer kalemlerin etkisi                    -72.800
Üniversite net bütçesi (senaryo)         3.157.040
```

---

## 3. Sorudaki bütün metrikler

KPI kartları artık sorunun sırasını izliyor:

| # | Kart | Değer |
|---|---|---|
| 1 | Akademik personel gideri | 6.120.000 → 6.732.000 USD · **+612.000 USD (%10 artış)** |
| 2 | Net bütçe | 2.900.000 → 2.288.000 USD · **−612.000 USD (%21,1 azalış)** |
| 3 | Personel gideri payı | %18,51 → %19,99 · **Artış: +1,48 puan** |
| 4 | Toplam kurum harcaması | 33.060.000 → 33.672.000 USD · +612.000 USD (%1,85 artış) |
| 5 | İdari personel gideri | 2.090.000 → 2.090.000 USD · **Değişmedi** |

Sorulan oran (`academic_personnel_expense_ratio`) **önce backend'e eklendi**;
`REQUIRED_FIELDS` listesine de girdi, yani metrik üretilemezse cevap
"başarılı" sayılmıyor ve pencere hiç oluşmuyor.

---

## 4. Akademik ve idari personelin ayrılması

### Bu turda bulunan hata — Türkçe küçük harf

`"İdari personel giderleri".lower()` Python'da `"idari personel giderleri"`
**değil**, `"i̇dari personel giderleri"` (i + birleşen üstteki nokta) üretir.
Bu yüzden kalem eşleşmiyor ve varsayılan kovaya — **teknoloji giderine** —
düşüyordu. Teknoloji kalemi projeksiyonda **döviz kuruyla** büyüdüğü için
2,09 milyon USD'lik idari maaş, kur senaryolarında kurla birlikte artıyordu.

Düzeltme:

* `_fold()` — Türkçe'ye duyarlı küçük harf çevirimi
* `administrative_personnel` ve `scholarship` kendi kovalarını aldı
* `ScenarioBaseline.annual_administrative_personnel_expense` alanı eklendi
* Motor idari gideri ayrı yürütüyor: akademik maaş zammından ve kurdan
  etkilenmiyor, yalnızca idari maaş değişimi ve kadro değişiminden etkileniyor
* `annual_personnel_expense` **akademik personel** anlamını koruyor —
  motor ortalama akademik maaşı bu değeri kadroya bölerek buluyor

**Taban toplam gider DEĞİŞMEDİ:** 33.060.000 USD (önce 6,12+5,20+4,10+10,25+7,39;
sonra 6,12+2,09+5,20+4,10+10,25+5,30). Bir test bunu koruyor.

Ayrıca `init_db()` içine küçük bir **eksik sütun denetimi** eklendi: projede
migration aracı yok ve elinizdeki veritabanı dosyası yeni sütunu tanımazdı.
Yalnızca ekleme yapar, idempotenttir.

---

## 5. Senaryoya uygun uyarı

*"Ek personel alımı ve fiziksel yatırım maliyetleri hesaplanmadı"* uyarısı
**öğrenci artışı** senaryosuna aittir: orada yeni öğrenciler yeni kadro ve
yeni derslik gerektirir. Maaş senaryosunda kadro da mekân da sabittir.

Maaş senaryosunun kendi kapsam kutusu:

> **Senaryonun kapsamı**
> ⃠ Yalnızca akademik personel maaşları %10 artırılmıştır; idari personel
>   maaşları ve akademik kadro sayısı sabit tutulmuştur.
> ⃠ Ek ders ödemeleri kapsam dışıdır; mali kayıtta ayrı kalem tutulmuyor.
> ⃠ Yan haklar ve işveren yükleri kapsam dışıdır; personel gideri kalemi
>   brüt maaş toplamı olarak alınmıştır.
> ⃠ Döviz kuru sabit kabul edilmiştir.
> ⃠ Enflasyon uygulanmamıştır.

Varsayımlar araç çıktısında `assumptions` alanında taşınıyor; arayüz onları
üretmiyor, yalnızca gösteriyor.

---

## 6. Risk seviyesi eşiklerden türetiliyor

`RISK_THRESHOLDS` tek yerde tanımlı:

| Eşik | Uyarı | Kritik |
|---|---|---|
| Kapasite karşılama oranı | < %80 | < %50 |
| Net bütçedeki gerileme | ≥ %10 | ≥ %20 |
| Personel gideri payı | ≥ %30 | ≥ %40 |
| Senaryo sonrası bütçe negatif | — | her zaman kritik |

`_risk_assessment()` seviyeyi **ve sebebini** döndürüyor. Sebep karar
özetinin altında yazıyor:

> **Sebep:** net bütçe %21,1 geriliyor — eşik %20.

Bir test aynı panelin farklı veriyle farklı seviye ürettiğini doğruluyor
(info → warning → critical).

---

## 7. Başlık ve yönetim özeti

Önce: *"Kurum için hesaplanan sonuçlar aşağıdadır."*

Sonra:

> **%10 akademik maaş artışı yıllık akademik personel giderini 612.000 USD
> artırıyor ve net bütçeyi aynı tutarda azaltıyor; personel gideri payı
> %18,51 → %19,99.**

Cümle şablondan değil, doğrulanmış metriklerden kuruluyor: değişim yönü,
tutarların eşit olup olmadığı ve oranın yönü hepsi veriden geliyor. Panel
başlığı da zammı söylüyor: *"Akademik Personel Maaş Senaryosu — %10 Zam"*.

---

## 8. Grafik seçimi

| Grafik | Neden |
|---|---|
| `dumbbell_chart` | Maaş gideri önce–sonra (6.120.000 → 6.732.000) |
| `waterfall_chart` | Net bütçe etkisi, gerçek kademeli |
| `gauge_group` | Personel gideri payı (%19,99 ve %26,20) |
| `horizontal_comparison_bar` | Gider kalemlerinin dağılımı |

Öğrenci, derslik ve laboratuvar bileşeni **yok** — o metrikler bu senaryoda
üretilmiyor, dolayısıyla kurallar hiç tetiklenmiyor.

İki kural genelleştirildi:

* **Hareket etmeyen metrik grafik üretmez.** Kadro sayısı 180 → 180; eskiden
  bunun için anlamsız bir dumbbell çiziliyordu. Sayım metriği değişmiyorsa
  kural parasal bir kaleme geçiyor.
* **Yeni kural `_rule_ratio`:** bir bütünün içindeki pay (%) → gauge grubu.
  Karşılama oranından farkı, talebin karşılanmasını değil toplamın içindeki
  payı ölçmesi.

---

## 9. Test sonuçları

```
Backend birim testleri            449 passed, 17 skipped
Backend entegrasyon testleri      210 passed        (189 → +21)
Arayüz (jsdom, model hazır)       200 passed        (179 → +21)
Arayüz (jsdom, Ollama kapalı)     193 passed
Mock Ollama testleri               37 passed
------------------------------------------------------
0 hata
```

İstenen 13 kontrol:

| # | Kontrol | Test |
|---|---|---|
| 1 | 6.120.000 × %10 = 612.000 USD | `test_ten_percent_raise_costs_six_hundred_twelve_thousand` |
| 2 | Maaş artışı gelir metriği değil | `test_salary_increase_is_never_reported_as_revenue` |
| 3 | 612.000 iki kez sayılmaz | `test_the_same_amount_is_not_counted_twice_in_the_waterfall` · `maas: 612.000 selalede tek bir SUTUN olarak var` |
| 4 | Net bütçe değişimi −612.000 | `test_net_balance_falls_by_exactly_the_extra_cost` |
| 5 | 2.900.000 → 2.288.000 | aynı test · `maas: net butce 2.900.000 -> 2.288.000` |
| 6 | Şelale başlangıç → etki → sonuç | `test_waterfall_runs_from_opening_balance_to_closing_balance` · `8b) selale baslangic butcesinden sonuc butcesine iniyor` |
| 7 | Personel gideri oranı ekranda | `test_personnel_expense_ratio_is_visible_on_screen` · `maas: personel gideri orani ekranda` |
| 8 | Akademik ve idari ayrı | `test_academic_and_administrative_personnel_are_separate` |
| 9 | Kapasite yatırım uyarısı yok | `test_salary_panel_does_not_show_capacity_investment_warning` |
| 10 | Kadro sabitliği varsayımı görünür | `test_salary_panel_shows_its_own_assumptions` |
| 11 | Risk eşikten hesaplanıyor | `test_risk_level_is_derived_from_thresholds_with_a_stated_reason` · `test_risk_level_changes_with_the_data` |
| 12 | Bütün değerler structured_result'tan | `test_every_salary_number_resolves_to_structured_result` |
| 13 | Öğrenci senaryosu bozulmadı | `test_old_enrollment_panel_still_works` + mevcut 38 test |

Ek olarak: `test_administrative_salaries_are_not_inflated_by_the_exchange_rate`
(kur %50 artsa bile idari maaş sabit, taban toplam gider 33.060.000 USD).

### Güncellenen iki eski test

Etiket değiştiği için iki test güncellendi — gevşetilmedi, **sıkılaştırıldı**:

* `test_salary_scenario_does_not_change_headcount`: artık metne ek olarak
  metriği de doğruluyor (180 = 180, change = 0, not alanında "SABİT").
* `test_salary_scenario_required_metrics_appear_in_the_answer`: 2 satır
  yerine 5 satır kontrol ediyor (akademik, idari, toplam personel, toplam
  harcama, net bütçe).

---

## 10. Değiştirilen dosyalar

| Dosya | Değişiklik |
|---|---|
| `app/services/scenario_baseline_builder.py` | Türkçe küçük harf düzeltmesi, idari personel ve burs kendi kovalarında |
| `app/models/scenario_baseline.py` | `annual_administrative_personnel_expense` |
| `app/database.py` | Eksik sütun denetimi (`_add_missing_columns`) |
| `app/services/scenario_engine.py` | İdari personel ayrı yürüyor; 6 yeni alan; 2 yeni karşılaştırma satırı |
| `app/services/assistant/tool_schemas.py` | `flow`, `is_total`, 14 yeni maaş senaryosu alanı, `assumptions` |
| `app/services/assistant/tools.py` | Maaş senaryosu 11 metrik üretiyor; varsayımlar; gelir/gider yönleri |
| `app/services/assistant/metric_semantics.py` | `classify_flow`, `looks_like_total`, `unit_price` |
| `app/services/assistant/response_composer.py` | `flow`/`is_total` taşınıyor; zorunlu alanlar genişledi |
| `app/services/assistant/ui_spec.py` | `value_signs`, `data_source_ids` |
| `app/services/assistant/ui_planner.py` | Gerçek şelale, çift sayma koruması, `_rule_ratio`, `_rule_expense_composition`, hareketsiz metrik filtresi |
| `app/services/assistant/ui_spec_builder.py` | Maaş KPI/risk/karar/özet, `RISK_THRESHOLDS`, senaryoya özgü kapsam kutusu |
| `frontend/assets/ai-view-renderer.js` | Kümülatif şelale, işaret uygulama, karar gerekçesi |
| `frontend/assets/integration.css` | `.ai-decision-reason` ve seviye vurguları |
| `backend/tests_integration/test_ui_spec.py` | 21 yeni test |
| `tests_ui/test_frontend.js` | 21 yeni kontrol |
| `integration/tools_build_preview.js` | `salary` önizlemesi |

**Dokunulmayanlar:** Ollama provider, araç çağrı döngüsü, intent router,
öğrenci senaryosu metrikleri, kapasite/FTE formülleri, program tahsis modeli.

---

## 11. Manuel test adımları

1. `python -m pytest integration/backend/tests_integration/test_ui_spec.py`
   — örnek dosyaları da tazeler.
2. `node integration/tools_build_preview.js salary` →
   `docs/preview/salary_panel_preview.html` dosyasını tarayıcıda açın.
3. Şelalede ilk sütunun 2.900.000, son sütunun 2.288.000 olduğunu ve
   aradaki tek sütunun aşağı indiğini görün.
4. Uygulamada asistana sorun:
   *"Akademik personel maaşlarına %10 zam yapılırsa toplam personel
   giderleri, net bütçe ve personel giderlerinin toplam harcamalara oranı
   nasıl etkilenir?"*
5. **Analizi Görüntüle** → beş KPI kartı, karar özeti ve altındaki risk
   gerekçesi, dört grafik, kapsam kutusu görünmeli.
6. Ekranda "Fiziksel yatırım maliyeti hesaplanmadı" **görünmemeli**.
7. Tarayıcı konsolunda hata olmamalı.

### Canlı Ollama testi

Bu turda **çalıştırılmadı** — sanal ortamda gerçek Ollama yok. Asistan
zinciri değişmedi ve dosya sağlam (17 test toplanıyor), ancak "canlı testler
geçti" denemez.

```powershell
$env:ASSISTANT_LIVE_TEST="1"
& ".\.venv\Scripts\python.exe" -m pytest `
  ".\integration\backend\tests\test_assistant_ollama_live.py" -v -s
```

---

## 12. Kalan sınırlar

* **Yan haklar, işveren yükleri ve ek ders ödemeleri mali kayıtta ayrı kalem
  olarak tutulmuyor.** Hesaplanamıyor; kapsam kutusunda açıkça yazıyor.
* İdari kadro değişiminin birim maliyeti hâlâ akademik ortalamanın %65'i
  varsayımıyla hesaplanıyor (idari kadro başına maaş verisi mali dönemde var
  ama senaryo motoru kadro değişimini oradan okumuyor).
* Gider dağılımı grafiği yalnızca personel kalemlerini gösteriyor: eğitim,
  Ar-Ge ve altyapı kalemleri araç çıktısında metrik olarak yer almıyor.
* "Diğer kalemlerin etkisi" sütunu, tek tek raporlanmayan kalemlerin
  toplamıdır; öğrenci senaryosunda −72.800 USD olarak görünüyor.
