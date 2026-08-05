# Akıllı Asistan — Araç Çağırma (Tool Calling) Raporu

Model artık kurum verisine erişiyor. Kullanıcı doğal dilde soru sorduğunda
qwen3.5:9b gerekli araçları seçiyor, araçlar gerçek veritabanı ve mevcut
servislerden veri alıyor, model yalnızca gelen sonuçları yorumluyor.

**Modelin yapamadıkları:** SQL yazmak, endpoint URL'si üretmek, kendi kafasından
hesap yapmak, kayıt defterinde olmayan bir fonksiyon çağırmak.

---

## 1. Oluşturulan araçlar

| Araç | Ne yapar | Kullanıcıya gösterilen kaynak adı |
|---|---|---|
| `get_program_summary` | Program öğrenci sayısı, kontenjan, doluluk, mezuniyet ve bırakma oranı, öğrenci/öğretim üyesi oranı | Öğrenci kayıtları |
| `get_financial_summary` | Gelir, gider, net bütçe, personel gideri, burs gideri, öğrenci başına maliyet (USD) | Mali dönem kayıtları |
| `get_capacity_summary` | Derslik/laboratuvar kapasitesi, kullanım, doluluk, eş zamanlı kapasite açığı | Fiziksel kapasite kayıtları |
| `get_academic_staff_summary` | Personel sayısı, ortalama maaş, yıllık maaş maliyeti, önerilen kadro, kadro açığı | Akademik personel kayıtları |
| `run_enrollment_change_scenario` | Program öğrenci değişiminin mali, personel ve kapasite etkisi | Senaryo motoru |
| `run_staff_salary_scenario` | Maaş değişiminin personel gideri, toplam gider, bütçe dengesi ve öğrenci başına maliyet etkisi | Senaryo motoru |

Her araç kaydında: ad, açıklama, Pydantic girdi modeli, çıktı modeli, handler,
süre sınırı, gerekli yetki ve Türkçe veri kaynağı adı bulunur.

---

## 2. Araçların bağlandığı mevcut servisler

Hiçbir formül yeniden yazılmadı. Araçlar yalnızca sarmalayıcıdır.

| Araç | Çağırdığı servis |
|---|---|
| `get_program_summary` | `student_analytics_service.build_program_analytics()`, `academic_staff_service.list_staff()` |
| `get_financial_summary` | `finance_service.financial_summary()`, `finance_service.list_department_budgets()` |
| `get_capacity_summary` | `PhysicalFacility` sorgusu + `scenario_engine.SIMULTANEOUS_CLASSROOM_USE` |
| `get_academic_staff_summary` | `academic_staff_service.list_staff()`, `FinancialPeriod`, `student_analytics_service.build_overview()` |
| `run_enrollment_change_scenario` | `scenario_baseline_builder.build_from_financial_period()` → `scenario_engine.calculate()` → `scenario_risk.evaluate()` → `scenario_recommendations.build_recommendation()` |
| `run_staff_salary_scenario` | Aynı zincir, `academic_salary_change_percent` parametresiyle |

---

## 3. Entity resolver yapısı

`app/services/assistant/entity_resolver.py` — kullanıcının yazdığı birim adını
gerçek kayda bağlar. Model bir kimlik uyduramaz.

**Kabul edilen yazımlar:** Türkçe ad, veritabanındaki İngilizce ad, kod,
şapkasız yazım, büyük/küçük harf farkı.

```
"Bilgisayar Mühendisliği"  → CENG-BSC ✓
"Computer Engineering"     → CENG-BSC ✓
"CENG" / "CENG-BSC"        → CENG-BSC ✓
"bilgisayar muhendisligi"  → CENG-BSC ✓
```

**Üç sonuç, tahmin yok:**

| Durum | Davranış |
|---|---|
| Tek eşleşme | Kimlik döndürülür |
| Birden fazla eşleşme | `ambiguous` + seçenek listesi; model kullanıcıya sorar, kendi seçmez |
| Eşleşme yok | `not_found` + mevcut birimlerin listesi |

