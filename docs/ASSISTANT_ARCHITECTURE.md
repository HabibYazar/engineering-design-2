# Akıllı Asistan Mimarisi

> **Bu sistemde hiçbir dil modeli bağlı DEĞİLDİR ve sistem cevap ÜRETMEZ.**
> Bu belge, ileride seçilecek model için hazırlanan altyapıyı anlatır.

---

## 1. Neden şimdi model bağlanmadı?

Proje ekibi henüz bir dil modeli sağlayıcısına karar vermemiştir. Bu karar
verilmeden sağlayıcı bağlamak iki soruna yol açardı:

1. **Yanlış bağlanma maliyeti.** Her modülün kendi çağrı biçimini yazması,
   sağlayıcı değiştiğinde uygulamanın her yerinin elden geçirilmesi demektir.
2. **Dürüstlük.** Kural tabanlı bir eşleştirici yazıp "yapay zekâ" olarak
   sunmak, sunumda cevaplanamayacak sorular doğururdu.

Bu yüzden yapılan iş, **modelden bağımsız** bir iskelet kurmakla sınırlı
tutuldu. Model seçildiğinde yalnızca tek bir sınıf yazılacak.

---

## 2. Tamamlananlar / Tamamlanmayanlar

### Tamamlananlar

| Bileşen | Dosya | Durum |
|---|---|---|
| Sağlayıcıdan bağımsız arayüz | `app/services/assistant/base.py` | Hazır |
| Kurumsal veri erişim katmanı | `app/services/assistant/data_access.py` | Hazır — 8 toplayıcı |
| Bağlam derleyici | `app/services/assistant/context_builder.py` | Hazır — 6 konu |
| Sağlayıcı seçici (factory) | `app/services/assistant/provider_factory.py` | Hazır — kayıt defteri boş |
| Veri sözleşmeleri | `app/services/assistant/schemas.py` | Hazır |
| Ortam yapılandırma iskeleti | `.env.example` | Hazır — boş değişkenler |
| Arayüz ekranı | `frontend/assets/views-overview.js` | Hazır — durumu şeffaf gösteriyor |
| Durum/mimari endpoint'leri | `app/routers/assistant.py` | Hazır — 4 endpoint |

### Tamamlanmayanlar (bilinçli)

- LLM model seçimi
- Sağlayıcı entegrasyonu (somut `AssistantProvider` uygulaması)
- Doğal dil cevap üretimi
- Prompt tasarımı
- RAG
- Embedding üretimi
- Vector database
- Model değerlendirmesi
- **Gerçek assistant cevap endpoint'i**

---

## 3. Katmanlar

```
Kullanıcı sorusu
      │
      ▼
POST /api/assistant/prepare-context      app/routers/assistant.py
      │
      ▼
context_builder.build_context()          Soruyu KONUYA eşler
      │                                   (anahtar kelime — yapay zekâ değil)
      ▼
data_access.TOPIC_COLLECTORS[konu]       Konuya göre veri toplayıcıları
      │
      ▼
Mevcut servis katmanları                 student_analytics_service
      │                                   finance_service, kpi_service,
      ▼                                   academic_staff_service, ...
Ortak veritabanı (salt okunur)
      │
      ▼
List[ContextItem]  ──────────────────►  ╔══════════════════════════╗
                                        ║  BURADA DURUYOR          ║
                                        ║  Model bağlanınca bağlam ║
                                        ║  buradan modele gidecek  ║
                                        ╚══════════════════════════╝
```

### `base.py` — sağlayıcı sözleşmesi

```python
class AssistantProvider(ABC):
    name: str

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def generate(self, question: str, context: List[ContextItem]) -> str: ...
```

Ayrıca `NoProviderConfigured` sınıfı vardır. `is_available()` daima `False`
döner ve `generate()` çağrılırsa **hata fırlatır** — sessizce sahte bir metin
döndürmez.

### `data_access.py` — veri erişimi

Asistan doğrudan modellere veya SQL'e dokunmaz. Erişim tek katmandan geçer;
böylece ileride "asistan hangi verileri görebilir" sorusuna (rol bazlı
kısıtlama, hassas alanların dışarıda bırakılması) tek bir yerde cevap verilebilir.

