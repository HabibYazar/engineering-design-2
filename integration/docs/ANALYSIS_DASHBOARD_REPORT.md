# Dinamik Analiz Paneli — Yönetici Dashboard Tasarımı

Panel teknik olarak çalışıyordu ama bir *rapor* gibi görünüyordu: düz
çubuklar, uzun metin, birbirinin aynı grafikler. Bu turda panel bir *yönetici
dashboard*'una dönüştürüldü.

Değişmeyen üç şey: hesaplama motoru, `structured_result`ın tek sayısal
kaynak olması, kapalı bileşen kataloğu + kapsamlı CSS mimarisi.

**Statik önizleme:** `integration/docs/preview/analysis_panel_preview.html`
— tarayıcıda açın, sunucu gerekmez. `node integration/tools_build_preview.js`
ile gerçek builder çıktısından yeniden üretilir.

---

## 1. Değiştirilen dosyalar

| Dosya | Değişiklik |
|---|---|
| `app/services/assistant/metric_semantics.py` | **yeni** — metriğin anlam türünü belirleyen sınıflandırıcı |
| `app/services/assistant/ui_planner.py` | **yeni** — anlama göre grafik seçen 10 kural |
| `app/services/assistant/ui_spec.py` | Şema 2.0: 33 bileşen türü, `data` + `data_source_ids`, `span`, `tone`, `markers`, fallback zinciri |
| `app/services/assistant/ui_spec_builder.py` | Yeniden yazıldı: karar özeti, KPI kartları, risk kartları, karar listesi, 8 açılır bölüm |
| `app/services/assistant/tool_schemas.py` | `ScopedMetric.semantic_type` (isteğe bağlı; boşsa sınıflandırıcı belirler) |
| `app/services/assistant/response_composer.py` | Her metriğe `semantic_type` eklenir |
| `frontend/assets/ai-view-renderer.js` | 16 SVG grafik çizici, kaynak doğrulama, fallback, hata yalıtımı, erişilebilirlik |
| `frontend/assets/integration.css` | Modern koyu tema, 12 kolonlu grid, animasyon, mobil kırılım |
| `frontend/assets/views-assistant.js` | `structured_result` de saklanıyor (doğrulama için) |
| `frontend/index.html` | Önbellek anahtarı `?v=14` |
| `backend/tests_integration/test_ui_spec.py` | 38 test |
| `tests_ui/test_frontend.js` | 72 arayüz kontrolü |
| `integration/tools_build_preview.js` | **yeni** — statik önizleme üretici |

**Dokunulmayanlar:** Ollama provider, araç çağrı döngüsü, intent router,
`response_composer`ın hesaplama/metin üretimi, kapasite ve FTE formülleri,
program tahsis modeli.

---

## 2. Eklenen grafik bileşenleri

Katalog 12'den **33 bileşene** çıktı. Yeni grafikler:

```
dumbbell_chart      slope_chart        bullet_chart
radial_gauge        semi_circle_gauge  gauge_group
waterfall_chart     forecast_line_chart stacked_area_chart
grouped_bar_chart   horizontal_comparison_bar
heatmap             risk_matrix        treemap
radar_chart         sparkline          progress_ring
```

Yeni kart ve metin bileşenleri: `decision_summary`, `kpi_card`,
`risk_summary_card`, `decision_list`, `legend_panel`.

Katalog **iki yerde birden kapalı**: backend'de Pydantic `Literal`,
frontend'de `AI_COMPONENTS` sözlüğü. `sankey_chart` gibi bir tür ne API'den
çıkabilir ne de çizilir.

### Fallback zinciri

```
dumbbell   → horizontal_comparison_bar → bar_chart
bullet     → grouped_bar_chart → bar_chart
radial_gauge → progress_ring
semi_circle_gauge → radial_gauge → progress_ring
waterfall  → grouped_bar_chart → bar_chart
forecast   → line_chart
stacked_area → line_chart
heatmap    → grouped_bar_chart
risk_matrix → risk_summary_card
treemap    → horizontal_comparison_bar
radar      → grouped_bar_chart
```

