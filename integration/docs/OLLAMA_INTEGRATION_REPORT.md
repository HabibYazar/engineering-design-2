# Akıllı Asistan — Yerel Ollama Entegrasyonu Raporu

Akıllı Asistan artık gerçek bir dil modeliyle çalışıyor. Model kullanıcının
kendi makinesinde Ollama üzerinden koşar; hiçbir bulut servisine istek
gönderilmez ve hiçbir API anahtarı kullanılmaz.

---

## 1. İncelenen mevcut mimari

Entegrasyondan önce asistan katmanı beş dosyadan oluşuyordu ve **bilinçli
olarak modelsizdi**:

| Dosya | Durumu |
|---|---|
| `base.py` | `AssistantProvider` soyut arayüzü + `NoProviderConfigured`. Somut uygulaması yoktu. |
| `provider_factory.py` | Kayıt defteri **boştu**; her yapılandırma `NoProviderConfigured` döndürüyordu. |
| `data_access.py` | Kurumsal veriye salt okunur erişim — çalışır durumdaydı. |
| `context_builder.py` | Soruyu anahtar kelimeyle bir konuya eşleyip veri derliyordu. Yapay zekâ değil. |
| `schemas.py` | Durum ve bağlam sözleşmeleri. |

Uç noktalar: `/status`, `/sample-questions`, `/prepare-context`,
`/architecture`. Cevap üreten bir uç nokta yoktu — eski entegrasyon testi
`ask|answer|chat|complete|generate` içeren bir yol bulursa **başarısız
oluyordu**.

Frontend (`views-overview.js` içinde) "dil modeli bağlı değil" durumunu
gösteriyor ve `/prepare-context` çıktısını tablo olarak basıyordu. Sahte cevap
yoktu.

**Değerlendirme:** arayüz sözleşmesi (`AssistantProvider`) ve katman ayrımı
zaten doğru kurulmuştu, dolayısıyla yeniden yazmak gerekmedi. Sözleşme
korunarak somut bir sağlayıcı eklendi.

---

## 2. Değiştirilen ve oluşturulan dosyalar

### Yeni

| Dosya | Satır | İçerik |
|---|---|---|
| `app/services/assistant/ollama_provider.py` | ~390 | `OllamaProvider`, `AssistantProviderError`, `ProviderHealth`, düşünme metni ayıklama, akış filtresi. |
| `app/services/assistant/chat_service.py` | ~250 | Türkçe sistem yönergesi, `ConversationStore`, doğrulama, `answer()` / `stream_answer()` / `status()`. |
| `frontend/assets/views-assistant.js` | ~330 | Gerçek sohbet ekranı, durum rozetleri, güvenli metin gösterimi. |
| `backend/tests/test_assistant_ollama.py` | ~570 | 37 test, tamamı taklit HTTP istemcisiyle. |
| `backend/tests/test_assistant_ollama_live.py` | ~95 | Gerçek Ollama gerektiren 4 test; varsayılan olarak atlanır. |

### Değiştirilen

| Dosya | Değişiklik |
|---|---|
| `app/core/config.py` | 9 yeni ayar (aşağıda). Değerler **yalnızca burada** tanımlı. |
| `app/services/assistant/provider_factory.py` | Kayıt defterine `"ollama": OllamaProvider` eklendi; ortam değişkeni okuma yerine `settings` kullanılıyor. |
| `app/services/assistant/schemas.py` | `AssistantStatus` yeniden yazıldı; `ChatRequest` ve `ChatResponse` eklendi. |
| `app/routers/assistant.py` | `/chat` ve `/chat/stream` eklendi; `/status` yeni şemaya geçti; `/architecture` güncellendi. |
| `backend/.env.example` | LLM_API_KEY alanı **kaldırıldı** (yerel model anahtar istemez); Ollama ayarları ve kurulum adımları eklendi. |
| `backend/requirements.txt` | `httpx` açıkça eklendi. |
| `frontend/index.html` | `views-assistant.js` kaydedildi, `views-overview.js` kaldırıldı, sürüm `?v=10`. |
| `frontend/assets/integration.css` | +150 satır sohbet arayüzü stili. |
| `run_project.ps1` | 6. adım olarak Ollama kontrolü eklendi. |
| `backend/tests_integration/test_integration_all_modules.py` | "model bağlı olmamalı" testleri "yerel model kullanılmalı, sahte cevap üretilmemeli" testleriyle değiştirildi. |
| `tests_ui/test_frontend.js` | 10 yeni asistan kontrolü. |
| `frontend/assets/views-overview.js` | **Silindi** — içeriği `views-assistant.js`'e taşındı. |

