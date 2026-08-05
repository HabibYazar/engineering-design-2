# Senaryo Intent Router ve Dönem Politikası — Düzeltme Raporu

Canlı testlerde 16'dan 14'ü geçmişti. Kalan iki başarısızlığın ortak kökü
aynıydı: **iki karar modele bırakılmıştı.**

| Başarısızlık | Model ne yaptı | Ne yapması gerekiyordu |
|---|---|---|
| Maaş senaryosu | `get_financial_summary` çağırdı — mevcut bütçeyi döndürür, zammın etkisini hesaplamaz | `run_staff_salary_scenario` |
| Öğrenci senaryosu | Akademik yıl olarak 2026-2027'yi seçti — planlama dönemi, tutarları sıfır | 2025-2026 (aktif dönem) |

Araç seçimi bir muhakeme işi değil, bir **yönlendirme** işidir. Dönem seçimi
de bir tercih değil, bir **politikadır**. İkisi de artık backend'de,
deterministik olarak yapılıyor.

---

## 1. Senaryo intent router

`app/services/assistant/query_policy.py` — kural tabanlı, LLM'siz.

### Sınıflandırma

```
SCENARIO_TRIGGERS  →  artarsa · azalırsa · yapılırsa · değişirse · ne olur ·
                      nasıl etkilenir · senaryo · simülasyon · varsayalım

+ SALARY_SUBJECT    (maaş · ücret · zam · bordro · personel gideri)
      →  intent = staff_salary_scenario
         required_tool = run_staff_salary_scenario

+ ENROLLMENT_SUBJECT (öğrenci · kayıt sayısı · kontenjan)
      →  intent = enrollment_change_scenario
         required_tool = run_enrollment_change_scenario

Senaryo tetikleyicisi YOK, kurumsal soru VAR
      →  intent = current_state_query
```

Sıralama önemli: "Maaşlara %2 zam yapılırsa **bütçe** nasıl etkilenir?" hem
*bütçe* (mevcut durum) hem *zam yapılırsa* (senaryo) içerir. Senaryo baskındır.

Doğrulanan sınıflandırma:

```
staff_salary_scenario       ← Akademik personel maaşlarına %2 zam yapılırsa…
staff_salary_scenario       ← Personel ücretleri %5 artarsa ne olur?
staff_salary_scenario       ← Maaş giderleri azaltılırsa…
enrollment_change_scenario  ← Bilgisayar Mühendisliği öğrenci sayısı %15 artarsa…
enrollment_change_scenario  ← Kayıt sayısı yüzde 10 azalırsa…
current_state_query         ← Toplam gelir ne kadar?
general_chat                ← Merhaba
```

### Parametre çıkarımı

Yüzde değeri metinden çıkarılır, modelden değil:

| Yazım | Sonuç |
|---|---|
| `%2` | 2.0 |
| `yüzde 5` | 5.0 |
| `15 oranında` | 15.0 |
| `yüzde iki` | 2.0 |
| `%10 azalırsa` | **-10.0** (yön tespiti) |

Program adı `entity_resolver.find_in_text()` ile cümleden çözülür. Derece
sözcükleri (*lisans, yüksek*) serbest metin aramasında yok sayılır — kullanıcı
"Bilgisayar Mühendisliği öğrenci sayısı artarsa" derken "Lisans Programı"
yazmaz. Belirsiz (*Yazılım Mühendisliği* — hem lisans hem yüksek lisans var)
veya bulunamayan (*Uzay Mühendisliği*) adlarda **tahmin edilmez**.

---

## 2. Zorunlu araç seçimi

Kullanıcının önerdiği tercih edilen davranış uygulandı: **backend intenti
kesin olarak belirlediğinde zorunlu aracı doğrudan çalıştırır.** Model
yalnızca sonucu yorumlar.

```
Kullanıcı: "Akademik personel maaşlarına %2 zam yapılırsa bütçe nasıl etkilenir?"
   │
   ├─ intent               = staff_salary_scenario
   ├─ required_tool        = run_staff_salary_scenario
   ├─ salary_change_%      = 2          (metinden)
   ├─ academic_year        = 2025-2026  (politikadan)
   │
   ├─ ARAÇ BACKEND TARAFINDAN ÇALIŞTIRILIR
   ├─ sonuç `tool` mesajı olarak konuşmaya eklenir
   ├─ modele araç listesi GÖNDERİLMEZ  ("yeni araç çağırma, yorumla")
   │
   └─ Model: sonucu Türkçe cümleye döker
```

