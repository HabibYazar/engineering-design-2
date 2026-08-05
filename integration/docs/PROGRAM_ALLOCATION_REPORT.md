# Program Düzeyinde Kaynak Tahsisi — Veri Modeli Genişletmesi

Önceki turda tespit edilen eksik kapatıldı: veri modelinde program–personel ve
program–mekân ilişkisi yoktu. Asistan program sorularına üniversite geneli
sayıları (180 öğretim üyesi, 1.020 koltuk) döndürmek zorunda kalıyordu.

---

## 1. Yeni tablolar

### `ProgramAcademicStaffAllocation`

| Alan | Anlamı |
|---|---|
| `academic_year`, `program_id`, `academic_staff_id` | Tekil üçlü |
| `allocation_percent` | Kişinin mesaisinin yüzde kaçı bu programa |
| `weekly_course_hours` | Bu programda haftalık ders saati |
| `role` | koordinatör / öğretim üyesi / yardımcı öğretim elemanı |
| `is_primary` | Kişinin ana programı mı |

**Kural:** bir kişinin bir yıldaki toplam tahsisi %100'ü aşamaz —
`validate_staff_allocation_totals()` denetler, test sabitler.

**Kişi sayısı ≠ FTE.** Bir programda 18 öğretim üyesi ders veriyor olabilir
ama her biri mesaisinin bir kısmını ayırıyorsa gerçek kapasite farklıdır.
İkisi ayrı alanlarda raporlanır.

### `ProgramFacilityAllocation`

| Alan | Anlamı |
|---|---|
| `allocation_type` | classroom / laboratory / studio / workshop |
| `weekly_allocated_hours` | Programın mekânı haftada kaç saat kullandığı |
| `shared_usage_percent` | Mekân kapasitesinin bu programa düşen payı |
| `priority_level` | 1 birincil, 2 paylaşımlı, 3 ara sıra |

**Kural:** bir mekânın haftalık toplam tahsisi 40 saati aşamaz —
`validate_facility_allocation_hours()` denetler.

**Paylaşım açıkça modellenir.** Bir laboratuvarı üç program paylaşıyorsa
hiçbiri tam kapasiteyi kendi kapasitesi gibi gösteremez.

---

## 2. Merkezi formül katmanı

`app/services/program_allocation_service.py` — bütün formüller **tek yerde**.
Araçlar, senaryo motoru ve raporlar bu fonksiyonları çağırır.

```
haftalık derslik ihtiyacı   = öğrenci sayısı × 18 (öğrenci başına haftalık ders saati)
haftalık derslik kapasitesi = Σ(koltuk sayısı × tahsisli saat × paylaşım payı)
haftalık lab ihtiyacı       = öğrenci sayısı × 4
gerekli FTE                 = öğrenci sayısı / 20 (hedef öğrenci-FTE oranı)
haftalık ders kapasitesi    = FTE × 12 saat
yoğun saat derslik talebi   = öğrenci sayısı × 0,35
yoğun saat lab talebi       = öğrenci sayısı × 0,18
kapasite kullanım oranı     = ihtiyaç / kapasite × 100
```

### Birim sözlüğü

| Birim | Anlamı |
|---|---|
| koltuk-saat | Dersliğin haftalık kapasitesi (koltuk × saat) |
| istasyon-saat | Laboratuvarın haftalık kapasitesi |
| eş zamanlı kişi | Yoğun saatte aynı anda mekânda bulunan öğrenci |
| FTE | Tam zaman eşdeğeri öğretim üyesi |

**"Kişi" tek başına kapasite birimi değildir.** 60 kişilik bir derslik haftada
40 saat açıksa kapasitesi 2.400 koltuk-saattir.

---

## 3. Demo verisi

`shared_demo_data/10_program_allocations.json` — hangi programın hangi mekânı
kullandığını **anlamsal olarak** tanımlar. Saatler ve paylaşım payları seed
tarafından hesaplanır.

| Kural | Uygulama |
|---|---|
| 180 akademik personel korunur | 180 kişinin tamamı tahsis edildi; toplam FTE = 180,00 |
| Kişi birden çok programda ders verebilir | Bölümünde ikinci program varsa mesai %70/%30 bölünür |
| Her programa en az bir derslik | 14 programın hepsinde ≥1 derslik |
| Laboratuvar yalnızca gerektiren programlara | İşletme, İktisat, Uluslararası İlişkiler → laboratuvar **yok** |
| Mimarlık stüdyo | STD-ARCH1, STD-ARCH2 (`allocation_type = studio`) |
| Hemşirelik sağlık laboratuvarı | LAB-NUR1 |
| Seed idempotent | İkinci çalıştırmada kayıt çoğalmaz — testli |

