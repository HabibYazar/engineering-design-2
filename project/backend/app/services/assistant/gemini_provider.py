"""Google Gemini sağlayıcısı — OpenAI uyumlu uç üzerinden.

NEDEN OPENAI UYUMLU UÇ
----------------------
Gemini'nin iki API yüzeyi var: Google'ın kendi `generateContent` şeması
ve OpenAI ile uyumlu `/v1beta/openai/chat/completions` ucu. İkincisi
seçildi çünkü projenin araç katmanı (araç şemaları, `tool_calls`,
`tool_call_id` eşlemesi, akış biçimi) zaten OpenAI sözleşmesine göre
yazılmış durumda.

Google'ın kendi şemasını kullanmak `contents`/`parts`/`functionCall`
dönüşümleri, farklı rol adları ve farklı akış biçimi demekti — yani
`chat_service`in araç döngüsünü baştan yazmak. Uyumlu uç aynı işi
yaparken o riski ortadan kaldırıyor.

WEB ERİŞİMİ — YERLEŞİK ARAMA ASLA AÇILMAZ
------------------------------------------
Gemini, istek gövdesine `google_search` (ya da `google_search_retrieval`)
aracı eklenerek internete çıkabilir. Kurumun kuralı bunu yasaklıyor:
asistan yalnızca kendi veritabanımızı okur.

Bu modül o aracı EKLEMEZ ve modelin araç listesine sızmasını da
engeller (`_arac_temizle`). Aynı tuzağa Groq'ta da düşülmüştü:
`groq/compound` modelleri yerleşik arama taşıyordu ve seçilseler yasak,
tek bir model adı yüzünden kimsenin göremeyeceği bir yerden delinecekti.

SÖZLEŞME
--------
`AssistantProvider` yüzeyini karşılar: `name`, `model`, `etkin_model()`,
`resolve_model()`, `is_available()`, `health()`, `warm_up()`, `chat()`,
`chat_with_tools()`, `stream_chat()`.
"""

from __future__ import annotations

import json
import logging
import os
from collections import OrderedDict
from typing import Dict, Iterator, List, Optional, Tuple

import httpx

from app.core.config import settings
from app.services.assistant.base import AssistantProvider
from app.services.assistant.provider_shared import (
    AssistantProviderError,
    ProviderHealth,
    parse_tool_calls,
    split_thinking,
)

logger = logging.getLogger(__name__)

ERROR_NO_KEY = (
    "Gemini API anahtarı tanımlı değil. backend/.env dosyasına "
    "GEMINI_API_KEY satırını ekleyin."
)
ERROR_UNAUTHORIZED = (
    "Gemini API anahtarı reddedildi. Google AI Studio'dan alınmış, geçerli "
    "bir anahtar olduğundan emin olun."
)
ERROR_RATE_LIMIT = (
    "Gemini kullanım sınırına ulaşıldı. Kısa bir süre sonra tekrar deneyin."
)
ERROR_SERVICE_UNREACHABLE = (
    "Gemini servisine ulaşılamıyor. İnternet bağlantısını kontrol edin."
)
ERROR_TIMEOUT = "Gemini yanıt vermedi (zaman aşımı). Lütfen tekrar deneyin."
ERROR_INVALID_RESPONSE = "Gemini'den geçerli bir yanıt alınamadı."
ERROR_MODEL_MISSING_TEMPLATE = (
    "{model} modeli bu API anahtarıyla kullanılamıyor. .env dosyasındaki "
    "GEMINI_MODEL değerini geçerli bir modelle değiştirin."
)
ERROR_NO_USABLE_MODEL = (
    "Hesabınızda araç çağırabilen bir sohbet modeli bulunamadı. "
    "Erişilebilir modeller: {models}"
)
READY_TEMPLATE = "Yapay zekâ hazır — {model}"

#: Model listesi bu süre boyunca yeniden sorulmaz (saniye).
#: Ücretsiz katmanda dakikada 5 İSTEK hakkı var; durum ucu bunu tek
#: başına tüketmemeli.
MODEL_ONBELLEK_SANIYE = 300.0

#: OTOMATİK MODEL SEÇİMİ — TERCİH SIRASI (ön ek eşleşmesi).
#: `.env` içindeki ad hesapta yoksa bu sıradan ilk bulunan kullanılır.
#: Groq'ta yaşandığı gibi, sağlayıcı bir modeli emekliye ayırdığında
#: asistanın tamamen susmaması için.
MODEL_TERCIHI: Tuple[str, ...] = (
    "gemini-3-pro",
    "gemini-3-flash",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-pro",
    "gemini-1.5-flash",
    "gemini-pro",
)

#: SOHBET/ARAÇ İŞİNE UYGUN OLMAYANLAR — seçimde elenir.
#: Gömme, görüntü üretimi ve ses modelleri sohbet ucuna gelse de araç
#: çağıramaz; seçilirlerse "model bulundu ama araçlar çalışmıyor" gibi
#: teşhisi zor bir arıza üretirler.
MODEL_ELE: Tuple[str, ...] = (
    "embedding", "aqa", "imagen", "veo", "tts", "audio", "vision",
    "learnlm", "gemma",
)

