# Modül 14 — User and Authorization Management

> Kullanıcı girişini doğrular ve rol bilgisini döner. PDF Bölüm 14 kapsamındadır.

## Amaç

Sistemin farklı kullanıcı rollerine (üst yönetim, dekan, bölüm başkanı) göre farklı yetki seviyeleri tanımlayabilmesi için temel giriş mekanizmasını sağlar.

## Ana Dosyalar
models/
user.py User sınıfı (username, password, role)
schemas/
user_schema.py LoginRequest (Pydantic doğrulama şeması)
routes/
auth_routes.py 3 endpoint: /login, /users, /health
services/
auth_service.py Giriş doğrulama ve kullanıcı listeleme mantığı

## Veri Akışı
```
seed_data.py (kök) — users listesi
        |
        ▼
auth_service.login(username, password)
        ├── eşleşme bulunursa → {message: "Login Successful", role}
        └── eşleşme yoksa     → {message: "Invalid username or password", role: ""}
        |
        ▼
auth_service.get_users()
        └── şifre HARİÇ tüm kullanıcıları listeler
```
## Endpoint'ler

| Endpoint | Açıklama | Gövde / Dönen veri |
|---|---|---|
| `POST /login` | Kullanıcı girişi | Gövde: `{username, password}` → Döner: `{message, role}` |
| `GET /users` | Kayıtlı kullanıcı listesi | username, role (şifre dönmez) |
| `GET /health` | Servis durumu | status, message |

## Temel Hesaplamalar

Bu modül hesaplama değil, **doğrulama** yapar: gönderilen `username`/`password` ikilisi, `seed_data.py`'daki kayıtlarla birebir eşleştirilir. Eşleşme yoksa boş rol (`""`) ile "Invalid" mesajı döner — sistem hiçbir zaman hata (4xx/5xx) fırlatmaz, her zaman `200 OK` ile anlamlı bir mesaj döner.

## Diğer Modüllerle Bağlantı

Bu modül bağımsız çalışır. Kök dizindeki ortak `seed_data.py`'dan `users` listesini okur. İleride Modül 4 ve 5'teki endpoint'lerin bu modülden gelen role göre kısıtlanması (yetkilendirme) planlanabilir — şu an henüz bağlı değil.

## Sunumda Gösterilecek Noktalar

1. **Şifre asla dönmez** — `/users` endpoint'i bilinçli olarak şifreyi response'tan çıkarır, bu bir güvenlik prensibi.
2. **Düz metin şifre uyarısı** — şu an demo amaçlı şifreler düz metin, gerçek sistemde hash'lenmesi (bcrypt vb.) gerektiği açıkça belirtilmeli.
3. **Yetkilendirmenin henüz bağlanmadığı** — giriş çalışıyor ama diğer modüllerin endpoint'lerini role göre kısıtlama henüz yapılmadı, bu bir sonraki aşama.