Renderer zinciri sonuna kadar izler. Zincir de tükenirse **yalnızca o kart**
"Bu grafik çizilemedi. Diğer bölümler etkilenmedi." kutusuna dönüşür.

---

## 3. Grafik seçim kuralları

Grafik türü ne modelin ne de programcının keyfine bırakıldı. Her metrik bir
**anlam türü** taşır; `ui_planner` bu türe bakar.

### Anlam türü nasıl belirlenir

`metric_semantics.classify(key, unit, label)` — önce birim, sonra anahtar:

| Birim / ipucu | Anlam türü |
|---|---|
| `USD` | `monetary_change` |
| `%` + "coverage"/"shortfall" | `capacity_coverage` |
| `%` + "utilization" | `utilization` |
| `FTE` + "gap"/"marginal" | `staffing_gap` |
| `FTE` (diğer) | `target_comparison` |
| koltuk-saat / istasyon-saat / eş zamanlı kişi + "_demand" | `capacity_demand` |
| aynı birimler + "capacity" | `target_comparison` |
| `kişi` + "gap" | `staffing_gap` |
| `öğrenci`, `kişi` | `count_change` |
| `durum` | `status` |

Bir araç anlamı kendisi bildirebilir (`ScopedMetric.semantic_type`);
bildirmezse bu kurallar işler. Yarın eklenecek bir metrik de doğru grafiğe
düşer.

### Anlam → grafik

| Veri anlamı | Grafik |
|---|---|
| önce → sonra değişimi | `dumbbell_chart` / `slope_chart` |
| kapasite ↔ ihtiyaç ↔ hedef | `bullet_chart` |
| talebin karşılanma oranı | `radial_gauge` (gauge grubu) |
| gelir / gider / net etki | `waterfall_chart` |
| yıllara göre seyir | `line_chart` / `stacked_area_chart` |
| gelecek tahmini | `forecast_line_chart` + güven aralığı |
| birim karşılaştırması | `radar_chart` (≤6 birim) / `heatmap` |
| olasılık × etki | `risk_matrix` |
| kaynak dağılımı | `treemap` |
| haftalık kapasite talebi | `horizontal_comparison_bar` |

Eşleştirmeler **isme değil veriye** bakar. Örnek — bullet chart: aynı
birimdeki metriklerden *senaryosu olmayan* biri sabit kapasitedir, *hem
mevcut hem senaryo değeri olan* biri hareketli ihtiyaçtır. `program_staff_fte`
veya `program_instructor_fte` fark etmez.

Sınırlar: en fazla **4 grafik**, aynı tür **iki kez kullanılmaz** (gauge gibi
küçük çoklular hariç), bir kural çökerse yalnızca o kural atlanır.

### Genellik testi

`test_chart_rules_are_generic_for_an_unrelated_dataset`, hiç görülmemiş
anahtarlarla uydurma bir kuruma ait metrikler verir
(`program_trainee_count`, `program_studio_coverage`, `program_grant_effect`)
ve aynı dört grafiğin seçildiğini doğrular. `test_planner_picks_other_chart_families`
sıralama → radar, dağılım → treemap, risk → matris yollarını kontrol eder.

> Bu turda bulunan bir genellik hatası: mali zincirin başı önce
> `"revenue"` adı aranarak bulunuyordu; "hibe" kalemi olan bir veri setinde
> şelale hiç üretilmiyordu. Artık zincirin sonu net/bakiye metriği, başı ise
> **en özel kapsamdaki diğer parasal kalem** olarak seçiliyor.

---

## 4. Yeni dashboard yerleşimi

12 kolonlu grid. Her bileşen `span` taşır; mobilde hepsi tek kolona düşer.

