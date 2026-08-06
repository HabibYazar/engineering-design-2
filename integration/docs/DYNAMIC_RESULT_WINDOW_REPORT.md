# Dinamik Sonuç Penceresi — Uygulama Raporu

Asistan artık cevabı yalnızca uzun bir Markdown metni olarak vermiyor.
Backend, doğrulanmış `structured_result`tan **deterministik bir arayüz
tanımı** (`ui_spec`) üretiyor; arayüz bu tanımı kapalı bir bileşen
kataloğuyla çiziyor.

```
araç sonucu → structured_result → ui_spec → renderer → pencere
   (Pydantic)      (Pydantic)     (Pydantic)  (vanilla JS)
```

Modelin bu zincirdeki tek işi kısa yönetim yorumunu yazmaktır. **Model
sayı üretmez, HTML üretmez, CSS üretmez, JavaScript çalıştırmaz.**

---

## 1. UI şeması

`app/services/assistant/ui_spec.py`

| Sınıf | Görev |
|---|---|
| `UiSpec` | Pencerenin tamamı: sürüm, tür, kimlik, başlık, tema, bölümler, izlenebilirlik |
| `Section` | Beş bölüm türünden biri: `metric_grid`, `chart_grid`, `risk_summary`, `management_comment`, `details` |
| `Component` | Tek görsel bileşen; `source_keys` ile hangi metrikten geldiğini söyler |
| `ChartSeries` | Grafik serisi: `label`, `role` (`baseline`/`scenario`/`capacity`), sayı listesi |
| `Theme` | Beş kapalı belirteç; serbest CSS yok |

Bütün modellerde `ConfigDict(extra="forbid")`. Şemada olmayan bir alan
(ör. `html`, `on_click`, `css`) doğrulamadan geçmez.

`source_keys` alanı belgeleme değil, **kanıttır**: testler her kartın
gösterdiği sayıyı bu anahtarlarla `structured_result`a geri bağlar.

---

## 2. Bileşen kayıt defteri

Kapalı katalog — 12 tür:

```
metric_card          comparison_metric    bar_chart
line_chart           gauge                risk_card
information_box      recommendation_list  data_source_panel
scope_badge          assumptions_panel    expandable_details
```

İki yerde birden kapalıdır:

* **Backend** — `ComponentType` bir `Literal`; `script_block` gibi bir tür
  Pydantic doğrulamasında düşer, API'den hiç çıkamaz.
* **Frontend** — `AI_COMPONENTS` sözlüğünde karşılığı olmayan tür
  çizilmez; `console.warn` yazılıp bileşen atlanır, uygulama çökmez.

Tek kapı yeterli değildi: API dışarıdan da beslenebilir, arayüz de yalnız
başına güvenilir olmalı.

---

## 3. Renderer

`frontend/assets/ai-view-renderer.js` — 400 satır, bağımlılık yok, CDN yok.

* `aiRenderView(spec)` → `<style>` + `.ai-generated-view` + bölümler + altbilgi
* `aiRenderComponent(component)` → tek bileşen; bilinmeyen tür boş döner
* `aiSafeText(raw)` → **önce kaçırır, sonra** sınırlı biçimlendirme uygular
  (başlık, madde listesi, paragraf). Ters sırada yapılsaydı gelen bir
  `<script>` sayfaya girerdi.
* `aiSafeId(viewId)` → CSS seçicisine girmeden önce beyaz liste
  (`[A-Za-z0-9_-]`)
* `aiBarChart(c)` → çubuklar `div` yüksekliğiyle çizilir; tıklanabilir veya
  çalıştırılabilir hiçbir şey üretilmez

Grafik değerleri `title` özniteliğinde de yazılır, böylece fare üzerine
gelince tam sayı okunur.

---

## 4. Oluşturulan dinamik pencere

`app/services/assistant/ui_spec_builder.py` — **hesap yapmaz, metinden sayı
ayıklamaz.** Her değer `structured_result["metrics"]` içindeki bir kayıttan
biçimlendirilerek gelir.

CENG-BSC %15 artış senaryosu için üretilen pencere:

**Temel Sonuçlar — 5 kart**

| Kart | Değer |
|---|---|
| Öğrenci sayısı | 370 öğrenci → 426 öğrenci (+56) |
| Program FTE açığı | 0,50 FTE → 3,30 FTE · *Senaryonun etkisi: +2,80 FTE* |
| Ek gelir etkisi | +329.840 USD |
| Derslik karşılama oranı | %44,86 → %38,96 |
| Laboratuvar karşılama oranı | %75,84 → %65,87 |