### Saat dağıtımı — bir düzeltme

İlk sürümde saatler JSON'a elle yazılmıştı ve mekânların 40 saatlik
penceresini doldurmuyordu; Bilgisayar Mühendisliği'nin derslik kullanım oranı
**%521** çıkıyordu. Artık bir mekânı kullanan programlar 40 saati **öğrenci
sayılarıyla oranlı** paylaşıyor; toplam tam 40 saat ve paylar tam %100.

Sonuç, kurum genelindeki gerçekle tutarlı (%176 kurum ortalaması):

| Program | Öğrenci | FTE | Derslik kullanımı | Lab |
|---|---|---|---|---|
| Bilgisayar Mühendisliği | 370 | 18,00 | %222,9 | 2 |
| İşletme | 488 | 20,60 | %173,6 | yok |
| Mimarlık | 295 | 20,00 | %132,8 | 2 stüdyo |

Bu veri setinde gerçekten kapasite açığı var — 4.000 öğrenci × 18 saat =
72.000 koltuk-saat talebe karşılık 1.020 koltuk × 40 saat = 40.800 koltuk-saat
kapasite.

---

## 4. Güncellenen araçlar

### `get_program_summary`

```json
{
  "allocated_staff_headcount": 18,
  "allocated_staff_fte": "18.00",
  "weekly_teaching_capacity_hours": "216.00",
  "student_staff_ratio": "20.56",
  "target_student_staff_ratio": "20"
}
```

Oran **FTE üzerinden** hesaplanır; 18 kişinin yarısı bu programda ders
veriyorsa gerçek kapasite 9 FTE'dir.

### `get_capacity_summary` (program verildiğinde)

```json
{
  "allocated_classrooms": 2,
  "allocated_laboratories": 2,
  "weekly_classroom_capacity_seat_hours": "2987.57",
  "weekly_classroom_demand_seat_hours": "6660.00",
  "weekly_laboratory_capacity_station_hours": "1122.41",
  "weekly_laboratory_demand_station_hours": "1480.00",
  "classroom_utilization_percent": "222.92",
  "peak_concurrent_capacity": 86,
  "peak_concurrent_demand": 130,
  "capacity_gap": 44,
  "capacity_status": "yetersiz"
}
```

İşletme programı için `allocated_laboratories: null` ve
*"bu programa tahsis edilmiş laboratuvar kaydı bulunamadı"* notu.

### `run_enrollment_change_scenario`

Program kaynak raporu **mevcut ve senaryo öğrenci sayısıyla iki kez** aynı
formülden geçirilir.

---

## 5. Senaryo çıktısı

```
**2025-2026 — Bilgisayar Mühendisliği Lisans Programı**

Senaryo: program öğrenci sayısında %15 değişim (+56 öğrenci).

### Program kapsamındaki sonuçlar — Bilgisayar Mühendisliği Lisans Programı
- Öğrenci sayısı: 370 öğrenci → 426 öğrenci (+56 öğrenci)
- Programda ders veren öğretim üyesi: 18 kişi
- Program akademik kapasitesi: 18 FTE
- Gerekli akademik kapasite: 18,50 FTE → 21,30 FTE (+2,80 FTE)
- Ek akademik kapasite ihtiyacı: 0,50 FTE → 3,30 FTE (+2,80 FTE)
- Program derslik kapasitesi: 2.987,57 koltuk-saat
  - Bazı mekânlar başka programlarla paylaşılıyor; kapasite yalnızca bu
    programa düşen pay kadar sayıldı.
- Program haftalık derslik ihtiyacı: 6.660 → 7.668 koltuk-saat (+1.008)
- Program derslik kullanım oranı: %222,92 → %256,66
- Program laboratuvar kapasitesi: 1.122,41 istasyon-saat
- Program haftalık laboratuvar ihtiyacı: 1.480 → 1.704 istasyon-saat (+224)
- Program laboratuvar kullanım oranı: %131,86 → %151,82
- Bu programdaki artışın ek gelir etkisi: +329.840 USD

### Bölüm kapsamındaki sonuçlar — Bilgisayar Mühendisliği
- Bölüm akademik personeli: 18 kişi

### Üniversite bütçesine ve kaynaklarına etkisi — Üniversite geneli
- Üniversite toplam yıllık geliri: 35.960.000 USD → 36.289.840 USD (+329.840 USD)
- Üniversite net bütçesi: 2.900.000 USD → 3.157.040 USD (+257.040 USD)
- …
```

