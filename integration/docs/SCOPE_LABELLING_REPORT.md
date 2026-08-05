# Kapsam Etiketleme — Düzeltme Raporu

Cevap teknik olarak doğruydu ama **okunuşu yanlıştı**. Tek bir blokta program
ve üniversite sayıları etiketsiz yan yana duruyordu:

```
- Öğrenci sayısı: 370 → 426          ← program
- Akademik personel: 180 kişi        ← ÜNİVERSİTE
- Önerilen personel: 203 kişi        ← ÜNİVERSİTE
- Derslik kapasitesi: 1.020 kişi     ← ÜNİVERSİTE
- Derslik talebi: 1.420 kişi         ← ÜNİVERSİTE
```

Okuyan yönetici 426 öğrencilik bir programın 1.420 kişilik derslik talebi
ürettiğini, 180 öğretim üyesinin bu programa ait olduğunu sanıyordu.

---

## 1. Her metrik artık kapsamını taşıyor

`ScopedMetric` modeli eklendi. Değeri olan hiçbir gösterge kapsamsız kalmıyor:

```python
class ScopedMetric(BaseModel):
    key: str
    label: str
    scope_type: str      # university | faculty | department | program
    scope_name: str
    unit: str            # öğrenci | kişi | eş zamanlı kişi | USD | %
    baseline / scenario / change
    formula: Optional[str]
    note: Optional[str]
```

`structured_result` içindeki **her** metrik `scope_type`, `scope_name`, `unit`
ve varsa `formula` taşıyor — testle sabitlendi.

---

## 2. Yeni cevap yapısı

```
**2025-2026 — Bilgisayar Mühendisliği Lisans Programı**

Senaryo: program öğrenci sayısında %15 değişim (+56 öğrenci).

### Program kapsamındaki sonuçlar — Bilgisayar Mühendisliği Lisans Programı
- Öğrenci sayısı: 370 öğrenci → 426 öğrenci (+56 öğrenci)
- Eş zamanlı derslik ihtiyacı: 130 → 149 eş zamanlı kişi (+19)
  - Derslikler bölüm düzeyinde tahsis edilir; programa ayrılmış derslik
    kapasitesi verisi yoktur. Yalnızca TALEP hesaplanabilir.
- Eş zamanlı laboratuvar ihtiyacı: 67 → 77 eş zamanlı kişi (+10)
- Program için önerilen öğretim üyesi: 22 kişi
  - Program bazında akademik personel dağılımı bulunamadı; mevcut program
    kadrosu ile karşılaştırma yapılamıyor.
- Bu programdaki artışın ek gelir etkisi: +329.840 USD

### Bölüm kapsamındaki sonuçlar — Bilgisayar Mühendisliği
- Bölüm akademik personeli: 18 kişi

### Üniversite bütçesine ve kaynaklarına etkisi — Üniversite geneli
- Üniversite toplam yıllık geliri: 35.960.000 USD → 36.289.840 USD (+329.840 USD)
- Üniversite net bütçesi: 2.900.000 USD → 3.157.040 USD (+257.040 USD)
- Üniversite akademik personeli: 180 kişi → 180 kişi
- Üniversite için önerilen kadro: 203 kişi
- Üniversite derslik kapasitesi: 1.020 kişi
- Üniversite eş zamanlı derslik talebi: 1.400 → 1.420 eş zamanlı kişi (+20)
- Üniversite derslik kapasite açığı: 400 eş zamanlı kişi
- Üniversite laboratuvar kapasitesi: 328 kişi
- Üniversite eş zamanlı laboratuvar talebi: 720 → 730 eş zamanlı kişi (+10)
- Üniversite laboratuvar kapasite açığı: 402 eş zamanlı kişi
- Kapasite durumu: yetersiz
```

Program bölümü üniversite bölümünden **önce** gelir ve içinde tek bir kurum
geneli sayı bulunmaz.

---

## 3. Program verisi program verisiyle karşılaştırılıyor

| Gösterge | Önce | Sonra |
|---|---|---|
| Akademik personel | 180 (üniversite) program metriği gibi | Üniversite kapsamında etiketli; ayrıca **bölüm** kadrosu (18 kişi) kendi başlığında |
| Önerilen personel | 203 (üniversite) | Program için 22 kişi (`426 / 20`), üniversite için 203 ayrı satırda |
| Derslik/laboratuvar talebi | 1.420 / 730 (üniversite) | Program talebi ayrıca hesaplanıyor: 149 / 77 (`426 × 0,35` ve `426 × 0,18`) |
| Yıllık gelir | 35.960.000 program geliri gibi | "Üniversite toplam yıllık geliri" + ayrı satırda "Bu programdaki artışın ek gelir etkisi: +329.840 USD" |

**Program kadrosu verisi yok** — uydurulmuyor:
*"Program bazında akademik personel dağılımı bulunamadı; mevcut program
kadrosu ile karşılaştırma yapılamıyor."*

