# Canlı Ollama Testleri — Hata Analizi ve Düzeltme Raporu

Önceki turda "tool calling tamamlandı" denmişti; canlı testler sizin
makinenizde çalıştırıldığında 8 testten 4'ü düştü. Bu rapor o hataların kök
nedenlerini ve yapılan düzeltmeleri anlatır.

**Önceki "tüm testler geçti" raporu geçersizdir.** Mock testler geçiyordu
çünkü mock'lar hatalı varsayımları da taklit ediyordu.

---

## 1. Başarısız testlerin kök nedenleri

### 1.1 "Sistemde tanımlı akademik yıl yok" — 3 test

**Belirti:** `entity_resolver.available_academic_years()` boş liste döndü.

**Kök neden:** Canlı test dosyası `app.database.SessionLocal` kullanıyordu.
Bu oturum `settings.DATABASE_URL` üzerinden çözülüyor ve varsayılan değeri
**göreli** bir yol:

```python
DATABASE_URL: str = "sqlite:///./university_management.db"
```

`./` çalışma dizinine göre çözülür. pytest depo kökünden çalıştırıldığında
SQLite orada **yeni ve boş** bir dosya oluşturdu. Testler o boş dosyaya
bağlandı; hiçbir akademik yıl, program veya mali dönem yoktu.

İkinci katman: `tests/conftest.py` zaten `DATABASE_URL`'i geçici bir dizine
yönlendiriyordu, ama o veritabanına **yalnızca birim testlerinin modül
verisi** yükleniyor — tam demo veri seti değil. Yani doğru dosyaya bağlansa
bile veri yoktu.

### 1.2 Model araç çağırmadan `general_model_knowledge` cevabı üretti

**Belirti:** "Bilgisayar Mühendisliği'nin mevcut öğrenci sayısı nedir?"
sorusuna model hiç araç çağırmadan metin üretti; sistem bunu kullanıcıya
sundu.

**Kök neden:** Araç kullanımı yalnızca **sistem yönergesiyle** isteniyordu.
Bir sistem yönergesi ricadır, garanti değildir. Model onu yok saydığında
sunucu tarafında hiçbir engel yoktu.

Ayrıca bu senaryonun mock testi (`test_model_cannot_produce_numbers_without_tools`)
yanlış davranışı **doğru kabul ediyordu**: "araç kullanılmadıysa metadata
genel bilgi der" diye yazılmıştı. Test hatayı doğrulamak yerine onaylıyordu.

### 1.3 120 saniyede Ollama zaman aşımı — 1 test

**Kök nedenler, üç tane:**

| Neden | Etki |
|---|---|
| **Isınma yok** | İlk soruda 9B model diskten belleğe yükleniyor; tek başına dakikalar sürebiliyor |
| **`keep_alive` gönderilmiyor** | Ollama varsayılan olarak modeli 5 dakika sonra bellekten atıyor, her test yeniden yükletiyor |
| **`think` açık** | qwen3 ailesi cevaptan önce uzun bir muhakeme bloğu üretiyor — bu metin zaten kullanıcıya gösterilmiyordu, yani süre tamamen boşa gidiyordu |

Ayrıca canlı test uygulamanın 120 saniyelik sınırını kullanıyordu; model
yüklemesi için bu yetersizdi.

### 1.4 Personel verisi tutarsızlığı

**Belirti:** Personel kayıtları 88 kişi, mali dönem bordrosu 180 kadro.

**Kök neden:** Seed betiği 180 personeli **iki akademik yıla rastgele
bölüştürüyordu**:

```python
academic_year=rng.choice(spec["academic_years"])   # 2024-2025 veya 2025-2026
```

Sonuç: 92 + 88. `AcademicStaff` yıllık bir anlık görüntü tablosudur; kurumun
180 personeli her yıl için ayrı satır taşımalıydı. Bir kişiyi tek bir yıla
rastgele atamak, "2025-2026'da kaç personel var?" sorusunu yarı yanıtlıyordu.

