# abu_kds.db — SQLite

`data_sources/` altındaki **bütün veri** tek bir SQLite veritabanına dönüştürüldü:
24 Excel + 9 CSV + 3 PDF kat planı + 2 metin belgesi. Hiçbir dosya dışarıda
kalmadı.

    59 tablo · 36.020 satır · 6,4 MB · 29 indeks

Kurulum gerekmiyor; SQLite Python'un standart kütüphanesinde var.

```python
import sqlite3
db = sqlite3.connect("data_sources/database/abu_kds.db")
db.execute("SELECT * FROM yks_ankara_programs_2026 LIMIT 5").fetchall()
```

---

## Veritabanı kendi kendini anlatıyor

Üç yardımcı tablo var:

| tablo | ne işe yarar |
|---|---|
| `_tables` | 59 tablonun kataloğu — hangi dosyanın hangi sayfasından geldiği, satır/sütun sayısı, dönüşüm notu |
| `_source_metadata` | Excel'lerin `Metadata` sayfalarındaki 117 kayıt — kaynak, uyarı, doğrulama notları |
| `_documents` | README ve özet metinleri tam içerikleriyle; `content` sütununda `LIKE` ile aranabilir |

"Bu sayı nereden geldi" sorusu veritabanının içinden cevaplanır:

```sql
SELECT source_file, source_sheet, note FROM _tables
WHERE table_name = 'yks_2025_ankara_programs';
```

---

## ⚠️ Altı yapı düz tablo değildi, dönüştürüldü

Bunlar olduğu gibi aktarılsa kullanılamaz veri çıkardı.

**1. Öğrenci Sayıları `.xls` (5 dosya → 1 tablo)**
Başlık iki katlıydı: bir satır grup adı (`Okuyan Lisans`), altındaki satır
cinsiyet kırılımı (`E`/`K`/`T`). Birleştirilip `lisans_e`, `lisans_k`,
`lisans_t` hâline getirildi.

Daha önemlisi: **portal çıktısında yıl sütunu yok.** Yıl dosya adından türetildi
(`Öğrenci Sayıları.xls` = 2025-2026, `(1)` = 2024-2025, `(2)` = 2023-2024,
`(3)` = 2022-2023). `(4)` atlandı — `(3)` ile bayt bayt aynı dosya.

Doğrulama: ABÜ 2025-2026 → **3.626**, KİDR raporundaki resmî rakamla aynı.
Seri de tutarlı: 1.393 → 2.300 → 3.135 → 3.626.

**2. Kat planı Excel'i → `classrooms` (97 derslik)**
Kaynakta katlar **yan yana bloklar** hâlindeydi (KAT 0 → c1, KAT 1 → c7,
KAT 2 → c13). Düz tabloya çevrildi, kat bilgisi `floor` sütunu oldu.

**3. 72 derslik sayfası → `room_schedule` (1.535 kayıt)**
Her derslik ayrı sayfada haftalık ızgaraydı (saat × gün). Tek uzun tabloya
açıldı: `room`, `time_slot`, `day`, `booking`.

Başlık satırı her sayfada aynı yerde değildi — bazılarında 2., bazılarında
3. satırda. Sabit satır sayılsaydı `C 056` sessizce düşerdi (39 ders kaydı).

**15 dersliğin hiç dersi yok**, bu yüzden tabloda görünmezler; hangileri olduğu
`_tables.note` alanında yazılı. Boş slotlar kaynakta `0` yazıyordu, kayda
alınmadı — **bir slotun yokluğu boş olduğu anlamına gelir.**

**4. `DERS_PLANI` → `course_schedule` (1.303 kayıt)**
Odalar sütundu (21 oda × 1.285 satır). Uzun tabloya açıldı; `day`, `period`,
`time_slot` ve birim bilgisi korundu. Dört sütunun adı da `Online`'dı; ayırt
edilebilsin diye `Online 2`, `Online 3`, `Online 4` olarak numaralandı.