Her kartta kapsam rozeti var: *Program: Bilgisayar Mühendisliği Lisans
Programı*. Etiketsiz sayı kalmıyor.

**Riskler — iki ayrı kart**

```
Mevcut durumdaki riskler  (Senaryodan bağımsız)
  · program derslik kullanım oranı mevcut durumda %222,92 — zaten aşılmış
  · program laboratuvar kullanım oranı mevcut durumda %131,86 — zaten aşılmış

Senaryonun eklediği etki
  · Program derslik ihtiyacı: +1.008 koltuk-saat
  · Program laboratuvar ihtiyacı: +224 istasyon-saat
  · Program FTE açığı: +2,80 FTE
  · Üniversite derslik açığı:     380 → 400 eş zamanlı kişi (eklenen: +20)
  · Üniversite laboratuvar açığı: 392 → 402 eş zamanlı kişi (eklenen: +10)
```

Kurumun 380 kişilik açığı senaryodan önce de vardı; pencere bunu senaryoya
yazmıyor.

**Ayrıntılar — kapalı açılır bölümler**

`Ayrıntılı program sonuçları` · `Üniversite geneli etkiler` ·
`Hesaplama yöntemi` (formüller) · `Tam metin rapor` (5.700 karakterlik
Markdown)

Varsayılan görünüm 2.366 karakter; tam raporun yarısından kısa. 40 satırlık
metin artık sohbet balonunu doldurmuyor.

**Sohbet balonu** kısa özet + `Analizi Görüntüle` düğmesi gösteriyor.
Pencere tanımı konuşma geçmişinde saklandığı için aynı analiz sonradan
tekrar açılabiliyor.

---

## 5. Grafikler — 3 adet

| Grafik | Kategori | Seriler |
|---|---|---|
| Öğrenci sayısı | Öğrenci sayısı | mevcut (mavi) · senaryo (turuncu) |
| Akademik kapasite | Akademik kapasite (FTE) | kapasite (gri) · mevcut gerekli · senaryo gerekli |
| Fiziksel kapasite | Derslik (koltuk-saat) · Laboratuvar (istasyon-saat) | kapasite · mevcut talep · senaryo talebi |

Renk anlamı üç grafikte de aynı: **mavi = mevcut durum, turuncu = senaryo
sonucu, gri = kullanılabilir kapasite.** Bu yüzden legend açıklaması
penceredeki ilk grafiğe **bir kez** konuyor; diğerlerinin `legend` alanı
boş. Aynı açıklamayı üç kez yazmak ekranı kalabalıklaştırmaktan başka bir
şey yapmazdı.

Legend renkleri doğrudan kod değil, kapsamlı CSS değişkeni:
`var(--ai-baseline)`, `var(--ai-scenario)`, `var(--ai-capacity)`.

---

## 6. Scoped CSS sistemi

Model tema seçebilir ama **CSS yazamaz.** Beş belirteç, hepsi kapalı liste:

| Belirteç | Değerler |
|---|---|
| `accent` | indigo · teal · amber · slate · rose |
| `density` | compact · comfortable |
| `card_radius` | sharp · soft · round |
| `chart_emphasis` | low · normal · high |
| `risk_emphasis` | low · normal · high |

Renderer bunları tek bir kurala çevirir:

```css
.ai-generated-view[data-view-id="aiv-809b63e710c0"]{
  --ai-accent:#4f46e5; --ai-gap:14px; --ai-card-radius:10px;
  --ai-chart-opacity:0.8; --ai-risk-opacity:0.85;
  --ai-baseline:#2563eb; --ai-scenario:#ea580c; --ai-capacity:#94a3b8;
}
```

Üretilen blokta **yalnızca `--ai-` ile başlayan değişken tanımları** var;
başka hiçbir özellik yazılamaz. Seçici her zaman `[data-view-id]` ile
sınırlı. `body`, `html`, `*`, `#sidebar`, `header` ve uygulamanın diğer
sayfaları hedeflenemiyor — gerçek stiller `integration.css` içindeki sabit
`.ai-*` sınıflarında duruyor, model onlara dokunamıyor.

Listede olmayan bir belirteç sessizce varsayılana düşüyor:
`accent: "red;} body { display:none } .x{color:"` → `--ai-accent:#4f46e5`.

---

## 7. Güvenlik kontrolleri

