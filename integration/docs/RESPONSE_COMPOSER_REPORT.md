# Deterministik Cevap Oluşturucu — Düzeltme Raporu

Canlı testlerde 17'den 16'sı geçti. Kalan tek başarısızlık
`test_live_multi_tool_enrollment_question` idi ve teşhisiniz doğruydu:

| Aşama | Durum |
|---|---|
| Araç seçimi | ✅ `run_enrollment_change_scenario` |
| Dönem | ✅ 2025-2026 |
| Program | ✅ Bilgisayar Mühendisliği |
| Senaryo motoru | ✅ 370 → 426 öğrenci |
| **Final cevap** | ❌ Model 370 ve 426'yı **yazmadı** |

Bu bir araç çağırma hatası değil, bir **cevap oluşturma** hatasıydı. Model
mali etkileri anlattı, senaryonun ana metriğini atladı.

Sistem yönergesine "bu sayıları yaz" eklemek çözüm değildir — yönerge bir
ricadır ve model onu daha önce iki kez yok saydı. Kritik metriklerin cevapta
bulunması artık **backend tarafından garanti ediliyor**.

---

## 1. Deterministik cevap oluşturucu

`app/services/assistant/response_composer.py` — yeni.

Final cevap iki parçadan oluşur:

```
[Backend'in yazdığı zorunlu gerçekler]   ← response_composer
[Modelin yazdığı yönetim değerlendirmesi] ← LLM
```

Model **yalnızca ikinci parçayı** üretir. Birinci parça araç çıktısından
biçimlendirilir; model onu ne değiştirebilir ne de atlayabilir.

### Gerçek çıktı — model 370 ve 426'yı hiç yazmadığı hâlde

```
**2025-2026 — Bilgisayar Mühendisliği Lisans Programı**

### Hesaplanan sonuçlar
- Öğrenci sayısı: 370 → 426
- Değişim: +56 öğrenci (%15)
- Yıllık gelir: 35.960.000 USD → 36.289.840 USD
- Gelir etkisi: +329.840 USD
- Net bütçe: 2.900.000 USD → 3.157.040 USD
- Bütçe etkisi: +257.040 USD
- Akademik personel: 180 kişi
- Önerilen personel: 203 kişi
- Ek personel ihtiyacı: +23 kişi
- Laboratuvar kapasitesi: 328 kişi
- Senaryo laboratuvar talebi: 730 kişi
- Laboratuvar kapasite farkı: +402 kişi
- Derslik kapasitesi: 1.020 kişi
- Senaryo derslik talebi: 1.420 kişi
- Derslik kapasite farkı: +400 kişi
- Kapasite durumu: yetersiz

### Tespit edilen riskler
- Derslik kapasitesi yetersiz: … 400 kişilik açık oluşuyor.
- Laboratuvar kapasitesi yetersiz: … 402 kişilik açık oluşuyor.

### Yönetim değerlendirmesi
- Gelir artışı bütçeyi olumlu etkiler.
- Kadro planlaması gözden geçirilmeli.
- Laboratuvar yatırımı önceliklidir.
```

### Oluşturucu hesap YAPMAZ

Buradaki her sayı araç çıktısından **olduğu gibi** alınır. Değişim, yüzde ve
fark değerleri araç katmanında hesaplanır. Bu ayrım bilinçli: iki farklı
yerde yapılan aynı hesap er ya da geç birbirinden ayrılır.

Bu yüzden senaryo araçlarına zorunlu alanlar eklendi:

| Araç çıktısına eklenen | Neden |
|---|---|
| `program_student_change`, `student_change_percentage` | Değişim satırı için |
| `revenue_change_usd`, `net_balance_change_usd` | Mali etki satırları için |
| `recommended_staff_count`, `staff_gap` | Personel ihtiyacı için |
| `laboratory_capacity/demand/gap`, `classroom_capacity/demand/gap`, `capacity_status` | Kapasite satırları için |
| `salary_change_percentage` (maaş senaryosu) | Değişim yüzdesi için |

Araç çıktısında bulunmayan alan **uydurulmaz**; `Veri bulunamadı` yazılır.

---

## 2. Modelin sonucu yeniden hesaplaması engellendi

Modele gönderilen yönerge:

> "Aşağıdaki 'Hesaplanan sonuçlar' bölümü backend tarafından hazırlanmıştır
> ve kullanıcıya AYNEN gösterilecektir. Bu değerleri değiştirme, yeniden
> hesaplama, yuvarlama veya farklı birimle (milyon USD / USD) tekrar yazma.
> Sayıları tekrar listeleme; yalnızca etkilerini yorumla."

Ama yönergeye güvenilmiyor: model farklı bir sayı yazsa bile **zorunlu
gerçekler bölümü değişmez** ve `structured_result` araç değerlerini taşır.
Model gerçekler bölümünü kopyalarsa tekrar eden satırlar atılır — aynı sayı
iki kez görünmez.

**Birim koruması.** `_usd()` tutarı asla milyona çevirmez. Küçük tutarlarda
ondalık korunur: 30,60 USD "31 USD" diye yuvarlanmıyor (öğrenci başına
maliyet gibi göstergelerde anlamı bozardı).

---

## 3. Zorunlu metrik doğrulaması

Cevap kullanıcıya gitmeden önce araç çıktısı denetlenir:

| Araç | Zorunlu alanlar |
|---|---|
| `run_enrollment_change_scenario` | `scope.academic_year`, `scope.program`, `baseline.program_student_count`, `scenario.program_student_count`, `student_change_percentage` |
| `run_staff_salary_scenario` | `scope.academic_year`, `salary_change_percentage`, `previous_annual_staff_cost_usd`, `new_annual_staff_cost_usd` |
| `get_program_summary` | `scope.academic_year`, `program_name` |
| `get_financial_summary` | `scope.academic_year` |