Önceki tur bunu yalnızca `notes` alanında açıklayıp geçmişti — veri hatası
gizlenmemişti ama **düzeltilmemişti** de.

---

## 2. Değiştirilen dosyalar

| Dosya | Değişiklik |
|---|---|
| `tests/test_assistant_ollama_live.py` | **Yeniden yazıldı.** Kendi geçici veritabanını kuruyor, seed ediyor, doğruluyor; 16 test. |
| `app/services/assistant/query_policy.py` | **Yeni.** Kurumsal soru sınıflandırması ve zorunlu araç politikası metinleri. |
| `app/services/assistant/chat_service.py` | Politika bağlandı: araçsız kurumsal cevap reddi, zorunlu retry, `db=None` kısa devresi. |
| `app/services/assistant/ollama_provider.py` | `think`, `keep_alive`, `context_length` parametreleri; `warm_up()`; `ASSISTANT_LIVE_TIMEOUT_SECONDS` desteği. |
| `app/core/config.py` | `OLLAMA_THINK=False`, `OLLAMA_KEEP_ALIVE="10m"`, `OLLAMA_TEMPERATURE=0.0`. |
| `seed_all_demo_data.py` | Personel seed'i yeniden yazıldı: 180 personel **her akademik yıl için**. |
| `app/services/academic_staff_service.py` | `staff_overview()` yıl verilmezse en güncel yılı kullanır. |
| `app/services/assistant/tool_schemas.py` | `active_academic_staff_count`, `payroll_academic_positions`, `cost_basis`, `staffing_data_consistent` alanları. |
| `app/services/assistant/tools.py` | Personel aracı iki sayıyı ayrı ayrı döndürüyor. |
| `tests_integration/test_assistant_tools.py` | Yanlış davranışı onaylayan test düzeltildi + 4 yeni politika testi. |
| `tests_ui/test_frontend.js` | Asistan testi kurumsal soru soruyor (genel sohbet araç kullanmaz). |

---

## 3. Test veritabanı oluşturma ve seed yöntemi

```
Oturum başlar
   │
   ├─ production_database_fingerprint  ← üretim DB'sinin boyutu + mtime
   │
   ├─ tempfile.mkdtemp()               ← mutlak yollu geçici dizin
   │  sqlite:///{db_path.as_posix()}      (göreli yol YOK)
   │
   ├─ subprocess.run([sys.executable, "seed_all_demo_data.py"])
   │     env: DATABASE_URL = geçici dosya
   │     cwd: integration/backend
   │
   ├─ seeded_data_is_complete           ← 6 zorunlu kontrol
   │     • 2025-2026 mali dönemi var
   │     • öğrenci verisi var
   │     • Bilgisayar Mühendisliği çözümleniyor (CENG-BSC)
   │     • mali dönem kaydı var
   │     • 2025-2026 akademik personeli var
   │     • fiziksel kapasite kaydı var
   │
   ├─ warm_up()                         ← model belleğe alınır
   │
   ├─ testler (kendi sessionmaker'ından oturum alır)
   │
   └─ shutil.rmtree(temp_dir)           ← geçici DB silinir
```

**Neden ayrı süreç:** Seed betiği modül seviyesinde `from app.database import
SessionLocal` yapıyor. Aynı süreçte `DATABASE_URL`'i değiştirmek bu bağlamayı
değiştirmez; testin motoruyla uygulamanın motoru karışabilirdi. Ayrı süreç bu
sınıfı hataları imkânsız kılar ve **gerçek seed betiğini** üretimdeki gibi
çalıştırır.

Doğrulanan çıktı:

```
[canlı test] Geçici veritabanı: /tmp/assistant_live_xxxx/live_assistant.db
[canlı test] Demo verisi yükleniyor…
[canlı test] Veri doğrulandı: 4000 öğrenci, 180 personel (2025-2026),
             42 mekân, 6 mali dönem.
[canlı test] Model ısıtılıyor (qwen3.5:9b, keep_alive=10m)…
[canlı test] Model bellekte.
```