| Saldırı | Savunma | Sonuç |
|---|---|---|
| `<script>` / `<iframe>` / `<img onerror>` başlıkta, gövdede, markdown'da | `fmt.esc()` her metin alanında; biçimlendirme kaçırmadan **sonra** | DOM'a hiç etiket girmiyor, düz metne dönüşüyor |
| Bilinmeyen `type: "script_block"` | Pydantic `Literal` + frontend kayıt defteri | Bileşen atlanıyor, pencere çiziliyor |
| Şemada olmayan `html` / `on_click` alanı | `extra="forbid"` | `ValidationError` |
| Tema üzerinden CSS enjeksiyonu | Kapalı belirteç sözlüğü | Varsayılana düşüyor |
| `view_id` ile seçici kırma: `aiv-x"] , * { display:none } .y[a="` | `aiSafeId()` beyaz listesi | `aiv-xdisplaynoneya` — tek `{`, global seçici yok |
| Modelin uydurduğu sayı (`%68,42`, `9.876.543`) | Kart/grafik yalnızca `structured_result`tan besleniyor | Sayı hiçbir bileşene sızmıyor |
| Modelin JavaScript çalıştırması | Şemada yürütülebilir alan yok; renderer `eval`/`innerHTML`-of-model kullanmıyor | Mümkün değil |

`window.__pwned` bayrağıyla doğrulandı: zehirlenmiş pencere çizildikten
sonra bayrak hâlâ 0.

---

## 8. Test sonuçları

```
Backend birim testleri            449 passed, 17 skipped
Backend entegrasyon testleri      178 passed        (önceki 151 → +27)
Arayüz (jsdom, model hazır)       154 passed        (önceki 108 → +46)
Arayüz (jsdom, Ollama kapalı)     147 passed
Mock Ollama testleri               37 passed
------------------------------------------------------
0 hata
```

İstenen 15 kontrol:

| # | Kontrol | Nerede | Durum |
|---|---|---|---|
| 1 | Kartlardaki bütün sayılar `structured_result` ile aynı | `test_every_card_number_comes_from_structured_result` + `pencere: kart sayilari structured_result ile ayni` | ✅ |
| 2 | Serbest metinden sayı ayrıştırılmaz | `test_no_number_is_parsed_from_free_text` + `pencere: uydurma sayilar varsayilan gorunumde yok` | ✅ |
| 3 | Bilinmeyen component type reddedilir | `test_unknown_component_type_is_rejected*` + `pencere: bilinmeyen bilesen turu cizilmiyor` | ✅ |
| 4 | Global CSS üretilemez | `test_theme_only_accepts_closed_tokens`, `test_ui_spec_carries_no_css_or_markup` + 4 arayüz kontrolü | ✅ |
| 5 | Program ve üniversite metrikleri ayrı bölümlerde | `test_program_and_university_metrics_stay_in_separate_sections` + 3 arayüz kontrolü | ✅ |
| 6 | Derslik açığı 380 → 400, etki +20 | `test_classroom_gap_is_shown_as_380_to_400_with_plus_20` | ✅ |
| 7 | Laboratuvar açığı 392 → 402, etki +10 | `test_laboratory_gap_is_shown_as_392_to_402_with_plus_10` | ✅ |
| 8 | FTE açığı 0,50 → 3,30, marjinal +2,80 | `test_fte_gap_card_shows_zero_fifty_to_three_thirty_and_marginal` | ✅ |
| 9 | Mavi/turuncu legend bir kez görünür | `test_legend_is_defined_exactly_once_for_the_whole_view` + `pencere: legend aciklamasi tek bir kez cizildi` | ✅ |
| 10 | Uzun Markdown varsayılan görünümde yok | `test_long_markdown_is_not_part_of_the_default_view` + `pencere: 40 satirlik markdown varsayilan gorunumde degil` | ✅ |
| 11 | "Analizi Görüntüle" çalışır | `asistan: dugme pencereyi acti` + canlı uçtan uca kontrol | ✅ |
| 12 | Açılır teknik detaylar çalışır | `pencere: acilir teknik detay acilip icerigi gosteriyor` | ✅ |
| 13 | Maliyet hariç uyarısı görünür | `test_cost_exclusion_warning_is_visible_by_default` + 2 arayüz kontrolü | ✅ |
| 14 | XSS ve zararlı CSS engellenir | `test_malicious_interpretation_stays_plain_text` + 7 arayüz kontrolü | ✅ |
| 15 | Eski asistan ve backend testleri geçer | 449 + 178 + 37 | ✅ |

### Örnek dosyalar elle yazılmıyor

