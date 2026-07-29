# Modül Görünümleri (module_views)

Bu klasör **yalnızca sunum ve kod inceleme amaçlıdır**. Projenin çalışan yapısına dahil
değildir; hiçbir modül buradan import edilmez.

## ⚠️ Önemli Notlar

- Buradaki tüm dosyalar `app/`, `sample_data/` ve kök dizindeki **orijinallerin birebir
  kopyalarıdır**. İçerikleri değiştirilmemiş, başlarına açıklama eklenmemiştir.
- **Çalışan kod her zaman orijinal konumundadır.** Bu klasördeki kopyalar üzerinde
  değişiklik yapmak uygulamayı etkilemez.
- Kopyalar orijinal katman yapısını korur (`models/`, `schemas/`, `routers/`, `services/`).
  Bunun sebebi: aynı isimli dosyalar farklı katmanlarda bulunabiliyor (örneğin
  `models/faculty.py` ve `schemas/faculty.py`); düz kopyalama bu dosyaların birbirini
  ezmesine yol açardı.
- Seed script'leri her modül klasörünün kökündedir.
- Bu klasördeki Python dosyaları **çalıştırılamaz** (import yolları `app.` paketine
  göredir). Amaç okuma ve sunumdur.

## Modül Özet Tablosu

| Modül | Klasör | Ad | Ana Sorumluluk | Dosya | Model | Endpoint |
|---|---|---|---|---|---|---|
| 1 | `module_01_core_data/` | University Structure and Core Data Management | Fakülte, bölüm, program ve idari birim yönetimi | 14 | 4 | 20 |
| 2 | `module_02_student_analytics/` | Strategic Education and Student Analytics | Öğrenci sayıları, oranlar, trendler ve erken uyarılar | 12 | 4 | 21 |
| 9 | `module_09_scenario_analysis/` | What-if Scenario Analysis | Finans, personel ve kapasite senaryo simülasyonu | 10 | 4 | 15 |
| 10 | `module_10_ranking_evaluations/` | THE, QS and YÖK Evaluation and Monitoring | Değerlendirme çerçeveleri, veri hazırlık ve iç uyum izleme | 17 | 8 | 33 |
| 13 | `module_13_data_integration/` | Data Integration | CSV / XLSX / JSON toplu veri aktarımı | 42 | 1 | 5 |

**Toplam:** 95 dosya kopyalandı · 21 veritabanı tablosu · 65 endpoint yolu

## Katmanlı Mimari

Projenin tamamı aynı katman düzenini kullanır:

```
Router      →  yalnızca HTTP: isteği alır, servisi çağırır, cevabı döndürür
Service     →  tüm iş mantığı ve hesaplamalar
Schema      →  Pydantic v2 giriş/çıkış doğrulaması
Model       →  SQLAlchemy 2.0 veritabanı tabloları
```

**Kural:** Router içinde hesaplama yapılmaz. Bu ayrım sayesinde formüller veritabanı ve
HTTP katmanından bağımsız olarak test edilebilir.

## Modüller Arası Bağlantı Haritası

```
                    ┌──────────────────────────────┐
                    │  Modül 1 - Üniversite Yapısı │
                    │  Faculty → Department →      │
                    │  AcademicProgram             │
                    └───────┬──────────────────────┘
                            │ akademik program
              ┌─────────────┴─────────────┐
              ▼                           ▼
   ┌──────────────────────┐   ┌────────────────────────┐
   │ Modül 2 - Öğrenci    │   │ Modül 13 - Veri        │
   │ Analitiği            │   │ Entegrasyonu           │
   │ Student, Records,    │◄──┤ 11 kaynak türü için    │
   │ Snapshots            │   │ CSV/XLSX/JSON import   │
   └────┬─────────────┬───┘   └───────────┬────────────┘
        │             │                   │ besler
        │ aktif       │ öğrenci           │
        │ öğrenci     │ göstergeleri      ▼
        ▼             ▼        ┌────────────────────────────┐
   ┌─────────────────────┐     │ Modül 10 - THE/QS/YÖK      │
   │ Modül 9 - Senaryo   │     │ Değerlendirme ve İzleme    │
   │ Analizi             │     │ Framework → Dimension →    │
   │ Baseline, Scenario, │     │ Indicator → MetricValue    │
   │ Input, Result       │     └────────────────────────────┘
   └─────────────────────┘
```