#: MODELE ASLA SUNULMAYACAK ARAÇ ADLARI.
#: Gemini'nin yerleşik arama/kod çalıştırma araçları. Bunlar bizim araç
#: kayıt defterimizden geçmez, sonuçları denetlenemez ve doğrudan
#: internete çıkar.
YASAK_ARACLAR = frozenset({
    "google_search",
    "google_search_retrieval",
    "code_execution",
    "url_context",
})


#: ARAÇ ÇAĞRISI KİMLİĞİ → MODELİN DÖNDÜRDÜĞÜ EK ALANLAR ("düşünce imzası").
#:
#: NEDEN VAR
#: ---------
#: Gemini 3 araç çağırırken `thought_signature` adlı imzalı bir alan
#: döndürüyor ve BİR SONRAKİ turda aynı çağrı geri gönderilirken bu alan
#: da gelmezse isteği reddediyor:
#:
#:     "Function call is missing a thought_signature in functionCall
#:      parts. This is required for tools to work correctly."
#:
#: İmza modelin o çağrıyı NEDEN yaptığının şifrelenmiş kaydı. Google
#: bunu, araç sonucunu okurken modelin kendi muhakemesini
#: doğrulayabilmesi için istiyor; taklit edilemez, yeniden üretilemez.
#:
#: Bizim araç döngümüz (`chat_service`) sağlayıcıdan bağımsız olsun diye
#: asistan mesajını SADE alanlarla (ad + argüman) yeniden kuruyor. Bu
#: tasarım Ollama ve Groq'ta doğruydu; Gemini 3'te imzayı yolda
#: düşürüyor. Depo o kaybı, döngünün biçimini bozmadan telafi ediyor.
#:
#: Sınırlı tutulur: uzun oturumlarda süresiz büyümesin.
_IMZA_DEPOSU: "OrderedDict[str, Tuple[Dict, Dict]]" = OrderedDict()
_IMZA_TAVANI = 200


def _imza_yaz(kimlik: str, ust: Dict, fonksiyon: Dict) -> None:
    if not kimlik or not (ust or fonksiyon):
        return
    _IMZA_DEPOSU[kimlik] = (ust, fonksiyon)
    _IMZA_DEPOSU.move_to_end(kimlik)
    while len(_IMZA_DEPOSU) > _IMZA_TAVANI:
        _IMZA_DEPOSU.popitem(last=False)


def _imza_topla(ham_cagrilar) -> None:
    """Cevaptaki araç çağrılarının STANDART DIŞI alanlarını saklar.

    Alan adı `thought_signature` diye SABİTLENMEZ: bilinen alanların
    (`id`, `type`, `function.name`, `function.arguments`) dışındaki her
    şey saklanır. Google yarın imzanın adını değiştirse ya da yanına
    ikinci bir alan koysa bu kod sessizce kırılmaz.
    """
    if not isinstance(ham_cagrilar, list):
        return
    for c in ham_cagrilar:
        if not isinstance(c, dict):
            continue
        kimlik = c.get("id")
        if not kimlik:
            continue
        fn = c.get("function") if isinstance(c.get("function"), dict) else {}
        _imza_yaz(
            str(kimlik),
            {k: v for k, v in c.items() if k not in ("id", "type", "function")},
            {k: v for k, v in fn.items() if k not in ("name", "arguments")},
        )


#: 429 gövdesindeki kota kimliğinde geçen "günlük" işaretleri.
_GUNLUK_IZ = ("perday", "per_day", "daily", "requestsperday")


def _hata_govdesi(response: httpx.Response) -> Dict:
    """Cevaptaki `error` nesnesini döndürür — gövde LİSTE olsa bile.

    NEDEN
    -----
    Gemini'nin OpenAI uyumlu ucu hatayı bazen sözlük, bazen TEK
    ELEMANLI LİSTE olarak döndürüyor:

        [{"error": {"code": 429, "message": "...", "details": [...]}}]

    Kod yalnızca sözlük bekliyordu; liste geldiğinde `.get("error")`
    çalışmıyor ve hata SEBEPSİZ görünüyordu. Ekrandaki "Gemini isteği
    reddetti: [{" ile başlayan ham çıktılar ve boş `error.message`
    şikâyetlerinin kaynağı buydu — mesaj gövdede vardı, biz
    okuyamıyorduk.
    """
    try:
        govde = response.json()
    except ValueError:
        return {}
    if isinstance(govde, list):
        govde = next((x for x in govde if isinstance(x, dict)), {})
    if not isinstance(govde, dict):
        return {}
    hata = govde.get("error")
    return hata if isinstance(hata, dict) else {}


