# Ekip dosyası — açıklanamayan 19 değer çelişkisi

Bu satırlar `2021_2025_.xlsx` dosyasında **DOĞRULANDI** etiketli olmasına rağmen
bizim hiçbir kaydımızla eşleşmiyor: ne toplamımıza, ne de alt bileşenlerimizden birine.
Granülerlik farkıyla açıklanamazlar; kaynağa dönülmesi gerekir.

Aktarılmadılar (aktarım yalnızca 2021 ve 2025 yıllarını kapsıyor).

| # | Bölüm | Üniversite | Yıl | Dosya | Bizdeki bileşenler | Dosya etiketi |
|---|---|---|---|---|---|---|
| 1 | Yazılım Mühendisliği | Ankara Bilim Üniversitesi | 2023 | **11** | 44 (%50 İndirimli); 20 (Ücretli); 10 (Burslu) | KAYNAK KONTROLÜ GEREKLİ |
| 2 | Yeni Medya ve İletişim | Ankara Bilim Üniversitesi | 2024 | **8** | 35 (%50 İndirimli); 6 (Burslu); 2 (Ücretli) | DOĞRULANDI |
| 3 | Yeni Medya ve İletişim | Ankara Bilim Üniversitesi | 2023 | **5** | 29 (%50 İndirimli); 4 (Burslu) | DOĞRULANDI |
| 4 | İşletme | Ankara Bilim Üniversitesi | 2024 | **6** | 34 (%50 İndirimli); 5 (Burslu) | DOĞRULANDI |
| 5 | İşletme | Ankara Bilim Üniversitesi | 2023 | **5** | 25 (%50 İndirimli); 4 (Burslu) | DOĞRULANDI |
| 6 | Siyaset Bilimi ve Kamu Yönetimi | Ankara Bilim Üniversitesi | 2024 | **7** | 34 (%50 İndirimli); 5 (Burslu) | DOĞRULANDI |
| 7 | Siyaset Bilimi ve Kamu Yönetimi | Ankara Bilim Üniversitesi | 2023 | **6** | 25 (%50 İndirimli); 4 (Burslu) | DOĞRULANDI |
| 8 | İngilizce Mütercim ve Tercümanlık | Ankara Bilim Üniversitesi | 2023 | **7** | 30 (%50 İndirimli); 11 (Ücretli); 6 (Burslu) | DOĞRULANDI |
| 9 | Web Tasarımı ve Kodlama | Ankara Bilim Üniversitesi | 2024 | **6** | 25 (%50 İndirimli); 4 (Burslu) | DOĞRULANDI |
| 10 | Bilgisayar Mühendisliği | Ankara Üniversitesi | 2022 | **70** | 80 (Mühendislik Fakültesi); 75 (Mühendislik Fakültesi); 5 (Ücretli) | DOĞRULANDI — basarisiralamalari.com (2025-2022) |
| 11 | Bilişim Sistemleri Mühendisliği | Ankara Bilim Üniversitesi | 2024 | **70** | 68 (%50 İndirimli); 11 (Burslu); 4 (Ücretli) | DOĞRULANDI — Burslu program |
| 12 | Bilişim Sistemleri Mühendisliği | Ankara Bilim Üniversitesi | 2023 | **48** | 54 (%50 İndirimli); 10 (Ücretli); 10 (Burslu) | DOĞRULANDI — Burslu program |
| 13 | Bilişim Sistemleri Mühendisliği | Ankara Bilim Üniversitesi | 2022 | **48** | 43 (%50 İndirimli); 9 (Burslu); 8 (Ücretli) | DOĞRULANDI — Burslu program |
| 14 | Hukuk | Tobb Ekonomi Ve Teknoloji Üniversitesi | 2024 | **10** | 60 (Ücretli); 38 (%50 İndirimli); 15 (Burslu) | DOĞRULANDI — Burslu |
| 15 | Hukuk | Tobb Ekonomi Ve Teknoloji Üniversitesi | 2023 | **21** | 55 (Ücretli); 38 (%50 İndirimli); 14 (Burslu) | DOĞRULANDI — Burslu |
| 16 | Hukuk | Tobb Ekonomi Ve Teknoloji Üniversitesi | 2022 | **26** | 55 (Ücretli); 38 (%50 İndirimli); 16 (Burslu) | DOĞRULANDI — Burslu |
| 17 | Yazılım Mühendisliği | Atilim Üniversitesi | 2024 | **5** | 55 (%25 İndirimli); 9 (Burslu) | DOĞRULANDI |
| 18 | Yazılım Mühendisliği | Atilim Üniversitesi | 2023 | **5** | 51 (%25 İndirimli); 8 (Burslu) | DOĞRULANDI |
| 19 | Yazılım Mühendisliği | Atilim Üniversitesi | 2022 | **4** | 68 (%25 İndirimli); 12 (Burslu) | DOĞRULANDI |

**Toplam: 19 çelişki.**

## Ekipten istenecekler

1. Bu 19 satırın kaynak URL'i ve alındığı tarih.
2. Değerin hangi YÖK program koduna ve hangi burs varyantına ait olduğu.
3. `ANA_KARSILASTIRMA` sayfasındaki iki uydurma puan/sıra satırının düzeltilmesi:
   - ABÜ Bilgisayar Mühendisliği 2025 (kaynakta boş, `456.38332 / 3225` kopyalanmış)
   - Çankaya Hukuk 2025 (kaynakta boş, `409.9915 / 31354` kopyalanmış)
4. Gelecek derlemelerde her bölüm için **tüm** YÖK program kodlarının ve **tüm** burs
   varyantlarının ayrı satır olarak verilmesi. Tek varyantlık satır yıl serisine katılamıyor.