İstenen sekiz maddenin tamamı karşılanıyor: mevcut FTE, gerekli FTE, ek
ihtiyaç, program derslik kapasitesi ve talebi, program laboratuvar kapasitesi
ve talebi, paylaşımlı mekân etkisi (not olarak), üniversite bütçesine marjinal
etki.

**Bir düzeltme daha:** FTE ve koltuk-saat gibi ondalıklı birimler tam sayıya
yuvarlanıyordu — 18,50 FTE "18 FTE" görünüyordu. Yarım kadroluk fark
kayboluyordu; ondalık korundu.

---

## 6. Değiştirilen dosyalar

| Dosya | Değişiklik |
|---|---|
| `app/models/program_allocation.py` | **Yeni** — iki tahsis tablosu, `WEEKLY_AVAILABLE_HOURS` |
| `app/models/__init__.py` | Yeni modellerin kaydı |
| `app/services/program_allocation_service.py` | **Yeni** — merkezi formül katmanı, doğrulama, kapasite raporu |
| `shared_demo_data/10_program_allocations.json` | **Yeni** — anlamsal tahsis haritası |
| `seed_all_demo_data.py` | `seed_program_allocations()`; saatler öğrenci ağırlığıyla dağıtılıyor |
| `app/services/assistant/tool_schemas.py` | Program tahsisi alanları (özet, kapasite, senaryo blokları) |
| `app/services/assistant/tools.py` | Üç araç program tahsislerini kullanıyor |
| `app/services/assistant/response_composer.py` | Ondalıklı birimler (FTE, koltuk-saat) korunuyor |
| `tests_integration/test_assistant_tools.py` | 9 yeni test; 3 test yeni metriklere göre güncellendi |

**Dokunulmayanlar:** Ollama provider, chat_service araç döngüsü, intent
router, response composer mimarisi, kapsam etiketleme yapısı.

---

## 7. Test sonuçları

```
Backend birim testleri          449 passed, 17 skipped
Backend entegrasyon testleri    143 passed
Arayüz (jsdom, model hazır)     108 passed
Arayüz (jsdom, Ollama kapalı)   103 passed
Canlı test dosyası               17 passed
--------------------------------------------------
0 hata
```

İstenen 9 test:

| Test | Doğrular |
|---|---|
| `test_staff_allocation_never_exceeds_one_hundred_percent` | Kişi başına tahsis ≤ %100 |
| `test_university_fte_matches_staff_capacity` | FTE ≤ kişi sayısı; 180 kişinin tamamı tahsisli |
| `test_facility_allocation_never_exceeds_available_hours` | Mekân başına ≤ 40 saat |
| `test_programs_without_laboratories_get_none` | İşletme/İİ/İktisat'a lab yok; Mimarlık stüdyo, Hemşirelik sağlık lab |
| `test_enrollment_scenario_uses_only_its_own_allocations` | CENG senaryosu yalnızca A101/A102 ve LAB-CE1/LAB-CE2 |
| `test_university_total_is_not_shown_as_program_staff` | Program metriklerinde 180 yok |
| `test_capacity_metrics_carry_a_time_dimension` | koltuk-saat/istasyon-saat/eş zamanlı kişi; düz "kişi" yok; formül zorunlu |
| `test_program_summary_separates_headcount_from_fte` | Kişi sayısı ile FTE ayrı; oran FTE üzerinden |
| `test_allocation_seed_is_idempotent` | Seed iki kez çalışınca kayıt çoğalmaz |

---

## 8. Canlı test

```powershell
$env:ASSISTANT_LIVE_TEST="1"
& ".\.venv\Scripts\python.exe" -m pytest `
  ".\integration\backend\tests\test_assistant_ollama_live.py" -v -s
```

Hedef: **17 passed**

---

## 9. Kalan sınırlar

- **Mali veri hâlâ program düzeyinde değil.** Gelir ve gider mali dönem
  kaydında kurum geneli tutuluyor; program etkisi marjinal fark olarak
  veriliyor ve öyle etiketleniyor.
- **Senaryo motoru kurum geneli çalışır.** Program öğrenci değişimi
  oranlanarak uygulanır; `method_note` bunu her cevapta belirtir.
- **Ders programı (timetable) yok.** Kapasite haftalık toplam üzerinden
  hesaplanıyor; gün/saat çakışması modellenmiyor.
- Yetki kontrolü hazır ama `/chat` uç noktasına bağlı değil.
- Akış modunda araç çağrısı ve composer yok.
