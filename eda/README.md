# Modül 4, 5 ve 14 — Akademik Personel, Fiziksel Kaynaklar, Kullanıcı Yetkilendirme

Stratejik Üniversite Yönetimi ve Karar Destek Sistemi projesinin **PDF Bölüm 4, 5, 14** kapsamındaki modülleri. FastAPI ile geliştirilmiştir; klasör tek başına indirilse bile çalışır, ana backend'e bağımlılığı yoktur.

| Modül | PDF Bölümü | Kapsam | Durum |
|---|---|---|---|
| Modül 4 | 4 — Academic Staff Performance Analysis | Ders yükü, yayın, atıf, proje bazlı personel performans skoru | Çalışıyor |
| Modül 5 | 5 — Physical Resources and Capacity Analysis | Derslik/laboratuvar kapasite ve doluluk oranı analizi | Çalışıyor |
| Modül 14 | 14 — User and Authorization Management | Kullanıcı girişi ve rol bazlı yetkilendirme | Çalışıyor |

## 🚀 Hızlı Başlangıç

```
python -m venv venv
source venv/Scripts/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Ardından tarayıcıdan: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

Arayüz demosu için `frontend.html` dosyasını sunucu çalışırken çift tıklayıp tarayıcıda aç.

Uygulama şu an **sahte veri (seed_data.py)** ile çalışır, veritabanı bağlantısı yoktur. Veriyi değiştirmek için kök dizindeki `seed_data.py` dosyasını düzenlemek yeterlidir.

## 🔗 Modüllerin Birbirinden Bağımsızlığı

Üç modül de birbirinden bağımsız çalışır, ortak nokta sadece veri kaynağıdır:
seed_data.py (kök)
├── staffs → Modül 4 bunu okur
├── classrooms → Modül 5 bunu okur
└── users → Modül 14 bunu okur

## 📡 Endpoint'ler

| Grup | Endpoint | Açıklama |
|---|---|---|
| Health | `GET /` · `GET /health` | Servis ayakta mı kontrolü |
| Modül 4 | `GET /staff` | Tüm akademik personeli listeler |
| Modül 4 | `GET /ranking` | Yayın ve atıfa göre performans skoru hesaplar |
| Modül 5 | `GET /classrooms` | Tüm derslikleri listeler |
| Modül 5 | `GET /capacity` | Derslik doluluk oranlarını hesaplar |
| Modül 14 | `POST /login` | Kullanıcı adı/şifre ile giriş, rol döner |
| Modül 14 | `GET /users` | Kayıtlı kullanıcıları listeler |

## 🎬 Demo Akışı

| Adım | Endpoint | Gösterilen |
|---|---|---|
| 1 | `GET /health` | Servis ayakta |
| 2 | `GET /staff` | 4 akademik personel, yayın/atıf verisiyle |
| 3 | `GET /ranking` | Yayın × 5 + atıf × 2 formülüyle hesaplanan skor sıralaması |
| 4 | `GET /classrooms` | 4 derslik, kapasite/doluluk verisiyle |
| 5 | `GET /capacity` | Doluluk yüzdesi hesaplanmış hali |
| 6 | `POST /login` | `admin` / `1234` ile giriş, rol bilgisi dönüşü |
| 7 | `GET /users` | Kayıtlı 2 kullanıcı, şifre gösterilmeden |

`POST /login` gövdesi (`/docs` üzerinden kopyalanıp çalıştırılabilir):
```json
{
  "username": "admin",
  "password": "1234"
}
```

## 📁 Klasör Yapısı
eda/
├── main.py # FastAPI uygulaması (bağımsız çalışır)
├── seed_data.py # Tüm modüllerin sahte verisi (tek kaynak)
├── requirements.txt
├── frontend.html # Arayüz demosu (bağımsız HTML dosyası)
├── module_04_academic_staff/
│ ├── models/ # Staff sınıfı
│ ├── routes/ # /staff, /ranking endpoint tanımları
│ └── services/ # Skor hesaplama mantığı
├── module_05_physical_resources/
│ ├── models/ # Classroom sınıfı
│ ├── routes/
│ └── services/ # Kapasite hesaplama mantığı
└── module_14_user_authorization/
├── models/ # User sınıfı
├── schemas/ # LoginRequest (Pydantic)
├── routes/
└── services/ # Giriş ve kullanıcı listeleme mantığı

## 💾 Demo Verisi Hakkında

Veri `seed_data.py` içinde elle tanımlıdır, veritabanı bağlantısı yoktur:
- **4 akademik personel** — yayın ve atıf sayılarıyla
- **4 derslik** — kapasite ve doluluk bilgisiyle
- **2 kullanıcı** — admin ve bölüm başkanı rolleriyle

Veriyi değiştirmek isteyen biri sadece `seed_data.py`'ı düzenler, servis dosyalarına dokunmasına gerek yoktur.