**5. PDF kat planları → `floor_plan_spaces` (94 mekân)**
Üç PDF mimari çizimdir, tablo değil. Çizimden **mekân etiketi** (SINIF,
KÜTÜPHANE, AMFİ-5, TERAS…) ve **m² alanı** çıkarıldı.

Eşleştirme metin sırasına göre **yapılmadı** — PDF'te metin çıkarma sırası
güvenilmez. Etiket ile alanı **koordinata göre** eşleştirildi (alan, etiketin
hemen altında duruyor). 94 alanın **93'ü** bir etiketle eşleşti.

Tolerans sabit olamadı: kat 0 sayfa biriminde (~1191×842), kat 1-2 ise yaklaşık
7 kat büyük bir dönüşüm ölçeğinde geliyor. Eşik her dosyanın kendi koordinat
yayılımından türetiliyor. Sabit tolerans kullanılsaydı kat 1 ve 2'de 53 mekân
etiketsiz kalırdı.

**Çizimde oda KODU yok**, bu yüzden `floor_plan_spaces` ile `classrooms`
birleştirilemez. `x`/`y` sütunları çizimdeki konumdur.


**6. `DERS_PLANI` içinde ders olmayan satırlar → `room_utilization`**
Kaynak sayfada bloklar alt alta tekrarlandığı için iki tür satır ders kaydı gibi
içeri girmişti: **40 tekrar eden başlık satırı** (`day = 'Gün'`) ve **44 derslik
kullanım oranı** satırı. Başlıklar silindi; kullanım oranları kendi tablosuna
taşındı — 21 odanın doluluk oranı, atılacak değil işe yarar veri.

    C 232 %97,8 · C 220 %93,3 · AMFİ1 %88,9 · C 233 %86,7

`course_schedule` böylece 1.303 → **1.219 gerçek ders kaydına** indi. Kaynakta
oda başına birden çok oran var ve neye göre ayrıldıkları yazmıyor; `block`
sütunu ayırt edilebilsin diye korundu.

### İki program tablosu aynı veri değil

`room_schedule` 57 odayı, `course_schedule` 21 odayı kapsıyor ve
`course_schedule` kayıtlarının yalnızca **%25'i** diğerinde karşılık buluyor.
İki farklı kaynak gösterimi; ikisi de korundu. `room_schedule` daha geniş,
`course_schedule` daha ayrıntılı (gün + ders saati numarası).

---

## Doluluk: beş yıl, tek tanım

Doluluk oranı iki farklı ana bakabilir ve bu ikisi karıştırılırsa grafik yalan
söyler.

1. **Ana yerleştirme sonrası** — yerleşen *ve kayıt yaptıran* öğrenci
2. **Ek yerleştirme dahil** — nihai durum, her zaman daha yüksek

Projedeki eski tablolar 2021-2024 için 2. tanımı kullanıyordu. 2025'in nihai
yerleşen sayısı ise hiçbir açık kaynakta yok — YÖK Atlas 2026'yı yayımlayınca
2025 görünümünü kaldırdı ve servis geçmiş yıllar için yalnızca kontenjan taşıyor.

**Aynı yıl, iki tanım.** 2023 verisinde her ikisi de hesaplanabiliyor:

| 2023 | doluluk |
|---|---|
| Nihai (ek yerleştirme dahil) | %99,4 |
| Kayıt yaptıran (ek öncesi) | %90,5 |
| fark | **8,9 puan** |

Tek bir öğrenci değişmiyor; sadece hangi ana bakıldığı değişiyor.

### Yapılan düzeltme

ÖSYM'nin **2021, 2022, 2023, 2024 ve 2025** ek yerleştirme kılavuzları indirildi
ve hepsi aynı yöntemle işlendi:

    yerlesen_kayit_yaptiran = kontenjan − ek_yerlestirme_bos_kontenjani

Beş kılavuzdan **88.123 satır** okundu, **17'si** ayrışamadı (%0,02).