def _kota_detayi(response: httpx.Response) -> str:
    """429 cevabından kullanıcıya DOĞRU olanı söyleyen mesajı üretir.

    Google `error.details` içinde `QuotaFailure` ve `RetryInfo`
    döndürüyor: hangi kota doldu, ne kadar beklenmeli. Bunlar
    okunmadan verilen "kısa bir süre sonra deneyin" tavsiyesi günlük
    kotada yanlıştır — kullanıcıyı bekleterek oyalar.
    """
    hata = _hata_govdesi(response)
    kimlik, bekleme = "", ""
    for d in hata.get("details") or []:
        if not isinstance(d, dict):
            continue
        for ih in d.get("violations") or []:
            if isinstance(ih, dict):
                kimlik = str(ih.get("quotaId") or ih.get("quotaMetric") or kimlik)
        if d.get("retryDelay"):
            bekleme = str(d["retryDelay"])

    metin = str(hata.get("message") or "")
    logger.warning("Gemini kota doldu: quotaId=%r retryDelay=%r | %s",
                   kimlik, bekleme, metin[:200])
    # Günlük/dakikalık ayrımı `quotaId` yoksa mesaj metninden de çıkar.
    sade = (kimlik + " " + metin).lower().replace("-", "").replace("_", "")

    # Google kalan hakkı `limit: N` biçiminde yazıyor; kullanıcıya
    # söylenirse sorunun büyüklüğü anlaşılır.
    sinir = ""
    for parca in metin.split("limit:")[1:2]:
        sinir = parca.split(",")[0].strip()

    if any(iz in sade for iz in _GUNLUK_IZ):
        return ((f"Gemini'nin GÜNLÜK ücretsiz kotası doldu"
                 + (f" (günde {sinir} istek)" if sinir else "") + ". Bekleyerek "
                 "çözülmez; kota Pasifik saatiyle gece yarısı sıfırlanır. "
                 "Hemen devam etmek için .env içinde GEMINI_MODEL değerini "
                 "kotası ayrı bir modelle (örneğin gemini-2.5-flash) "
                 "değiştirin ya da Google AI Studio'dan faturalandırmayı "
                 "açın."))
    if bekleme:
        return (f"Gemini dakikalık istek sınırına ulaşıldı. {bekleme} sonra "
                "tekrar deneyin (ücretsiz katmanda dakikada 5 istek).")
    return ""


def _effective_timeout() -> int:
    ham = os.getenv("ASSISTANT_LIVE_TIMEOUT_SECONDS")
    if ham:
        try:
            return max(1, int(ham))
        except ValueError:
            pass
    return settings.GEMINI_TIMEOUT_SECONDS


def model_sec(mevcut: List[str], istenen: str = "") -> Optional[str]:
    """Hesaptaki modeller arasından kullanılabilir olanı seçer.

    Tanınan bir aile bulunamazsa `None` döner — RASTGELE MODEL SEÇİLMEZ.
    Groq'ta "kalanın ilkini al" mantığı bir seslendirme modelini sohbet
    için seçmişti; aynı hataya düşülmüyor.
    """
    kullanilabilir = [
        m for m in mevcut if not any(k in m.lower() for k in MODEL_ELE)
    ]
    if istenen and istenen in mevcut:
        return istenen
    for tercih in MODEL_TERCIHI:
        for m in kullanilabilir:
            if m.lower().startswith(tercih.lower()):
                return m
    return None


#: Gemini'nin fonksiyon şemasında KABUL ETMEDİĞİ JSON Schema anahtarları.
#: Gemini OpenAPI 3.0'ın bir ALT KÜMESİNİ kabul eder; JSON Schema'nın
#: tamamını değil. Bu anahtarlardan biri gövdede olursa istek HTTP 400
#: ile reddedilir ve `error.message` BOŞ döner — yani hata sebebini
#: söylemez.
SEMA_ATILAN = frozenset({
    "$schema", "$defs", "$ref", "definitions", "additionalProperties",
    "default", "title", "examples", "format", "pattern",
    "exclusiveMinimum", "exclusiveMaximum", "const", "not",
    "allOf", "oneOf", "patternProperties", "dependencies",
    "minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems",
})


