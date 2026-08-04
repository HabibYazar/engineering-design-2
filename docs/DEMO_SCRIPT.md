# Sunum Senaryosu — 8-10 dakika

Hedef: 13 modülün tek üründe çalıştığını, sayıların tutarlı olduğunu ve
sistemin dürüst olduğunu (eksik veriyi eksik göstermesini) kanıtlamak.

---

## Sunum öncesi (5 dakika önce)

```powershell
.\run_project.ps1 -FreshDatabase -RunTests
```

Kontrol listesi:

- [ ] Seed özet tablosu 4.466 kayıt gösterdi
- [ ] `432 passed` yazdı
- [ ] Tarayıcı `http://127.0.0.1:8000` adresinde açıldı
- [ ] Üst barda **"● API bağlı"** yeşil görünüyor
- [ ] İkinci sekmede `http://127.0.0.1:8000/docs` hazır

Tarayıcıyı yakınlaştırın (Ctrl + `+`) — projeksiyonda tablolar okunsun.

---

## 1. Giriş — dürüstlük gösterisi (45 sn)

**Yapılacak:** Parolayı bilerek yanlış girin (`admin` / `yanlis`) → **Giriş yap**.

**Söylenecek:**
> "Kimlik doğrulama sahte değil. Yanlış parola sunucudan 401 alıyor ve hata
> kullanıcıya gösteriliyor. Parolalar veritabanında düz metin değil,
> PBKDF2 ile saltlanmış özet olarak duruyor."

**Yapılacak:** `admin` / `demo1234` ile girin.

---

## 2. Yönetim panosu (2 dakika)

**Söylenecek:**
> "Bu pano beş farklı modülden veri derliyor: öğrenci analitiği, finans,
> fiziksel kaynaklar, performans yönetimi ve akademik personel. Hiçbir sayı
> arayüzde yazılı değil; hepsi API'den geliyor."

**Gösterilecek göstergeler:**

| Gösterge | Değer | Hangi modül |
|---|---|---|
| Toplam öğrenci | 4.000 | Modül 2 |
| Akademik personel | 180 | Modül 4 |
| Toplam gelir | ₺935,0M | Modül 6 |
| Gelir–gider dengesi | ₺2,0M (fazla) | Modül 6 |
| Mekân doluluk oranı | %73,9 | Modül 5 |
| KPI genel başarı | %78,6 | Modül 8 |

**Kırılım tablosunda** bir fakülte satırına tıklayın → bölümler açılır.

> "Fakülte toplamları ayrı bir yerde saklanmıyor; bölümlerden hesaplanıyor.
> Bu yüzden fakülte toplamıyla bölüm toplamının ayrışması mümkün değil."

Bütçe aşımı olan bölümlerin kırmızı rozetini gösterin.

---

## 3. Öğrenci Analitiği — iki modül tek ekranda (1 dakika)

Menü → **Öğrenci Analitiği (M2·M3)**

> "Ekipte iki kişi öğrenci analitiği yazmıştı ve ikisi de `/api/student-analytics`
> adresini kullanıyordu. Bu bir çakışmaydı: FastAPI'de aynı yol iki kez
> kaydedilirse ikincisi sessizce gölgede kalır. Prefix'lerden birini
> `/api/education-analytics` yaptık ve arayüzde iki modülün çıktısını **tek
> ekranda, ayrı kartlarda** gösteriyoruz. Kullanıcı için iki sekme yok."

Sağdaki **Modül 3** rozetli kartı gösterin (burs ve uluslararasılaşma halkaları).

Program karnesi tablosunda en düşük doluluklu programı gösterin.

---

## 4. Fiziksel Kaynaklar — hard-code veri temizliği (1 dakika)

Menü → **Fiziksel Kaynaklar (M5)**

En alttaki **Kişi başına düşen kapasite** kartına gidin.

> "Orijinal kodda burada `TOTAL_STUDENTS = 3200` ve `TOTAL_STAFF = 180`
> sabitleri vardı. Sabit sayıyla hesaplanan bir oran gerçek sistem verisi gibi
> görünüp yanlış karar aldırabilir. Şimdi bu sayılar veritabanından sayılıyor —
> ekranda 4.000 öğrenci ve 180 personel yazıyor ve panodaki değerlerle birebir
> aynı."