### Somut Entegrasyon Noktaları

| Kaynak | Hedef | Nasıl |
|---|---|---|
| Modül 1 → Modül 2 | `AcademicProgram` → `Student.academic_program_id` | Foreign key |
| Modül 1 → Modül 2 | `AcademicProgram` → `ProgramEnrollmentSnapshot` | Foreign key |
| Modül 2 → Modül 9 | Aktif öğrenci sayısı → `ScenarioBaseline.student_count` | `POST /api/scenarios/baselines/sync-student-data` |
| Modül 2 → Modül 9 | Canlı öğrenci sayısı → simülasyon başlangıcı | `?use_live_student_data=true` |
| Modül 1+2 → Modül 10 | 17 öğrenci metriği → gösterge verisi | `POST /api/ranking-evaluations/metrics/sync-student-data` |
| Modül 13 → 1, 2, 10 | Toplu veri aktarımı | 11 `resource_type` |

## Ortak Teknik Kararlar

| Karar | Gerekçe |
|---|---|
| **Decimal** (float değil) | Para ve oran hesaplarında ikili gösterim sapması milyonluk bütçelerde gerçek hataya dönüşür |
| **`MoneyType`** özel sütun tipi | SQLite `Numeric`'i float olarak saklar; Decimal'i metin olarak yazıp okuyarak kayıpsızlık garanti edilir |
| **Soft delete** | Kayıtlar silinmez, `is_active=False` yapılır — geçmiş raporlar bozulmaz |
| **`ROUND_HALF_UP`, 2 basamak** | Tüm yüzde ve para değerleri tutarlı biçimde yuvarlanır |
| **Sıfıra bölme koruması** | Her bölme güvenli yardımcıdan geçer; hata yerine 0 döner ve durum raporlanır |
| **Toplu SQL sorguları** | `GROUP BY` + `SUM(CASE WHEN...)` ile N+1 sorgu önlenir |
| **Yol sırası** | Sabit yollar (`/baselines`) parametreli yollardan (`/{id}`) önce tanımlanır |

## Sunumda Vurgulanacak Genel Noktalar

1. **Katmanlı mimari tutarlı biçimde uygulandı** — 5 modülün beşi de aynı Router/Service/
   Schema/Model ayrımını kullanıyor; hiçbir router içinde hesaplama yok.
2. **Modüller birbirini besliyor** — Modül 1'in yapısı Modül 2'yi, Modül 2'nin öğrenci
   verisi hem Modül 9 senaryolarını hem Modül 10 göstergelerini otomatik dolduruyor.
3. **Decimal hassasiyeti uçtan uca korunuyor** — özel `MoneyType` sütun tipi sayesinde
   veritabanına yazılan değer birebir geri okunuyor.
4. **Veri kalitesi ayrı bir boyut olarak ölçülüyor** — Modül 10 performansı ve veri
   hazırlığını ayrı hesaplayıp uyum skorunda birleştiriyor; eksik veri gizlenmiyor.
5. **940 otomatik test** — 412 pytest + 528 senaryo bazlı kontrol; her modül eklendikçe
   öncekilerin regresyonu doğrulandı.

## Test ve Çalıştırma

Bu klasör test kapsamına dahil **değildir**. Uygulama ve testler orijinal dosyalarla çalışır:

```bash
# Kurulum sırası
python seed_data.py
python seed_scenario_data.py
python seed_student_data.py
python seed_ranking_data.py

# Çalıştırma
uvicorn main:app --reload

# Testler (izole test veritabanı kullanır)
pytest
```
