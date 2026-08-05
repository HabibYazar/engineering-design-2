# Arayüz Yeniden Tasarımı — Uygulama Raporu

Bu rapor, sistemin "teknik analiz ekranı / veritabanı dökümü" görünümünden
çıkarılıp bir üniversite yöneticisinin saniyeler içinde anlayabileceği
kademeli bir arayüze dönüştürülmesi için yapılan çalışmayı belgeler.

Temel ilke: **veri kaldırılmadı, sıraya sokuldu.** Önce sonuç, sonra sebep,
en sonda yöntem. Ana ekranda karar için gereken az sayıda bilgi durur; ayrıntı
isteyen kullanıcı açılır bölümlerden erişir.

---

## 1. Değiştirilen frontend dosyaları

| Dosya | Durum | Yapılan değişiklik |
|---|---|---|
| `frontend/assets/api.js` | genişletildi | `ux` yardımcı katmanı (`details`, `tabs`, `bindTabs`, `skeleton`, `statusBadge`, `scoreBlock`, `limitedList`) ve `OrgFilter` sınıfı eklendi. Tüm ekranlar artık aynı açılır bölüm ve filtre davranışını paylaşıyor. |
| `frontend/assets/views-sustainability.js` | **yeni** | Program Sürdürülebilirliği ekranı sıfırdan yazıldı. Eskiden bu bölüm `views-analytics.js` içindeydi. |
| `frontend/assets/views-kpi.js` | **yeni** | Stratejik göstergeler ekranı üç sekmeye ayrıldı. Eskiden tek uzun tabloydu. |
| `frontend/assets/views-analytics.js` | sadeleştirildi | Sürdürülebilirlik ve KPI bölümleri çıkarıldı; öğrenci ve personel ekranları `OrgFilter`'a geçirildi; mekân listeleri ilk 5 satır + açılır bölüme indirildi; personel puanlama ağırlıkları açılır bölüme taşındı. |
| `frontend/assets/views-success.js` | güncellendi | Akademik Başarı ekranı `OrgFilter` ile fakülte → bölüm → program kırılımına bağlandı. |
| `frontend/assets/views-planning.js` | sadeleştirildi | Senaryo sonucunda üç karşılaştırma tablosu açılır bölüme alındı, risk listesi ilk 3 + açılır hale getirildi, İngilizce risk seviyeleri Türkçeleştirildi, erken uyarı ekranından yapılandırma dosyası yolu kaldırıldı. |
| `frontend/assets/integration.css` | genişletildi | Açılır bölüm, sekme, filtre çubuğu, durum rozeti, skor bloğu, kriter çubuğu, yükleme iskeleti ve özet şeridi stilleri (~265 satır). |
| `frontend/index.html` | güncellendi | İki yeni betik kaydedildi, önbellek sürümü `?v=8`'e yükseltildi. |

---

## 2. Değiştirilen backend dosyaları

Hesaplama formüllerine **dokunulmadı**. Backend'de yalnızca (a) etiketleme ve
(b) "veri yok" ile "sıfır" ayrımı üzerinde çalışıldı.

| Dosya | Yapılan değişiklik |
|---|---|
| `app/services/kpi_service.py` | `STATUS_NO_DATA` durumu; `DERIVED_KPI_RESOLVERS` ile türetilmiş göstergelerin gerçek kaynaktan çözülmesi; ölçülemeyen göstergelerin ortalamadan çıkarılması; `missing_data_list()`. |
| `app/routers/kpi.py` | `evaluate()` çağrılarına veritabanı oturumu geçirildi; `GET /api/kpi/missing-data` eklendi. |
| `app/schemas/kpi.py` | `current_value` ve `achievement_percent` artık `Optional` — ölçülmemiş gösterge `0` değil `null` döner. `has_data`, `measured_kpi_count`, `no_data_count`, `average_basis_note` eklendi. |
| `app/config/sustainability_weights.json` | Kriter kaynak açıklamaları teknik ifadelerden arındırıldı; `criterion_labels`, `criterion_descriptions` ve üç başlıklı `criterion_groups` eklendi. |
| `app/schemas/sustainability.py`, `app/routers/sustainability.py` | Ağırlık uç noktası artık etiket/açıklama/grup sözlüklerini de döndürüyor; arayüz kendi çeviri tablosunu tutmuyor. |
| `app/services/academic_staff_service.py`, `app/routers/academic_staff.py` | `staff_overview()` fakülte ve bölüm filtresi kabul ediyor — personel ekranının kırılımı gerçek backend sorgusuna bağlı. |

---

## 3. Sadeleştirilen ekranlar

**Program Sürdürülebilirliği** — En kapsamlı değişiklik.
Eskiden sayfa açılır açılmaz bütün programların skor listesi, 11 satırlık
ağırlık tablosu ve teknik kriter adları aynı anda görünüyordu. Şimdi:

1. Sayfa boş açılır; yalnızca filtre ve "Sonuçları Göster" düğmesi vardır.
2. Sonuç geldiğinde önce tek bir değerlendirme cümlesi ve durum rozeti gelir.
3. Kriterler üç anlamlı gruba ayrılmış çubuklarla gösterilir.
4. Eksik kriterler tek satırlık özet + "Detayları göster" ile sunulur.
5. Ağırlık tablosu ve yöntem açıklaması kapalı bir bölümdedir.

**Stratejik Göstergeler (KPI)** — Tek uzun tablo üç sekmeye ayrıldı:
*Genel Bakış* (en iyi 3 / en zayıf 3 boyut), *Müdahale Gerektirenler*
(sorun + önerilen aksiyon), *Tüm Göstergeler* (5 sütunlu tablo, satır
genişletilince formül ve kaynak görünür). Sekmeler ilk açılışta yüklenir,
diğerleri tıklanınca — sayfa açılışında üç ayrı sorgu atılmaz.

**Fiziksel Kaynaklar** — Mekân listeleri ilk 5 satır + "Tümünü göster";
kişi başına kapasite açılır bölüme alındı. Başlıklar teknik eşiklerden
(`%90 üstü`) yönetici diline çevrildi (`Acil kapasite ihtiyacı`).

**Senaryo Simülasyonu** — Sonuç ekranında önce tek cümlelik değerlendirme ve
en çok değişen göstergeler; mali / akademik / kapasite tablolarının tamamı
açılır bölümde. Risk listesi ilk 3 + açılır.

**Akademik Personel** — Sıralama ilk 10 + açılır; puanlama ağırlıkları açılır
bölümde bir tabloya taşındı.

**Erken Uyarı** — Kural bölümlerinden yapılandırma dosyası yolu kaldırıldı,
başlıklar kullanıcı diline çevrildi.

---

## 4. Teknik isimlerin Türkçe karşılıkları

Arayüzde artık hiçbir `snake_case` alan adı, modül numarası veya dosya yolu
görünmüyor. Karşılık tablosu backend'deki `sustainability_weights.json`
dosyasında tutulur; arayüz onu okur, kendi kopyasını tutmaz.

| Teknik ad | Kullanıcıya gösterilen |
|---|---|
| `student_demand` | Öğrenci talebi |
| `occupancy_rate` | Kontenjan doluluğu |
| `graduate_employability` | Mezun istihdamı |
| `academic_staff_quality` | Akademik kadro yeterliliği |
| `financial_sustainability` | Mali sürdürülebilirlik |
| `cost_per_student` | Öğrenci başına maliyet |
| `revenue_contribution` | Gelire katkı |
| `research_output` | Araştırma üretimi |
| `industry_collaboration` | Sanayi iş birliği |
| `regional_contribution` | Bölgesel katkı |
| `strategic_alignment` | Stratejik uyum |

Ayrıca risk seviyeleri (`low/medium/high/critical` → düşük / orta / yüksek /
kritik) ve mekân türleri de Türkçeleştirildi. Bir jsdom kontrolü, senaryo
sonucunda İngilizce seviye adlarının görünmediğini doğruluyor.

Kriterler üç başlık altında gruplandı: **Öğrenci ve eğitim**,
**Kaynak ve mali yapı**, **Stratejik katkı**.

---

## 5. Eklenen filtre akışları

Ortak `OrgFilter` bileşeni şu davranışı zorunlu kılar:

- Fakülte seçilmeden bölüm listesi kilitlidir.
- Bölüm seçilmeden program listesi kilitlidir.
- Üst seçim değişirse alt seçimler sıfırlanır ve tekrar kilitlenir.
- Hiçbir sorgu, kullanıcı **Sonuçları Göster** düğmesine basmadan atılmaz.

**Filtrenin kullanıldığı ekranlar** (organizasyon kırılımı anlamlı olduğu için):
Program Sürdürülebilirliği, Akademik Başarı, Öğrenci Analitiği,
Akademik Personel.

**Filtrenin bilinçli olarak kullanılmadığı ekranlar** (kurum geneli görünüm
oldukları için): Finansal Analiz, Stratejik Göstergeler, Erken Uyarı,
Yönetim Panosu, Sıralama Değerlendirmesi. Bunlarda yalnızca dönem/yıl seçimi
vardır. İki jsdom kontrolü bu ekranlarda fakülte/bölüm filtresi
bulunmadığını doğrular.

---

## 6. Düzeltilen "0 / veri yok" hataları