---

## 3. Ollama provider yapısı

```
Router (assistant.py)
  │  doğrulama, HTTP durum kodu çevirisi
  ▼
chat_service.py
  │  sistem yönergesi, konuşma geçmişi, mesaj doğrulama
  ▼
ollama_provider.py
  │  yalnızca ağ çağrısı ve cevap ayrıştırma
  ▼
http://127.0.0.1:11434
```

Router doğrudan Ollama'yı çağırmaz. Sağlayıcı değişirse yalnızca alt katman
değişir.

**`OllamaProvider` sorumlulukları:**

| Metot | İşi |
|---|---|
| `list_models()` | `GET /api/tags` — kurulu modelleri döndürür. Servis kapalıysa hata fırlatır (boş liste **döndürmez**; "model yok" ile "servis kapalı" farklı durumlardır). |
| `health()` | Servis + model kontrolü. **Hata fırlatmaz** — ekran açılışında çağrılır. |
| `is_available()` | Arayüz sözleşmesi. |
| `chat(messages)` | `POST /api/chat`, tek seferde cevap. `(görünen, düşünme)` döndürür. |
| `stream_chat(messages)` | Akışlı üretim; parça üreteci. |
| `generate(question, context)` | Eski arayüz imzası (geriye uyum). |

**Düşünme metni ayıklama.** Qwen ailesi cevaptan önce muhakeme üretir. Ollama
bunu iki biçimde döndürebilir ve **her ikisi de** ele alınır:

1. Ayrı `message.thinking` alanı → hiç okunmaz, cevaba konmaz.
2. Metin içinde `<think>…</think>` → `split_thinking()` ayıklar.
3. Yarıda kesilmiş `<think>` (kapanış etiketi yok) → kalan her şey düşünme sayılır.
4. **Akışta**: parça parça gelen `<thi` + `nk>` gibi bölünmüş etiketler için
   tampon tutulur; blok bitene kadar hiçbir şey yayınlanmaz.

Model yalnızca muhakeme üretirse boş balon gösterilmez; kontrollü hata döner.

**Proxy koruması.** `httpx` varsayılan olarak `HTTP_PROXY` / `ALL_PROXY`
ortam değişkenlerini kullanır. Bu, `127.0.0.1`'e giden isteği bile proxy'ye
yönlendirir. `_local_client()` bunu `trust_env=False` ile kapatır — hem
bağlantı kırılmasını hem de "veri makineden çıkmaz" güvencesinin bozulmasını
önler. *(Bu açık, geliştirme sırasında sanal ortamdaki bir SOCKS proxy ayarı
sayesinde ortaya çıktı ve testle sabitlendi.)*

---

## 4. Eklenen endpointler

### `GET /api/assistant/status`

Ollama kapalıyken de **200** döner:

```json
{
  "provider": "ollama",
  "model": "qwen3.5:9b",
  "enabled": true,
  "service_available": true,
  "model_available": true,
  "ready": true,
  "message": "Yapay zekâ hazır — qwen3.5:9b",
  "installed_models": ["qwen3.5:9b"]
}
```

### `POST /api/assistant/chat`

```json
{ "message": "Merhaba", "conversation_id": null, "stream": false }
```

