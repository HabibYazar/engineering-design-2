# Mevcut Açık, Kapasite Oranları ve Yorum Ayrımı — Düzeltme Raporu

Kapsamlar teknik olarak ayrılmıştı ama yorum katmanında ve bazı oranlarda
mantık hataları kalmıştı. Beş sorun düzeltildi.

---

## 1. Personel açığı üçe ayrıldı

**Sorun:** Kurumun 23 kişilik kadro açığı, sanki tamamı Bilgisayar
Mühendisliği'ndeki %15 artıştan doğmuş gibi anlatılıyordu. Açığın 20'si
senaryodan önce de vardı.

### Program kapsamı

| Gösterge | Değer |
|---|---|
| Program mevcut akademik kapasitesi | 18 FTE |
| Mevcut gerekli kapasite | 18,50 FTE |
| Senaryo gerekli kapasitesi | 21,30 FTE |
| **Mevcut program açığı** | **0,50 FTE** — *"Bu açık senaryodan bağımsızdır; şu anda da vardır."* |
| **Senaryo sonrası program açığı** | **3,30 FTE** |
| **Senaryodan kaynaklanan marjinal ihtiyaç** | **+2,80 FTE** |

### Üniversite kapsamı — beş yeni alan

```json
{
  "baseline_recommended_university_staff": 200,
  "scenario_recommended_university_staff": 203,
  "marginal_university_staff_requirement": 3,
  "baseline_university_staff_gap": 20,
  "scenario_university_staff_gap": 23
}
```

Cevapta:

```
- Üniversite için önerilen kadro: 200 kişi → 203 kişi (+3 kişi)
- Üniversite kadro açığı: 20 kişi → 23 kişi (+3 kişi)
  - Kurumun 20 kişilik kadro açığı senaryodan ÖNCE de vardı.
    Bu senaryonun eklediği ihtiyaç 3 kişidir.
```

---

## 2. Kapasite yüzdeleri düzeltildi

**Kök neden:** Yalnızca *kullanım oranı* (talep / kapasite) hesaplanıyordu.
Kullanım oranı %100'ü aşabilir; *karşılanma oranı* aşamaz. İkisi
karıştırıldığında "talebin %139'u karşılanıyor" gibi anlamsız veya
"%68'i karşılanamıyor" gibi yanlış ifadeler çıkıyordu.

İki yeni fonksiyon, `program_allocation_service` içinde:

```python
coverage_percent(demand, capacity)  = min(kapasite, talep) / talep × 100
shortfall_percent(demand, capacity) = 100 − karşılanma oranı
```

Doğrulanan değerler — sizin verdiğiniz sayılarla birebir:

| | Kapasite | Talep | Kullanım | Karşılanan | Karşılanamayan | Açık |
|---|---|---|---|---|---|---|
| Derslik | 1.020 | 1.420 | %139,22 | **%71,83** | **%28,17** | 400 |
| Laboratuvar | 328 | 730 | %222,56 | **%44,93** | **%55,07** | 402 |

Araç çıktısına eklenen alanlar: `capacity_coverage_percent`,
`capacity_shortfall_percent` — hem program hem üniversite kapsamında,
mevcut ve senaryo değerleriyle. **Backend hesaplar; LLM yeniden
hesaplamaz.**

---

## 3. Bütçe etkisi yatırım öncesi olarak etiketlendi

Yeni alanlar:

```json
{
  "operating_budget_effect_before_investment": "257040.00",
  "additional_staff_cost_included": false,
  "facility_investment_cost_included": false
}
```

Cevapta net bütçe satırının altında:

> *"Bu sonuç, gerekli EK PERSONEL ALIMI ve FİZİKSEL KAPASİTE YATIRIMLARI
> uygulanmadan öncesine aittir. Bu maliyetler hesaplandıktan sonra net
> finansal sürdürülebilirlik yeniden değerlendirilmelidir."*

Sistem yönergesi modele **kesin hüküm vermeyi yasaklıyor**: "Gelir artışı bu
maliyetleri karşılamaya yetmez" denemez. Testler bu ifadenin cevapta
bulunmadığını doğruluyor.

---

## 4. Yönetim yorumu kapsama göre bölündü

Modelden artık iki başlık isteniyor:

```
### Program değerlendirmesi
Yalnızca program kapsamı: öğrenci değişimi, program FTE kapasitesi ve
ihtiyacı, derslik koltuk-saat kullanımı, laboratuvar istasyon-saat
kullanımı, programın oluşturduğu ek gelir.

### Üniversite düzeyindeki etki
Yalnızca kurum kapsamı: toplam gelir değişimi, net bütçe değişimi, kurum
geneli kapasite açığındaki değişim, kurum geneli kadro etkisi.
```

Model başlıkları hiç yazmazsa `_clean_interpretation()` yorumu bir başlık
altına alır — başlıksız serbest metin, kapsamı belirsiz bir yorum demektir.

---

## 5. Riskler ikiye ayrıldı

Program mevcut durumda da kapasite sınırının üzerinde. Senaryo bu sorunu
**oluşturmuyor, büyütüyor**.