İki tasarım kararı geliştirme sırasında test edilerek düzeltildi:

- **Zayıf benzerlik kademesi kaldırıldı.** İlk sürümde "ortak sözcüğü olan"
  eşleşmeler kabul ediliyordu; sistemde bulunmayan "Uzay Mühendisliği" yalnızca
  *mühendisliği* sözcüğü ortak olduğu için var olan programlarla eşleşip
  "belirsiz" sayılıyordu. Doğru cevap "böyle bir program yok"tur.
- **"lisans" ve "yüksek" durak sözcüğü değildir.** Atıldıklarında "Yazılım
  Mühendisliği Lisans Programı" ile "…Yüksek Lisans Programı" aynı kümeye
  iniyor, tam adını yazan kullanıcı bile belirsizlik hatası alıyordu.

Ayrıca `resolve_academic_year()` uydurma yılı reddeder, `resolve_scope()`
program verildiğinde bölüm ve fakülteyi ondan **türetir** — çelişkili kapsam
kombinasyonu oluşamaz.

---

## 4. Tool calling döngüsü

```
Kullanıcı mesajı
   │
   ▼
chat_service.answer(message, db)
   │  system prompt + geçmiş + araç şemaları
   ▼
OllamaProvider.chat_with_tools()  ──►  qwen3.5:9b
   │                                      │
   │  ◄── tool_calls ─────────────────────┘
   ▼
ToolSession.run(name, arguments)          ← her çağrı için 6 kapı
   │  1 ad kayıtlı mı · 2 yetki · 3 şema · 4 tekrar · 5 süre · 6 çıktı şeması
   ▼
Mevcut servis / senaryo motoru → gerçek veritabanı
   │
   ▼
Sonuç `tool` rolüyle konuşmaya eklenir → model bir sonraki turu üretir
```

- **En fazla 5 araç turu** (`MAX_TOOL_STEPS`).
- **Toplam 90 saniye** duvar saati sınırı (`MAX_TOOL_WALL_SECONDS`).
- Sınıra gelindiğinde son tur **araç listesi gönderilmeden** yapılır; model
  yeni araç çağıramaz, eldeki sonuçlarla cevabı yazar.