```json
{
  "conversation_id": "37aa7595-ee2b-44e1-8848-37564cfc3d2f",
  "answer": "Merhaba! Ben Ankara Bilim Üniversitesi karar destek asistanıyım…",
  "provider": "ollama",
  "model": "qwen3.5:9b",
  "used_tools": [],
  "data_source": "general_model_knowledge"
}
```

`extra="forbid"`: bilinmeyen alan gönderilirse 422 döner. Bu proje daha önce
sessizce yok sayılan alan adı uyuşmazlığından zarar gördüğü için bilinçli.

### `POST /api/assistant/chat/stream`

Server-Sent Events:

```
data: {"type": "chunk", "text": "Merhaba "}
data: {"type": "chunk", "text": "dünya."}
data: {"type": "done", "conversation_id": "a22a9c8a-…"}
```

Akış başladıktan sonra HTTP durum kodu değiştirilemediği için hata da akışın
içinde bildirilir: `{"type": "error", "message": "…"}`.

Korunan uç noktalar: `/sample-questions`, `/prepare-context`, `/architecture`.

---

## 5. Frontend değişiklikleri

Ekran gerçek bir sohbet arayüzüne dönüştü: durum rozeti, mesaj balonları,
çok satırlı giriş (Enter gönderir, Shift+Enter satır atlar), karakter sayacı,
"Yeni konuşma" düğmesi.

**Durum metinleri** — belirsiz "API bağlı" ifadesi kaldırıldı:

| Durum | Gösterilen |
|---|---|
| Yükleniyor | Bağlantı kuruluyor… |
| Hazır | **Yapay zekâ hazır — qwen3.5:9b** |
| Servis kapalı | Ollama servisine ulaşılamıyor + `ollama serve` ipucu |
| Model yok | Model kurulu değil + `ollama pull qwen3.5:9b` ipucu |
| Yapılandırma kapalı | Akıllı Asistan devre dışı |
| Üretim sürüyor | Yanıt oluşturuluyor… |
| Hata | Hata oluştu + sunucudan gelen sebep |

Model hazır değilken giriş alanı ve gönder düğmesi kilitlenir — kullanıcı
cevap alamayacağı bir isteği göndermeye çalışmaz.

**Güvenli gösterim.** Model çıktısı asla ham HTML olarak basılmaz. `safeText()`
**önce** her şeyi kaçırır, **sonra** sınırlı bir biçimlendirme uygular
(paragraf, satır sonu, madde listesi, `**kalın**`, `` `kod` ``). Sıra tersine
çevrilseydi modelin ürettiği bir `<script>` sayfaya girerdi.

---

## 6. Kullanılan ortam ayarları

Hepsi `app/core/config.py` içinde **tek kez** tanımlıdır; provider, servis ve
router `settings` üzerinden okur.

| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `ASSISTANT_ENABLED` | `true` | Asistanı tamamen kapatır. |
| `LLM_PROVIDER` | `ollama` | Tanımlı tek değer. |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Yerel adres. |
| `OLLAMA_MODEL` | `qwen3.5:9b` | Kurulu olması gerekir. |
| `OLLAMA_TIMEOUT_SECONDS` | `120` | İlk çağrıda model belleğe yüklenir. |
| `OLLAMA_CONTEXT_LENGTH` | `8192` | `num_ctx`. |
| `OLLAMA_TEMPERATURE` | `0.2` | Yönetim raporunda tutarlılık > yaratıcılık. |
| `ASSISTANT_MAX_MESSAGE_LENGTH` | `4000` | Kullanıcı mesajı üst sınırı. |
| `ASSISTANT_MAX_CONVERSATIONS` | `100` | Bellekteki konuşma sayısı (LRU). |
| `ASSISTANT_MAX_HISTORY_MESSAGES` | `20` | Konuşma başına taşınan mesaj. |

`.env.example`'dan **`LLM_API_KEY` kaldırıldı** — yerel model anahtar
gerektirmez, dosyada durması yanlış beklenti yaratırdı.

---

## 7. Hata yönetimi

