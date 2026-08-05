# Yönetim Panosu Yeniden Tasarımı — Uygulama Raporu

Önceki turda diğer ekranlar sadeleştirilmişti; pano hâlâ organizasyon
hiyerarşisi olmadan bütün fakülte, bölüm ve program verisini aynı anda
gösteriyordu. Bu tur panoyu bir **yönetici özetine** dönüştürdü.

Temel kural: pano ilk açıldığında **yalnızca üniversite geneli** gösterilir.
Ayrıntı, kullanıcı isteyince ve ancak istediği seviyede yüklenir.

---

## 1. Değiştirilen dosyalar

### Frontend

| Dosya | Durum | Değişiklik |
|---|---|---|
| `frontend/assets/views-dashboard.js` | **yeni (740 satır)** | Pano sıfırdan yazıldı: kapsam durumu (`scope`), hiyerarşik seçici, breadcrumb, 6 özet kartı, kurumsal eğilim, önemli gelişmeler, gelir-gider özeti, gruplu riskler, fakülte ve bölüm karşılaştırması. |
| `frontend/assets/views-overview.js` | 400 → 155 satır | Pano kodu çıkarıldı; dosyada yalnızca Akıllı Asistan ekranı kaldı. |
| `frontend/assets/app.js` | güncellendi | Menü açılır gruplara çevrildi (`openNavGroup`, `navGroupOf`); emoji ikon seti tek renkli geometrik işaretlerle değiştirildi; menü grupları yeniden düzenlendi. |
| `frontend/assets/api.js` | güncellendi | `ref` katmanı artık fakülte/bölüm/program adlarını Türkçeye çeviriyor (`displayNames`, `_translate`, `orgName`). Çeviri tek yerde yapıldığı için bütün ekranlar yararlanıyor. |
| `frontend/assets/integration.css` | +230 satır | Menü akordeonu, kapsam çubuğu, breadcrumb, tıklanabilir kartlar, gelişme listeleri, risk özeti tablosu, tek satırlık bölüm karşılaştırması. |
| `frontend/index.html` | güncellendi | Yeni betik kaydedildi, önbellek sürümü `?v=9`. |
| `tests_ui/test_frontend.js` | +30 kontrol | Ağ isteği casusu ve 15 kabul kriterinin doğrulaması. |

### Backend

Hesaplama formüllerine ve eşiklere **dokunulmadı**. Yapılan değişiklikler
yalnızca etiket, ad ve gruplama düzeyindedir.

| Dosya | Değişiklik |
|---|---|
| `app/config/display_names.json` | **yeni** — 4 fakülte, 12 bölüm ve 14 programın Türkçe adları. Veritabanındaki İngilizce adlar modüller arası kod eşleşmesini taşıdığı için değiştirilmedi; görünen ad ayrı tutuldu. |
| `app/routers/reference.py` | **yeni** — `GET /api/reference/display-names`. |
| `app/config/early_warning_rules.json` | 15 kuralın adı ve önerilen aksiyonu düzgün Türkçeye çevrildi; her kurala `risk_category` eklendi. Eşikler ve `implemented` bayrakları aynı. |
| `app/services/early_warning_rule_engine.py` | `_alert()` artık birim adını ve mesaj metnini Türkçeleştiriyor; alarma `risk_category` ekleniyor. Kural mantığı değişmedi. |
| `app/schemas/early_warning.py` | `risk_category` alanı eklendi. |
| `main.py` | Referans router'ı bağlandı. |

---

## 2. Panonun önceki ve yeni yapısı

### Önce

```
Yönetim Panosu
├── 8 gösterge kartı (tıklanamaz)
├── Doluluk/mezuniyet grafiği     ← legend İKİ KEZ çiziliyordu
├── KPI karnesi + zayıf boyutlar
├── Bölüm bazlı gelir ve gider    ← her bölüm İKİ satır (gelir, gider)
├── Kritik riskler                ← 6 uyarı tek tek, kategori yok
└── Kırılım tablosu               ← BÜTÜN fakülteler + BÜTÜN bölümler
```

Sayfa açılışında çağrılan uç noktalar: öğrenci özeti, mali özet, kapasite,
KPI karnesi, personel, iki trend, uyarılar, **bölüm bütçeleri**, fakülte
listesi, **bölüm listesi**, **bölüm bazlı öğrenci analitiği** — 12 istek,
bunların 3'ü ayrıntı seviyesinde.

### Sonra

```
Yönetim Panosu · Üniversite Geneli
├── İnceleme kapsamı: [Üniversite Geneli ▼]      ← tek alan
├── Breadcrumb: Üniversite Geneli
├── 6 özet kartı (hepsi tıklanabilir)
├── Kurumsal eğilim (tek grafik, tek legend)
├── En önemli gelişmeler (en fazla 3 olumlu + 3 dikkat)
├── Gelir ve gider özeti (4 rakam + 5 yıllık çizgi)
└── Öncelikli riskler (kategori özeti + en kritik 5 + "Tüm 21 riski incele")
   └── Fakülte karşılaştırması (satıra tıkla → kapsam o fakülteye geçer)
```

Sayfa açılışında çağrılan uç noktalar: öğrenci özeti, personel özeti, mali
özet, başarı özeti, uyarılar, iki trend, mali eğilim, fakülte analitiği —
hepsi **kurum geneli**. Bölüm bütçesi ve program skoru uç noktaları
çağrılmaz.

---

## 3. Oluşturulan hiyerarşi

```
Üniversite Geneli
   └── Fakülte            (isteğe bağlı)
         └── Bölüm        (isteğe bağlı)
               └── Program (isteğe bağlı)
```

Uygulanan kurallar:

- Pano ilk açıldığında hiçbir fakülte, bölüm veya program seçili değildir.
- **Bölüm alanı fakülte seçilmeden ekrana çizilmez.** Pasif bir alan bile
  "burada bir şey seçebilirim" izlenimi verdiği için gizlenir, kilitlenmez.
- **Program alanı bölüm seçilmeden çizilmez.**
- Alt seviye seçmek zorunlu değildir; kullanıcı yalnızca fakülte seçerek
  fakülte genelini görebilir.
- Üst seviye değişirse alt seçimler sıfırlanır.
- **"Üniversite Geneline Dön"** düğmesi yalnızca ayrıntıdayken görünür.
- Seçilen kapsam hem sayfa alt başlığında hem breadcrumb'da yazar; breadcrumb'ın
  üst seviyeleri tıklanabilir.

Kapsam değiştiğinde pano gövdesi yeniden çizilir ve **yalnızca o seviyenin
verisi** çekilir. Fakülte seçilince bölüm karşılaştırması, bölüm seçilince
program alanı yüklenir.

---

## 4. Kaldırılan kalabalık alanlar

| Kaldırılan / taşınan | Yerine gelen |
|---|---|
| Bütün bölümlerin gelir-gider çubukları (12 bölüm × 2 satır = 24 çubuk) | Üniversite genelinde **Gelir ve gider özeti**: toplam gelir, toplam gider, net bütçe, geçen yıla göre değişim + 5 yıllık çizgi grafiği |
| Fakülte → bölüm kırılım tablosu (bütün fakülteler, açılınca bütün bölümler) | **Fakülte karşılaştırması** — 4 satır; bir fakülteye tıklayınca pano o kapsama geçer |
| 21 uyarının tek tek listelenmesi | **Kategori özeti** (Stratejik 10, Öğrenci talebi 7, Akademik 4) + en kritik 5 kayıt + "Tüm 21 riski incele →" |
| 8 gösterge kartı | 6 kart, hepsi ilgili ayrıntı sayfasına bağlı |
| KPI karnesi halkaları + zayıf boyut listesi | Panodan çıkarıldı; Performans Göstergeleri sayfasında zaten üç sekmeli olarak var |
| Grafik altındaki elle yazılmış ikinci legend | Tek legend (grafik çizicinin kendi ürettiği) |

Bölüm bazlı karşılaştırma **silinmedi**, kapsama bağlandı: fakülte
seçildiğinde "Fakülte içindeki bölümlerin mali karşılaştırması" olarak açılır,
ilk 5 bölüm görünür, kalanı "Tüm bölümleri göster" bölümündedir.

---

## 5. Düzeltilen görsel hatalar

| Hata | Düzeltme |
|---|---|
| Doluluk ve mezuniyet legend'ı iki kez görünüyordu | `lineChart` legend'ı zaten çiziyordu; elle eklenen ikinci legend kaldırıldı. Test bunu ayrıca doğruluyor. |
| Bölüm adları kesiliyordu | `.unit-name` iki satıra sarar (`overflow-wrap: anywhere`), kısaltma yok; satırda ayrıca tam ad tooltip'i var. |
| Gelir ve gider aynı bölüm için ayrı satırlardaydı | Tek satırda, üst üste iki çubuk + "Gelir / Gider / Net" rakamları. |
| İngilizce program isimleri risk listesinde görünüyordu | Ad çevirisi alarm üretiminin tek çıkış noktasında (`_alert`) yapılıyor; hem `scope_name` hem mesaj metni Türkçeleşiyor. |
| Ekran dikey olarak aşırı uzuyordu | Sabit yükseklik bütçesi: risk listesi 5, bölüm listesi 5, gelişmeler 3+3 satır; kalanı açılır bölümde. |
| Aynı önem seviyesindeki çok sayıda uyarı tek tek gösteriliyordu | Kategori özeti + yalnızca en kritik 5 kayıt. |
| Kartlar arasında bilgi önceliği yoktu | Kart sayısı 8'den 6'ya indi, sıralama yönetici okuma sırasına göre (öğrenci → personel → gelir → gider → başarı → risk); her kart bir ayrıntı sayfasına açılıyor. |
| Sol menüde 16 bağlantı birden açıktı, 6 farklı renkli emoji vardı | 6 akordeon grup; aynı anda tek grup açık, bulunulan grup otomatik açılır; tek renkli geometrik ikon seti. |

Menü grupları istenen şekilde yeniden adlandırıldı: **Ana Sayfa**,
**Akademik Analizler**, **Kaynak ve Finans**, **Performans**, **Planlama**,
**Sistem**.

---

## 6. Test sonuçları

```
Backend birim testleri        412 passed
Backend entegrasyon testleri   57 passed
Arayüz (jsdom) testleri        94 passed / 0 hatalı
------------------------------------------------
TOPLAM                        563 kontrol, 0 hata
```

Arayüz testine bu turda **30 yeni kontrol** eklendi. Testin içine bir ağ
isteği casusu konuldu; "ilk yüklemede ayrıntı uç noktası çağrılmıyor"
kriteri ancak gerçekten yapılan isteklere bakılarak doğrulanabilir.

| Kabul kriteri | Doğrulayan kontrol |
|---|---|
| 1. İlk açılışta bölüm/program listesi yok | `pano: acilista bolum/program listesi yok` |
| 2. Uzun gelir-gider listesi üniversite genelinde yok | `pano: bolum bazli gelir-gider listesi universite genelinde yok` |
| 3. Fakülte seçilmeden bölüm verisi istenmiyor | `pano: ilk yuklemede bolum ayrinti ucu cagrilmiyor` · `pano: bolum ve program alanlari cizilmemis` |
| 4. Bölüm seçilmeden program verisi istenmiyor | `pano: ilk yuklemede program ayrinti ucu cagrilmiyor` · `pano: bolum secilmeden program alani cikmiyor` |
| 5. Yalnızca ilk 5 risk | `pano: en fazla 5 risk gosteriliyor` · `pano: riskler kategoriye gore gruplanmis` |
| 6. "Tüm riskleri incele" çalışıyor | `pano: tum riskleri incele baglantisi Erken Uyari sayfasina gidiyor` |
| 7. Gelir ve gider tek satırda | `pano: gelir ve gider ayni satirda` · `pano: kalan bolumler acilir bolumde` |
| 8. İngilizce program isimleri yok | `pano: ingilizce birim adi gorunmuyor` |
| 9. Legend tekrarlanmıyor | `pano: egilim grafiginde tek legend var` · `pano: ayni legend etiketi iki kez yazilmamis` |
| 10. Sol menü açılır gruplar | `menu: acilir gruplardan olusuyor` · `menu: ayni anda tek grup acik` · `menu: bulunulan grup otomatik acildi` |
| 11. Drill-down çalışıyor | `pano: 6 ozet karti var` · `pano: kartlar ayrinti sayfalarina baglaniyor` · `pano: fakulteye tiklayinca kapsam degisti` |
| 12. Üniversite geneline dönüş | `pano: universite geneline donus calisiyor` |
| 13. Breadcrumb doğru | `pano: breadcrumb universite genelini gosteriyor` · `pano: breadcrumb uc seviyeyi gosteriyor` |
| 14. İlk yüklemede ayrıntı uçları çağrılmıyor | Ağ casusu ile iki kontrol (kriter 3–4 ile aynı) |
| 15. Mevcut testler geçiyor | 412 + 57 backend, önceki 64 arayüz kontrolünün tamamı |

### Test sırasında bulunan ve düzeltilen gerçek hata

Bölüm bütçesi satırları fakülteye göre **ada bakarak** süzülüyordu. Ad çevirisi
devreye girince arayüz Türkçe adı, bütçe uç noktası veritabanındaki adı
taşıdığı için hiçbir satır eşleşmedi ve fakülte kapsamı boş göründü. Süzme
kimliğe (`department_id`) çevrildi. Bu hatayı `pano: bolum karsilastirmasi en
fazla 5 satir gosteriyor` kontrolü yakaladı.

---

## Dokunulmayan alanlar

- **Backend hesaplama formülleri ve eşikleri** — kural motorunun mantığı,
  uyarı eşikleri, mali ve akademik hesaplamalar aynen duruyor. Değişen tek
  şey gösterilen ad, kategori etiketi ve alan sıralaması.
- **Akıllı Asistan / LLM bölümü** — hiçbir dosyasına dokunulmadı.
- **Hiçbir veri kaldırılmadı** — panodan çıkarılan her bilgi ya ilgili ayrıntı
  sayfasında ya da bir açılır bölümde erişilebilir durumda.
