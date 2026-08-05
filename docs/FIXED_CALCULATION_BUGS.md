# Düzeltilen Hesaplama Hataları

Bu belge, veri kalitesi ve hesaplama iyileştirmesi turunda **gerçekten bulunan
ve düzeltilen** hataları listeler. Her madde için hatanın ne olduğu, nasıl
kanıtlandığı ve nasıl düzeltildiği yazılıdır.

Hepsi `tests_integration/test_calculations_and_consistency.py` içindeki
testlerle kalıcı olarak korunmaktadır.

---

## 1. Senaryo parametreleri hiç uygulanmıyordu (KRİTİK)

**Belirti:** Kullanıcı senaryo ekranında hangi değeri girerse girsin sonuç
değişmiyordu. "Öğrenci sayısı %50 artsın" ile "hiçbir şey değişmesin" aynı
tabloyu üretiyordu.

**Kök neden:** Arayüz ile backend'in alan adları uyuşmuyordu.

| Arayüzün gönderdiği | Backend'in beklediği |
|---|---|
| `student_count_change_percent` | `student_change_percent` |
| `staff_count_change` | `academic_staff_change` |
| `new_program_student_count` | *(hiç yok)* |
| `closing_program_student_count` | *(hiç yok)* |

Pydantic varsayılan olarak tanımadığı alanları **sessizce yok sayar**. İstek
200 dönüyor, sonuç üretiliyor, ama uygulanan değişiklik sıfırdı.

**Kanıt:**

```
frontend: ogrenci +%50   -> ogr=5000 pers=220 gelir=660000000.00  [DEGISIM YOK]
frontend: personel +50   -> ogr=5000 pers=220 gelir=660000000.00  [DEGISIM YOK]
frontend: yeni program   -> ogr=5000 pers=220 gelir=660000000.00  [DEGISIM YOK]
```

**Düzeltme:**

1. `ScenarioInputCreate` şemasına `model_config = ConfigDict(extra="forbid")`
   eklendi. Tanınmayan alan artık **422 ile reddediliyor**.
2. Senaryo türleri ve alan adları arayüzde elle yazılmak yerine
   `GET /api/scenarios/catalog` endpoint'inden alınıyor. Arayüz artık alan adı
   uyduramaz.
3. `test_scenario_catalog_field_names_match_schema` testi, katalogdaki her alan
   adının şemada gerçekten var olduğunu doğruluyor.

**Test:** `test_unknown_input_field_is_rejected`,
`test_scenario_catalog_field_names_match_schema`

---

## 2. Maaş değişikliği senaryosu yoktu

**Belirti:** "Akademik personel maaşlarına %2 zam yapılırsa ne olur?" sorusu
sistemde cevaplanamıyordu. Personel gideri yalnızca kişi sayısıyla değişiyordu.

**Kök neden:** Baseline yalnızca `annual_personnel_expense` (toplam) tutuyordu.
Personel sayısı ve ortalama maaş ayrı ayrı bilinmediği için zammın etkisi
hesaplanamıyordu.

**Düzeltme:**

- `FinancialPeriod` modeline sürücü alanlar eklendi: `academic_staff_count`,
  `average_academic_salary_usd`, `administrative_staff_count`,
  `average_administrative_salary_usd`, `list_tuition_per_student_usd`,
  `average_scholarship_rate_percent`.
- `AcademicStaff` modeline `annual_salary_usd` eklendi.
- Senaryo girdisine `academic_salary_change_percent` ve
  `administrative_salary_change_percent` eklendi.
- Motor artık şu formülü kullanıyor:

```
yeni personel gideri = yeni kadro sayısı × (ortalama maaş × (1 + zam))
```

**Doğrulanan sonuç (%2 zam, 2025-2026 tabanı):**

| Gösterge | Önceki | Yeni | Değişim |
|---|---|---|---|
| Personel gideri | $6.120.000 | $6.242.400 | +$122.400 (+%2,00) |
| Gelir–gider dengesi | $2.900.000 | $2.777.600 | −$122.400 (−%4,22) |
| Öğrenci başına maliyet | $8.265 | $8.296 | +$31 (+%0,37) |

**Test:** `test_salary_increase_scenario_changes_personnel_expense`,
`test_salary_increase_propagates_to_balance_and_cost_per_student`

---

## 3. Senaryo tabanı mali analiz modülüyle çelişiyordu

**Belirti:** Aynı kurumun yıllık geliri Senaryo ekranında bir, Finansal Analiz
ekranında başka bir rakam gösteriyordu.

```
Mali modül geliri : 935,00 M
Senaryo tabanı    : 660,00 M
```

**Kök neden:** `ScenarioBaseline` elle girilmiş bağımsız bir kayıttı; mali
dönem verisiyle hiçbir bağı yoktu.

**Düzeltme:**

- `scenario_baseline_builder.py` yazıldı: seçilen mali dönemin **gerçekleşen**
  gelir/gider kalemlerinden geçici bir taban üretir.
- `POST /api/scenarios/preview?financial_period=2024-2025` ile herhangi bir
  dönem seçilebiliyor.