| Durum | HTTP | Kullanıcıya gösterilen |
|---|---|---|
| Ollama kapalı | 503 | "Yerel yapay zekâ servisine ulaşılamıyor. Ollama'nın çalıştığından emin olun." |
| Model kurulu değil (404) | 503 | "qwen3.5:9b modeli bulunamadı. ollama pull qwen3.5:9b komutuyla modeli kurun." |
| Zaman aşımı | 504 | "Yerel model yanıt vermedi (zaman aşımı)…" |
| Bozuk/eksik cevap | 502 | "Yerel modelden geçerli bir yanıt alınamadı…" |
| Boş mesaj | 422 | "Mesaj boş olamaz." |
| Çok uzun mesaj | 422 | "Mesaj çok uzun. En fazla 4000 karakter…" |
| Bilinmeyen alan | 422 | Pydantic doğrulama hatası |

Ek dayanıklılık:

- `/status` **asla** hata fırlatmaz. Beklenmeyen bir istisna bile
  (`ImportError`, bozuk proxy) yakalanır; ekran açılır, durum "hazır değil"
  görünür.
- Asistan bozukken diğer 15 ekran ve `/health` çalışmaya devam eder — testle
  doğrulanır.
- Sunucu günlüğüne kullanıcı mesajının **tamamı yazılmaz**; yalnızca konuşma
  kimliğinin ilk 8 karakteri, geçmiş uzunluğu ve mesaj uzunluğu.
- Düşünme metni günlüğe de içerik olarak yazılmaz, yalnızca karakter sayısı.
- Konuşma deposu LRU'dur; uzun süre açık kalan sunucuda bellek şişmez.

---

## 8. Test sonuçları

```
Backend birim testleri          449 passed, 4 skipped
  └─ tests/test_assistant_ollama.py        37 passed
  └─ tests/test_assistant_ollama_live.py    4 skipped (isteğe bağlı)
Backend entegrasyon testleri     59 passed
Arayüz (jsdom) testleri         103 passed / 0 hatalı
--------------------------------------------------
TOPLAM                          611 kontrol, 0 hata
```

İstenen 12 senaryonun karşılığı:

| # | Senaryo | Test |
|---|---|---|
| 1 | Ollama kapalıyken status | `test_status_when_ollama_is_down` |
| 2 | Model kurulu değilken status | `test_status_when_model_is_not_installed` |
| 3 | Model hazırken status | `test_status_when_model_is_ready` |
| 4 | Boş mesaj | `test_empty_message_is_rejected` (3 varyant) + `test_empty_message_never_reaches_the_model` |
| 5 | Çok uzun mesaj | `test_too_long_message_is_rejected` + `test_service_layer_also_enforces_length_limit` |
| 6 | Provider timeout | `test_provider_timeout_returns_gateway_timeout` + `test_timeout_uses_configured_value` |
| 7 | Ollama hata cevabı | `test_ollama_404_is_reported_as_missing_model`, `…_500_…`, `test_malformed_ollama_payload_is_rejected`, `test_connection_error_…` |
| 8 | Normal chat | `test_successful_chat_returns_model_answer` + yönerge/geçmiş/ayar testleri |
| 9 | Thinking sızmaması | `test_inline_thinking_block_is_stripped`, `test_separate_thinking_field_is_not_returned`, `test_unclosed_thinking_block_is_stripped`, `test_answer_with_only_thinking_is_an_error`, `test_streaming_filters_thinking` |
| 10 | Frontend durum metinleri | `test_frontend_has_explicit_status_texts`, `test_frontend_does_not_use_vague_api_connected_text` + 10 jsdom kontrolü |
| 11 | Mock kalmadığı | `test_no_mock_provider_remains`, `test_frontend_has_no_canned_answers`, `test_no_cloud_llm_provider_is_used`, `test_ollama_base_url_is_local`, `test_local_client_ignores_proxy_environment` |
| 12 | Uygulamayı çökertmeme | `test_status_survives_unexpected_provider_failure`, `test_other_endpoints_still_work_when_ollama_is_down`, `test_streaming_endpoint_reports_errors_inside_the_stream` |

