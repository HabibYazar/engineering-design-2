# Modül 11 — Risk ve Erken Uyarı Sistemi

PDF **Bölüm 11 – Risk and Early Warning System** karşılığı modül.

> ⚠️ **Kapsam düzeltmesi:** Bu modülün ilk sürümü (`early_warning.py`) tek tek
> öğrencileri GNO'suna göre "riskli" işaretliyordu. PDF'in 11. bölümü ise **üst yönetime
> giden kurum/program düzeyinde alarmlar** ister: bir programın doluluğu eşiğin altına
> düştüğünde, öğrenci kaybı arttığında, bütçe açığı oluştuğunda. Modül bu seviyede
> yeniden yazılmıştır; eski script `legacy_konsol_demo/` altına taşınmıştır.
> 

## Ana Sorumluluk

Modül 3 ve Modül 7'nin ürettiği göstergeleri yapılandırılabilir eşiklerle karşılaştırıp
üst yönetime önem derecesine göre sıralanmış alarmlar üretmek.

## Tasarım — Kural Motoru

Kurallar koda gömülü **değildir**, `config/rules.json` dosyasında tanımlıdır. Her kural
şunları taşır: eşik seti, kapsam (program/kurum/birim), veri kaynağı, PDF'teki karşılığı
ve önerilen aksiyon. Yeni bir alarm eklemek için JSON'a kayıt eklemek yeterlidir —
PDF'in "senior management shall be able to define additional scenarios" beklentisinin
karşılığı budur.

## Kural Kapsamı (15 kural)

**Çalışan kurallar (8):**

| Kural | PDF Koşulu |
| :--- | :--- |
| `program_occupancy_low` | Program enrollment rates fall below a critical threshold |
| `attrition_rate_increase` | Student attrition rates increase |
| `non_renewal_rate_increase` | Student attrition rates increase (kayıt yenilememe bileşeni) |
| `academic_performance_decline` | Academic performance indicators decline |
| `admission_score_below_national` | Talep kaybı öngörüsü (taban puan) |
| `demand_sharp_decline` | Doluluk trendi keskin düşüş |
| `sustainability_score_low` | Program düzeyi performans düşüşü (Modül 7 puanı) |
| `university_occupancy_low` | Kurum düzeyi doluluk düşüşü |

**Veri kaynağı bekleyen kurallar (7):** `budget_deficit`, `unit_budget_overrun`,
`additional_staff_need`, `capacity_insufficient`, `strategic_objective_delay`,
`accreditation_expiry`, `revenue_decline`.

Bunlar `implemented: false` olarak tanımlıdır; motor çalıştırmaz ama
`GET /api/early-warning/rules/pending` ile raporlar. Böylece PDF kapsamının tamamı
görünür kalır ve hangi alarmın hangi modüle bağlı olduğu belli olur.

## Önem Dereceleri

`kritik` → `yuksek` → `orta` → `dusuk`. Her kural kendi eşik setiyle derece belirler;
örneğin doluluk %50'nin altındaysa kritik, %65'in altındaysa yüksek, %80'in altındaysa
orta.

## Alarm İçeriği

Her alarm; kuralı, PDF karşılığını, önem derecesini, kapsamı, gözlenen değeri, aşılan
eşiği, insan tarafından okunabilir mesajı, **önerilen aksiyonu** ve veri kaynağını taşır.
PDF'in "risk level and recommended corrective actions" maddesinin karşılığıdır.

## Dosyalar

| Katman | Dosya |
| :--- | :--- |
| Yapılandırma | `config/rules.json` |
| Servis | `services/rule_engine.py` |
| Şema | `schemas/early_warning.py` |
| Router | `routers/early_warning.py` |

## Endpoint'ler


```
GET /api/early-warning/alerts?academic_year=2026-2027&severity=kritik&program_code=CENG-BSC
GET /api/early-warning/summary
GET /api/early-warning/rules

GET /api/early-warning/rules/pending
```

## Durum

Çalışıyor — 4 endpoint, demo verisinde 27 alarm üretiyor (11 kritik / 11 yüksek / 5 orta).