Üretim veritabanına dokunulmadığı, parmak izi karşılaştırmasıyla test
ediliyor. Önceki sürümdeki kontrol aynı fonksiyon içinde ölçüp
karşılaştırdığı için hiçbir şey kanıtlamıyordu; artık parmak izi **seed'den
önce** alınıyor.

---

## 4. Zorunlu araç politikası (Institutional Query Policy)

### Soru sınıflandırması

`query_policy.is_institutional_query()` şu işaretleri arar: sayı soruları
(*kaç, ne kadar, oranı, yüzde*), öğrenci, personel/maaş/kadro, mali
(*gelir, gider, bütçe, burs*), kapasite (*derslik, laboratuvar*),
organizasyon (*fakülte, bölüm, program*) ve senaryo (*artarsa, yapılırsa,
ne olur*).

Selamlaşma ve teşekkür kalıpları **tek başına** mesajı oluşturuyorsa genel
sohbettir. Sınıflandırma bilinçli olarak yanlış-pozitife eğimlidir: kararsız
bir soruda araç zorunlu kılmak, uydurma sayı üretmekten iyidir.

```
"Merhaba"                                   → genel
"Teşekkürler"                               → genel
"Sen kimsin?"                               → genel
"Bilgisayar Mühendisliği kaç öğrencisi var?" → KURUMSAL
"Toplam gelir ne kadar?"                     → KURUMSAL
"Laboratuvar kapasitesi yeterli mi?"         → KURUMSAL
"Maaşlara %2 zam yapılırsa ne olur?"         → KURUMSAL
```

### Akış

```
Kurumsal soru + db var
   │
   ├─ 1. çağrı: araçlar sunulur
   │     ├─ model araç çağırdı  → normal döngü
   │     └─ model metin üretti  → METİN ATILIR
   │            │
   │            └─ 2. çağrı: "Bu soru kurumsal veri gerektiriyor.
   │                          Uygun aracı çağırmadan cevap verme."
   │                   ├─ araç çağırdı → normal döngü
   │                   └─ yine metin   → KONTROLLÜ HATA
   │
   └─ Sonuç: araç sonucu yoksa
        answer      = "Kurumsal veriye güvenilir biçimde erişilemediği için
                       sayısal cevap oluşturulmadı."
        data_source = "institutional_data_unavailable"
```

`data_source` kurumsal sorularda **asla** `general_model_knowledge` olmaz.
Modelin uydurduğu sayı kullanıcıya ulaşmaz — test bunu `"9999" not in answer`
ile doğruluyor.

### Veri oturumu yoksa

Kurumsal soru geldiğinde `db=None` ise **Ollama hiç çağrılmaz**:

```json
{
  "answer": "Bu soru kurum verisi gerektiriyor ancak veri oturumu oluşturulamadı. Sayısal bir cevap üretilmedi.",
  "used_tools": [],
  "data_source": "institutional_data_unavailable"
}
```

Bu aynı zamanda testin 120 saniye model beklemesini de ortadan kaldırır.

---

## 5. Zaman aşımı ve ısınma değişiklikleri

| Ayar | Önce | Sonra | Gerekçe |
|---|---|---|---|
| `OLLAMA_THINK` | (gönderilmiyordu) | `False` | Hesabı araçlar yapıyor; muhakeme metni zaten gizleniyordu |
| `OLLAMA_KEEP_ALIVE` | (gönderilmiyordu) | `"10m"` | Model her istekte yeniden yüklenmesin |
| `OLLAMA_TEMPERATURE` | `0.2` | `0.0` | Araç seçimi kararlı olsun |
| Canlı test zaman aşımı | 120 sn (uygulama sınırı) | `ASSISTANT_LIVE_TIMEOUT_SECONDS`, varsayılan 300 sn | Model yüklemesi için pay |
| Isınma | yok | Oturum başında bir kez `warm_up()` | İlk yükleme maliyeti kullanıcının sorusundan önce ödensin |