- Aynı araç aynı parametrelerle ikinci kez çağrılırsa **çalıştırılmaz**;
  önceki sonuç döndürülür. Parametre sırası farkı sahte tekrar üretmez
  (anahtar sıralı JSON'dur).

Akış (`/chat/stream`) modunda araç çağrısı yapılmaz — tur araları kullanıcıya
yarım cümle gösterirdi. Araçlı sorular tek seferlik `/chat` ile cevaplanır.

---

## 5. Değiştirilen endpointler

### `POST /api/assistant/chat` — genişletildi

```json
{
  "conversation_id": "…",
  "answer": "2025-2026 · Bilgisayar Mühendisliği: 370 öğrenci.",
  "provider": "ollama",
  "model": "qwen3.5:9b",
  "used_tools": [{ "name": "get_program_summary", "success": true }],
  "data_sources": ["Öğrenci kayıtları"],
  "academic_year": "2025-2026",
  "scope": {
    "faculty": "Mühendislik ve Mimarlık Fakültesi",
    "department": "Bilgisayar Mühendisliği",
    "program": "Bilgisayar Mühendisliği Lisans Programı"
  },
  "calculated_at": "2026-08-05T…",
  "data_source": "institutional_data"
}
```

`scope` ve `academic_year` **modelin cümlesinden değil araç çıktısından**
okunur; model yanlış bir bölüm adı yazsa bile metadata doğru kalır.

`data_source` iki değer alır: `institutional_data` (en az bir araç başarılı)
veya `general_model_knowledge` (araç kullanılmadı).

### `GET /api/assistant/status` — `tool_count` eklendi

### Değişmeyenler
`/chat/stream`, `/sample-questions`, `/prepare-context`, `/architecture`.

---

## 6. Frontend veri kaynağı görünümü

Her asistan cevabının altında:

```
2025-2026 akademik yılı · Bilgisayar Mühendisliği Lisans Programı
▸ Kullanılan veriler                                    1 kaynak
```

Açıldığında:

```
• Öğrenci kayıtları
• Mali dönem kayıtları
• Akademik personel kayıtları
• Fiziksel kapasite kayıtları
• Senaryo motoru
```

**Teknik araç adları gösterilmez.** `used_tools` alanı cevapta gelir ama
arayüz onu hiç okumaz; bir test bunu doğrular (`views-assistant.js` içinde
hiçbir araç adı geçmemeli).

Araç kullanılmamışsa balonun altında italik bir not çıkar: *"Bu cevap kurum
verisine değil, modelin genel bilgisine dayanıyor."*

Bu turda dinamik pencere, grafik veya CSS üretimi **eklenmedi**.

---

## 7. Güvenlik kontrolleri

| Risk | Önlem | Test |
|---|---|---|
| Model SQL yazar | Girdi şemalarında `sql`, `query`, `where`, `raw`, `url`, `endpoint` gibi alan **yok**; serbest metin yalnızca birim adıdır ve resolver'dan geçer | `test_tools_expose_no_free_form_sql_field` |
| Model endpoint üretir | Araçlar servis fonksiyonlarını doğrudan çağırır; HTTP katmanı devrede değil | — |
| Model kendi hesabını yapar | Bütün sayılar servis/motor çıktısıdır; sistem yönergesi "Kendi kafandan hesap YAPMA" der | `test_system_prompt_forbids_inventing_numbers` |
| Bilinmeyen fonksiyon çağrısı | Kayıt defterinde olmayan ad çalıştırılmaz | `test_unknown_tool_name_is_never_executed` |
| Bozuk parametre | Pydantic doğrulaması; `extra="forbid"` ile bilinmeyen alan sessizce yok sayılmaz | `test_invalid_tool_arguments_are_rejected`, `test_tool_inputs_forbid_unknown_fields` |
| Şema dışı çıktı | Çıktı doğrulamadan geçmezse **modele gönderilmez** | `tool_runner._execute` 6. adım |
| Sonsuz döngü | 5 tur + 90 saniye + tekrar filtresi | `test_tool_step_limit_is_enforced` |
| Askıda kalan araç | Araç başına süre sınırı (15–30 sn), ayrı iş parçacığında | `test_tool_timeout_is_reported_without_numbers` |
| Yetkisiz veri | `required_permission`; yetkisi olmayan araç modele **tanıtılmaz bile** | `ToolRegistry.schemas(permissions)` |
| Zaman aşımı mesajında sayı | Hata metninde rakam yok — model onu veri sanmasın | `test_tool_timeout_is_reported_without_numbers` |

Kullanıcı promptu araç adını veya handler'ı seçemez: model yalnızca kayıt
defterindeki adları önerebilir, ad doğrulaması sunucu tarafındadır.
`ToolDefinition` dondurulmuş (frozen) bir dataclass'tır; çalışma zamanında
handler değiştirilemez.

---

## 8. Test sonuçları

```
Backend birim testleri          449 passed, 8 skipped
Backend entegrasyon testleri     96 passed
  └─ test_assistant_tools.py     37 passed  (araç çağırma)
Arayüz (jsdom) testleri         108 passed / 0 hatalı
--------------------------------------------------
TOPLAM                          653 kontrol, 0 hata
```

İstenen 20 senaryonun karşılığı:

| # | Senaryo | Test |
|---|---|---|
| 1 | Program adı çözümleme | `test_resolves_turkish_program_name` |
| 2 | Türkçe / İngilizce / kod eşleşmesi | `test_turkish_english_and_code_all_match` (6 varyant) |
| 3 | Belirsiz program adı | `test_ambiguous_program_name_asks_the_user` |
| 4 | Bilinmeyen program | `test_unknown_program_is_not_guessed`, `test_unknown_academic_year_is_rejected` |
| 5 | Program özet aracı | `test_program_summary_matches_the_analytics_service` |
| 6 | Mali özet aracı | `test_financial_summary_matches_the_finance_service` |
| 7 | Kapasite aracı | `test_capacity_summary_uses_all_enrolled_students` |
| 8 | Personel aracı | `test_staff_summary_cost_matches_the_scenario_engine` |
| 9 | %15 öğrenci artışı | `test_enrollment_scenario_scales_program_change_to_the_university`, `…_numbers_come_from_the_engine` |
| 10 | %2 maaş artışı | `test_salary_scenario_two_percent_raise`, `…_does_not_change_headcount` |
| 11 | Araçsız sayı üretimi | `test_model_cannot_produce_numbers_without_tools` |
| 12 | Bilinmeyen tool adı | `test_unknown_tool_name_is_never_executed`, `test_unknown_tool_is_rejected_by_the_registry` |
| 13 | Geçersiz parametre | `test_invalid_tool_arguments_are_rejected` |
| 14 | Tekrarlanan çağrı | `test_duplicate_tool_call_is_not_executed_twice`, `test_argument_order_does_not_create_a_false_duplicate` |
| 15 | Maksimum adım sınırı | `test_tool_step_limit_is_enforced` |
| 16 | Tool timeout | `test_tool_timeout_is_reported_without_numbers` |
| 17 | Veri bulunamadı | `test_missing_data_returns_null_not_zero` |
| 18 | Sonuçların cevaba aktarılması | `test_tool_results_are_sent_back_to_the_model` |
| 19 | Veri kaynağı metadata'sı | `test_metadata_reports_turkish_data_sources`, `test_chat_endpoint_returns_full_metadata` |
| 20 | Thinking görünmemesi | `test_thinking_never_reaches_the_answer` + arayüz kontrolü |

### Geliştirme sırasında bulunan gerçek hatalar

Bunların hepsi araç çıktıları gerçek servis sonuçlarıyla karşılaştırılarak
yakalandı ve teste bağlandı:

| Hata | Belirti | Düzeltme |
|---|---|---|
| **Birim karışıklığı (mali)** | `total_revenue_usd: 50.40` — model 50,4 milyon doları "50 dolar" okurdu | `finance_service` MİLYON USD tutar; araçta ×1.000.000 |
| **Birim karışıklığı (senaryo)** | Personel gideri 6,12 **trilyon** dolar göründü | Senaryo motoru zaten TAM USD döndürüyor; çarpım kaldırıldı |
| **Yıl filtresi (kapasite)** | Eş zamanlı talep 280 çıktı (gerçek: 1.400) — kapasite açığı beşte bir göründü | `build_overview(academic_year=…)` yalnızca o yıl kayıt olanı sayıyor; filtre kaldırıldı |
| **Yıl filtresi (senaryo)** | %15'lik program artışı kurum geneline %7 yansıdı (doğrusu %1,4) — mali etki 5 kat abartılı | Payda 4.000 kayıtlı öğrenci olarak düzeltildi |
| **Personel/bordro çelişkisi** | Personel tablosu 88 kişi, mali dönem 180 kadro — asistan tek cevapta iki farklı rakam verirdi | Maliyet mali dönem kaydından; fark `notes` alanında açıkça yazılıyor |
| **Zayıf ad eşleşmesi** | Olmayan "Uzay Mühendisliği" belirsiz sayıldı | Kısmi eşleşme kademesi kaldırıldı |

---

## 9. Gerçek Ollama canlı testleri

Bu geliştirme ortamında Ollama **kurulu değildir**; canlı testler yazıldı,
sözdizimi doğrulandı ve varsayılan olarak atlanıyor. Uçtan uca akış, Ollama'nın
API sözleşmesini ve araç çağrısı biçimini taklit eden geçici bir HTTP
sunucusuyla gerçek ağ üzerinden doğrulandı: araç çağrıldı, sonuç `tool`
rolüyle modele döndü, model sonucu cevaba yazdı, düşünme metni filtrelendi ve
arayüzde "Kullanılan veriler" bölümü çıktı.

**Kendi makinenizde çalıştırmak için:**

```bash
ollama serve
ollama pull qwen3.5:9b
cd integration/backend
ASSISTANT_LIVE_TEST=1 pytest tests/test_assistant_ollama_live.py -v
```

Bu dosyadaki testler istenen üç soruyu çalıştırır ve **cevaptaki her sayıyı
backend servisinin sonucuyla karşılaştırır**:

| Test | Soru | Doğrulama |
|---|---|---|
| `test_live_current_student_count_comes_from_tools` | "Bilgisayar Mühendisliği'nin mevcut öğrenci sayısı nedir?" | Cevaptaki sayı `build_program_analytics()` sonucuyla aynı olmalı; senaryo aracı **çağrılmamalı** |
| `test_live_salary_scenario_numbers_match_the_engine` | "%2 zam yapılırsa bütçe nasıl etkilenir?" | Maliyet artışı `run_staff_salary_scenario` çıktısıyla ±%1 içinde eşleşmeli |
| `test_live_multi_tool_enrollment_question` | "%15 artarsa mali durum, personel ve laboratuvar nasıl etkilenir?" | Senaryo sonrası öğrenci sayısı araç çıktısıyla aynı olmalı; `data_source` = `institutional_data` |
| `test_live_unknown_program_is_not_invented` | "Uzay Mühendisliği'nde kaç öğrenci var?" | Model sayı vermemeli, bulunamadığını söylemeli |

Bir sayı bile araç sonucu olmadan üretilirse bu testler **başarısız olur**.

---

## 10. Bilinen eksikler

**Veri modelinden gelen sınırlar** (araç bunları uydurmuyor, `notes` alanında
açıkça yazıyor):

- **Mali kayıtlar program düzeyinde tutulmuyor.** Bölüm bütçesi varsa o
  kullanılır; program sorulduğunda kurum geneli rakam döner ve bu belirtilir.
- **Derslik/laboratuvar bölüme bağlı, programa değil.** Program bazlı mekân
  ayrımı yok.
- **Kişi bazlı maaş verisi yok.** Ortalama maaş mali dönem kaydından gelir.
- **Eş zamanlı kapasite açığı yalnızca üniversite geneli hesaplanır**;
  alt kapsamda öğrenci–mekân eşleşmesi verisi bulunmuyor.
- **Personel sayısı ile bordro kadrosu farklı** (88 / 180). Maliyet bordrodan
  alınır, fark cevapta belirtilir. Bu bir veri kalitesi bulgusudur; düzeltilmesi
  demo veri setinin güncellenmesini gerektirir.

**Teknik eksikler:**

- **Senaryo motoru kurum geneli çalışır.** Program düzeyindeki değişim
  öğrenci sayısı oranlanarak uygulanır; `method_note` bunu her cevapta yazar.
  Program bazlı mali model yok.
- **Yetki kontrolü hazır ama bağlı değil.** `ToolSession.permissions`
  çalışıyor ve testli; sohbet uç noktası henüz oturum yetkilerini geçirmiyor,
  bu yüzden tüm araçlar açık. Oturum bilgisinin `/chat`e taşınması gerekiyor.
- **Akış modunda araç yok.** `/chat/stream` çalışır ama araçsızdır.
- **Araç sonuçları önbelleklenmiyor.** Aynı konuşmada aynı araç farklı
  parametrelerle tekrar çağrılırsa veritabanı yeniden sorgulanır.
- **Eş zamanlı istek sınırı yok.** Tek kullanıcılı demo için yeterli.
- **`context_builder` hâlâ modele bağlı değil.** Araç katmanı onun yerini
  aldı; ayrı duran bu modül ya kaldırılmalı ya da anahtar kelime ipucu olarak
  araç seçimine bağlanmalı.

Bu turda **eklenmedi** (istendiği gibi): dinamik grafik, pencere, HTML/CSS
üretimi, RAG, embedding, vektör veritabanı.