**Program kapasitesi verisi yok** — kurum kapasitesi program kapasitesi gibi
kullanılmıyor. Yalnızca program TALEBİ hesaplanıyor, kapasite tarafı için
notta sebep yazıyor.

---

## 4. Birim ve formül

Eş zamanlı talep artık düz "kişi" değil, **"eş zamanlı kişi"**. Her kapasite
metriğinde formül var:

```
university_classroom_demand
  unit    : eş zamanlı kişi
  formula : üniversite toplam öğrenci sayısı × 0.35
program_classroom_demand
  unit    : eş zamanlı kişi
  formula : program öğrenci sayısı × 0.35 (eş zamanlı derslik kullanım katsayısı)
```

---

## 5. Kapsam uyumluluk kontrolü

`check_scope_consistency()` final cevaptan önce çalışır:

1. Her göstergenin `scope_type`, `scope_name` ve `unit` alanı dolu mu?
2. Kapsam tanınan dört değerden biri mi?
3. Bir **talep** değeri kendi kapsamının öğrenci sayısından büyükse, birim düz
   "kişi/öğrenci" olamaz ve formül yazılmış olmalı.

Uyumsuzlukta `ScopeConsistencyError` fırlar; cevap başarı sayılmaz.

---

## 6. Bu turda bulunan ek hata

Kapasite satırında parantez içi değişim, **kapasite açığını** gösteriyordu:

```
- Üniversite eş zamanlı derslik talebi: 1.400 → 1.420 (+400)   ← YANLIŞ
```

Talep 20 arttı, 400 değil; 400 kapasite açığıdır. `change` ile `gap` ayrıldı,
açık kendi satırına taşındı ve testle sabitlendi.

---

## 7. Değiştirilen dosyalar

| Dosya | Değişiklik |
|---|---|
| `app/services/assistant/tool_schemas.py` | `ScopedMetric` modeli; dört senaryo/özet çıktısına `scoped_metrics` |
| `app/services/assistant/tools.py` | Kapsam etiketli gösterge listesi; program talebi, program önerilen kadro, bölüm kadrosu; `change` ile `gap` ayrıldı |
| `app/services/assistant/response_composer.py` | `check_scope_consistency()`, kapsam gruplu yazım, `_render_scoped()`, `_metric_from_scoped()` |
| `tests_integration/test_assistant_tools.py` | 7 yeni test; kapsam gruplu yapıya göre 9 test güncellendi |

---

## 8. Test sonuçları

```
Backend birim testleri          449 passed, 17 skipped
Backend entegrasyon testleri    134 passed
Arayüz (jsdom, model hazır)     108 passed
Arayüz (jsdom, Ollama kapalı)   103 passed
Canlı test dosyası               17 passed
--------------------------------------------------
0 hata
```

İstenen 6 test:

| Test | Doğrular |
|---|---|
| `test_university_staff_is_not_labelled_as_program_staff` | 180 program metriği olarak görünmez; program bölümünde "180" geçmez |
| `test_every_metric_is_labelled_with_scope_and_unit` | Her metrikte `scope_type`, `scope_name`, `unit` |
| `test_demand_above_student_count_must_declare_unit_and_formula` | 426 öğrenciye 1.420 "kişi" talebi → hata |
| `test_simultaneous_demand_unit_is_explicit` | Birim "eş zamanlı kişi", formül yazılı, program talebi 149 |
| `test_program_revenue_effect_is_separated_from_university_total` | Program etkisi ile kurum toplamı ayrı |
| `test_answer_is_grouped_by_scope` | Başlıklar ayrı ve program önce |

Ek: `test_capacity_gap_is_not_reported_as_a_change`.

`test_live_multi_tool_enrollment_question` **değiştirilmedi**; 370 ve 426
kontrolü yerinde ve geçiyor.

---

## 9. Durum

**"Tool calling tamamlandı" demiyorum** — gerçek Ollama çıktısını görene kadar.

```powershell
$env:ASSISTANT_LIVE_TEST="1"
& ".\.venv\Scripts\python.exe" -m pytest `
  ".\integration\backend\tests\test_assistant_ollama_live.py" -v -s
```

Hedef: **17 passed**

### Bilinen eksikler

- **Program düzeyinde kadro ve mekân tahsisi verisi yok.** Araçlar bunu
  uydurmuyor, notta söylüyor. Gerçek program kadrosu için veri modeline
  program–öğretim üyesi ilişkisi eklenmeli.
- Senaryo motoru kurum geneli çalışır; program değişimi oranlanarak uygulanır
  (`method_note` her cevapta belirtir).
- Yetki kontrolü hazır ama `/chat` uç noktasına bağlı değil.
- Akış modunda araç çağrısı ve composer yok.
- Arayüz `structured_result` alanını henüz kullanmıyor (dinamik grafik bir
  sonraki aşama).