### Sonuç: düşüş sahteymiş

| yıl | kayıt yaptıran (tutarlı) | nihai (eski, tutarsız) |
|---|---|---|
| 2021 | **%88,6** | %93,2 |
| 2022 | **%93,0** | %99,4 |
| 2023 | **%90,5** | %99,4 |
| 2024 | **%88,1** | %97,4 |
| 2025 | **%88,5** | — |

Eski tablolarla çizilseydi 2024'ten 2025'e **%97,4 → %88,5**, yani 9 puanlık bir
çöküş görünürdü. Tutarlı seride **%88,1 → %88,5** — düşüş değil, hafif artış.
O çöküşün tamamı tanım farkıydı.

### Doğrulama

2023, birbirinden bağımsız iki yoldan hesaplandı:

| yol | sonuç |
|---|---|
| ÖSYM PDF'inden ayrıştırılan | %90,5 |
| Veri setindeki `ekkontenjan2023` sütunu | %91,0 |
| fark | 0,5 puan |

### Kullanım

- `occupancy_registered_pct` — **beş yılda da aynı şeyi ölçer**, grafikte bunu kullanın
- `occupancy_final_pct` — ek yerleştirme dahil; yalnızca 2021-2024'te var, 2025 için kaynak yok
- İkisini aynı çizgide karıştırmayın
- `in_ek_guide = 0` → program ek kılavuzda yok, yani ana yerleştirmede kontenjanı
  tamamen dolmuş

### ABÜ'de gerçek bir düşüş var

Ankara geneli yatay seyrederken ABÜ'nün doluluğu gerçekten geriliyor:

    2021 %51,7 → 2022 %91,8 → 2023 %83,4 → 2024 %67,6 → 2025 %55,1

Bu, yukarıdakinin aksine tanım kaynaklı değil — beş yıl da aynı yöntemle
hesaplandı. Kontenjan aynı dönemde 437'den 1.164'e çıkmış; yani kontenjan
büyürken doluluk düşüyor. `program_count` sütunu yıllar arasında farklı
kaynaklardan geldiği için karşılaştırmada **kontenjan toplamını** kullanın.

---

## Dönüşüm kuralları

- **Sütun adları** ASCII snake_case'e çevrildi (`Üniversite Adı` →
  `universite_adi`). Veritabanında Türkçe karakterli sütun adı yok.
- **Tipler** içerikten çıkarıldı: tam sayı → `INTEGER`, ondalık → `REAL`,
  gerisi → `TEXT`. Türkçe sayı biçimi (`1.234,56`) da tanınıyor.
- **Boş hücre `NULL`.** Sıfır yazılmadı — sıfır ile "veri yok" karışmıyor.
- Tamamen boş satırlar atıldı. Başlığı olup verisi olmayan sütunlar şema
  bilgisi olarak korundu.
- CSV'ler BOM'lu (`utf-8-sig`) okundu, ayırıcı otomatik bulundu.
- 9 dosyanın `Metadata` sayfası ayrı tablo açmak yerine `_source_metadata`
  içinde birleştirildi.
- Başlığı 1. satırda olmayan sayfalarda doğru satır elle belirtildi
  (`ankara_ozel_universiteler…` → 4. satır).

### Değiştirilen tek değer

`_documents` içindeki özet metninde, dosyanın üretildiği bilgisayara ait yerel
bir klasör yolu yazılıydı. Veriyle ilgisi olmadığı için
`[yerel yol kaldırıldı]` ile değiştirildi. Kaynak `.txt` dosyasına
dokunulmadı, orijinal hâliyle duruyor.

Bunun dışında hiçbir veri değiştirilmedi.

---

## Tablolar