| Sorun | Önce | Sonra |
|---|---|---|
| Bölgesel katkı endeksi | `0,00` · **riskli** | `73,00` · hedefte (gerçek kayıtlardan hesaplanıyor) |
| Üniversite-sanayi iş birliği endeksi | `0,00` · **riskli** | `76,09` · hedefte |
| Genel başarı ortalaması | %72,90 (iki sıfır ortalamayı aşağı çekiyordu) | %85,76 · "16 ölçülen gösterge üzerinden" notuyla |
| Ölçülmemiş gösterge | `0` döner, hedefin altında görünür | `null` döner, "veri eksik" rozetiyle gösterilir ve **ortalamaya girmez** |
| Eksik sürdürülebilirlik kriteri | `0 / 100` puan | "Veri bulunamadı" · eksik kriter sayısı tek satır özet + açılır detay |
| Veri tamlığı düşük program | Skor kesin sonuç gibi | %60 altında **ön değerlendirme** etiketi |
| Bütçe gerçekleşme oranı | Bütçe yoksa `0` | `null` |
| Toplam alan (m²) | Ölçüm yoksa `0` | `null` |

Kural şu: **ölçülmemiş bir şey sıfır değildir.** Sıfır bir ölçüm sonucudur,
eksik veri bir ölçüm eksikliğidir; ikisi arayüzde farklı gösterilir ve
ortalamalarda farklı işlem görür.

---

## 7. Performans iyileştirmeleri

- **İstek yapılmadan önce niyet beklenir.** Sürdürülebilirlik ekranı açılışta
  hiçbir sorgu atmaz; kullanıcı seçim yapıp düğmeye basınca tek bir istek gider.
  Önceden sayfa açılışında bütün programların skoru tek tek çekiliyordu.
- **Sekmeler tembel yüklenir.** KPI ekranında yalnızca görünen sekmenin verisi
  çekilir; `KPI_LOADED` kümesi aynı sekmenin tekrar yüklenmesini engeller.
- **Tek program seçildiğinde** liste uç noktası yerine doğrudan
  `/scores/{code}` çağrılır.
- **Uzun listeler kırpılır.** Personel sıralaması ilk 10, mekân listeleri
  ilk 5, risk listesi ilk 3 satır çizer; kalanı açılır bölümde — DOM'a
  yüzlerce satır birden basılmaz.
- **Yükleme iskeleti** kullanılır; ekran boş kalıp sonra sıçramaz.

---

## 8. Test sonuçları

Tüm paketler temiz bir veritabanı ve tam demo veri seti üzerinde çalıştırıldı.

```
Backend birim testleri        412 passed
Backend entegrasyon testleri   57 passed
Arayüz (jsdom) testleri        64 passed / 0 hatalı
------------------------------------------------
TOPLAM                        533 kontrol, 0 hata
```

Arayüz testine bu turda eklenen kontroller ve doğruladıkları kabul kriteri:

| Kontrol | Kriter |
|---|---|
| `sustainability: açılışta program listesi yok` | 1 |
| `sustainability: bölüm başlangıçta kilitli` / `fakülte seçilince bölüm açıldı` | 2 |
| `sustainability: program başlangıçta kilitli` / `bölüm seçilince program açıldı` | 3 |
| `sustainability: teknik alan adı görünmüyor` | 4 |
| `menüde modül numarası yok` | 5 |
| `sustainability: eksik kriterler tek satır özet` | 6 |
| `sustainability: eksik kriter 0 puan olarak gösterilmiyor` | 7 |
| `sustainability: sonuç geldi` (açıklamalı skor) | 8 |
| `sustainability: ağırlık tablosu ana ekranda değil` | 9 |
| `kpi: üç sekme var` / `Genel Bakış varsayılan açık` | 10 |
| `kpi: ana ekranda formül yığılmamış` / `tabloda 5 sütun` | 11 |
| `kpi: türetilmiş göstergeler gerçek değer gösteriyor` / `riskli işaretlenmiyor` | 12 |
| `senaryo: İngilizce risk seviyesi görünmüyor` | 13 |
| Backend paketlerinin tamamı | 14 |
| Yukarıdaki 20 yeni kontrol | 15 |

Ayrıca `finance` ve `alerts` ekranlarında fakülte/bölüm filtresi bulunmadığı
doğrulandı — filtrenin her sayfaya körlemesine eklenmediğinin kanıtı.

---

## Dokunulmayan alanlar

- **Hesaplama formülleri ve backend iş mantığı** — yalnızca etiketler ve
  eksik veri semantiği değişti; sayı üreten hiçbir formül düzenlenmedi.
- **Akıllı Asistan / LLM bölümü** — hiçbir dosyasına dokunulmadı. Sistem hâlâ
  bağlı bir dil modeli bulunmadığını açıkça bildiriyor ve sahte cevap üretmiyor.
- **Hiçbir veri kaldırılmadı** — ana ekrandan çıkarılan her bilgi bir açılır
  bölümde erişilebilir durumda.
