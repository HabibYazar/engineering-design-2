# Bilinen Sınırlamalar

Ürünün ne yapıp ne yapmadığı. Sunum sırasında sorulabilecek "bu gerçekten
çalışıyor mu" sorularının dürüst cevabı buradadır.

---

## 1. Uygulanmamış modüller

### Modül 12 — dâhil edilmedi

`halilhan/frontend/index.html` Modül 12'ye ait bir arayüz taslağıdır ancak
**karşılık gelen backend kodu ekip deposunda bulunmamaktadır**. Model, servis,
endpoint veya veri şeması yoktur.

**Karar:** Modül 12 ürüne dâhil edilmedi. Boş bir menü öğesi veya sahte veri
gösteren bir ekran eklenmedi. Dosya
`integration/archive_before_merge/halilhan_module12_frontend_original/`
altında korunmaktadır.

---

## 2. Veri seti

| Konu | Durum |
|---|---|
| Veri kaynağı | **Kurgusal.** `integration/shared_demo_data/` altındaki varsayımlardan üretilir. Gerçek bir kurumun verisi değildir. |
| Kurum adı | "Ankara Teknoloji Üniversitesi" — kurgusaldır |
| Öğrenci/personel kayıtları | İsimler rastgele havuzdan üretilir; gerçek kişi değildir |
| Mali rakamlar | Yapısı gerçekçi, değerleri kurgusaldır |
| Taban puanlar | ÖSYM ölçeğinde (0-500) ama gerçek ÖSYM verisi değildir |
| Kıyaslama kurumları | Kurgusaldır |

Veri kod içine gömülmemiştir; JSON dosyalarını değiştirip yeniden seed ederek
gerçek veriyle değiştirilebilir.

---

## 3. Yapay zekâ / LLM

**Sisteme bağlı hiçbir dil modeli yoktur ve sistem cevap üretmez.**

| Yapılmayan | Neden |
|---|---|
| LLM sağlayıcısı seçimi | Ekip kararı henüz verilmedi |
| OpenAI / Gemini / Claude / Ollama / Hugging Face bağlantısı | Sağlayıcı seçilmedi |
| API istemci paketi kurulumu | `requirements.txt` içine eklenmedi |
| API anahtarı | İstenmedi, koda yazılmadı |
| Doğal dil cevap üretimi | Model yok |
| Prompt tasarımı | Model yok |
| RAG / embedding / vector database | Sonraki aşama |
| Cevap üreten endpoint | Bilinçli olarak eklenmedi |

**Yapılanlar:** sağlayıcıdan bağımsız arayüz, veri erişim katmanı, bağlam
derleyici, sağlayıcı factory, şemalar, `.env.example`, durum ekranı.

`context_builder.py` içindeki konu eşleştirme **anahtar kelime tabanlıdır** ve
kodda, arayüzde ve bu belgede yapay zekâ olarak sunulmaz.

Ayrıntı: [`ASSISTANT_ARCHITECTURE.md`](ASSISTANT_ARCHITECTURE.md)

---

## 4. Modül 10 — sıralama üretmez

Modül 10 **gerçek THE, QS veya YÖK sıralaması hesaplamaz**. Ürettiği şey:

- Bu çerçevelerdeki göstergeler için kurumun ne kadar veriye sahip olduğu
  (veri hazırlık puanı)
- Mevcut veriye dayalı kurum içi performans puanı
- Uyum puanı = performans × hazırlık / 100

Gerçek sıralamalar bu kuruluşların kendi metodolojileri ve dış verileriyle
hesaplanır. Arayüzde bu uyarı ekranın en üstünde gösterilir.

---

## 5. Kimlik doğrulama ve yetkilendirme

| Sınırlama | Ayrıntı |
|---|---|
| **Oturumlar süreç belleğinde** | Sunucu yeniden başlatılınca tüm oturumlar düşer. Birden fazla worker ile çalıştırılırsa oturumlar paylaşılmaz. Üretimde Redis veya veritabanı tablosu gerekir. |
| **Oturum süresi dolmuyor** | Jetonun son kullanma tarihi yoktur. |
| **Rol bazlı veri filtreleme yok** | Roller ve yetkiler tanımlı, arayüz `manage_users` yetkisine göre bölüm gizliyor. Ancak **API tarafında** bir dekanın yalnızca kendi fakültesinin verisini görmesi henüz kısıtlanmıyor. Bu bilinçli bir eksiktir; yarım bir kısıtlama güvenlik yanılsaması yaratırdı. |
| **Endpoint'ler kimlik doğrulama istemiyor** | Jeton üretiliyor ve doğrulanabiliyor ancak diğer endpoint'lerde zorunlu değil. Demo kolaylığı için; üretimde `Depends(require_auth)` eklenmeli. |
| **Parola politikası yok** | Minimum 4 karakter dışında kural yok. |
| **Parola sıfırlama yok** | — |
| Demo parolaları herkese açık | `07_system_users.json` içinde. Gerçek kuruluma taşınmamalı. |