```
┌──────────────────────────────────────────────────────────────┐
│ KARAR ÖZETİ                                        span 12   │
│ "Bilgisayar Mühendisliği Lisans Programı: %15 öğrenci artışı │
│  ek gelir oluşturuyor ancak programın mevcut akademik ve     │
│  fiziksel kapasite açığını önemli ölçüde büyütüyor."          │
│ [2025-2026] [Program senaryosu] [Bilgisayar Müh.] [Yüksek risk]│
├──────────────────────────────────────────────────────────────┤
│ TEMEL GÖSTERGELER — 5 KPI kartı (auto-fit)                   │
│ Öğrenci  │ FTE açığı │ Ek gelir │ Derslik % │ Laboratuvar %  │
│ 426      │ 3,30 FTE  │ +329.840 │ %38,96    │ %65,87         │
│ ▲ +56    │ +2,80 FTE │   USD    │ ▼ -5,90p  │ ▼ -9,97p       │
├──────────────────────────────────────────────────────────────┤
│ ● Mevcut durum  ● Senaryo sonucu  ● Kapasite/hedef  span 12  │
├───────────────────────────┬──────────────────────────────────┤
│ Öğrenci sayısı — dumbbell │ Akademik Kapasite — bullet       │
│                  span 6   │                       span 6     │
├───────────────────────────┼──────────────────────────────────┤
│ Karşılama oranı — 2 gauge │ Mali Etki Zinciri — waterfall    │
│                  span 6   │                       span 6     │
│                           │ ⚠ Hesaplanmayan maliyetler       │
├──────────────────────────────────────────────────────────────┤
│ EN KRİTİK RİSKLER — 3 kart (span 4 + auto-fit)               │
│ Akademik kapasite │ Derslik kapasitesi │ Laboratuvar         │
│ [Kritik] +2,80 FTE│ [Kritik] +1.008 kh │ [Yüksek] +224 ih    │
├──────────────────────────────────────────────────────────────┤
│ KARAR ÖNERİLERİ — en fazla 4 madde              span 12      │
├──────────────────────────────────────────────────────────────┤
│ AYRINTILAR — 8 kapalı accordion                 span 12      │
└──────────────────────────────────────────────────────────────┘
```

### Bu senaryodaki grafikler

**A. Öğrenci değişimi — dumbbell**
370 (mavi) ve 426 (turuncu) iki nokta, aralarında gri bağlantı çizgisi,
ortada `+56` etiketi. Altında metinsel değer tablosu.

**B. Akademik kapasite — bullet**
Gri bant = 18 FTE kullanılabilir kapasite. İnce mavi çubuk = 18,50 mevcut
ihtiyaç. İnce turuncu çubuk = 21,30 senaryo ihtiyacı. Kesikli dikey çizgi =
kapasite sınırı işareti. Üçü aynı eksende.

**C. Fiziksel kapasite — iki radial gauge**
Merkezde büyük senaryo oranı (%38,96 / %65,87), halkanın altında soluk mavi
yayla mevcut oran, altında "Mevcut: %44,86" ve "▼ 5,90 puan".

**D. Mali etki — waterfall**
`+329.840` (yeşil, artış) → `-72.800` (kırmızı, azalış) → `+257.040` (indigo,
toplam). Ortadaki kalem **türetilmiştir**: `net.change − brüt.change`.
Renderer bu farkı iki kaynaktan yeniden hesaplar.

Yanında ayrı bir uyarı kartı:

> ⃠ Ek personel maliyeti hesaplanmadı
> ⃠ Fiziksel yatırım maliyeti hesaplanmadı

**Hesaplanmayan maliyetler şelaleye sıfır kalem olarak konmadı.** Sıfır bir
ölçüm sonucudur, "bilmiyoruz" değildir; ikisini karıştırmak grafiği yalancı
yapardı. `test_uncalculated_costs_never_appear_as_zero` bunu koruyor.

### Renk sistemi

| Anlam | Renk | Değişken |
|---|---|---|
| Mevcut durum | mavi | `--ai-baseline: #3b82f6` |
| Senaryo sonucu | turuncu | `--ai-scenario: #f97316` |
| Kapasite / hedef | gri | `--ai-capacity: #94a3b8` |
| Olumlu mali etki | yeşil | `--ai-positive: #22c55e` |
| Uyarı | amber | `--ai-warning: #f59e0b` |
| Kritik risk | kırmızı | `--ai-critical: #ef4444` |
| Bilgilendirme | indigo | `--ai-info: #6366f1` |

Bileşen kendi rengini **seçemez**; yalnızca `role`/`tone` belirteci seçer,
rengi renderer sabit sözlükten verir. Bu yüzden bir renk iki grafikte farklı
anlam taşıyamaz.

