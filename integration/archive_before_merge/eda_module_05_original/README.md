# Modül 5 — Physical Resources and Capacity Analysis

> Derslik kapasite ve doluluk oranlarını analiz eder. PDF Bölüm 5 kapsamındadır.

## Amaç

Üst yönetimin hangi dersliklerin dolu, hangilerinin boş kaldığını görmesini sağlar. İleride yeni program açma kararlarında fiziksel kapasite yeterliliğini değerlendirmek için temel oluşturur.

## Ana Dosyalar
models/
classroom.py Classroom sınıfı (room, capacity, occupied)
routes/
classroom_routes.py 2 endpoint: /classrooms, /capacity
services/
capacity_service.py Doluluk oranı hesaplama mantığı

## Veri Akışı
```
seed_data.py (kök) — classrooms listesi
        |
        ▼
capacity_service.get_classrooms()
        |
        ├── /classrooms isteği → ham derslik listesini döner
        |
        ▼
capacity_service.calculate_capacity()
```

## Endpoint'ler

| Endpoint | Açıklama | Dönen veri |
|---|---|---|
| `GET /classrooms` | Ham derslik listesi | room, capacity, occupied |
| `GET /capacity` | Hesaplanmış doluluk oranı | room, capacity, occupied, occupancy (%) |

## Temel Hesaplamalar
doluluk oranı = (dolu koltuk / toplam kapasite) × 100

Sonuç `%XX.XX` formatında string olarak döner (örn. `"87.5%"`), sayısal işlem yapılacaksa `%` işareti temizlenmeli.

## Diğer Modüllerle Bağlantı

Bu modül bağımsız çalışır. Kök dizindeki ortak `seed_data.py`'dan `classrooms` listesini okur.

## Sunumda Gösterilecek Noktalar

1. **Ham veri vs hesaplanmış veri ayrımı** — `/classrooms` sadece kayıtları gösterirken `/capacity` gerçek analiz sunuyor, bu ayrım PDF'in "ham veri değil, karar destek" vurgusuyla örtüşüyor.
2. **Kapsam sınırı** — şu an sadece derslik var; PDF'de laboratuvar, ofis, kütüphane de geçiyor, bunlar ilk demo kapsamı dışında bırakıldı, bir sonraki aşamada eklenecek.
3. **Doluluk formülünün basitliği** — karmaşık bir algoritma yerine bilinçli olarak sade bir oran hesabı seçildi, çünkü PDF'in istediği şey net bir gösterge, karmaşık bir tahmin modeli değil.
        ├── her derslik için: doluluk % = (dolu / kapasite) × 100
        └── /capacity isteği → oda, kapasite, dolu, doluluk% listesini döner.