**Katman salt okunurdur.** Hiçbir veri yazmaz.

Toplayıcılar (gerçek servis fonksiyonlarını çağırırlar, veri kopyalamazlar):

| Fonksiyon | Kaynak modül | Kullandığı servis |
|---|---|---|
| `student_overview()` | Modül 2 | `student_analytics_service.build_overview()` |
| `program_demand()` | Modül 2 | `student_analytics_service.build_program_analytics()` |
| `sustainability_scores()` | Modül 7 | `sustainability_service.evaluate_all()` |
| `financial_summary()` | Modül 6 | `finance_service.financial_summary()` |
| `kpi_scorecard()` | Modül 8 | `kpi_service.scorecard()` |
| `staff_performance()` | Modül 4 | `academic_staff_service.staff_overview()` |
| `capacity_overview()` | Modül 5 | `physical_resources_service.capacity_overview()` |
| `early_warnings()` | Modül 11 | `early_warning_rule_engine.evaluate()` |
| `ranking_readiness()` | Modül 10 | `FrameworkAssessment` sorgusu |

Bir modül veri döndüremezse bağlam boşa çıkmaz; o satır `"veri yok"` olarak
işaretlenir. **"Veri yok" ile "sıfır" ayrımı burada da korunur** — modele boş
değer yerine durumu anlatan bir metin gider.

### `context_builder.py` — konu eşleştirme

Soru, anahtar kelime sözlüğüyle bir konuya eşlenir. **Bu bir yapay zekâ
değildir ve öyle sunulmaz.** Sistem soruyu "anlamaz", yalnızca hangi verilerin
toplanacağına karar verir.

| Konu | Örnek tetikleyiciler | Toplanan veriler |
|---|---|---|
| öğrenci talebi | öğrenci, doluluk, kontenjan, talep, taban puan | M2 özet + M2 program doluluk + M7 skorlar |
| mali durum | gelir, gider, bütçe, maliyet, burs, açık | M6 özet + M8 karne |
| akademik performans | yayın, atıf, araştırma, proje, patent | M4 özet + M10 değerlendirme |
| fiziksel kapasite | derslik, laboratuvar, kapasite, mekân, alan | M5 özet + M2 özet |
| risk ve uyarı | risk, uyarı, kritik, düşüş, erken uyarı | M11 uyarılar + M7 skorlar |
| performans göstergeleri | kpi, gösterge, hedef, karne, stratejik | M8 karne + M10 değerlendirme |
| *(eşleşme yok)* | — | M2 + M6 + M8 + M11 genel |

Her soruda tüm veritabanını taramak hem yavaş olurdu hem de modele gereksiz
gürültü gönderirdi.

Hiçbir anahtar kelime tutmazsa `matched_topic` **`null`** döner — sistem
eşleşme olduğunu iddia etmez.

### `provider_factory.py` — sağlayıcı seçimi

Bu dosya **hiçbir sağlayıcı paketini import etmez** ve hiçbir ağ çağrısı
yapmaz. Ortam değişkenlerini okur:

```python
PROVIDER_REGISTRY: Dict[str, Type[AssistantProvider]] = {}   # şu anda BOŞ
```

Kayıt defteri boş olduğu için `get_provider()` her durumda
`NoProviderConfigured()` döndürür.

`get_status()` kullanıcıya gösterilecek durumu üretir. **API anahtarının
kendisi asla döndürülmez**; yalnızca tanımlı olup olmadığı bildirilir —
anahtarı cevaba koymak onu tarayıcı geçmişine ve günlüklere sızdırırdı.

---

## 4. API

| Endpoint | Ne yapar | Cevap üretir mi? |
|---|---|---|
| `GET /api/assistant/status` | Yapılandırma durumu | Hayır |
| `GET /api/assistant/sample-questions` | 6 örnek soru | Hayır |
| `POST /api/assistant/prepare-context` | Soru için kurumsal veriyi toplar | **Hayır** |
| `GET /api/assistant/architecture` | Bileşen durumu + bağlanma adımları | Hayır |

`/api/assistant/ask` benzeri bir endpoint **bilinçli olarak yoktur**.

`prepare-context` cevabındaki `notice` alanı her seferinde şunu içerir:

> Bu bir dil modeli cevabı DEĞİLDİR. Sisteme bağlı bir LLM bulunmadığı için
> sistem cevap üretmez; aşağıda yalnızca sorunuza cevap verilebilmesi için
> gerekli olan kurumsal veriler listelenmiştir.

---

## 5. Arayüz ekranı

`http://127.0.0.1:8000/#/assistant`

Ekran şunları gösterir:

1. **Durum kartları** — `ASSISTANT_ENABLED`, `LLM_PROVIDER`, `LLM_MODEL`,
   API anahtarı tanımlı mı. Değerler arayüzde sabit yazılmaz; sunucudan gelir.
2. **Açık uyarı** — dil modelinin bağlı olmadığı ve sistemin cevap üretmediği.
3. **Soru kutusu + örnek sorular** — "Bağlamı hazırla" düğmesi.
4. **Hazırlanan bağlam** — eşleşen konu ve toplanan gerçek veri tablosu; her
   satırda hangi modülden geldiği yazılı.
5. **Mimari tablosu** — hangi bileşenin hazır, hangisinin eksik olduğu.
6. **Bağlanma adımları** — model seçildiğinde yapılacaklar.

Ekranda sağlayıcı veya model adı **uydurulmaz**, örnek AI cevabı verilmez.

### Örnek sorular

Bunlar "sistemin cevaplayabildiği sorular" değil, **"sistemin doğru veriyi
toplayabildiği sorulardır"**. Fark önemlidir ve arayüzde de böyle anlatılır.

- Hangi programların doluluk oranı düşüyor?
- Öğrenim ücreti %10 artarsa gelir ve burs yükü nasıl etkilenir?
- Araştırma performansı en zayıf olan alanlar hangileri?
- Derslik ve laboratuvar kapasitesi yeterli mi?
- Şu anda hangi kritik riskler var?
- Stratejik hedeflere ulaşma durumumuz nedir?

---

## 6. Güvenlik ve API anahtarı yönetimi

| Kural | Uygulama |
|---|---|
| Anahtar kaynak koda yazılmaz | `.env.example` içinde `LLM_API_KEY=` (boş) |
| `.env` sürüm kontrolüne girmez | `.gitignore` içinde |
| Anahtar API cevaplarında dönmez | Yalnızca `api_key_configured: bool` |
| Anahtar günlüklere yazılmaz | `provider_factory` anahtarı hiç loglamaz |
| Sağlayıcı yoksa istek reddedilir | `NoProviderConfigured.generate()` hata fırlatır |

Entegrasyon testi (`test_no_api_key_in_source_code`) tüm `.py` dosyalarını
tarayıp `sk-...`, `AIza...` ve `api_key = "..."` kalıplarını arar.

---

## 7. Model bağlandığında yapılacaklar

1. Ekip olarak bir sağlayıcıya karar verin. **Bu karar bu projede bilinçli
   olarak verilmemiştir.**
2. Sağlayıcının istemci paketini `requirements.txt` dosyasına ekleyin.
3. `AssistantProvider` arayüzünü uygulayan bir sınıf yazın:

   ```python
   class MyProvider(AssistantProvider):
       name = "..."
       def is_available(self) -> bool: ...
       def generate(self, question, context) -> str: ...
   ```

4. `provider_factory.PROVIDER_REGISTRY` sözlüğüne kaydedin. **Başka hiçbir
   yeri değiştirmeniz gerekmez.**
5. `.env` dosyanıza `LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY` girin.
   Anahtarı asla kaynak koda veya Git'e yazmayın.
6. `ASSISTANT_ENABLED=true` yapın ve `/api/assistant/status` ile sağlayıcının
   kullanılabilir göründüğünü doğrulayın.
7. Cevap üreten endpoint'i (`POST /api/assistant/ask`) **ancak bu adımlardan
   sonra** ekleyin.

### Sonraki aşama olarak dokümante edilenler

RAG, embedding ve vector database bu projede kurulmamıştır. Kurulacaksa
`data_access.py` katmanı doğal başlangıç noktasıdır: şu anda yapılandırılmış
göstergeler döndürüyor; ileride aynı katman doküman parçaları da döndürebilir.