Legend panelde **bir kez**, ilk grafiğin üstünde. Gauge'larda legend yerine
doğrudan etiket var. Grafiklerin kendi veri tabloları legend değildir ve
farklı etiketler kullanır ("Mevcut" / "Senaryo"), böylece tekrar izlenimi
oluşmaz.

---

## 5. Accordion yapısı

Ana ekranda uzun metin yok. Sekiz bölüm, hepsi **kapalı**:

1. Detaylı yönetim değerlendirmesi (LLM yorumu)
2. Program kapsamındaki bütün sonuçlar
3. Üniversite geneli etkiler
4. Hesaplama yöntemi (formüller)
5. Varsayımlar ve hariç tutulan maliyetler
6. Kullanılan veri kaynakları
7. Teknik sonuç (`structured_result` JSON)
8. Ham asistan cevabı (5.700 karakter)

`<details>/<summary>` kullanıldı: klavye desteği tarayıcıdan geliyor, ayrı
bir tuş dinleyicisi yazmaya gerek kalmadı.

Sohbet balonunda hâlâ yalnızca kısa özet + **Analizi Görüntüle** düğmesi var.

---

## 6. Güvenlik kontrolleri

| Saldırı | Savunma | Sonuç |
|---|---|---|
| Katalog dışı `sankey_chart` / `script_block` | Pydantic `Literal` + frontend kayıt defteri | Bileşen atlanır, panel çizilir |
| Şemada olmayan `html` / `on_click` / `style` alanı | `extra="forbid"` | `ValidationError` |
| `<script>`, `<iframe>`, `<img onerror>`, `<svg onload>` | Her metin alanında `fmt.esc()`; biçimlendirme kaçırmadan **sonra** | DOM'a etiket girmiyor, düz metne dönüşüyor |
| Tema üzerinden CSS enjeksiyonu (`accent: "red;} body{…}"`) | Kapalı belirteç sözlüğü | Varsayılana düşüyor |
| `view_id` ile seçici kırma (`aiv-x"] , * { display:none }`) | `aiSafeId()` beyaz listesi | `aiv-xdisplaynoneya`, tek `{`, global seçici yok |
| ui_spec'teki sayının bozulması | `data_source_ids` + `source_metric_ids` çözülüp karşılaştırılır | **Kaynak kazanır**, konsola uyarı |
| Modelin uydurduğu sayı (`%68,42`, `9.876.543`) | Kart ve grafikler yalnızca `structured_result`tan beslenir | Hiçbir bileşene sızmıyor |
| Modelin JavaScript çalıştırması | Şemada yürütülebilir alan yok; renderer model içeriğini `eval` etmez | Mümkün değil |

Üretilen `<style>` bloğu tek kurallık ve gövdesinde **yalnızca `--ai-` ile
başlayan değişken tanımları** var:

```css
.ai-generated-view[data-view-id="aiv-809b63e710c0"]{
  --ai-accent:#6366f1; --ai-gap:16px; --ai-card-radius:14px;
  --ai-baseline:#3b82f6; --ai-scenario:#f97316; --ai-capacity:#94a3b8;
  --ai-positive:#22c55e; --ai-warning:#f59e0b; --ai-critical:#ef4444;
  --ai-info:#6366f1;
}
```

`body`, `html`, `*`, `#sidebar`, `header` ve uygulamanın diğer sayfaları
hedeflenemiyor. Gerçek stiller `integration.css` içindeki sabit `.ai-*`
sınıflarında; model onlara dokunamıyor.

---

## 7. Responsive davranış

| Kırılım | Davranış |
|---|---|
| ≥ 861 px | 12 kolonlu grid; grafikler `span 6`, riskler `span 4`, karar özeti `span 12` |
| ≤ 860 px | `.ai-grid` tek kolona düşer, `.ai-cell` `grid-column: 1 / -1`, KPI değeri 1,5 rem'e iner, iç boşluk 14 px'e düşer |