Uygulamanın kendi sınırı config'te 120 saniye kalır; ortam değişkeni yalnızca
canlı testte devreye girer. Ollama hazır değilse testler zaman aşımına
uğramak yerine **atlanır** (`pytest.skip`), böylece paket kilitlenmez.

---

## 6. Personel verisi çözümü

**Karar:** 180 gerçekten toplam akademik kadrodur (hem
`03_academic_staff.json.total_staff` hem mali dönem sürücüsü 180 diyor).
Seed düzeltildi.

```python
# ÖNCE: 180 kişi iki yıla rastgele bölüştürülüyordu → 92 + 88
academic_year=rng.choice(spec["academic_years"])

# SONRA: her akademik yıl için 180 kişi (yıllık anlık görüntü)
for academic_year in spec["academic_years"]:
    for index in range(1, spec["total_staff"] + 1):
        staff_number = f"AK{index:04d}-{year_suffix}"
```

Aynı kişi yıllar arasında aynı numara kökünü taşır (`AK0001-2425` /
`AK0001-2526`); sicil numarası tekil olmak zorunda olduğu için yıl eki
eklendi.

`staff_overview()` yıl verilmediğinde artık **en güncel yılı** kullanır —
aksi halde iki yılın satırları toplanıp "360 personel" gibi anlamsız bir
sayı çıkıyordu.

**Alanlar da netleştirildi.** `academic_staff_count` tek başına belirsizdi:

| Alan | Anlamı |
|---|---|
| `active_academic_staff_count` | Personel kayıtlarında bu yıl görünen kişi sayısı |
| `payroll_academic_positions` | Mali dönem bordro planlamasındaki kadro sayısı |
| `cost_basis` | Maaş maliyetinin hangi sayıdan hesaplandığı |
| `staffing_data_consistent` | İki sayı eşit mi |
| `academic_staff_count` | Geriye uyum; `active_academic_staff_count` ile aynı |

Kadro açığının hangi sayıya göre hesaplandığı `notes` alanında açıkça yazar.

**Sonuç:**

```json
{
  "active_academic_staff_count": 180,
  "payroll_academic_positions": 180,
  "staffing_data_consistent": true,
  "cost_basis": "bordro kadrosu",
  "annual_salary_cost_usd": "6120000.00",
  "student_staff_ratio": "22.22"
}
```

`student_staff_ratio` 45,45'ten 22,22'ye düzeldi ve artık senaryo motorunun
`baseline_student_staff_ratio` değeriyle aynı.

### Bu düzeltme sırasında çıkan ikinci hata

Personel seed'ini yeniden yazarken `annual_salary_usd` alanını düşürmüştüm;
`test_academic_staff_salaries_are_populated` bunu yakaladı ve geri eklendi.

---

## 7. Mock test sonuçları

```
Backend birim testleri          449 passed, 16 skipped
Backend entegrasyon testleri    100 passed
Arayüz (jsdom, model hazır)     108 passed
Arayüz (jsdom, Ollama kapalı)   103 passed
--------------------------------------------------
0 hata
```

Bu turda eklenen politika testleri:

| Test | Doğrular |
|---|---|
| `test_model_cannot_produce_numbers_without_tools` | Araçsız kurumsal cevap kullanıcıya ulaşmaz; uydurma sayı engellenir |
| `test_institutional_question_retries_before_giving_up` | İlk turda araç çağırmayan model ikinci şans alır ve uyarı mesajı gönderilir |
| `test_general_chat_is_not_forced_to_use_tools` | "Merhaba" için gereksiz ikinci tur yapılmaz |
| `test_institutional_question_without_database_skips_the_model` | `db=None` ise model hiç çağrılmaz |
| `test_query_policy_classifies_questions_correctly` | 6 kurumsal + 4 genel örnek |