def _sema_uyarla(o):
    """JSON Schema'yı Gemini'nin kabul ettiği alt kümeye indirger.

    NEDEN GEREKTİ
    -------------
    Araç şemaları Pydantic'ten üretiliyor ve `Optional[str]` alanları
    şuna dönüşüyor:

        {"anyOf": [{"type": "string"}, {"type": "null"}]}

    Gemini `anyOf` kabul etmiyor; karşılığı `nullable` bayrağıdır.
    Ölçüldü: şemalarımızda 46 `anyOf`, 54 `default`, 11
    `additionalProperties` var. Groq bunları yok sayıyordu, Gemini
    isteği tümden reddediyor.

    KORUNANLAR: `type`, `description`, `enum`, `properties`, `required`,
    `items`. Bunlar aracın ne yaptığını ve nasıl çağrılacağını anlatır;
    atılırsa model aracı yanlış çağırır.

    ATILANLAR yalnızca DOĞRULAMA ayrıntılarıdır (`minimum`, `pattern`,
    `default`). Onların işini zaten bizim `tool_runner` katmanımız
    yapıyor: model yanlış değer gönderse bile araç çalışmadan önce
    Pydantic doğruluyor. Yani kaybedilen bir güvence yok.
    """
    if isinstance(o, list):
        return [_sema_uyarla(x) for x in o]
    if not isinstance(o, dict):
        return o

    # `anyOf: [X, {"type":"null"}]` → X + nullable
    if "anyOf" in o:
        secenekler = [x for x in o["anyOf"] if isinstance(x, dict)]
        bos_var = any(x.get("type") == "null" for x in secenekler)
        gercek = [x for x in secenekler if x.get("type") != "null"]
        if len(gercek) == 1:
            birlesik = {k: v for k, v in o.items() if k != "anyOf"}
            birlesik.update(gercek[0])
            if bos_var:
                birlesik["nullable"] = True
            return _sema_uyarla(birlesik)
        # Birden çok gerçek seçenek: tür belirsiz, en genelde bırakılır.
        kalan = {k: v for k, v in o.items() if k != "anyOf"}
        kalan.setdefault("type", "string")
        if bos_var:
            kalan["nullable"] = True
        return _sema_uyarla(kalan)

    # ALAN ADLARI META-ANAHTAR DEĞİLDİR.
    # ------------------------------------------------------------------
    # `properties` (ve `$defs`) sözlüğünün ANAHTARLARI, şemanın kendi
    # kelimeleri değil KULLANICI ALAN ADLARIDIR. Ayrım yapılmazsa
    # `title`, `default`, `format`, `items`, `not` gibi bir isim taşıyan
    # her alan sessizce silinir — ama `required` listesinde kalır ve
    # Gemini isteği şöyle reddeder:
    #
    #     "schema at top-level requires unspecified property 'title'"
    #
    # Tam olarak bu yaşandı: `render_chart` aracının `title` alanı
    # ayıklanınca araç şeması tutarsız hale geldi ve ASİSTANIN TAMAMI
    # çalışmaz oldu. Hata `render_chart`ta göründü ama tuzağı bu
    # fonksiyon kurmuştu; `title` adlı alan taşıyan her araçta patlardı.
    ISIM_SOZLUKLERI = ("properties", "$defs", "definitions",
                       "patternProperties")
    sonuc = {}
    for k, v in o.items():
        if k in ISIM_SOZLUKLERI:
            if k in SEMA_ATILAN:
                continue          # `$defs` gibi tümden atılanlar
            # Anahtarlar korunur, yalnızca DEĞERLER indirgenir.
            sonuc[k] = {ad: _sema_uyarla(alt) for ad, alt in v.items()} \
                if isinstance(v, dict) else _sema_uyarla(v)
            continue
        if k in SEMA_ATILAN:
            continue
        sonuc[k] = _sema_uyarla(v)
    return sonuc


def _arac_temizle(tools: Optional[List[Dict]]) -> Optional[List[Dict]]:
    """Yerleşik web/kod araçlarını istekten ayıklar.

    Bu bir "olur da" önlemi değil, KURALIN KOD KARŞILIĞI: araç listesi
    ileride nereden gelirse gelsin, internete çıkan bir araç buradan
    geçemez.
    """
    if not tools:
        return tools
    temiz = []
    for t in tools:
        ad = ((t.get("function") or {}).get("name") or "").lower()
        # Bazı yerleşik araçlar `function` yerine doğrudan anahtar olarak
        # gelir: {"google_search": {}}
        anahtarlar = {k.lower() for k in t.keys()}
        if ad in YASAK_ARACLAR or (anahtarlar & YASAK_ARACLAR):
            logger.warning("Yerlesik web/kod araci istekten cikarildi: %s", ad or anahtarlar)
            continue
        # Şema, Gemini'nin kabul ettiği alt kümeye indirgenir.
        fn = t.get("function")
        if isinstance(fn, dict) and isinstance(fn.get("parameters"), dict):
            t = {**t, "function": {**fn,
                                   "parameters": _sema_uyarla(fn["parameters"])}}
        temiz.append(t)
    return temiz