```
### Mevcut durumdaki riskler (senaryodan bağımsız)
- Bilgisayar Mühendisliği Lisans Programı: program derslik kullanım oranı
  mevcut durumda %222,92 — tahsis edilmiş kapasite zaten aşılmış durumda.
  Senaryo bu oranı %256,66'e yükseltiyor.
- … laboratuvar kullanım oranı mevcut durumda %131,86 …
  Senaryo bu oranı %151,82'e yükseltiyor.

### Senaryonun eklediği etki (üniversite geneli)
- Derslik kapasitesi yetersiz: … 400 kişilik açık oluşuyor.
- Laboratuvar kapasitesi yetersiz: … 402 kişilik açık oluşuyor.
```

`structured_result` içinde de `baseline_risks` ve `scenario_risks` ayrı
listeler.

Ayrıca kullanım oranı satırlarına not eklendi:
*"Program MEVCUT durumda da tahsisli derslik kapasitesini aşıyor; senaryo bu
sorunu oluşturmuyor, büyütüyor."*

---

## 6. Bu turda bulunan ek hata

Üniversite kapasite açığı satırı yalnızca senaryo değerini gösteriyordu:

```
- Üniversite derslik kapasite açığı: 400 eş zamanlı kişi     ← eksik
```

Mevcut açık görünmüyordu. Düzeltildi:

```
- Üniversite derslik kapasite açığı: 380 → 400 eş zamanlı kişi
```

Açığın 380'i zaten vardı; senaryo 20 ekledi.

---

## 7. Değiştirilen dosyalar

| Dosya | Değişiklik |
|---|---|
| `app/services/program_allocation_service.py` | `coverage_percent()`, `shortfall_percent()`; kapasite raporuna karşılanma oranları |
| `app/services/assistant/tool_schemas.py` | 5 kadro açığı alanı + 3 bütçe kapsamı alanı |
| `app/services/assistant/tools.py` | Baseline/senaryo/marjinal ayrımı, karşılanma oranları, bütçe ve kullanım notları, mevcut kapasite açığı |
| `app/services/assistant/response_composer.py` | İki bölümlü yorum yönergesi, `_baseline_capacity_risks()`, risk ayrımı |
| `app/services/assistant/chat_service.py` | Başlık kontrolü iki başlığa göre |
| `tests_integration/test_assistant_tools.py` | 8 yeni test |

**Dokunulmayanlar:** Ollama provider, araç çağrı döngüsü, intent router,
kapsam etiketleme yapısı, program tahsis modeli.

---

## 8. Test sonuçları

```
Backend birim testleri          449 passed, 17 skipped
Backend entegrasyon testleri    151 passed
Arayüz (jsdom, model hazır)     108 passed
Arayüz (jsdom, Ollama kapalı)   103 passed
Canlı test dosyası               17 passed
--------------------------------------------------
0 hata
```

İstenen 8 test:

| Test | Doğrular |
|---|---|
| `test_classroom_shortfall_percent_is_correct` | 1.020 / 1.420 → %28,17 |
| `test_laboratory_shortfall_percent_is_correct` | 328 / 730 → %55,07; karşılanma oranı %100'ü aşamaz |
| `test_total_university_gap_is_not_attributed_to_the_scenario` | 20 mevcut, 23 senaryo, 3 marjinal |
| `test_program_marginal_requirement_stays_at_two_point_eight` | 0,50 / 3,30 / +2,80 FTE |
| `test_interpretation_is_split_into_program_and_university` | İki başlık zorunlu |
| `test_budget_effect_is_labelled_as_before_investment` | Yatırım öncesi etiketi; "karşılamaya yetmez" ifadesi yok |
| `test_baseline_and_scenario_risks_are_separated` | İki ayrı risk bölümü + structured listeler |
| `test_deterministic_block_survives_a_wrong_percentage_from_the_model` | Model "%68" yazsa bile blokta %28,17 ve %55,07 |

Son test canlı senaryoyu taklit ediyor: sahte model kasten *"Talebin %68'i
karşılanamıyor"* yazıyor; deterministik blok ve `structured_result`
değişmiyor.

---

## 9. Canlı test

```powershell
$env:ASSISTANT_LIVE_TEST="1"
& ".\.venv\Scripts\python.exe" -m pytest `
  ".\integration\backend\tests\test_assistant_ollama_live.py" -v -s
```

Hedef: **17 passed**

---

## 10. Kalan sınırlar

- **Ek personel ve yatırım maliyeti hesaplanmıyor.** Alanlar (`..._included`)
  false döner ve cevapta bu açıkça yazar. Hesaplamak için birim personel
  maliyeti ve mekân yatırım birim fiyatı verisi gerekir.
- **Mali veri program düzeyinde değil.** Program etkisi marjinal fark olarak
  veriliyor ve öyle etiketleniyor.
- Senaryo motoru kurum geneli çalışır; program değişimi oranlanarak uygulanır.
- Ders programı (timetable) yok; kapasite haftalık toplam üzerinden.
- Yetki kontrolü hazır ama `/chat` uç noktasına bağlı değil.