**Uçtan uca doğrulama.** Ollama'nın API sözleşmesini taklit eden geçici bir
HTTP sunucusuyla gerçek ağ üzerinden akış denendi: durum `ready: true`,
`/chat` düşünme bloğu ayıklanmış cevap döndürdü, `/chat/stream` yalnızca
görünen parçaları yayınladı, jsdom testinde cevap balona yazıldı ve muhakeme
metni ekranda görünmedi.

**İsteğe bağlı canlı test:**

```bash
ollama serve
ollama pull qwen3.5:9b
ASSISTANT_LIVE_TEST=1 pytest tests/test_assistant_ollama_live.py -v
```

Bu testler Türkçe cevap verildiğini, düşünme metninin sızmadığını ve **modelin
kurum verisi istendiğinde sayı uydurmadığını** kontrol eder — sistem
yönergesinin gerçekten işe yarayıp yaramadığını ölçen tek testtir.

---

## 9. Uygulamayı çalıştırma

```powershell
# 1) Ollama (bir kez)
#    https://ollama.com adresinden kurun
ollama pull qwen3.5:9b
ollama serve        # çoğu kurulumda arka planda kendiliğinden çalışır

# 2) Proje
.\run_project.ps1
```

`run_project.ps1` 6. adımda Ollama'yı kontrol eder ve **projeyi durdurmaz**:

- Model kurulu: `Ollama calisiyor ve qwen3.5:9b kurulu. Akilli Asistan hazir.`
- Model eksik: `Uyari: qwen3.5:9b modeli bulunamadi.` + kurulum komutu + kurulu modeller
- Ollama kapalı: `Uyari: Ollama calismiyor. Akilli Asistan devre disi baslayacak.`

Ollama **otomatik başlatılmaya çalışılmaz**; servis yönetici yetkisi
gerektirebilir ve kullanıcının makinesinde arka plan servisi başlatmak bu
betiğin işi değildir.

Ollama olmadan da proje tam çalışır: 15 ekranın hepsi açılır, yalnızca Akıllı
Asistan "servise ulaşılamıyor" durumunu gösterir.

Doğrulama: `.\run_project.ps1 -RunTests`

---

## 10. Bilinen eksikler

Bu aşamada **bilinçli olarak yapılmayanlar** (bir sonraki aşamaya bırakıldı):

- **Araç çağrısı (tool calling) yok.** Model veritabanını sorgulayamaz,
  senaryo motorunu çalıştıramaz. "Bilgisayar Mühendisliği öğrenci sayısı %15
  artarsa ne olur?" sorusuna sayı vermez; hangi verilere ihtiyaç duyduğunu
  söyler. Sistem yönergesi bunu açıkça dayatır.
- **`context_builder` modele bağlı değil.** Hazır ama ayrı duruyor;
  `/architecture` uç noktası bunu "eksik" olarak raporlar.
- **RAG, embedding, vector database yok.**
- **Dinamik UI üretimi yok.**
- **Konuşmalar kalıcı değil.** Bellekte tutulur, sunucu yeniden başlayınca
  silinir. Kullanıcı mesajlarını veritabanına yazmak ayrı bir gizlilik kararı
  gerektirir.
- **Arayüz akışlı uç noktayı henüz kullanmıyor.** `/chat/stream` çalışır ve
  testlidir; ekran şimdilik tek seferlik `/chat` çağırır. İlk çağrının 120
  saniyeye kadar sürebildiği düşünülürse akışa geçmek gözle görülür bir
  iyileştirme olacaktır.
- **Model adı doğrulanmadı.** `qwen3.5:9b` yapılandırmadan gelir. Bu etiket
  Ollama kütüphanesinde yoksa `/status` "model bulunamadı" der ve kurulu
  modelleri listeler — sistem yanlış modelle sessizce çalışmaz.
- **Eş zamanlı istek sınırı yok.** Tek kullanıcılı demo için sorun değil;
  çok kullanıcılı kullanımda kuyruk gerekir.