class GeminiProvider(AssistantProvider):
    """Gemini ile OpenAI uyumlu uç üzerinden konuşan sağlayıcı."""

    name = "gemini"

    #: Süreç ömrü boyunca bir kez çözülen model.
    _otomatik_model: Optional[str] = None
    #: (zaman, model adları) — kota tüketimini seyreltmek için.
    _model_onbellek: Optional[Tuple[float, Tuple[str, ...]]] = None

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> None:
        self.base_url = (base_url or settings.GEMINI_BASE_URL).rstrip("/")
        self.model = model or settings.GEMINI_MODEL or ""
        self._api_key = api_key if api_key is not None else (settings.GEMINI_API_KEY or "")
        self.timeout_seconds = timeout_seconds or _effective_timeout()
        self.temperature = (
            settings.GEMINI_TEMPERATURE if temperature is None else temperature
        )

    # ------------------------------------------------------------------
    # Durum
    # ------------------------------------------------------------------
    def etkin_model(self) -> str:
        return self.model or type(self)._otomatik_model or settings.GEMINI_MODEL or ""

    def _istemci(self) -> httpx.Client:
        if not self._api_key:
            raise AssistantProviderError(ERROR_NO_KEY, kind="not_configured")
        return httpx.Client(
            timeout=self.timeout_seconds,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        )

    def list_models(self) -> List[str]:
        """Anahtarın erişebildiği modeller — KISA SÜRELİ ÖNBELLEKLİ.

        NEDEN ÖNBELLEK
        --------------
        Ücretsiz katmanda sınır TOKEN değil İSTEK sayısıdır: ölçülen
        değer dakikada 5. Durum ucu her sayfa açılışında çağrılıyor ve
        her çağrı `/models` soruyordu; kullanıcı daha soru sormadan
        kotanın beşte biri yanıyordu.

        Çözüm sorguyu KALDIRMAK değil SEYRELTMEK. Kaldırsaydık durum ucu
        Gemini kapalıyken bile "hazır" derdi — kota tasarrufu için
        dürüstlükten çalmak olurdu. Önbellek ikisini de korur: durum
        gerçek bir çağrıya dayanır, ama dakikada bir kez.
        """
        import time as _t
        simdi = _t.monotonic()
        onbellek = type(self)._model_onbellek
        if onbellek and simdi - onbellek[0] < MODEL_ONBELLEK_SANIYE:
            return list(onbellek[1])
        try:
            with self._istemci() as client:
                response = client.get(f"{self.base_url}/models")
                self._raise_for_status(response)
                payload = response.json()
        except AssistantProviderError:
            raise
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise AssistantProviderError(
                ERROR_SERVICE_UNREACHABLE, kind="service_down") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise AssistantProviderError(
                ERROR_INVALID_RESPONSE, kind="invalid_response") from exc

        veri = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(veri, list):
            return []
        # Uyumlu uç kimlikleri "models/gemini-2.5-flash" biçiminde
        # döndürebiliyor; önek atılır ki `.env` içindeki sade ad eşleşsin.
        adlar = [
            str(m.get("id")).split("/")[-1]
            for m in veri
            if isinstance(m, dict) and m.get("id")
        ]
        import time as _t
        type(self)._model_onbellek = (_t.monotonic(), tuple(adlar))
        return adlar

    def resolve_model(self) -> Optional[str]:
        """Kullanılacak modeli belirler.

        AÇIKÇA YAPILANDIRILAN AD ÖNCELİKLİDİR.
        ------------------------------------------------------------------
        İlk sürüm önce `/models` listesine bakıyor, ad listede yoksa
        başka bir modele düşüyordu. Bu, tek bir model için verilmiş
        anahtarlarda yanlış: liste ya boş döner ya da anahtarın
        erişemediği modelleri sayar; her iki durumda da sistem
        çalışmayan bir modele geçer.

        Kullanıcı `.env` içine bir ad yazdıysa niyeti bellidir; otomatik
        keşif onun yerine geçmez. Otomatik seçim yalnızca ad BOŞ
        bırakıldığında ya da liste sorgusu ad hakkında kesin bilgi
        verdiğinde devreye girer.
        """
        if type(self)._otomatik_model:
            return type(self)._otomatik_model

        yapilandirilan = self.model or settings.GEMINI_MODEL or ""
        if yapilandirilan:
            type(self)._otomatik_model = yapilandirilan
            self.model = yapilandirilan
            return yapilandirilan

        try:
            mevcut = self.list_models()
        except AssistantProviderError:
            return None

        secilen = model_sec(mevcut, "")
        if not secilen:
            return None
        if secilen != (self.model or settings.GEMINI_MODEL):
            logger.warning(
                "Yapilandirilan Gemini modeli (%s) hesapta yok; %s secildi.",
                self.model or settings.GEMINI_MODEL, secilen,
            )
        type(self)._otomatik_model = secilen
        self.model = secilen
        return secilen

    def health(self) -> ProviderHealth:
        if not self._api_key:
            return ProviderHealth(False, False, (), ERROR_NO_KEY)

        try:
            modeller = self.list_models()
        except AssistantProviderError as exc:
            return ProviderHealth(False, False, (), exc.user_message)

        secilen = self.resolve_model()
        if not secilen:
            return ProviderHealth(
                True, False, tuple(modeller),
                ERROR_NO_USABLE_MODEL.format(models=", ".join(sorted(modeller)[:12])),
            )

        # LİSTE, YAPILANDIRMAYI ÇÜRÜTMEZ — YALNIZCA UYARIR.
        # ------------------------------------------------------------------
        # Anahtar tek bir model için verilmiş olabilir; o durumda `/models`
        # ya boş döner ya da erişilemeyen modelleri sayar. Bu yüzden
        # "listede yok" durumu HATA değil NOT'tur: sistem hazır sayılır,
        # gerçek karar ilk sohbet çağrısına bırakılır. Aksi hâlde çalışan
        # bir kurulum, yalnızca liste ucu yüzünden kapalı görünürdü.
        if modeller and secilen not in modeller:
            return ProviderHealth(
                True, True, tuple(modeller),
                f"{secilen} kullanılıyor (model listesinde görünmüyor; "
                f"anahtar tek modele özel olabilir).",
            )
        return ProviderHealth(
            True, True, tuple(modeller), READY_TEMPLATE.format(model=secilen))

    def is_available(self) -> bool:
        if not settings.ASSISTANT_ENABLED:
            return False
        try:
            return self.health().ready
        except AssistantProviderError:
            return False

    def warm_up(self) -> bool:
        """Bulut modelinde ısıtma gerekmez; sözleşme için var."""
        return bool(self._api_key)

    # ------------------------------------------------------------------
    # Mesaj biçimi
    # ------------------------------------------------------------------
    @staticmethod
    def _openai_mesajlari(messages: List[Dict]) -> List[Dict]:
        """Araç mesajlarını OpenAI/Gemini uyumlu biçime çevirir.

        `chat_service` araç döngüsünü sağlayıcıdan bağımsız kurar ve sade
        bir biçim kullanır. Uyumlu uç üç şey daha ister: her `tool_calls`
        girdisinde benzersiz `id`, `arguments` alanının JSON METNİ olması
        ve her `tool` mesajının `tool_call_id` taşıması.

        Kimlik eşleşmesi SIRAYA göre kurulur: döngü, bir asistan
        mesajının hemen ardına o mesajdaki çağrıların sonuçlarını aynı
        sırayla ekler.
        """
        cikti: List[Dict] = []
        bekleyen: List[str] = []

        for m in messages:
            rol = m.get("role")
            if rol == "assistant" and m.get("tool_calls"):
                cagrilar = []
                bekleyen = []
                for i, c in enumerate(m["tool_calls"]):
                    fn = c.get("function") or {}
                    kimlik = c.get("id") or f"call_{len(cikti)}_{i}"
                    bekleyen.append(kimlik)
                    args = fn.get("arguments")
                    govde_fn = {
                        "name": fn.get("name"),
                        "arguments": args if isinstance(args, str)
                        else json.dumps(args or {}, ensure_ascii=False),
                    }
                    cagri = {"id": kimlik, "type": "function"}
                    # Düşünce imzasını GERİ KOY (bkz. _IMZA_DEPOSU).
                    ust_ek, fn_ek = _IMZA_DEPOSU.get(kimlik, ({}, {}))
                    if fn_ek:
                        govde_fn.update(fn_ek)
                    cagri.update(ust_ek)
                    cagri["function"] = govde_fn
                    cagrilar.append(cagri)
                cikti.append({
                    "role": "assistant",
                    "content": m.get("content") or "",
                    "tool_calls": cagrilar,
                })
            elif rol == "tool":
                kimlik = m.get("tool_call_id") or (
                    bekleyen.pop(0) if bekleyen else "call_bilinmiyor")
                cikti.append({
                    "role": "tool",
                    "tool_call_id": kimlik,
                    "content": m.get("content") or "",
                })
            else:
                cikti.append(m)
        return cikti

    def _payload(
        self,
        messages: List[Dict[str, str]],
        stream: bool,
        tools: Optional[List[Dict]] = None,
    ) -> Dict:
        payload: Dict = {
            "model": self.resolve_model() or self.etkin_model(),
            "messages": self._openai_mesajlari(messages),
            "stream": stream,
            "temperature": self.temperature,
            "max_tokens": settings.GEMINI_MAX_TOKENS,
        }

        # DÜŞÜNME SEVİYESİ AÇIKÇA SÖYLENİR.
        # --------------------------------------------------------------
        # Bu satır yoktu ve eksikliği sessizdi: parametre gönderilmeyince
        # Google modelin VARSAYILAN seviyesini uyguluyor, Gemini 3 Flash
        # için bu `medium` (≈8.192 tokenlık düşünme bütçesi). `max_tokens`
        # de 8.192 olduğundan model, üretim bütçesinin tamamını iç
        # muhakemeye harcayıp cevabı hiç yazmadan sınıra dayanabiliyordu.
        # Ölçülen belirti: tur 40 saniye sürüyor, dönen metin boş.
        #
        # Sözleşme: ai.google.dev/gemini-api/docs/openai — `reasoning_effort`
        # OpenAI uyumlu uçta desteklenir ("minimal"/"low"/"medium"/"high").
        # Gemini 3'te düşünme KAPATILAMAZ; yalnızca seviyesi düşürülür.
        #
        # Ayar boş bırakılırsa parametre gönderilmez ve eski davranış
        # (modelin varsayılanı) aynen geri gelir.
        seviye = (settings.GEMINI_REASONING_EFFORT or "").strip().lower()
        if seviye in ("minimal", "low", "medium", "high"):
            payload["reasoning_effort"] = seviye

        temiz = _arac_temizle(tools)
        if temiz:
            payload["tools"] = temiz
            payload["tool_choice"] = "auto"
        return payload

    # ------------------------------------------------------------------
    # Hata eşlemesi
    # ------------------------------------------------------------------
    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        hata = _hata_govdesi(response)
        mesaj = str(hata.get("message") or "")

        # İMZA HATASI — sebebi açıkça söyle.
        # Bu hata "model bozuk" ya da "anahtar yanlış" gibi görünür ama
        # ikisi de değildir: araç döngüsünde imzanın taşınmadığını
        # anlatır. Sessizce "geçerli yanıt alınamadı"ya düşerse teşhis
        # baştan başlar.
        if "thought_signature" in mesaj:
            logger.error("Gemini dusunce imzasi eksik: %s", mesaj[:300])
            raise AssistantProviderError(
                "Araç çağrısı düşünce imzası olmadan gönderildi. Sunucu "
                "yeniden başlatılmadıysa başlatın; sorun sürerse .env "
                "içinde GEMINI_MODEL=gemini-2.5-flash deneyin.",
                kind="bad_request")

        if response.status_code in (401, 403):
            raise AssistantProviderError(ERROR_UNAUTHORIZED, kind="unauthorized")
        if response.status_code == 429:
            # KOTA TÜRÜNÜ AYIRT ET.
            # ------------------------------------------------------------
            # Google 429 gövdesinde hangi kotanın dolduğunu ve ne kadar
            # beklenmesi gerektiğini söylüyor. Bunu okumadan "kısa bir
            # süre sonra tekrar deneyin" demek YANLIŞ BİLGİDİR: dakikalık
            # sınırda doğru, günlük sınırda kullanıcıyı boşuna bekletir.
            # Ölçüldü: kullanıcı 40 dakika bekledi ve aynı mesajı aldı.
            detay = _kota_detayi(response)
            if detay:
                raise AssistantProviderError(detay, kind="rate_limit")
            raise AssistantProviderError(ERROR_RATE_LIMIT, kind="rate_limit")

        if response.status_code == 413:
            raise AssistantProviderError(
                "İstek, modelin token bütçesine sığmadı. Soruyu kısaltmak "
                "yardımcı olabilir.",
                kind="request_too_large",
            )
        if response.status_code == 404:
            raise AssistantProviderError(
                ERROR_MODEL_MISSING_TEMPLATE.format(model=self.etkin_model()),
                kind="model_missing",
            )
        if response.status_code == 400:
            # HAM GÖVDE GÜNLÜĞE YAZILIR.
            # ----------------------------------------------------------
            # Önceki sürüm yalnızca `error.message` alanını yazıyordu.
            # Gemini bu alanı BOŞ bırakabiliyor ve günlükte "Gemini 400:"
            # diye anlamsız bir satır kalıyordu — yani teşhis aracının
            # kendisi arızayı gizliyordu. Reddin sebebi gövdenin başka
            # bir alanında olabilir; tamamı yazılır.
            logger.warning("Gemini 400 ham govde: %s", response.text[:1200])
            ayrinti = mesaj or response.text[:200]
            raise AssistantProviderError(
                f"Gemini isteği reddetti: {ayrinti}" if ayrinti
                else ERROR_INVALID_RESPONSE,
                kind="bad_request",
            )
        logger.warning("Gemini HTTP %s: %s", response.status_code,
                       response.text[:400])
        raise AssistantProviderError(ERROR_INVALID_RESPONSE, kind="invalid_response")

    # ------------------------------------------------------------------
    # Sohbet
    # ------------------------------------------------------------------
    def chat(
        self, messages: List[Dict[str, str]], tools: Optional[List[Dict]] = None
    ) -> Tuple[str, str]:
        _, visible, thinking = self.chat_with_tools(messages, tools)
        return visible, thinking

    def chat_with_tools(
        self, messages: List[Dict[str, str]], tools: Optional[List[Dict]] = None
    ) -> Tuple[List[Dict], str, str]:
        """Dönen üçlü: (araç çağrıları, görünen cevap, düşünme metni)."""
        try:
            with self._istemci() as client:
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    json=self._payload(messages, stream=False, tools=tools),
                )
                self._raise_for_status(response)
                payload = response.json()
        except AssistantProviderError:
            raise
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            logger.warning("Gemini baglanti hatasi: %s", exc.__class__.__name__)
            raise AssistantProviderError(
                ERROR_SERVICE_UNREACHABLE, kind="service_down") from exc
        except (httpx.ReadTimeout, httpx.TimeoutException) as exc:
            logger.warning("Gemini zaman asimi (%s sn)", self.timeout_seconds)
            raise AssistantProviderError(ERROR_TIMEOUT, kind="timeout") from exc
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Gemini cevabi okunamadi: %s", exc.__class__.__name__)
            raise AssistantProviderError(
                ERROR_INVALID_RESPONSE, kind="invalid_response") from exc

        try:
            ham = ((payload.get("choices") or [{}])[0].get("message") or {})
            _imza_topla(ham.get("tool_calls"))
        except (AttributeError, IndexError, TypeError):
            pass
        return self._extract_with_tools(payload)

    def _extract_with_tools(self, payload: Dict) -> Tuple[List[Dict], str, str]:
        if not isinstance(payload, dict):
            raise AssistantProviderError(ERROR_INVALID_RESPONSE, kind="invalid_response")
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise AssistantProviderError(ERROR_INVALID_RESPONSE, kind="invalid_response")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if not isinstance(message, dict):
            raise AssistantProviderError(ERROR_INVALID_RESPONSE, kind="invalid_response")

        content = message.get("content") or ""
        thinking_field = message.get("reasoning") or ""
        visible, inline_thinking = split_thinking(content)
        thinking = "\n".join(p for p in (thinking_field, inline_thinking) if p)
        tool_calls = parse_tool_calls(message.get("tool_calls"))

        if not visible and not tool_calls:
            # BOŞ CEVABIN SEBEBİNİ SÖYLE.
            # Gemini 3 bir DÜŞÜNME modelidir ve düşünme adımları da
            # `max_tokens` bütçesinden harcanır. Uzun bir konuşmada model
            # bütçeyi düşünürken bitirirse `finish_reason: "length"` ile
            # BOŞ içerik döner — istek başarılıdır (HTTP 200), cevap
            # yoktur. "Geçerli yanıt alınamadı" demek bu durumu
            # teşhis edilemez kılıyordu; sebebi ve çözümü söylenir.
            neden = ""
            kullanim = payload.get("usage") if isinstance(payload, dict) else None
            try:
                neden = str(choices[0].get("finish_reason") or "")
            except (AttributeError, IndexError, TypeError):
                pass
            logger.warning(
                "Gemini bos cevap dondu: finish_reason=%r usage=%r",
                neden, kullanim)
            if neden == "length":
                raise AssistantProviderError(
                    "Model cevabı yazmadan token bütçesini doldurdu "
                    "(düşünme adımları da bütçeden harcanır). Yeni "
                    "konuşma başlatmak ya da .env içinde "
                    "GEMINI_MAX_TOKENS değerini artırmak çözer.",
                    kind="empty_response")
            raise AssistantProviderError(ERROR_INVALID_RESPONSE, kind="invalid_response")
        return tool_calls, visible, thinking

    def _extract(self, payload: Dict) -> Tuple[str, str]:
        _, visible, thinking = self._extract_with_tools(payload)
        if not visible:
            raise AssistantProviderError(ERROR_INVALID_RESPONSE, kind="invalid_response")
        return visible, thinking

    # ------------------------------------------------------------------
    # Akış
    # ------------------------------------------------------------------
    def stream_chat(self, messages: List[Dict[str, str]]) -> Iterator[str]:
        """Cevabı parça parça üretir; `<think>` blokları yayınlanmaz."""
        inside_think = False
        artik = ""
        try:
            with self._istemci() as client:
                with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    json=self._payload(messages, stream=True),
                ) as response:
                    if response.status_code >= 400:
                        response.read()
                        self._raise_for_status(response)
                    for line in response.iter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        veri = line[5:].strip()
                        if veri == "[DONE]":
                            break
                        try:
                            chunk = json.loads(veri)
                        except ValueError:
                            continue
                        secim = (chunk.get("choices") or [{}])[0]
                        parca = (secim.get("delta") or {}).get("content") or ""
                        if not parca:
                            continue
                        artik += parca
                        while True:
                            if inside_think:
                                kapanis = artik.lower().find("</think>")
                                uzun = 8
                                if kapanis < 0:
                                    kapanis = artik.lower().find("</thinking>")
                                    uzun = 11
                                if kapanis < 0:
                                    artik = ""
                                    break
                                artik = artik[kapanis + uzun:]
                                inside_think = False
                                continue
                            acilis = artik.lower().find("<think>")
                            uzun = 7
                            if acilis < 0:
                                acilis = artik.lower().find("<thinking>")
                                uzun = 10
                            if acilis < 0:
                                yarim = artik.rfind("<")
                                if yarim >= 0 and len(artik) - yarim <= 10:
                                    if artik[:yarim]:
                                        yield artik[:yarim]
                                    artik = artik[yarim:]
                                else:
                                    if artik:
                                        yield artik
                                    artik = ""
                                break
                            if artik[:acilis]:
                                yield artik[:acilis]
                            artik = artik[acilis + uzun:]
                            inside_think = True
        except AssistantProviderError:
            raise
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise AssistantProviderError(
                ERROR_SERVICE_UNREACHABLE, kind="service_down") from exc
        except (httpx.ReadTimeout, httpx.TimeoutException) as exc:
            raise AssistantProviderError(ERROR_TIMEOUT, kind="timeout") from exc
        except httpx.HTTPError as exc:
            raise AssistantProviderError(
                ERROR_INVALID_RESPONSE, kind="invalid_response") from exc

    # ------------------------------------------------------------------
    def generate(self, question: str, context) -> str:  # pragma: no cover
        visible, _ = self.chat([{"role": "user", "content": question}])
        return visible