Parametreler metinden çıkarılamazsa (ör. program adı belirsiz) modele
**yalnızca gerekli araç** sunulur; başka araç seçemez.

### Final kontrol

Cevap kullanıcıya gitmeden önce:

- Gerekli araç çağrıldı mı?
- Araç başarılı mı?
- Çıktı şeması doğrulandı mı?

Biri başarısızsa modelin serbest metni **gösterilmez**; kontrollü hata döner.

Doğrulama — sahte model kasten `get_financial_summary` seçtiği hâlde:

```
SORU: Akademik personel maaşlarına %2 zam yapılırsa bütçe nasıl etkilenir?
  arac  : [{'name': 'run_staff_salary_scenario', 'success': True}]
  yil   : 2025-2026
  dayanak: institutional_data

SORU: Bilgisayar Mühendisliği öğrenci sayısı %15 artarsa…
  arac  : [{'name': 'run_enrollment_change_scenario', 'success': True}]
  yil   : 2025-2026
  kapsam: {'program': 'Bilgisayar Mühendisliği Lisans Programı', …}
```

---

## 3. Akademik yıl politikası

`FinancialPeriod` modeline `period_type` alanı eklendi. Demo veri zaten
2026-2027'yi planlama yılı diye tanımlıyordu (`_not: "2026-2027 planlama
yilidir… tutarlar sifirdir"`), ama bu bilgi **veritabanında yoktu**; yıl
seçimi yalnızca "en büyük yıl" mantığıyla yapılıyordu.

| Yıl | period_type | Öğrenci |
|---|---|---|
| 2021-2022 … 2024-2025 | `actual` | 3.200 → 3.840 |
| **2025-2026** | **`current`** | 4.000 |
| 2026-2027 | `planning` | 0 |

### Seçim sırası — model karışmaz

```
1. current dönem varsa            → onu seç
2. yoksa en güncel actual dönem   → onu seç
3. planning / forecast            → ASLA varsayılan olarak seçilmez
```

Kullanıcı açıkça isterse planlama dönemine izin verilir:

| Soru | Seçilen dönem |
|---|---|
| "Maaşlara %2 zam yapılırsa…" | 2025-2026 |
| "**2026-2027 döneminde** maaşlara %2 zam yapılırsa…" | 2026-2027 |
| "**Gelecek yıl** öğrenci sayısı %15 artarsa…" | planlama dönemine izin verilir |

"Gelecek yıl", "önümüzdeki dönem", "planlama", "projeksiyon" ifadeleri
planlama niyeti sayılır. Karar `entity_resolver.default_academic_year()`
içinde, modele hiç sorulmadan verilir.

---

## 4. Bu turda bulunan üçüncü hata

Düşmanca bir sahte model (her soruya `get_financial_summary` çağıran) gerçek
bir açık ortaya çıkardı: **başarılı ama alakasız bir araç kapıyı geçiyordu.**

"Uzay Mühendisliği programında kaç öğrenci var?" sorusuna model mali özet
aracını çağırdı, araç başarıyla çalıştı, sistem "araç sonucu var" diye cevabı
kabul etti ve kullanıcıya *"2025-2026: gelir 50.400.000 USD"* döndü.

İki hedefli düzeltme:

1. **`entity_resolver.unresolved_unit_in_text()`** — kullanıcı bir birim adı
   yazmış ama sistemde yoksa **model hiç çağrılmaz**; kontrollü cevap döner:
   *"'Uzay Mühendisliği' adında bir program, bölüm veya fakülte sistemde
   bulunamadı."*
2. Bir **programın** öğrenci göstergesi soruluyorsa `get_program_summary`
   zorunlu olur — ama yalnızca cümlede gerçekten çözümlenebilir bir program
   adı geçiyorsa. ("Mekânların doluluk oranı" bir program sorusu değildir;
   ilk denemede yanlışlıkla zorunlu kılınmıştı ve testle yakalandı.)

---

## 5. Değiştirilen dosyalar