- `seed_all_demo_data.py` sonunda kayıtlı aktif taban güncel mali dönemle
  eşitleniyor.

**Doğrulanan sonuç:**

```
mali brüt gelir      : $50.400.000
burs gideri          : $14.440.000
mali net             : $35.960.000
senaryo tabanı       : $35.960.000   ← birebir aynı
```

**Test:** `test_scenario_baseline_matches_financial_module`,
`test_financial_period_selection_changes_baseline`

---

## 4. Kapasite yeterliliği yanlış ölçütle hesaplanıyordu

**Belirti:** Kapasite her senaryoda "yetersiz" veya "sınırda" çıkıyordu; uyarı
anlamını yitirmişti.

**Kök neden:** **Tüm** öğrencilerin **aynı anda** derslikte olduğu varsayılıyordu:

```python
if computation.projected_student_count > computation.projected_classroom_capacity:
```

4000 öğrencili bir kurumun 4000 kişilik derslik kapasitesine sahip olması
beklenemez; ders programı gün ve saate yayılır.

**Düzeltme:**

- Eş zamanlı kullanım katsayıları tanımlandı (kaynak: `00_assumptions.json`):
  derslik %35, laboratuvar %18.
- Karşılaştırma artık `öğrenci sayısı × katsayı` üzerinden yapılıyor.
- **Aynı hata ikinci bir yerde daha vardı:** `scenario_risk.py` kendi
  karşılaştırmasını yapıyordu. O da düzeltildi; iki dosya artık aynı ölçütü
  kullanıyor.

**Test:** `test_capacity_uses_simultaneous_use_factor`

---

## 5. Kontenjan artışı gerçekçi olmayan gelir üretiyordu

**Belirti (potansiyel):** Kontenjan senaryosu yoktu; eklendiğinde naif
uygulama kontenjan artışının tamamını öğrenciye çevirirdi.

**Düzeltme:** `QUOTA_FILL_ELASTICITY = 0,85` katsayısı eklendi. Kontenjanı %100
artırmak öğrenci sayısını %85 artırır — boş kontenjan gelir üretmez.

**Test:** `test_quota_change_uses_fill_elasticity`

---

## 6. Geçersiz burs oranı hesaplanıyordu

**Belirti:** Burs oranını %105'e çıkaran bir senaryo hesaplanıyor, negatif
öğrenim geliri üretiyor ve sonradan "kritik risk" olarak etiketleniyordu.

**Düzeltme:** Efektif burs oranı %0–%100 dışına çıkarsa istek hesaplanmadan
önce **422 ile reddediliyor** ve sebebi açıklanıyor. Geçersiz girdiyi hesaplayıp
riskli ilan etmek yerine kapıda reddetmek doğru davranıştır.

**Test:** `test_scholarship_rate_cannot_exceed_100_percent`

---

## 7. Bölgesel istihdam oranı %160 çıkıyordu

**Belirti:**

```
bölgede istihdam: 452 mezun / 281 mezun = %160,85
```

**Kök neden:** Bir **yılın** istihdam sayısı, **tüm yılların** mezun havuzuna
bölünüyordu. Payda `Student.current_status == "graduated"` sayımıydı.

**Düzeltme:**

- Payda o akademik yılın mezun sayısı oldu
  (`AcademicSuccessRecord.graduate_count` toplamı).
- Oran yine de %100'ü aşarsa **hesaplanmıyor**; `null` dönüp sebebi
  bildiriliyor. Sessizce imkânsız bir oran göstermek yerine hesaplamayı
  reddetmek doğru.

**Sonuç:** 452 / 767 = **%58,93**

**Test:** `test_regional_employment_share_is_plausible`

---

## 8. Ölçülen öğrenci sayısı üniversite toplamıyla uyuşmuyordu

**Belirti:** Akademik Başarı ekranı 917 öğrenci gösterirken Öğrenci Analitiği
4000 gösteriyordu.

**Kök neden:** Başarı ölçümünün ağırlığı olarak, o yıl **yeni yerleşen**
öğrenci sayısı (`enrollment_snapshot.enrolled_student_count`) kullanılıyordu.

**Düzeltme:** Ağırlık, programa **kayıtlı toplam** öğrenci sayısı oldu.

**Doğrulanan sonuç:**

```
üniversite toplamı : 4000
fakülte toplamı    : 4000
bölüm toplamı      : 4000
program toplamı    : 4000
```

**Test:** `test_faculty_department_program_totals_are_consistent`,
`test_student_count_is_consistent_across_modules`

---

## 9. Karışık ve belirsiz para birimi

**Belirti:** Sistemde TL, milyon TL, bin TL ve birimsiz sayılar karışıktı.
Arayüzde `₺` ile birimsiz değerler yan yana duruyordu.

**Düzeltme:**

- Tüm parasal değerler **USD** oldu. Mali tablolar milyon USD, kişi başına
  oranlar tam USD.
- Alan adları düzeltildi: `cost_per_student_thousand_try` →
  `cost_per_student_thousand_usd`.
- Yuvarlama kaybı olmayan tam USD alanları eklendi: `cost_per_student_usd`,
  `revenue_per_student_usd`.
- Arayüzde `fmt.usd`, `fmt.usdMillion`, `fmt.usdPerPerson` biçimlendiricileri
  eklendi; her tutar `$` işareti ve birimiyle gösteriliyor.

**Test:** `test_all_amounts_are_usd`

---

## 10. KPI'lar neyi ölçtüğü belirsiz çıplak sayılardı

**Belirti:** Ekranda "52,2" gibi bir değer görünüyordu; ne ölçtüğü, nasıl
hesaplandığı, yükselmesinin iyi mi kötü mü olduğu belli değildi.

**Özellikle iki gösterge:** *Bölgesel Katkı* ve *Üniversite–Sanayi İş Birliği*
elle girilmiş tek bir puandı ve hangi veriden geldiği hiçbir yerde yazmıyordu.

**Düzeltme:**

1. `StrategicKpi` modeline künye alanları eklendi: `description`, `formula`,
   `data_source`, `higher_is_better`, `value_source`.
2. 16 göstergenin tamamına açıklama, formül ve veri kaynağı yazıldı.
3. Maliyet göstergeleri `higher_is_better=False` işaretlendi — arayüz artık
   maliyet artışını yeşil göstermiyor.
4. `direction_label` alanı değişimi sade dille anlatıyor:
   "geçen döneme göre arttı (kötüleşme)".
5. **İki gösterge gerçek formüle bağlandı:**

**Üniversite–Sanayi İş Birliği Endeksi**

```
endeks = Σ (bileşen ÷ stratejik hedef × 100 × ağırlık)
```

| Bileşen | Ağırlık | Hedef |
|---|---|---|
| Aktif sanayi iş birliği sayısı | 0,20 | 45 |
| Ortak proje sayısı | 0,25 | 40 |
| Sanayi destekli araştırma bütçesi | 0,30 | 3,50 M USD |
| Staj yapan öğrenci sayısı | 0,15 | 350 |
| İş birliği protokolü sayısı | 0,10 | 25 |

**Bölgesel Katkı Endeksi**

| Bileşen | Ağırlık | Hedef |
|---|---|---|
| Bölgede istihdam edilen mezun | 0,35 | 600 |
| Yerel kamu projesi | 0,20 | 20 |
| Toplum hizmeti saati | 0,15 | 12.000 |
| Bölgesel KOBİ iş birliği | 0,15 | 30 |
| Belediye iş birliği | 0,10 | 10 |
| Halka açık etkinlik | 0,05 | 40 |

Ağırlıklar ve hedefler `shared_demo_data/09_engagement.json` içindedir —
kodda gömülü değildir. Arayüz her bileşenin ham değerini, hedefini ve endekse
katkısını ayrı ayrı gösterir; endeks "kara kutu puan" olmaktan çıkmıştır.

**Test:** `test_every_kpi_has_complete_metadata`,
`test_cost_kpis_are_marked_lower_is_better`,
`test_industry_collaboration_index_is_computed_from_components`,
`test_regional_contribution_index_is_computed_from_components`

---

## Eski testlerde yapılan değişiklikler

Üç eski regresyon testi, TL dönemine ait **sabit sayıları** doğruluyordu:

| Test | Eski beklenti | Yeni yaklaşım |
|---|---|---|
| `test_module9_baseline_seed_present` | `annual_tuition_per_student == "180000.00"` | Tabanın mantıklı olduğu doğrulanıyor (pozitif, burs oranı 0–100 arası) |
| `test_module9_simulation_math_unchanged` | `projected_technology_expense == "48750000.00"` | **Formül** doğrulanıyor: `taban × (1+enflasyon) × (1+kur)` |
| `test_module9_risk_engine_still_works` | Geçersiz senaryonun `critical` dönmesi | Geçersiz girdi 422; geçerli ağır senaryoda `budget_deficit` riski üretilmesi |

Sihirli sayı yerine formül doğrulamak daha güçlüdür: veri değişse de formül
bozulursa test yakalar.

---

## Özet

| # | Hata | Etki | Durum |
|---|---|---|---|
| 1 | Senaryo parametreleri uygulanmıyor | Senaryo modülü fiilen çalışmıyordu | Düzeltildi |
| 2 | Maaş senaryosu yok | Ana kullanım senaryosu eksikti | Eklendi |
| 3 | Taban ile mali modül çelişiyor | Yanlış karar riski | Düzeltildi |
| 4 | Kapasite ölçütü yanlış (2 yerde) | Uyarılar anlamsızdı | Düzeltildi |
| 5 | Kontenjan esnekliği yok | Gerçekçi olmayan gelir | Eklendi |
| 6 | Geçersiz burs oranı hesaplanıyor | Negatif gelir üretiyordu | Düzeltildi |
| 7 | Bölgesel istihdam %160 | İmkânsız oran | Düzeltildi |
| 8 | Öğrenci toplamları uyuşmuyor | Ekranlar çelişiyordu | Düzeltildi |
| 9 | Karışık para birimi | Okunamaz tutarlar | USD'ye standardize |
| 10 | KPI'lar açıklamasız | Karar verilemez göstergeler | Künye + 2 gerçek formül |