### yks — 18 tablo, 21.946 satır
| tablo | satır | sütun |
|---|---|---|
| `occupancy_by_year` | 7928 | 13 |
| `yks_ankara_history_2023_2025` | 4613 | 10 |
| `yks_ankara_programs_2026` | 1794 | 24 |
| `yks_ankara_2022_2024_raw` | 1768 | 72 |
| `yks_2025_ankara_programs` | 1614 | 20 |
| `yks_ankara_2022` | 1530 | 31 |
| `yks_ankara_2021` | 1406 | 31 |
| `yks_2025_by_department` | 322 | 9 |
| `yks_abu_validation` | 316 | 6 |
| `yks_abu_4year` | 212 | 14 |
| `yks_abu_history_2023_2025` | 118 | 8 |
| `yks_abu_programs_2026` | 60 | 21 |
| `yks_abu_program_summary` | 53 | 8 |
| `yks_2025_abu_programs` | 40 | 20 |
| `yks_ankara_university_summary_2026` | 23 | 12 |
| `yks_2025_university_summary` | 22 | 7 |
| `universities_profile` | 22 | 32 |
| `occupancy_by_year_university` | 105 | 9 |

### finance — 8 tablo, 3.733 satır
| tablo | satır | sütun |
|---|---|---|
| `fees_ankara_programs_2026` | 1794 | 15 |
| `fees_estimated_revenue_derived` | 1077 | 8 |
| `fees_private_universities` | 708 | 9 |
| `fees_abu_2025_2026` | 37 | 8 |
| `fees_abu_2025_2026_by_language` | 37 | 6 |
| `fees_abu_2026_2027` | 32 | 8 |
| `fees_private_universities_summary` | 25 | 11 |
| `fees_university_summary_2026` | 23 | 10 |

### infrastructure — 5 tablo, 2.989 satır
| tablo | satır | sütun |
|---|---|---|
| `room_schedule` | 1535 | 4 |
| `course_schedule` | 1219 | 7 |
| `classrooms` | 97 | 6 |
| `floor_plan_spaces` | 94 | 5 |
| `room_utilization` | 44 | 4 |

### students — 8 tablo, 2.529 satır
| tablo | satır | sütun |
|---|---|---|
| `yok_departments` | 1236 | 7 |
| `yok_faculties` | 818 | 6 |
| `students_yok_portal` | 246 | 20 |
| `students_by_university_2020_2026` | 126 | 9 |
| `students_detail_2024_2026` | 77 | 20 |
| `foreign_students` | 15 | 5 |
| `students_abu_timeseries` | 6 | 9 |
| `foreign_students_faculty_summary` | 5 | 3 |

### academic_staff — 5 tablo, 2.075 satır
| tablo | satır | sütun |
|---|---|---|
| `academic_staff_by_program_2026` | 1794 | 17 |
| `academic_staff_by_university_2020_2026` | 126 | 11 |
| `students_per_staff_2020_2026` | 126 | 6 |
| `academic_staff_university_summary_2026` | 23 | 11 |
| `academic_staff_abu_timeseries` | 6 | 8 |

### department_matching — 5 tablo, 1.246 satır
| tablo | satır | sütun |
|---|---|---|
| `matching_similar_departments` | 765 | 12 |
| `matching_same_departments` | 373 | 14 |
| `matching_abu_programs` | 60 | 12 |
| `matching_abu_departments` | 26 | 4 |
| `matching_universities` | 22 | 6 |

### merge_reports — 5 tablo, 241 satır
| tablo | satır | sütun |
|---|---|---|
| `merge_ambiguous_records` | 151 | 8 |
| `merge_new_fields` | 43 | 6 |
| `merge_inventory` | 42 | 5 |
| `merge_summary` | 3 | 6 |
| `merge_remaining_ambiguous` | 2 | 9 |

### curriculum · strategic · docs
| tablo | satır | sütun |
|---|---|---|
| `curriculum_courses` | 1205 | 6 |
| `strategic_goals` | 37 | 11 |
| `strategic_report_facts` | 13 | 6 |
| `strategic_source_conflicts` | 4 | 8 |
| `_documents` | 2 | 5 |

---

## İndeksler ve örnek sorgular