`tests_ui/fixtures/ui_spec_sample.json` ve `structured_result_sample.json`,
**backend testi tarafından her koşuda yeniden üretiliyor**
(`test_ui_fixture_for_the_frontend_test_is_regenerated`). Elle yazılmış bir
örnek backend değiştiğinde sessizce eskir ve arayüz testi artık
üretilmeyen bir yapıyı doğrulamaya devam ederdi.

### Canlı Ollama testi

Bu turda **çalıştırılmadı** — sanal ortamda gerçek Ollama yok. Dosya
sağlam (17 test toplanıyor), asistan zinciri değişmedi, ancak
"canlı testler geçti" denemez. Çalıştırma:

```powershell
$env:ASSISTANT_LIVE_TEST="1"
& ".\.venv\Scripts\python.exe" -m pytest `
  ".\integration\backend\tests\test_assistant_ollama_live.py" -v -s
```

Hedef: **17 passed**

---

## 9. Bu turda bulunan hatalar

**1. Kaydırma hatası çizilmiş pencereyi siliyordu.**
`openAssistantView` içinde çizim ve `scrollIntoView` aynı `try` bloğundaydı.
`scrollIntoView` bulunmayan bir ortamda pencere başarıyla çiziliyor, sonra
istisna yakalanıp yerine "Analiz penceresi çizilemedi" hata kutusu
geçiyordu. Çalışan bir özelliği yardımcı bir davranış yüzünden kaybetmek
olurdu. Kaydırma artık çizimden sonra ve ayrı bir denemede yapılıyor.

**2. Yönetim yorumunda ham Markdown başlıkları görünüyordu.**
Pencerede `### Program değerlendirmesi` diye yazıyordu. `aiSafeText` başlık
satırlarını tanımıyordu; artık `.ai-sub-head` olarak çiziliyor.

**3. `data-view-id` özniteliği ile CSS seçicisi farklı temizlikten
geçiyordu.** Öznitelik `fmt.esc()`, seçici `aiSafeId()` kullanıyordu;
zararlı bir kimlikte ikisi eşleşmez, tema hiç uygulanmazdı. İkisi de artık
aynı temizlenmiş değeri kullanıyor.

**4. Legend üç grafikte birden tanımlıydı.** İlk grafiğin serileri tek
rolde toplandığı için iki çubuk aynı renkteydi ve legend yanıltıcıydı.
Grafikler rol bazlı serilere çevrildi, legend tek yere alındı.

---

## 10. Değiştirilen dosyalar

| Dosya | Değişiklik |
|---|---|
| `app/services/assistant/ui_spec.py` | **yeni** — şema ve kapalı katalog |
| `app/services/assistant/ui_spec_builder.py` | **yeni** — deterministik üretici |
| `app/services/assistant/chat_service.py` | `ui_spec` üretimi ve cevaba eklenmesi |
| `app/services/assistant/schemas.py` | `ChatResponse.ui_spec` |
| `frontend/assets/ai-view-renderer.js` | **yeni** — çizici, güvenli metin, scoped CSS |
| `frontend/assets/views-assistant.js` | Analiz paneli, kısa özet balonu, "Analizi Görüntüle" |
| `frontend/assets/integration.css` | `.ai-*` sınıfları (yalnızca kapsamlı seçiciler) |
| `frontend/index.html` | Renderer kaydı, önbellek anahtarı `?v=13` |
| `tests_integration/test_ui_spec.py` | **yeni** — 27 test |
| `tests_ui/test_frontend.js` | 46 yeni kontrol + örnek dosya yükleme |
| `tests_ui/fixtures/*.json` | **yeni** — backend tarafından üretilen örnekler |

**Dokunulmayanlar:** Ollama provider, araç çağrı döngüsü, intent router,
response composer, kapasite/FTE formülleri, program tahsis modeli.

---

## 11. Kalan sınırlar

* `line_chart` ve `gauge` katalogda kayıtlı ama üretici henüz bu türleri
  seçmiyor; zaman serisi verisi geldiğinde kullanılacak.
* Model şu an tema ve bileşen sırası **seçmiyor**; ikisi de sabit. Şema
  buna hazır: modele "hangi doğrulanmış metrik öne çıksın" sorusu
  sorulabilir, ama yeni sayı üretemez.
* Öğrenci senaryosu dışındaki sonuç türleri (maaş senaryosu, kurumsal özet)
  yalnızca kart üretiyor; grafik ve risk bölümleri boş kalıyor.
* Pencere yazdırma/dışa aktarma yok.