Biri eksikse `MissingMetricError` fırlar, eksik alan günlüğe yazılır ve
kullanıcıya kontrollü mesaj döner:

> "Senaryo sonucu eksik üretildi; bazı zorunlu göstergeler hesaplanamadı."

Modelin yorumunda bir metrik geçmemesi sorun sayılmaz — zorunlu gerçekler
zaten backend tarafından yazılıyor.

---

## 4. `structured_result` alanı

`POST /api/assistant/chat` cevabına eklendi:

```json
{
  "answer": "…",
  "structured_result": {
    "type": "enrollment_change_scenario",
    "academic_year": "2025-2026",
    "scope": { "program": "Bilgisayar Mühendisliği Lisans Programı" },
    "metrics": [
      {
        "key": "program_student_count",
        "label": "Öğrenci sayısı",
        "baseline": 370,
        "scenario": 426,
        "change": 56,
        "unit": "öğrenci"
      }
    ],
    "risks": [],
    "recommendations": []
  }
}
```

Uçtan uca doğrulandı. Arayüz şimdilik yalnızca `answer` metnini gösteriyor;
alan sonraki dinamik grafik aşaması için korunuyor.

---

## 5. Bu turda bulunan ek eksik

Test yazarken bir ürün açığı çıktı: **model boş cevap döndürürse hazır
hesaplanmış sonuçlar kayboluyordu.** Sağlayıcı `invalid_response` hatası
fırlatıyor, hata yukarı çıkıyor ve doğru hesaplanmış senaryo kullanıcıdan
gizleniyordu.

Düzeltildi: hesaplanan sonuçlar hazırsa modelin yorumu olmadan da cevap
verilir. `test_facts_are_returned_even_with_an_empty_model_interpretation`
bunu sabitliyor.

---

## 6. Değiştirilen dosyalar

| Dosya | Değişiklik |
|---|---|
| `app/services/assistant/response_composer.py` | **Yeni** — zorunlu gerçekler bölümü, `structured_result`, zorunlu alan doğrulaması |
| `app/services/assistant/tool_schemas.py` | Senaryo çıktılarına zorunlu metrik alanları |
| `app/services/assistant/tools.py` | Değişim, personel ihtiyacı ve kapasite açığı **araç katmanında** hesaplanıyor |
| `app/services/assistant/chat_service.py` | Composer bağlantısı, `_clean_interpretation()`, `MISSING_METRIC_MESSAGE`, boş yorum koruması, sistem yönergesi 7b |
| `app/services/assistant/schemas.py` | `structured_result` alanı |
| `tests_integration/test_assistant_tools.py` | 11 yeni test |

---

## 7. Test sonuçları

```
Backend birim testleri          449 passed, 17 skipped
Backend entegrasyon testleri    127 passed
Arayüz (jsdom, model hazır)     108 passed
Arayüz (jsdom, Ollama kapalı)   103 passed
Canlı test dosyası               17 passed
--------------------------------------------------
0 hata
```

İstenen 10 test:

| # | Test |
|---|---|
| 1 | `test_enrollment_facts_are_composed_by_the_backend` |
| 2 | `test_student_numbers_survive_when_the_model_skips_them` |
| 3 | `test_model_cannot_overwrite_the_composed_facts` |
| 4 | `test_structured_result_contains_baseline_and_scenario` |
| 5 | `test_money_values_keep_the_usd_unit` |
| 6 | `test_facts_are_returned_even_with_an_empty_model_interpretation` |
| 7 | `test_missing_required_metric_produces_a_controlled_error` |
| 8 | `test_salary_scenario_required_metrics_appear_in_the_answer` |
| 9 | `test_composer_only_formats_and_never_calculates` |
| 10 | `test_same_number_is_never_shown_in_two_units` |

Ek: `test_missing_tool_field_is_written_as_veri_bulunamadi`.

**Test beklentisi gevşetilmedi.** `test_live_multi_tool_enrollment_question`
olduğu gibi duruyor; 370 ve 426 kontrolü yerinde.

Canlı test dosyası bu ortamda, **kritik metrikleri kasten atlayan** bir sahte
modelle çalıştırıldı ve 17/17 geçti — hatanın kendisini taklit eden bir
modelle.

---

## 8. Canlı testi çalıştırma

```powershell
ollama serve
ollama pull qwen3.5:9b

$env:ASSISTANT_LIVE_TEST="1"
& ".\.venv\Scripts\python.exe" -m pytest `
  ".\integration\backend\tests\test_assistant_ollama_live.py" `
  -v -s
```

Hedef: **17 passed**

---

## 9. Durum

**"Tool calling tamamlandı" demiyorum.** Gerçek Ollama çıktısını görmeden
söyleyemem.

Bu turdan sonra modelin cevabı bozabileceği alan daralıyor: araç seçimi,
dönem seçimi, parametre çıkarımı ve kritik metriklerin cevapta bulunması
artık backend'de. Modele kalan tek iş yorumlamak — ve yorumu tamamen boş
olsa bile hesaplanan sonuçlar kullanıcıya gidiyor.

### Bilinen eksikler (değişmedi)

- Yetki kontrolü hazır ama `/chat` uç noktasına bağlı değil.
- Akış modunda (`/chat/stream`) araç çağrısı ve composer yok.
- Senaryo motoru kurum geneli çalışır; program değişimi oranlanarak uygulanır.
- Mali ve kapasite verisi program düzeyinde tutulmuyor.
- Arayüz `structured_result` alanını henüz kullanmıyor (bilinçli — dinamik
  grafik bir sonraki aşama).
