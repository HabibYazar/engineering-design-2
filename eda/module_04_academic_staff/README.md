# Modül 4 — Academic Staff Performance Analysis

> Akademik personelin yayın ve atıf verilerine dayalı performans skorunu hesaplar. PDF Bölüm 4 kapsamındadır.

## Amaç

Üst yönetimin akademik personel performansını tek bir sayıya (skor) indirgeyerek karşılaştırabilmesini sağlar. İleride bölüm/fakülte bazlı karşılaştırma ve farklı ağırlıklandırma seçenekleri eklenmeye uygun bir temel oluşturur.

## Ana Dosyalar
models/
staff.py Staff sınıfı (id, name, publication, citation)
routes/
staff_routes.py 2 endpoint: /staff, /ranking
services/
scores_calculator.py Skor hesaplama mantığı

## Veri Akışı
```
seed_data.py (kök) — staffs listesi
        |
        ▼
scores_calculator.get_staff()
        |
        ├── /staff isteği → ham personel listesini döner
        |
        ▼
scores_calculator.calculate_score()
        ├── her personel için: skor = yayın×5 + atıf×2
        └── /ranking isteği → {isim, skor} listesini döner
```

## Endpoint'ler

| Endpoint | Açıklama | Dönen veri |
|---|---|---|
| `GET /staff` | Ham personel listesi | id, name, publication, citation |
| `GET /ranking` | Hesaplanmış performans skoru | name, score |

## Temel Hesaplamalar
skor = (yayın sayısı × 5) + (atıf sayısı × 2)

Ağırlıklar (`5` ve `2`) şu an `scores_calculator.py` içinde sabit kodlu. İleride bölüme göre değişebilir ağırlıklandırma istenirse (PDF'de belirtildiği gibi), bu değerlerin bir `config/weights.json` dosyasına taşınması gerekir — henüz yapılmadı.

## Diğer Modüllerle Bağlantı

Bu modül bağımsız çalışır, başka hiçbir modüle ihtiyaç duymaz. Tek ortak nokta: veri kaynağı olarak kök dizindeki `seed_data.py`'ı kullanır (`module_05` ve `module_14` de aynı dosyayı, farklı listeler için kullanır).

## Sunumda Gösterilecek Noktalar

1. **`/staff` ve `/ranking` farkı** — biri ham veri, diğeri hesaplanmış sonuç. İkisinin aynı kaynaktan (`seed_data.py`) geldiğini ama farklı işlendiğini göster.
2. **Skor formülünün mantığı** — neden yayına atıftan daha yüksek ağırlık verildiğini (5 vs 2) açıklayabilirsin, bu bilinçli bir tasarım kararı.
3. **Genişleyebilirlik** — yeni bir personel eklemek için sadece `seed_data.py`'a bir satır eklemek yeterli, kod değişikliği gerekmiyor.