| Dosya | Değişiklik |
|---|---|
| `app/services/assistant/query_policy.py` | `QueryIntent`, `classify()`, `extract_percentage()`, `extract_academic_year()`, senaryo/konu kalıpları |
| `app/services/assistant/entity_resolver.py` | `period_type` farkındalığı: `default_academic_year()`, `academic_year_types()`, `mentions_planning_period()`, `find_in_text()`, `unresolved_unit_in_text()`, `_core_tokens()` |
| `app/services/assistant/chat_service.py` | Zorunlu araç akışı, `_build_forced_arguments()`, bulunamayan birim kısa devresi, final zorunlu-araç kontrolü, sistem yönergesi 7a |
| `app/models/financial_period.py` | `period_type` sütunu |
| `shared_demo_data/05_finance.json` | Her döneme `period_type` |
| `seed_all_demo_data.py` | `period_type` seed'i |
| `tests_integration/test_assistant_tools.py` | 12 yeni test; intent router sonrası geçersizleşen 4 test güncellendi |
| `tests/test_assistant_ollama_live.py` | Retry testi zorunlu aracı olmayan soruya çevrildi; `test_live_forced_tool_makes_retry_unnecessary` eklendi |

---

## 6. Test sonuçları

```
Backend birim testleri          449 passed, 17 skipped
Backend entegrasyon testleri    116 passed
Arayüz (jsdom, model hazır)     108 passed
Arayüz (jsdom, Ollama kapalı)   103 passed
Canlı test dosyası               17 passed  (sözleşme taklidi ile)
--------------------------------------------------
0 hata
```

İstenen 10 test:

| # | Test |
|---|---|
| 1 | `test_salary_raise_is_classified_as_salary_scenario` |
| 2 | `test_enrollment_change_is_classified_as_enrollment_scenario` |
| 3 | `test_current_state_questions_are_classified_correctly` |
| 4 | `test_default_year_is_current_not_planning` |
| 5 | `test_planning_period_is_never_the_default` |
| 6 | `test_explicit_planning_year_is_allowed` |
| 7 | `test_next_year_phrase_allows_planning_period` |
| 8 | `test_wrong_tool_is_not_accepted_for_a_salary_scenario` |
| 9 | `test_enrollment_scenario_tool_is_mandatory` |
| 10 | `test_final_answer_is_blocked_when_required_tool_fails` |

Ek: `test_percentage_extraction` (5 varyant),
`test_forced_tool_arguments_come_from_the_message`,
`test_unknown_unit_short_circuits_before_the_model`.

**Test beklentileri gevşetilmedi.** `test_live_salary_scenario_numbers_match_the_engine`
ve `test_live_multi_tool_enrollment_question` olduğu gibi duruyor; artık
`run_staff_salary_scenario` ve 2025-2026 kesin olarak sağlanıyor.

Canlı test dosyası bu ortamda, **kasten yanlış araç seçen** bir sahte modelle
çalıştırıldı ve 17/17 geçti. Bu, modelin araç seçimi bozuk olsa bile sonucun
doğru olduğunu gösterir.

---

## 7. Canlı testi çalıştırma

```powershell
ollama serve
ollama pull qwen3.5:9b

$env:ASSISTANT_LIVE_TEST="1"
& ".\.venv\Scripts\python.exe" -m pytest `
  ".\integration\backend\tests\test_assistant_ollama_live.py" `
  -v -s
```

Hedef: **17 passed** (bir test eklendiği için 16 değil 17).

---

## 8. Durum

**"Tool calling tamamlandı" demiyorum.** Bunu ancak gerçek Ollama ile
çalıştırdığınızda ve sonuç tam geçtiğinde söyleyebilirim.

Bu turda düzeltilen iki hatanın kökü, modelin araç ve dönem seçmesine izin
verilmesiydi. Artık ikisi de backend'de deterministik; modelin bu iki konuda
yanılma ihtimali ortadan kalktı. Kalan risk, modelin **yorumlama** aşamasında
sayıları yanlış aktarmasıdır — canlı testler her sayıyı servis sonucuyla
karşılaştırarak bunu denetliyor.

### Bilinen eksikler (değişmedi)

- Yetki kontrolü hazır ama `/chat` uç noktasına bağlı değil.
- Akış modunda (`/chat/stream`) araç çağrısı yok.
- Senaryo motoru kurum geneli çalışır; program değişimi oranlanarak uygulanır.
- Mali ve kapasite verisi program düzeyinde tutulmuyor.