Sık kullanılan birleştirme anahtarlarına 26 indeks kuruldu: `university_name`,
`program_code`, `academic_year`, `room`, `universite`, `program_kodu`,
`room_code`, `isim`, `floor`, `id`.

**Üniversite karşılaştırması (üç tabloyu birleştirir):**

```sql
SELECT y.university_name,
       COUNT(DISTINCT y.program_code) AS program,
       SUM(y.quota)                   AS kontenjan,
       s.toplam                       AS ogrenci,
       k.toplam_ogretim_elemani       AS kadro
FROM yks_ankara_programs_2026 y
LEFT JOIN students_by_university_2020_2026 s
       ON s.university_name = y.university_name AND s.academic_year = '2025-2026'
LEFT JOIN academic_staff_by_university_2020_2026 k
       ON k.university_name = y.university_name AND k.academic_year = '2025-2026'
GROUP BY y.university_name
ORDER BY kontenjan DESC;
```

ABÜ satırı: 60 program · 1.202 kontenjan · 3.626 öğrenci · 134 öğretim elemanı.

**Kat başına derslik alanı:**

```sql
SELECT floor, COUNT(*) AS mekan, ROUND(SUM(area_m2),1) AS toplam_m2
FROM floor_plan_spaces WHERE space_label LIKE '%SINIF%' GROUP BY floor;
```

**Bir dersliğin haftalık doluluğu:**

```sql
SELECT day, time_slot, booking FROM room_schedule
WHERE room = 'C 007' ORDER BY day, time_slot;
```

---

## Doğrulama

Dönüşümden sonra çalıştırılan kontroller:

| kontrol | sonuç |
|---|---|
| Katalogdaki satır sayıları gerçek tablolarla tutuyor mu | **59/59 tuttu** |
| Boş kalan tablo | yok |
| ASCII olmayan sütun adı | yok |
| Sayısal sütunlar gerçekten sayısal mı (`typeof`) | tümü `integer`/`real` |
| ABÜ 2025-2026 öğrenci sayısı | 3.626 — resmî rakamla aynı |
| Çapraz tablo birleştirmesi | çalışıyor, bilinen değerleri veriyor |
| PDF mekân eşleşmesi | 93/94 |
| `_documents` içinde arama | çalışıyor |

---

## Bilinmesi gerekenler

- **`universities_profile` üniversite künyesidir** — akademik verinin yanında
  `website`, `eposta`, `telefon`, `fax`, `adres`, `rektor` sütunları da taşır.

- **`fees_estimated_revenue_derived` türetilmiş veridir**, ölçüm değil.

- **Doluluk için `occupancy_by_year` kullanın.** Diğer tablolardaki yıllık
  doluluk oranları aynı tanımda değildir; bu tablo beş yılı da aynı yöntemle
  hesaplar. Ayrıntı aşağıda.

- **`yks_ankara_2022_2024_raw`** üçüncü şahıs veri setinden küçültülmüş ham
  dosyadır (72 sütun) ve diğer `yks_*` tablolarıyla örtüşen veri taşır.

- **`strategic_source_conflicts`** kaynaklar arasındaki 4 çelişkiyi listeler;
  gizlenmedi, tablo olarak duruyor.

- `.gitignore` içinde `*.db` kuralı yok (yalnızca `Thumbs.db`), veritabanı
  depoya dahil olur.

- **Kaynak dosyalar silinmedi.** Veritabanı onların yanında duruyor; Excel,
  CSV ve PDF'ler hâlâ `data_sources/` altında.

## Ne dışarıda kaldı

Hiçbir şey. `data_sources/` altındaki 41 veri dosyasının tamamı işlendi —
24 Excel, 9 CSV, 3 PDF, 2 metin belgesi, 3 README/özet.

PDF'ler tabloya çevrilirken yalnızca **metin katmanı** kullanıldı; çizimin
kendisi (duvarlar, ölçüler, semboller) veritabanına alınamaz. Orijinal PDF'ler
`infrastructure/` altında duruyor.