KPI ve risk satırları 12 kolonluk gridi zorlamak yerine
`repeat(auto-fit, minmax(190px, 1fr))` kullanır — 5 kart 12 kolona bölünmez;
sıkıştırmak yerine sığdırmak doğru davranış.

Erişilebilirlik:

* Renk tek anlam taşıyıcısı değil — her seviyenin metin karşılığı var
  (Kritik / Yüksek / İzlenmeli / Uygun) ve her grafiğin altında metinsel
  değer tablosu duruyor.
* Her grafik `role="img"` + `aria-label` taşıyor.
* Accordion ve kapat düğmesi klavyeyle kullanılabiliyor; kapat düğmesinin
  `aria-label`'ı var.
* Tooltip dışında da bütün temel değerler görünür.
* `prefers-reduced-motion` ile animasyonlar kapanıyor.

---

## 8. Test sonuçları

```
Backend birim testleri            449 passed, 17 skipped
Backend entegrasyon testleri      189 passed        (178 → +11)
Arayüz (jsdom, model hazır)       179 passed        (154 → +25)
Arayüz (jsdom, Ollama kapalı)     172 passed
Mock Ollama testleri               37 passed
------------------------------------------------------
0 hata
```

İstenen 20 kontrol:

| # | Kontrol | Nerede |
|---|---|---|
| 1 | Ana görünümde uzun Markdown yok | `test_long_markdown_is_absent_from_the_default_view` · `1) ana gorunumde uzun Markdown raporu yok` |
| 2 | Uzun rapor yalnızca accordion açılınca | `test_long_report_lives_only_inside_a_closed_accordion` · `2b) accordion acilinca uzun metin goruntuleniyor` |
| 3 | En fazla 5 KPI kartı | `test_default_view_respects_the_information_hierarchy` · `3) …en fazla 5 KPI karti var` |
| 4 | Aynı grafik türü tekrarlanmıyor | `test_no_chart_type_is_repeated_unnecessarily` · `4) …gereksiz tekrarlanmiyor` |
| 5 | Öğrenci değişimi dumbbell/fallback | `test_student_change_uses_a_dumbbell_or_valid_fallback` · `5) + 5b)` |
| 6 | FTE karşılaştırması bullet/fallback | `test_fte_comparison_uses_a_bullet_or_valid_fallback` · `6) + 6b)` |
| 7 | Oranlar gauge/fallback | `test_coverage_uses_gauges_or_valid_fallback` · `7) + 7b)` |
| 8 | Mali etki waterfall/fallback | `test_financial_impact_uses_a_waterfall_or_valid_fallback` · `8)` |
| 9 | Bütün sayılar `structured_result` ile aynı | `test_every_number_in_the_panel_resolves…`, `test_chart_values_equal_their_declared_sources`, `test_kpi_card_values_equal…` · `9) + 9b)` |
| 10 | Ham LLM metninden sayı ayrıştırılmaz | `test_no_number_is_parsed_from_the_raw_model_text` · `10)` |
| 11 | Hesaplanmayan maliyetler sıfır değil | `test_uncalculated_costs_never_appear_as_zero`, `…are_shown_as_a_visible_warning` · `11) + 11b)` |
| 12 | Renk anlamları tutarlı | `test_colour_meaning_is_consistent_across_every_chart` · `12) + 12b)` |
| 13 | Legend tekrarlanmıyor | `test_legend_is_defined_exactly_once…` · `13) 13b) 13c)` |
| 14 | Bilinmeyen grafik tipi reddedilir | `test_unknown_chart_type_is_rejected` · `14) + 14b)` |
| 15 | Zararlı HTML/JS/CSS reddedilir | `test_extra_fields_and_free_css_are_rejected`, `test_malicious_interpretation…` · `15) → 15g)` |
| 16 | Bir grafik hatası diğerlerini etkilemez | `16) 16b) 16c)` |
| 17 | Mobil tek kolon | `17) 17b) 17c)` |
| 18 | Accordion klavyeyle | `18) → 18f)` |
| 19 | KPI kartlarında birim ve kapsam | `test_kpi_cards_carry_unit_and_scope` · `19) 19b) 19c)` |
| 20 | Eski testler geçmeye devam ediyor | 449 + 189 + 37 |