**Yapılan:** parolalar PBKDF2-HMAC-SHA256 ile saltlanıp özetlenir, sabit süreli
karşılaştırılır, hiçbir API cevabında yer almaz; kullanıcı devre dışı
bırakılınca açık oturumları düşer.

---

## 6. Performans

| Konu | Ölçüm | Not |
|---|---|---|
| Erken Uyarı ekranı | ~2,5 sn | Kural motoru 14 program × 4000 öğrenci üzerinde çalışıyor. Yükleme göstergesi var. Önbellek veya önceden hesaplama ile iyileştirilebilir. |
| `/api/early-warning/alerts` | ~0,65 sn | Aynı sebep |
| `/api/program-sustainability/scores` | ~1,0 sn | Aynı sebep |
| Diğer endpoint'ler | <0,1 sn | — |
| Seed | ~4 sn | 4.466 kayıt |
| SQLite | Tek yazar | Demo için yeterli; çok kullanıcılı üretimde PostgreSQL gerekir |
| Sayfalama | `limit` en fazla 500 | Bazı analiz endpoint'leri iç sorguda 10.000 satır çekiyor |

---

## 7. Arayüz

| Sınırlama | Ayrıntı |
|---|---|
| Grafikler SVG ile elle çizilir | Zoom, pan, dışa aktarma yoktur. Harici kütüphane kullanılmadığı için (CDN yasağı) bilinçli tercih. |
| Yazdırma / PDF dışa aktarma yok | — |
| Excel dışa aktarma yok | İçe aktarma var (Modül 13), dışa aktarma yok |
| Arayüz dili Türkçe | Veritabanındaki bazı adlar (fakülte, bölüm, program) İngilizce — Habib'in orijinal seed'inden geliyor |
| Bazı ekranlarda düzenleme yok | Öğrenci, personel, mekân, KPI için API'de tam CRUD var ancak arayüzde yalnızca Üniversite Yapısı ve Kullanıcı ekranlarında oluşturma formu var |
| Tarayıcı desteği | Modern tarayıcılar (ES2020, `??=`, `?.`). IE desteklenmez. |
| Mobil | Responsive ancak asıl hedef masaüstü/projeksiyon |

---

## 8. Teknik borçlar

| Borç | Etki | Öneri |
|---|---|---|
| Migration aracı yok | Şema değişince `init_db()` yalnızca eksik tabloyu ekler; **kolon ekleme/değiştirme uygulanmaz** | Alembic eklenmeli |
| Modül 3'ün varsayılan yılı sabit | `DEFAULT_ACADEMIC_YEAR = "2026-2027"` — ortak veride bu yıl boş olduğu için arayüz yılı açıkça gönderiyor | Yapılandırmadan okunmalı |
| `data_access.CURRENT_ACADEMIC_YEAR` sabit | Asistan katmanında "2025-2026" gömülü | Ortak yapılandırmaya taşınmalı |
| `CURRENT_YEAR` arayüzde sabit | `views-overview.js` içinde | `/api/assumptions` gibi bir endpoint'ten okunabilir |
| Fakülte/bölüm adları İngilizce | Arayüz Türkçe, veriler karışık | Ortak veri setinde Türkçeleştirilebilir |
| Modül 3 ve Modül 2 örtüşüyor | İkisi de öğrenci analitiği üretiyor, farklı formüllerle | Uzun vadede tek servis altında birleştirilmeli |
| Arayüzde birim testi yok | 31 uçtan uca kontrol var, fonksiyon bazlı test yok | — |
| `pytest` iki ayrı dizin | `tests/` ve `tests_integration/` ayrı conftest kullanıyor | Ortak veri seti birim testlerini bozmasın diye bilinçli |
| Hata mesajları yalnızca Türkçe | — | i18n gerekirse eklenmeli |

---

## 9. Test kapsamı dışında kalanlar

- Yük / stres testi yapılmadı
- Güvenlik taraması (OWASP) yapılmadı
- Tarayıcı uyumluluk matrisi çıkarılmadı
- Ekran görüntüsü tabanlı görsel regresyon testi yok (jsdom kullanıldığı için
  CSS render doğrulanmıyor; DOM içeriği doğrulanıyor)
- Eşzamanlı kullanıcı senaryosu test edilmedi

---

## 10. Özet — ne çalışıyor, ne çalışmıyor

### Çalışıyor

- 13 modülün tamamı tek backend'de, 181 endpoint
- 14 ekran gerçek API verisiyle
- Tek veritabanı, tek ortak veri seti, idempotent seed
- Gerçek kimlik doğrulama, özetlenmiş parolalar
- Veri aktarımı önizleme + satır bazlı hata raporu
- Senaryo simülasyonu (Decimal hassasiyetle)
- Kural tabanlı erken uyarı
- 432 pytest testi + 31 arayüz kontrolü
- Tek komutla çalıştırma

### Çalışmıyor / eksik

- Modül 12 (backend kodu yok)
- LLM cevap üretimi (bilinçli — model seçilmedi)
- Rol bazlı API veri filtreleme
- Kalıcı oturum yönetimi
- Şema migration aracı
- Dışa aktarma (PDF/Excel)