**Büyüme projeksiyonu:** kutuya `40` yazıp **Hesapla**.

> "Kapasite açığı hesaplanıyor ve yeterli mi değil mi açıkça söyleniyor."

---

## 5. Finansal Analiz — Decimal ve bütçe aşımı (1 dakika)

Menü → **Finansal Analiz (M6)**

> "Bu modül orijinalde bir JSON dosyasına yazan, Python'ın standart HTTP
> sunucusuyla çalışan ayrı bir uygulamaydı ve tutarlar float'tı. Dokuz gider
> kalemi toplandığında kuruş sapması oluşuyordu. Şimdi SQLAlchemy modeli ve
> Decimal kullanıyor."

Bölüm bütçeleri tablosunu gösterin — **bütçe aşımı** (kırmızı), **hafif aşım**
(sarı), **bütçe içinde** (yeşil) rozetleri.

> "Bütçesi tanımlanmamış bir bölüm olsaydı gerçekleşme oranı sıfır değil, boş
> görünürdü. Sistem eksik veriyi sıfır gibi göstermiyor."

---

## 6. Senaryo Analizi — canlı hesaplama (1,5 dakika)

Menü → **Senaryo Analizi (M9)**

Senaryo türü: **Öğrenim ücreti değişikliği**, değer: `10` → **Önizle**

> "Hesaplama sunucuda Decimal ile yapıldı. Gelir ve maliyet projeksiyonu, risk
> kuralları ve öneri döndü. Dikkat: bu bir **önizleme**, veritabanına hiçbir
> kayıt yazılmadı."

İkinci deneme: türü **Program kapatma** yapın → **Önizle**

> "Farklı senaryo, farklı risk seti. Risk kuralları sabit metin değil; girdiye
> göre tetikleniyor."

---

## 7. Erken Uyarı — kuralın şeffaflığı (1 dakika)

Menü → **Erken Uyarı (M11)**

(Ekran ~2,5 saniyede yükleniyor — kural motoru 4000 öğrenci üzerinde çalışıyor.
Yükleme göstergesi görünür.)

> "22 uyarı üretildi, 2'si kritik."

Bir uyarıya işaret edin:

> "Her uyarı hangi kuraldan geldiğini, **ölçülen değeri**, **eşiği** ve **veri
> kaynağını** gösteriyor. Kara kutu uyarı bırakmadık."

Sağdaki **"Henüz çalıştırılamayan kurallar"** kutusunu gösterin:

> "Bu kurallar tanımlı ama gerekli veri girilmediği için değerlendirilemiyor.
> Sonuç üretiyormuş gibi göstermek yerine açıkça listeliyoruz."

---

## 8. Veri Aktarımı — önizleme (1 dakika)

Menü → **Veri Aktarımı (M13)**

Kaynak türü `faculties` seçin → **Şablon indir** (sütunlar sağda görünüyor).

İndirilen dosyayı seçip **Önizle (yazmadan)**.

> "Önizleme modunda veritabanına hiçbir kayıt yazılmıyor. Satır bazlı hata
> raporu geliyor. Hata yoksa 'Gerçekten aktar' düğmesi açılıyor. 11 kaynak türü
> ve CSV, Excel, JSON formatları destekleniyor."

---

## 9. Akıllı Asistan — dürüst durum (1,5 dakika)

Menü → **Akıllı Asistan**

> "Hoca ileride LLM entegrasyonu istiyor. Ancak **ekip henüz bir model
> seçmedi**. Bu yüzden bilinçli olarak hiçbir sağlayıcı bağlamadık."

Durum kartlarını gösterin: `ASSISTANT_ENABLED=false`, sağlayıcı **seçilmedi**,
model **seçilmedi**, API anahtarı **tanımsız**.

> "Bu değerler arayüzde yazılı değil, sunucudan geliyor."

Örnek sorulardan birini seçin → **Bağlamı hazırla**

> "Bakın ne oldu: sistem soruya **cevap üretmedi**. Bunun yerine, bu soruya
> cevap verilebilmesi için hangi kurumsal verilerin gerekli olduğunu belirledi
> ve **gerçek veritabanından** topladı. Her satırda hangi modülden geldiği
> yazıyor."
>
> "Model bağlandığında tam olarak bu bağlam modele gidecek. Şu anda uydurma bir
> cevap üretmek yerine durumu açıkça söylüyoruz."

En alttaki mimari tablosunu gösterin:

> "Dört bileşen hazır, bir tanesi — somut sağlayıcı sınıfı — bilinçli olarak
> eksik. Model seçildiğinde tek bir sınıf yazılıp bir sözlüğe kaydedilecek,
> başka hiçbir yer değişmeyecek."

---

## 10. Kapanış — teknik kanıt (45 sn)

**Swagger sekmesine geçin** (`/docs`)

> "181 endpoint, modül modül gruplanmış. Arayüzdeki her sayı bu endpoint'lerden
> geliyor; Swagger'dan da doğrulanabilir."

**Terminale dönün:**

```
432 passed
```

> "412 birim testi ve 20 entegrasyon testi. Entegrasyon testleri özellikle
> birleştirmede bozulabilecek şeyleri kontrol ediyor: router çakışması, çift
> tablo, modüller arası bağlantılar, parolanın sızmaması, API anahtarının kodda
> olmaması ve eksik verinin sıfır gösterilmemesi. Ayrıca 31 kontrollük bir
> arayüz testi 14 ekranın gerçek veriyle dolduğunu doğruluyor."

---

## Muhtemel sorular

**"Bu veriler gerçek mi?"**
> Hayır, kurgusal. `integration/shared_demo_data/` altındaki 8 JSON dosyasından
> deterministik olarak üretiliyor. Gerçek veriyle değiştirmek için sadece bu
> dosyaları değiştirip seed'i yeniden çalıştırmak yeterli — kod değişmiyor.

**"Neden LLM bağlamadınız?"**
> Ekip henüz model seçmedi. Seçim yapılmadan sağlayıcı bağlamak yanlış olurdu.
> Altyapıyı sağlayıcıdan bağımsız hazırladık; model seçildiğinde tek bir sınıf
> yazılacak.

**"Modül 12 nerede?"**
> Ekip deposunda Modül 12 için arayüz taslağı var ama backend kodu yok. Sahte
> bir ekran üretmek yerine dâhil etmedik ve bunu dokümante ettik.

**"Herkesin kodu korundu mu?"**
> Evet. Orijinal klasörlerin hiçbiri silinmedi, ayrıca birleştirmede kullanılan
> dosyaların birleştirme öncesi hâli `archive_before_merge/` altında (90 dosya).
> Git'te de `integration-backup-before-merge` branch'i var.

**"Bu gerçek THE/QS sıralaması mı?"**
> Hayır. Modül 10 kurum içi performans ve veri hazırlık göstergeleri hesaplıyor.
> Ekranın en üstünde bu uyarı yazılı.

**"Neden Erken Uyarı ekranı yavaş?"**
> Kural motoru 14 program × 4000 öğrenci üzerinde çalışıyor, yaklaşık 2,5 saniye.
> Yükleme göstergesi var. Önbellek eklenebilir; şimdilik doğruluğu hızın önünde
> tuttuk.

---

## Zamanlama

| Bölüm | Süre |
|---|---|
| Giriş | 0:45 |
| Pano | 2:00 |
| Öğrenci Analitiği | 1:00 |
| Fiziksel Kaynaklar | 1:00 |
| Finans | 1:00 |
| Senaryo | 1:30 |
| Erken Uyarı | 1:00 |
| Veri Aktarımı | 1:00 |
| Asistan | 1:30 |
| Kapanış | 0:45 |
| **Toplam** | **~11:30** |

Süre kısaysa Veri Aktarımı ve Fiziksel Kaynaklar bölümleri atlanabilir (~9 dk).
