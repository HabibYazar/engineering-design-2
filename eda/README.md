# Modül 4, 5 ve 14 — Akademik Personel, Fiziksel Kaynaklar, Kullanıcı Yetkilendirme

Stratejik Üniversite Yönetimi ve Karar Destek Sistemi projesinin **PDF Bölüm 4, 5, 14** kapsamındaki modülleri. FastAPI ile geliştirilmiştir; klasör tek başına indirilse bile çalışır, ana backend'e bağımlılığı yoktur.

| Modül | PDF Bölümü | Kapsam | Durum |
|---|---|---|---|
| Modül 4 | 4 — Academic Staff Performance Analysis | Ders yükü, yayın, atıf, proje bazlı personel performans skoru | Çalışıyor |
| Modül 5 | 5 — Physical Resources and Capacity Analysis | Derslik/laboratuvar kapasite ve doluluk oranı analizi | Çalışıyor |
| Modül 14 | 14 — User and Authorization Management | Kullanıcı girişi ve rol bazlı yetkilendirme | Çalışıyor |

## 🚀 Hızlı Başlangıç

Ardından tarayıcıdan: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

Arayüz demosu için `frontend.html` dosyasını sunucu çalışırken çift tıklayıp tarayıcıda aç.

Uygulama şu an **sahte veri (seed_data.py)** ile çalışır, veritabanı bağlantısı yoktur. Veriyi değiştirmek için kök dizindeki `seed_data.py` dosyasını düzenlemek yeterlidir.

## 🔗 Modüllerin Birbirinden Bağımsızlığı

Üç modül de birbirinden bağımsız çalışır, ortak nokta sadece veri kaynağıdır:
