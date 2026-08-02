# Modül 3, 7 ve 11 — Öğrenci Analitiği, Program Sürdürülebilirliği, Erken Uyarı

Stratejik Üniversite Yönetimi ve Karar Destek Sistemi projesinin **PDF Bölüm 3, 7 ve 11**
kapsamındaki modülleri. FastAPI + SQLAlchemy ile geliştirilmiştir; klasör tek başına
indirilse bile çalışır, ana backend'e bağımlılığı yoktur.

| Modül | PDF Bölümü | Kapsam | Durum |
| :--- | :--- | :--- | :--- |
| **Modül 3** | 3 — Strategic Education and Student Analytics | Öğrenci sayıları, doluluk, mezuniyet, öğrenci kaybı, burs/uluslararası oranlar, taban puan ve talep trendi | Çalışıyor |
| **Modül 7** | 7 — Academic Program Sustainability Analysis | 11 kriterli ağırlıklı sürdürülebilirlik puanı ve program kategorizasyonu | Çalışıyor |
| **Modül 11** | 11 — Risk and Early Warning System | Yapılandırılabilir kural motoru ile üst yönetime alarm üretimi | Çalışıyor |

---

## 🚀 Hızlı Başlangıç

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

Ardından tarayıcıdan:

- **http://127.0.0.1:8000/panel** — Modül 3 öğrenci analitiği arayüzü
- **http://127.0.0.1:8000/docs** — tüm modüllerin interaktif API dokümantasyonu

Alternatif çalıştırma yolları:

```powershell
# Paket kontrolu + veritabani hazirligi + sunucu (tek komut)
powershell -ExecutionPolicy Bypass -File .\run_demo.ps1

# Veriyi sifirlayarak
powershell -ExecutionPolicy Bypass -File .\run_demo.ps1 -Reset

# Otomatik yeniden yukleme ile
uvicorn main:app --reload
```

Uygulama ilk açılışta `demo.db` (SQLite) dosyasını oluşturur ve demo verisini yükler.
Veriyi sıfırlamak için `demo.db` dosyasını silip yeniden çalıştırmak yeterlidir.

---

## 🔗 Modüllerin Birbirine Bağlanışı

Üç modül zincirleme çalışır — demoda anlatılacak ana fikir budur:

```
Modül 3                    Modül 7                      Modül 11
Öğrenci verisinden   ──►   Göstergelerden          ──►  Puan ve göstergeleri
göstergeler üretir         sürdürülebilirlik            eşiklerle karşılaştırıp
(doluluk, kayıp,           puanı ve kategori            üst yönetime alarm
mezuniyet, taban puan)     hesaplar                     üretir
```

---

## 📡 Endpoint'ler (18 yol / 19 işlem)

| Grup | Endpoint |
| :--- | :--- |
| Arayüz | `GET /panel` — Modül 3 paneli (tek HTML dosyası) |
| Health | `GET /` · `GET /health` · `GET /demo-info` |
| **Modül 3** | `GET /api/student-analytics/academic-years` |
| | `GET /api/student-analytics/overview` — üniversite geneli (roll-up) |
| | `GET /api/student-analytics/programs` — program kırılımı |
| | `GET /api/student-analytics/programs/{program_code}` — tek program (drill-down) |
| | `GET /api/student-analytics/admission-scores` — taban puan / Ankara / Türkiye |
| | `GET /api/student-analytics/demand-trends` — 3 yıllık talep trendi |
| | `GET /api/student-analytics/performance-trends` — GNO trendi |
| **Modül 7** | `GET /api/program-sustainability/weights` — 11 kriter ve ağırlıkları |
| | `GET /api/program-sustainability/scores` — puan + kategori + veri tamlığı |
| | `POST /api/program-sustainability/scores` — diğer modüllerin verisiyle yeniden puanla |
| | `GET /api/program-sustainability/scores/{program_code}` |
| | `GET /api/program-sustainability/categories` — kategori dağılımı |
| **Modül 11** | `GET /api/early-warning/alerts` — alarmlar (`severity`, `program_code` filtreli) |
| | `GET /api/early-warning/summary` — alarm özeti |
| | `GET /api/early-warning/rules` — tanımlı tüm kurallar |
| | `GET /api/early-warning/rules/pending` — diğer modülleri bekleyen kurallar |

---

## 🎬 Demo Akışı

