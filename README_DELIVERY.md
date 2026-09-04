# ABÜ KDS — Karar Destek Sistemi (Teslim Paketi)

Ankara Bilim Üniversitesi için geliştirilen web tabanlı karar destek
sistemi. Bu klasör projenin **temiz, kendi kendine yeten** kopyasıdır:
çalışmak için başka hiçbir klasöre ihtiyaç duymaz.

## Klasör yapısı

```
EngineeringDesign2_TESLIM_2026-09-02/
├── project/              ← çalıştırılabilir uygulama
│   ├── backend/          FastAPI + SQLAlchemy (Python 3.10+)
│   │   └── university_management.db    ← AKTİF VERİTABANI
│   ├── frontend/         Vanilla JS arayüz (derleme adımı yok)
│   ├── data/             uygulamanın ÇALIŞIRKEN okuduğu veriler
│   ├── shared_demo_data/ örnek/demo kayıtları
│   └── run_project.ps1   tek komutla başlatma
├── data_sources/         ham ve yetkili KAYNAK arşivi (uygulama okumaz)
├── docs/                 veri künyesi ve proje yapısı
└── README_DELIVERY.md    bu dosya
```

## Çalıştırma

PowerShell'de:

```powershell
cd project
.\run_project.ps1
```

Betik sanal ortamı kurar, bağımlılıkları yükler ve sunucuyu başlatır.
Tarayıcı birkaç saniye içinde kendiliğinden açılır.

- **Adres:** http://127.0.0.1:8000
- **API dokümanı:** http://127.0.0.1:8000/docs
- **Sağlık kontrolü:** http://127.0.0.1:8000/health
- **Port değiştirmek için:** `.\run_project.ps1 -Port 8080`

Bağımlılıklar zaten kuruluysa: `.\run_project.ps1 -SkipInstall`

### Bağımlılıklar

Python 3.10 veya üstü gerekir. Paketler `project/backend/requirements.txt`
içinde tanımlıdır; `run_project.ps1` bunları kendiliğinden kurar. Elle
kurmak isterseniz:

```powershell
cd project\backend
python -m pip install -r requirements.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

## Veritabanı

Aktif veritabanı: **`project/backend/university_management.db`**

Gerçek kurum verisiyle **dolu olarak** teslim edilir — 2020–2026 YKS
kontenjan/yerleşen verileri, akademik kadro, öğrenci sayıları, eğitim
ücretleri, müfredat ve derslik verileri. Ayrıca yüklemeye gerek yoktur;
`run_project.ps1` varsayılan olarak veri yüklemesi **yapmaz**.

## Yapay Zeka Kokpiti (isteğe bağlı)

Asistan Google Gemini kullanır ve **yalnızca bu projenin kendi
veritabanlarını** okur; internette arama yapmaz.

### Veri temelli (database-grounded) çalışma

Kaynak veriler Excel, CSV ve PDF gibi çeşitli biçimlerde geliyordu.
Bunların tamamı tek bir merkezî SQLite veritabanında birleştirildi:

    project/data/abu_kds/abu_kds.db — 62 tablo · 36.020 satır

Asistanın kurumsal soruları bu dosyadan cevaplanır ve akış şudur:

1. Kullanıcının sorusu hangi veri ailesini gerektiriyor, belirlenir
   (öğrenci, akademik kadro, YKS/taban puan, finans, altyapı, müfredat,
   stratejik hedefler).
2. Backend ilgili tabloyu **salt okunur** sorgular. SQL'i backend kurar;
   modele serbest SQL yetkisi verilmez.
3. Yalnızca soruyla ilgili, küçük ve yapılandırılmış sonuç modele
   gönderilir — veritabanının tamamı asla istemciye ya da modele
   basılmaz.
4. Gemini bu gerçek veriye dayanarak karar destek cevabını üretir.
5. Kurumsal bir soruda gerçek veri bulunamazsa cevap **uydurulmaz**;
   sistem neyin eksik olduğunu söyler.

Veritabanı hiçbir koşulda değiştirilmez: bağlantı `mode=ro` ile açılır,
migration/seed çalıştırılmaz. Kaynak Excel/CSV/PDF dosyaları
`data_sources/` altında olduğu gibi durur; veritabanı onların yerine
değil, yanına eklenmiştir.

Veritabanının kendi belgesi `project/data/abu_kds/README.md`
dosyasındadır: 59 tablonun kataloğu, dönüşüm kuralları ve doğrulama
sonuçları orada.

### Soru anlama ve cevap güvenceleri

Asistan katmanı, sessizce yanlış sayı üretmeyi *yapısal olarak*
imkânsız kılmak üzere kuruldu. Öne çıkan davranışlar:

| Davranış | Nerede |
|---|---|
| Türkçe varlık çözümleme — ek toleransı, benzer adları karıştırmama | `entity_katalogu.py` |
| "tüm / hepsi / genel / üniversitelere göre" → tek kuruma kilitlenmez | `kapsam.py` |
| Ölçü belirtilmemiş sorularda ilgili TÜM ölçüleri ayrı ayrı hesaplama | `coklu_metrik.py` |
| Kurumsal kişi adı uydurmayı önleme; uydurulursa yalnız adı temizleme | `kisi_adi.py` |
| Grafik verisini mevcut sorgu sonucundan türetme (yeni sorgu yok) | `grafik_uret.py` |
| "line yap / pie yap / donut yap" — modele gitmeden tür dönüştürme | `grafik_donustur.py` |
| Grafik olmayan ama tablo içeren cevabı grafiğe çevirme | `tablo_oku.py` |

Bu davranışların hepsi:

* **Deterministik ve hızlıdır** — grafik türü değiştirme, "tüm/hepsi"
  çözümlemesi ve kişi adı denetimi için ikinci bir model çağrısı
  yapılmaz; ölçülen maliyet milisaniye düzeyindedir.
* **Cevabı asla tümden reddetmez** — sorunlu parça temizlenir, cevabın
  geri kalanı kullanıcıya gider.
* **Sağlayıcı arızasına dayanıklıdır** — kota, zaman aşımı ve boş cevap
  durumlarında eldeki veriden deterministik cevap üretilir. Yerel
  model YOKTUR ve kullanılmaz.
* **Grafik kodunu kullanıcıya göstermez** — modelin ürettiği
  `render_chart` / JSON blokları görünür metinden ayıklanır.

Desteklenen grafik türleri: `line`, `bar`, `hbar` (yatay sütun),
`pie` (pasta), `donut` (halka), `scatter`, `grouped`, `stacked`.
Kullanıcı "çizgi grafik yap", "pasta yap", "yatay bar" gibi doğal
ifadelerle tür değiştirebilir; veri değişmez, yalnızca görselleştirme
değişir.

Anahtar tanımlamak için:

```powershell
cd project\backend
copy .env.example .env
```

Ardından `.env` içindeki `GEMINI_API_KEY=YOUR_KEY_HERE` satırına kendi
anahtarınızı yazın (https://aistudio.google.com/apikey).

**Anahtar olmadan da proje tam olarak çalışır** — yalnızca Yapay Zeka
Kokpiti ekranı "sağlayıcı yapılandırılmadı" durumunu gösterir; diğer
bütün ekranlar normal çalışır.

> Güvenlik: Bu pakette gerçek bir API anahtarı **yoktur**. Yalnızca
> `.env.example` şablonu bulunur.

## İki veri klasörü — karıştırmayın

| | `project/data/` | `data_sources/` |
|---|---|---|
| Rol | Uygulamanın çalışırken okuduğu veri | Ham / yetkili kaynak arşivi |
| Kim okur | Backend servisleri | İnsan; denetim ve tekrar üretim |
| Örnek | `bolum_eslesme/bolum_eslesme.csv` | `department_matching/Ankara_Bilim_Ayni_Benzer_Bolumler_TAM.xlsx` |
| Silinirse | Uygulama bozulur | Uygulama çalışmaya devam eder |

Aynı/benzer bölüm eşleştirmesinde bu ayrım şöyle işler: **XLSX yetkili
kaynaktır** (hangi bölümlerin karşılaştırılabilir olduğunu YÖK'ün kendi
sınıflandırması belirler), **CSV ise ondan türetilmiş çalışma zamanı arama
tablosudur**. Kaynak değişirse CSV `project/backend/build_bolum_eslesme.py`
ile yeniden üretilir.

Dosya listesi ve rolleri: `docs/DATA_MANIFEST.csv`
Kod yerleşimi: `docs/PROJECT_STRUCTURE.md`

## Teslim doğrulaması

Bu paket teslim edilmeden önce şunlar çalıştırıldı:

```
project/backend> python -m pytest tests -q
1455 passed, 6 failed
```

Kalan 6 hata, bu teslim döngüsünden **önce** de var olan ve iş
mantığıyla ilgili bilinen açık kalemlerdir (akademik personel
performans skoru, hiyerarşi kapsamı, program eşleştirme modu, rakip
ücret kapsamı, YÖK Atlas 2025 penceresi). Yeni bir kırılma eklenmedi.

Pakette bulunmayanlar: gerçek API anahtarı, `__pycache__`, `.pyc`,
`.pytest_cache`, yedek (`.bak`) dosyaları, geliştirme arşivleri.