Canlı test dosyası bu ortamda **gerçek Ollama olmadan** da doğrulandı:
Ollama'nın araç çağırma sözleşmesini taklit eden bir HTTP sunucusuyla
16 testin tamamı geçti; seed, veri doğrulama, ısınma, araç akışı ve geçici
DB temizliği gerçek ağ üzerinden çalıştı.

---

## 8. Canlı testi çalıştırma

Ön koşul yalnızca Ollama'dır. **`run_project.ps1` çalıştırılması gerekmez** —
test kendi veritabanını kurar ve seed eder.

```powershell
ollama serve
ollama pull qwen3.5:9b

$env:ASSISTANT_LIVE_TEST="1"
& ".\.venv\Scripts\python.exe" -m pytest `
  ".\integration\backend\tests\test_assistant_ollama_live.py" `
  -v -s
```

Zaman aşımını değiştirmek isterseniz:

```powershell
$env:ASSISTANT_LIVE_TIMEOUT_SECONDS="600"
```

### Çalıştırılan 16 test

| # | Test | Ne doğruluyor |
|---|---|---|
| 1 | `service_is_reachable` | Ollama ayakta, model kurulu |
| 2 | `timeout_is_raised_for_live_tests` | Canlı zaman aşımı ≥ 300 sn |
| 3 | `thinking_is_disabled` | `think=False`, `keep_alive` tanımlı |
| 4 | `model_answers_in_turkish` | Türkçe cevap, muhakeme sızmıyor |
| 5 | `greeting_is_not_treated_as_institutional` | Selamlaşma araç zorlamıyor |
| 6 | `institutional_question_without_database_never_calls_the_model` | `db=None` → model çağrılmaz, sayı yok |
| 7 | `streaming_produces_text` | Akış çalışıyor |
| 8 | `current_student_count_comes_from_tools` | `get_program_summary` çağrıldı, sayı servis sonucuyla aynı, senaryo çalıştırılmadı |
| 9 | `salary_scenario_numbers_match_the_engine` | `run_staff_salary_scenario` çağrıldı, rakamlar motorla aynı |
| 10 | `multi_tool_enrollment_question` | `run_enrollment_change_scenario` çağrıldı, öğrenci sayıları araç çıktısıyla aynı |
| 11 | `unknown_program_is_not_invented` | Olmayan program için sayı üretilmiyor |
| 12 | `institutional_answer_without_tools_is_blocked` | Zorunlu retry + güvenli başarısızlık |
| 13 | `general_chat_does_not_force_tools` | Genel sohbette tek tur |
| 14 | `seeded_database_has_the_expected_year` | 2025-2026 seed edilmiş |
| 15 | `tests_do_not_touch_the_production_database` | Üretim DB'si değişmemiş, testler geçici DB'ye bağlı |
| 16 | `staffing_numbers_are_consistent` | 180 = 180, `cost_basis` belirtilmiş |

---

## 9. Bu turda düzeltilmeyenler

- **Yetki kontrolü hâlâ bağlı değil.** `ToolSession.permissions` çalışıyor ve
  testli; `/chat` uç noktası oturum yetkilerini geçirmiyor.
- **Akış modunda araç yok.** `/chat/stream` araçsız çalışır.
- **Senaryo motoru kurum geneli.** Program düzeyindeki değişim öğrenci sayısı
  oranlanarak uygulanır; `method_note` bunu her cevapta belirtir.
- **Mali ve kapasite verisi program düzeyinde yok.** Araçlar kurum geneli
  sayıyı döndürür ve `notes` alanında bunu söyler.

---

## Not

Bu rapor, canlı testlerin **sizin makinenizde** çalıştırılmasıyla
doğrulanacaktır. Bu ortamda gerçek Ollama bulunmadığı için akış, sözleşmeyi
taklit eden bir sunucuyla test edildi. Gerçek modelin araç seçim davranışı
(hangi soruda hangi aracı çağırdığı) yalnızca gerçek çalıştırmada
ölçülebilir; testler o davranışı sayı karşılaştırmasıyla denetleyecek şekilde
yazıldı.