Ek olarak grafik seçim kurallarının genelliği dört testle doğrulanıyor
(`test_chart_rules_are_generic_*`, `test_planner_picks_other_chart_families`,
`test_planner_never_exceeds_the_chart_budget`,
`test_semantic_classification_is_driven_by_unit_and_key`).

### Bu turda bulunan hatalar

**1. `data` sözlüğü SIRAYLA kaynağa bağlanıyordu.** Bullet chart'ın alanları
`capacity / baseline / scenario`, adresleri ise farklı metriklere aitti;
doğrulama katmanı doğru sayıyı "düzelterek" bozuyordu. Eşleşme artık
`data_source_ids` ile **ada** bağlı. (Grafik yine doğru çiziliyordu çünkü
çizici `series`'ten okuyor — sessiz bir hataydı, konsol uyarısı ortaya
çıkardı.)

**2. Mali zincir kuralı isme bağlıydı.** "revenue" geçmeyen bir gelir
kaleminde (hibe, bağış) şelale hiç üretilmiyordu — genellik testi yakaladı.

**3. Dumbbell alt başlığı legend metnini tekrar ediyordu.** "Mevcut
durumdan senaryo sonucuna" ifadesi legend etiketini içeriyordu; artık
"Senaryo öncesi ve sonrası".

### Manuel test adımları

1. `python -m pytest integration/backend/tests_integration/test_ui_spec.py`
   — arayüz örnek dosyalarını da tazeler.
2. `node integration/tools_build_preview.js` → `docs/preview/analysis_panel_preview.html`
   dosyasını tarayıcıda açın. Sağ üstteki düğmeyle aydınlık/koyu temayı
   karşılaştırın; pencereyi 860 px altına daraltıp tek kolona düştüğünü
   görün; accordion'ları Tab + Enter ile açın.
3. Uygulamayı çalıştırın (`run_project.ps1`), Akıllı Asistan'a
   *"Bilgisayar Mühendisliği öğrenci sayısı %15 artarsa ne olur?"* sorun.
4. Balonda kısa özet + **Analizi Görüntüle** düğmesi görünmeli.
5. Düğmeye basın: karar özeti, 5 KPI kartı, dumbbell + bullet + gauge +
   waterfall, 3 risk kartı, karar önerileri açılmalı.
6. Ayrıntı bölümlerinin kapalı geldiğini, açınca uzun metnin göründüğünü
   doğrulayın.
7. Tarayıcı konsolunda hata olmamalı.

### Canlı Ollama testi

Bu turda **çalıştırılmadı** — sanal ortamda gerçek Ollama yok. Dosya sağlam
(17 test toplanıyor) ve asistan zinciri değişmedi, ancak "canlı testler
geçti" denemez.

```powershell
$env:ASSISTANT_LIVE_TEST="1"
& ".\.venv\Scripts\python.exe" -m pytest `
  ".\integration\backend\tests\test_assistant_ollama_live.py" -v -s
```

Hedef: **17 passed**

---

## 9. Kalan sınırlar

* `slope_chart`, `forecast_line_chart`, `stacked_area_chart`, `heatmap`,
  `sparkline` katalogda ve çiziciye bağlı, ama mevcut araçlar zaman serisi
  üretmediği için planner henüz seçmiyor. Tarihsel veri geldiğinde kural
  zaten yerinde.
* Model tema, bileşen sırası ve grafik türü **seçmiyor**; hepsi backend'de
  sabit. Şema buna hazır — modele "hangi doğrulanmış metrik öne çıksın"
  sorulabilir, ama yeni sayı üretemez.
* Öğrenci senaryosu dışındaki sonuç türleri (maaş senaryosu, kurumsal özet)
  genel KPI kartları üretiyor; grafik kuralları çalışıyor ama o veri
  setlerinde yeterli metrik yok.
* Ek personel ve yatırım maliyeti hâlâ hesaplanmıyor; panel bunu iki yerde
  birden açıkça söylüyor.
* Playwright kurulu değil; uçtan uca akış jsdom ile doğrulandı (gerçek
  tıklamalar, gerçek DOM, gerçek CSSOM — ama gerçek düzen motoru değil).