| Adım | Endpoint | Gösterilen |
| :--- | :--- | :--- |
| 0 | `GET /panel` | **Arayüz** — Modül 3 göstergeleri, doluluk ve taban puan grafikleri |
| 1 | `GET /health` | Servis ayakta |
| 2 | `GET /api/student-analytics/overview` | 3.124 öğrenci, %67 doluluk, %13 uluslararası, ort. mezuniyet 4,5 yıl |
| 3 | `GET /api/student-analytics/programs` | En düşük doluluk MSE %27,5 — en yüksek SWE %98,8 |
| 4 | `GET /api/student-analytics/admission-scores` | CE taban puanı Türkiye ortalamasının 75 puan altında |
| 5 | `GET /api/student-analytics/demand-trends` | CENG %92 → %38 keskin düşüş |
| 6 | `GET /api/program-sustainability/weights` | 11 kriter, 3'ü hesaplanan / 8'i dış girdi |
| 7 | `GET /api/program-sustainability/scores` | SWE 85,2 (büyüme potansiyeli) — MSE 28,2 (birleştirme adayı) |
| 8 | `GET /api/program-sustainability/categories` | Programların 4 kategoriye dağılımı |
| 9 | `POST /api/program-sustainability/scores` | Modül 4/5 verisi eklenince CENG kategorisi değişiyor |
| 10 | `GET /api/early-warning/alerts` | 27 alarm, önem sırasına göre |
| 11 | `GET /api/early-warning/summary` | En riskli programlar |
| 12 | `GET /api/early-warning/rules/pending` | Diğer modülleri bekleyen 7 kural |

**9. adımın POST gövdesi** (`/docs` üzerinden kopyalanıp çalıştırılabilir):

```json
{
  "academic_year": "2026-2027",
  "external_inputs": {
    "CENG-BSC": {
      "research_performance": 78,
      "academic_staff_quality": 82,
      "strategic_contribution": 85,
      "revenue_expenditure_balance": 55,
      "graduate_employability": 74
    }
  }
}
```

Sonuç: CENG-BSC puanı 34,68 → 55,31'e, veri tamlığı %40 → %87'ye çıkar ve kategori
"Yeniden yapılandırılması gereken program"dan **"Stratejik kurumsal destek gerektiren
program"**a döner. Modüller arası bağımlılığın somut gösterimi budur.

---

## 📁 Klasör Yapısı

```
begüm/
├── main.py                          # FastAPI uygulaması (bağımsız çalışır)
├── database.py                      # SQLite oturum/Base katmanı
├── seed_data.py                     # Demo veri üreteci (deterministik)
├── requirements.txt
├── module_03_ogrenci_analitigi/
│   ├── models/                      # Student, StudentAcademicRecord,
│   │                                #   ProgramEnrollmentSnapshot, AcademicProgram
│   ├── schemas/                     # Pydantic yanıt şemaları
│   ├── services/                    # Gösterge hesaplamaları
│   └── routers/                     # Endpoint tanımları
├── module_07_surdurulebilirlik/
│   ├── config/weights.json          # 11 kriterin ağırlıkları (yapılandırılabilir)
│   └── schemas/ services/ routers/
├── module_11_erken_uyari/
│   ├── config/rules.json            # Kural tanımları (yapılandırılabilir)
│   └── schemas/ services/ routers/
└── legacy_konsol_demo/              # 1. hafta konsol script'leri (arşiv)
```

---

## 🗄️ Demo Verisi Hakkında

Modül 13'ün `sample_data/` klasöründeki CSV'ler 3-4 satırdır ve içlerinde bilerek bozuk
değerler bulunur — bunlar içe aktarma doğrulayıcısını sınamak için yazılmış hatalı veri
örnekleridir, analiz verisi değildir. Trend ve alarm üretebilmek için `seed_data.py`
tutarlı bir veri seti üretir:

- **8 akademik program**, Mühendislik ve Mimarlık Fakültesi pilot birimi
- **3 akademik yıl** (2024-2025, 2025-2026, 2026-2027)
- **3.124 öğrenci**, 7 kohort (2020-2026), **11.694 dönemlik akademik kayıt**

Kontenjan, kayıt sayısı ve taban puanlar elle tanımlanmıştır. **Mezun, terk ve kayıt
yenilememe sayıları uydurulmaz** — üretilen öğrenci popülasyonundan sayılarak çıkarılır,
böylece snapshot tablosu ile öğrenci tablosu birbiriyle çelişmez. Üretim sabit tohumla
(`RANDOM_SEED`) deterministiktir: sayılar her çalıştırmada aynıdır.

---

## 🔌 Entegrasyon Notları

- Tablo ve kolon adları Modül 1'in tanımlarıyla birebir aynıdır; `AcademicProgram`
  modeli Modül 1'e aittir ve burada yalnızca bağımsız çalışabilmek için kopyalanmıştır.
- `Student` modeline Modül 3 tarafından **`status_change_year`** alanı eklenmiştir
  (öğrencinin ayrılış yılı). Yıl bazlı öğrenci kaybı ve kayıt yenilememe oranlarının
  doğru paydayla hesaplanabilmesi için gereklidir.
- Modül 7'nin 11 kriterinden 8'i Modül 4, 5 ve 8'den gelir. Bu kriterler eksikken
  **uydurulmaz**; ağırlıklar mevcut kriterler üzerinde yeniden normalize edilir ve
  sonuca `data_completeness_percent` alanı eklenir.
- Modül 11'in 15 kuralından 8'i çalışır durumdadır; kalan 7'si diğer modüllerin verisini
  bekler ve `implemented: false` olarak `rules.json` içinde tanımlıdır.
