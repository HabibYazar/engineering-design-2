"""Gemini sağlayıcısı — ağ olmadan davranış doğrulaması.

Doğrulanan şey Gemini'nin çalışıp çalışmadığı DEĞİL, bizim kodumuzun
doğru istek kurup gelen cevabı doğru okuduğudur: istek gövdesi, araç
çağrısı ayrıştırma, hata eşlemesi, model seçimi ve — en önemlisi —
yerleşik web aracının isteğe SIZMAMASI.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.services.assistant.gemini_provider import (
    ERROR_NO_KEY,
    ERROR_RATE_LIMIT,
    ERROR_UNAUTHORIZED,
    YASAK_ARACLAR,
    GeminiProvider,
    model_sec,
)
from app.services.assistant.provider_shared import AssistantProviderError

ANAHTAR = "AIza_test_anahtari"


def _saglayici(handler, **kw) -> GeminiProvider:
    p = GeminiProvider(api_key=ANAHTAR, model="gemini-2.5-flash", **kw)
    tasiyici = httpx.MockTransport(handler)

    def _istemci():
        return httpx.Client(
            transport=tasiyici,
            headers={"Authorization": f"Bearer {ANAHTAR}",
                     "Content-Type": "application/json"},
        )

    p._istemci = _istemci  # type: ignore[method-assign]
    GeminiProvider._model_onbellek = None
    return p


def _cevap(mesaj: dict) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": mesaj}]})


# ---------------------------------------------------------------------------
# WEB YASAĞI — EN KRİTİK BÖLÜM
# ---------------------------------------------------------------------------
def test_yerlesik_web_araci_istekten_ayiklanir():
    """Gemini'nin `google_search` aracı ASLA gönderilmemeli.

    Kurumun kuralı: asistan yalnızca kendi veritabanımızı okur. Bu araç
    isteğe girerse yasak, bizim araç kayıt defterimizden geçmeden ve
    hiçbir yerde iz bırakmadan delinir. Aynı tuzağa Groq'ta `compound`
    modelleriyle düşülmüştü.
    """
    yakalanan = {}

    def handler(request: httpx.Request) -> httpx.Response:
        yakalanan["json"] = json.loads(request.content)
        return _cevap({"content": "tamam"})

    araclar = [
        {"type": "function", "function": {"name": "get_program_summary",
                                          "parameters": {}}},
        {"type": "function", "function": {"name": "google_search",
                                          "parameters": {}}},
        {"google_search_retrieval": {}},          # alternatif gösterim
        {"type": "function", "function": {"name": "code_execution",
                                          "parameters": {}}},
    ]
    _saglayici(handler).chat([{"role": "user", "content": "x"}], araclar)

    gonderilen = yakalanan["json"].get("tools") or []
    adlar = {(t.get("function") or {}).get("name") for t in gonderilen}
    assert adlar == {"get_program_summary"}
    # Alternatif gösterim de geçmemeli.
    assert not any(set(t.keys()) & YASAK_ARACLAR for t in gonderilen)


def test_yasak_arac_listesi_bilinen_tum_yerlesikleri_kapsar():
    for ad in ("google_search", "google_search_retrieval", "code_execution",
               "url_context"):
        assert ad in YASAK_ARACLAR


# ---------------------------------------------------------------------------
# İstek kurulumu
# ---------------------------------------------------------------------------
def test_istek_govdesi_ve_basligi_dogru_kurulur():
    yakalanan = {}

    def handler(request: httpx.Request) -> httpx.Response:
        yakalanan["url"] = str(request.url)
        yakalanan["auth"] = request.headers.get("Authorization")
        yakalanan["json"] = json.loads(request.content)
        return _cevap({"content": "merhaba"})

    araclar = [{"type": "function",
                "function": {"name": "get_program_summary", "parameters": {}}}]
    gorunen, _ = _saglayici(handler).chat(
        [{"role": "user", "content": "selam"}], araclar)

    assert gorunen == "merhaba"
    assert yakalanan["url"].endswith("/chat/completions")
    assert "generativelanguage.googleapis.com" in yakalanan["url"]
    assert yakalanan["auth"] == f"Bearer {ANAHTAR}"
    govde = yakalanan["json"]
    assert govde["model"] == "gemini-2.5-flash"
    assert govde["stream"] is False
    assert govde["temperature"] == 0.0
    assert govde["tool_choice"] == "auto"


# ---------------------------------------------------------------------------
# Araç döngüsü biçimi
# ---------------------------------------------------------------------------
def test_arac_donusu_openai_bicimine_cevrilir():
    """`chat_service`in sade biçimi uyumlu ucun beklediği biçime çevrilmeli."""
    yakalanan = {}

    def handler(request: httpx.Request) -> httpx.Response:
        yakalanan["json"] = json.loads(request.content)
        return _cevap({"content": "3.626 öğrenci."})

    _saglayici(handler).chat([
        {"role": "user", "content": "kaç öğrenci"},
        {"role": "assistant", "content": "",
         "tool_calls": [{"id": "call_abc",
                         "function": {"name": "get_program_summary",
                                      "arguments": {"program_name": "Psikoloji"}}}]},
        {"role": "tool", "name": "get_program_summary",
         "content": '{"students": 108}', "tool_call_id": "call_abc"},
    ])

    m = yakalanan["json"]["messages"]
    assert m[1]["tool_calls"][0]["id"] == "call_abc"
    assert m[1]["tool_calls"][0]["type"] == "function"
    ham = m[1]["tool_calls"][0]["function"]["arguments"]
    assert isinstance(ham, str)
    assert json.loads(ham) == {"program_name": "Psikoloji"}
    assert m[2]["tool_call_id"] == "call_abc"


def test_kimlik_yoksa_sira_ile_uretilir():
    yakalanan = {}

    def handler(request: httpx.Request) -> httpx.Response:
        yakalanan["json"] = json.loads(request.content)
        return _cevap({"content": "tamam"})

    _saglayici(handler).chat([
        {"role": "assistant", "content": "",
         "tool_calls": [{"function": {"name": "a", "arguments": {}}},
                        {"function": {"name": "b", "arguments": {}}}]},
        {"role": "tool", "name": "a", "content": "1"},
        {"role": "tool", "name": "b", "content": "2"},
    ])
    m = yakalanan["json"]["messages"]
    kimlikler = [c["id"] for c in m[0]["tool_calls"]]
    assert len(set(kimlikler)) == 2
    assert m[1]["tool_call_id"] == kimlikler[0]
    assert m[2]["tool_call_id"] == kimlikler[1]


def test_arac_cagrisi_ve_kimligi_ayristirilir():
    def handler(request: httpx.Request) -> httpx.Response:
        return _cevap({
            "content": None,
            "tool_calls": [{"id": "call_1", "type": "function",
                            "function": {"name": "get_program_summary",
                                         "arguments": '{"program_name":"Psikoloji"}'}}],
        })

    cagrilar, gorunen, _ = _saglayici(handler).chat_with_tools(
        [{"role": "user", "content": "x"}])
    assert gorunen == ""
    assert cagrilar == [{"name": "get_program_summary",
                         "arguments": {"program_name": "Psikoloji"},
                         "id": "call_1"}]


def test_bozuk_arguman_sessizce_atilmaz():
    def handler(request: httpx.Request) -> httpx.Response:
        return _cevap({"content": None,
                       "tool_calls": [{"function": {"name": "t",
                                                    "arguments": "{bozuk"}}]})

    cagrilar, _, _ = _saglayici(handler).chat_with_tools(
        [{"role": "user", "content": "x"}])
    assert cagrilar == [{"name": "t", "arguments": {}}]


def test_ne_metin_ne_arac_varsa_hata():
    def handler(request: httpx.Request) -> httpx.Response:
        return _cevap({"content": ""})

    with pytest.raises(AssistantProviderError):
        _saglayici(handler).chat_with_tools([{"role": "user", "content": "x"}])


# ---------------------------------------------------------------------------
# Muhakeme metni sızmamalı
# ---------------------------------------------------------------------------
def test_think_blogu_ayiklanir():
    def handler(request: httpx.Request) -> httpx.Response:
        return _cevap({"content": "<think>plan</think>3.626 öğrenci."})

    gorunen, dusunme = _saglayici(handler).chat([{"role": "user", "content": "x"}])
    assert gorunen == "3.626 öğrenci."
    assert "plan" in dusunme


# ---------------------------------------------------------------------------
# Hata eşlemesi
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("kod,kind,mesaj", [
    (401, "unauthorized", ERROR_UNAUTHORIZED),
    (403, "unauthorized", ERROR_UNAUTHORIZED),
    (429, "rate_limit", ERROR_RATE_LIMIT),
])
def test_http_hatalari_eslenir(kod, kind, mesaj):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(kod, json={"error": {"message": "gizli ayrıntı"}})

    with pytest.raises(AssistantProviderError) as exc:
        _saglayici(handler).chat([{"role": "user", "content": "x"}])
    assert exc.value.kind == kind
    assert exc.value.user_message == mesaj
    assert "gizli ayrıntı" not in exc.value.user_message


def test_400_sebebi_soyler():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "tool_call_id eksik"}})

    with pytest.raises(AssistantProviderError) as exc:
        _saglayici(handler).chat([{"role": "user", "content": "x"}])
    assert exc.value.kind == "bad_request"
    assert "tool_call_id eksik" in exc.value.user_message


def test_anahtar_yoksa_ag_denenmez():
    p = GeminiProvider(api_key="", model="m")
    with pytest.raises(AssistantProviderError) as exc:
        p.chat([{"role": "user", "content": "x"}])
    assert exc.value.kind == "not_configured"
    assert exc.value.user_message == ERROR_NO_KEY
    assert p.is_available() is False


# ---------------------------------------------------------------------------
# Model seçimi
# ---------------------------------------------------------------------------
def test_model_secimi_tercih_sirasina_uyar():
    assert model_sec(["gemini-1.5-flash", "gemini-2.5-pro"]) == "gemini-2.5-pro"
    assert model_sec(["gemini-2.0-flash", "gemini-1.5-flash"]) == "gemini-2.0-flash"
    # `.env` içindeki ad listede varsa AYNEN kullanılır.
    assert model_sec(["gemini-1.5-flash", "gemini-2.5-pro"],
                     "gemini-1.5-flash") == "gemini-1.5-flash"


def test_sohbet_disi_modeller_secilmez():
    """Gömme/görüntü modelleri araç çağıramaz; seçilmemeli."""
    assert model_sec(["text-embedding-004", "imagen-3.0-generate"]) is None
    assert model_sec(["text-embedding-004", "gemini-2.5-flash"]) == "gemini-2.5-flash"


def test_taninmayan_listede_rastgele_secim_yapilmaz():
    """Tanınan aile yoksa DURULUR — Groq'ta seslendirme modeli seçilmişti."""
    assert model_sec(["bilinmeyen/deneysel", "baska-model"]) is None


def test_model_kimliginden_onek_atilir():
    """Uyumlu uç `models/gemini-2.5-flash` biçiminde dönebiliyor."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"id": "models/gemini-2.5-flash"}]})

    assert _saglayici(handler).list_models() == ["gemini-2.5-flash"]


# ---------------------------------------------------------------------------
# Kayıt defteri
# ---------------------------------------------------------------------------
def test_fabrika_gemini_dondurur():
    from app.core.config import settings
    from app.services.assistant import chat_service, provider_factory

    assert settings.LLM_PROVIDER == "gemini"
    assert provider_factory.get_provider().name == "gemini"
    assert chat_service.get_provider().name == "gemini"


# ---------------------------------------------------------------------------
# ŞEMA UYARLAMA — ASIL 400 SEBEBİ BURADAYDI
# ---------------------------------------------------------------------------
def test_gemini_kabul_etmedigi_sema_anahtarlari_atilir():
    """Gemini JSON Schema'nın tamamını değil bir ALT KÜMESİNİ kabul eder.

    Araç şemaları Pydantic'ten üretiliyor ve içinde `anyOf` (46 adet),
    `default` (54), `additionalProperties` (11) gibi anahtarlar var.
    Groq bunları yok sayıyordu; Gemini isteği HTTP 400 ile reddediyor ve
    `error.message` alanını BOŞ bırakıyor — yani sebebini söylemiyor.
    """
    from app.services.assistant.gemini_provider import _arac_temizle, SEMA_ATILAN

    ham = [{"type": "function", "function": {
        "name": "t",
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "$defs": {"X": {"type": "string"}},
            "properties": {
                "yil": {"anyOf": [{"type": "string"}, {"type": "null"}],
                        "description": "Akademik yıl", "default": None},
                "adet": {"type": "integer", "minimum": 1, "maximum": 50,
                         "default": 10},
                "kip": {"type": "string", "enum": ["a", "b"], "default": "a"},
            },
            "required": ["yil"],
        }}}]
    p = _arac_temizle(ham)[0]["function"]["parameters"]

    def gez(o):
        if isinstance(o, dict):
            for k, v in o.items():
                yield k
                yield from gez(v)
        elif isinstance(o, list):
            for v in o:
                yield from gez(v)

    kalan = set(gez(p))
    assert not (kalan & SEMA_ATILAN), f"atılması gereken kaldı: {kalan & SEMA_ATILAN}"
    assert "anyOf" not in kalan

    # KORUNMASI GEREKENLER: aracın nasıl çağrılacağını anlatan alanlar.
    assert p["type"] == "object"
    assert p["required"] == ["yil"]
    assert p["properties"]["yil"]["type"] == "string"
    assert p["properties"]["yil"]["nullable"] is True
    assert p["properties"]["yil"]["description"] == "Akademik yıl"
    assert p["properties"]["adet"]["type"] == "integer"
    assert p["properties"]["kip"]["enum"] == ["a", "b"]


def test_gercek_arac_semalarinin_hepsi_uyarlanabilir():
    """Kayıt defterindeki 19 aracın hiçbiri yasaklı anahtar bırakmamalı."""
    from app.services.assistant import tools as _t  # noqa: F401
    from app.services.assistant import tools_extended as _te  # noqa: F401
    from app.services.assistant.gemini_provider import _arac_temizle, SEMA_ATILAN
    from app.services.assistant.tool_registry import registry

    uyarli = _arac_temizle(registry.schemas())

    def gez(o):
        """META-ANAHTARLARI gezer; `properties` altındaki ALAN ADLARINI değil.

        Ayrım şart: `render_chart` aracının `title` adlı bir alanı var
        ve o bir JSON Schema anahtarı değil, kullanıcı alan adıdır.
        """
        if isinstance(o, dict):
            for k, v in o.items():
                yield k
                if k in ("properties", "$defs", "definitions"):
                    if isinstance(v, dict):
                        for alt in v.values():
                            yield from gez(alt)
                    continue
                yield from gez(v)
        elif isinstance(o, list):
            for v in o:
                yield from gez(v)

    kalan = set(gez(uyarli))
    yasakli = (kalan & SEMA_ATILAN) | ({"anyOf"} & kalan)
    assert not yasakli, f"Gemini'nin reddedeceği anahtar kaldı: {yasakli}"
    # Araçlar kaybolmamalı.
    assert len(uyarli) == len(registry.schemas())


def test_model_listesi_onbellege_alinir():
    """Ücretsiz katmanda sınır İSTEK sayısı; liste her seferinde sorulmaz."""
    sayac = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        sayac["n"] += 1
        return httpx.Response(200, json={"data": [{"id": "gemini-2.5-flash"}]})

    p = _saglayici(handler)
    p.list_models()
    p.list_models()
    p.list_models()
    assert sayac["n"] == 1, "liste birden çok kez soruldu — kota israfı"


# ---------------------------------------------------------------------------
# DÜŞÜNCE İMZASI — GEMINI 3 ARAÇ DÖNGÜSÜNÜN ZORUNLU ALANI
# ---------------------------------------------------------------------------
def test_dusunce_imzasi_sonraki_tura_tasinir():
    """Gemini 3, döndürdüğü imzayı geri görmezse isteği 400 ile reddeder.

    Hata: "Function call is missing a thought_signature in functionCall
    parts." Araç döngüsü asistan mesajını sade alanlarla yeniden
    kurduğu için imza yolda düşüyordu; bu test o kaybı yakalar.
    """
    from app.services.assistant.gemini_provider import _IMZA_DEPOSU

    _IMZA_DEPOSU.clear()
    turlar = []

    def handler(request: httpx.Request) -> httpx.Response:
        turlar.append(json.loads(request.content))
        if len(turlar) == 1:
            return _cevap({
                "content": None,
                "tool_calls": [{
                    "id": "call_1", "type": "function",
                    "extra_content": {"google": {"thought_signature": "İMZA_XYZ"}},
                    "function": {"name": "get_program_summary",
                                 "arguments": '{"program_name":"Psikoloji"}'},
                }],
            })
        return _cevap({"content": "108 öğrenci."})

    p = _saglayici(handler)
    cagrilar, _, _ = p.chat_with_tools([{"role": "user", "content": "x"}])
    assert cagrilar[0]["id"] == "call_1"

    # Döngünün ikinci turu: chat_service'in SADE biçimi — imza yok.
    p.chat([
        {"role": "user", "content": "x"},
        {"role": "assistant", "content": "",
         "tool_calls": [{"id": "call_1",
                         "function": {"name": "get_program_summary",
                                      "arguments": {"program_name": "Psikoloji"}}}]},
        {"role": "tool", "name": "get_program_summary",
         "content": '{"students":108}', "tool_call_id": "call_1"},
    ])

    gonderilen = turlar[1]["messages"][1]["tool_calls"][0]
    assert gonderilen["extra_content"] == {
        "google": {"thought_signature": "İMZA_XYZ"}}, (
        "düşünce imzası geri gönderilmedi — Gemini 3 bu isteği reddeder")
    # Standart alanlar bozulmamalı.
    assert gonderilen["function"]["name"] == "get_program_summary"
    assert json.loads(gonderilen["function"]["arguments"]) == {
        "program_name": "Psikoloji"}


def test_imza_alan_adi_sabitlenmez():
    """Bilinen alanlar dışındaki HER ŞEY taşınır — ada bağlı değil.

    Google imzanın adını değiştirir ya da yanına ikinci bir alan
    koyarsa, kod sessizce eski hataya dönmemeli.
    """
    from app.services.assistant.gemini_provider import _IMZA_DEPOSU, _imza_topla

    _IMZA_DEPOSU.clear()
    _imza_topla([{"id": "c9", "type": "function",
                  "yeni_alan": 42,
                  "function": {"name": "t", "arguments": "{}",
                               "fn_ici_imza": "abc"}}])
    ust, fn = _IMZA_DEPOSU["c9"]
    assert ust == {"yeni_alan": 42}
    assert fn == {"fn_ici_imza": "abc"}


def test_imza_deposu_sinirsiz_buyumez():
    from app.services.assistant.gemini_provider import (
        _IMZA_DEPOSU, _IMZA_TAVANI, _imza_yaz)

    _IMZA_DEPOSU.clear()
    for i in range(_IMZA_TAVANI + 50):
        _imza_yaz(f"c{i}", {"s": i}, {})
    assert len(_IMZA_DEPOSU) == _IMZA_TAVANI
    assert "c0" not in _IMZA_DEPOSU          # en eski atıldı
    assert f"c{_IMZA_TAVANI + 49}" in _IMZA_DEPOSU


def test_imza_hatasi_anlasilir_mesaja_cevrilir():
    """400 + thought_signature, "geçerli yanıt alınamadı"ya düşmemeli."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {
            "code": 400,
            "message": ("Function call is missing a thought_signature in "
                        "functionCall parts.")}})

    with pytest.raises(AssistantProviderError) as hata:
        _saglayici(handler).chat([{"role": "user", "content": "x"}])
    assert "imza" in str(hata.value).lower()


def test_sema_atilan_kelimeler_ALAN_ADI_olarak_silinmez():
    """`properties` anahtarları meta-anahtar değil ALAN ADIDIR.

    Ayrım yapılmazsa `title` ya da `default` adlı bir alan sessizce
    silinir, `required` listesinde kalır ve Gemini isteği reddeder:

        "schema at top-level requires unspecified property 'title'"

    Bu gerçekten yaşandı: `render_chart` aracının `title` alanı
    ayıklanınca asistanın TAMAMI çalışmaz oldu — hata tek bir araçta
    göründü ama sebep şema temizleyicisiydi.
    """
    from app.services.assistant.gemini_provider import _arac_temizle

    ham = [{"type": "function", "function": {
        "name": "t",
        "parameters": {
            "type": "object",
            "title": "ATILMALI — bu şemanın meta başlığı",
            "properties": {
                # Hepsi SEMA_ATILAN'da geçen kelimeler ama burada ALAN ADI.
                "title": {"type": "string", "description": "Grafik başlığı"},
                "default": {"type": "string"},
                "format": {"type": "string"},
                "items": {"type": "integer"},
                "pattern": {"type": "string"},
            },
            "required": ["title", "format"],
        }}}]
    p = _arac_temizle(ham)[0]["function"]["parameters"]

    assert set(p["properties"]) == {"title", "default", "format",
                                    "items", "pattern"}
    assert p["properties"]["title"]["description"] == "Grafik başlığı"
    # Şemanın KENDİ `title` meta-anahtarı yine de atılmış olmalı.
    assert p.get("title") != "ATILMALI — bu şemanın meta başlığı"
    # En kritik değişmez: required'daki her ad tanımlı olmalı.
    assert set(p["required"]) <= set(p["properties"])


def test_hicbir_aracta_required_tanimsiz_alana_isaret_etmez():
    """Kayıt defterinin tamamı için geçerli değişmez.

    Gemini `required` içindeki bir ad `properties`te yoksa isteği
    tümden reddeder ve asistan hiçbir soruya cevap veremez.
    """
    from app.services.assistant import chart_tool as _ct  # noqa: F401
    from app.services.assistant import tools as _t  # noqa: F401
    from app.services.assistant import tools_extended as _te  # noqa: F401
    from app.services.assistant.gemini_provider import _arac_temizle
    from app.services.assistant.tool_registry import registry

    ham = {t["function"]["name"]: t for t in registry.schemas()}
    for arac in _arac_temizle(registry.schemas()):
        fn = arac["function"]
        p = fn.get("parameters") or {}
        alanlar = set(p.get("properties") or {})
        eksik = set(p.get("required") or []) - alanlar
        assert not eksik, f"{fn['name']}: required tanımsız alan {eksik}"

        # Uyarlama hiçbir alanı DÜŞÜRMEMELİ.
        asil = set(((ham[fn["name"]]["function"].get("parameters") or {})
                    .get("properties") or {}))
        assert asil == alanlar, f"{fn['name']}: kaybolan alan {asil - alanlar}"


# ---------------------------------------------------------------------------
# KOTA — DOĞRU BİLGİ VERMEK
# ---------------------------------------------------------------------------
def _kota_cevabi(quota_id: str, gecikme: str = "") -> httpx.Response:
    ihlal = {"quotaId": quota_id}
    detaylar = [{"@type": "type.googleapis.com/google.rpc.QuotaFailure",
                 "violations": [ihlal]}]
    if gecikme:
        detaylar.append({"@type": "type.googleapis.com/google.rpc.RetryInfo",
                         "retryDelay": gecikme})
    return httpx.Response(429, json={"error": {
        "code": 429, "status": "RESOURCE_EXHAUSTED",
        "message": "Quota exceeded", "details": detaylar}})


def test_gunluk_kota_beklemekle_gecmez_dendigi_soylenir():
    """"Kısa bir süre sonra deneyin" GÜNLÜK kotada yanlış bilgidir.

    Ölçüldü: kullanıcı 40 dakika bekledi ve aynı hatayı aldı. Google
    gövdede hangi kotanın dolduğunu zaten söylüyor; okumamak
    kullanıcıyı boşuna bekletiyordu.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        return _kota_cevabi("GenerateRequestsPerDayPerProjectPerModel-FreeTier")

    with pytest.raises(AssistantProviderError) as hata:
        _saglayici(handler).chat([{"role": "user", "content": "x"}])
    mesaj = str(hata.value)
    assert hata.value.kind == "rate_limit"
    assert "GÜNLÜK" in mesaj
    assert "Bekleyerek" in mesaj, "beklemenin çözmediği söylenmeli"


def test_dakikalik_kotada_bekleme_suresi_soylenir():
    def handler(request: httpx.Request) -> httpx.Response:
        return _kota_cevabi("GenerateRequestsPerMinutePerProjectPerModel",
                            gecikme="27s")

    with pytest.raises(AssistantProviderError) as hata:
        _saglayici(handler).chat([{"role": "user", "content": "x"}])
    mesaj = str(hata.value)
    assert "27s" in mesaj
    assert "GÜNLÜK" not in mesaj


def test_kota_ayrintisi_yoksa_genel_mesaj():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "slow down"}})

    with pytest.raises(AssistantProviderError) as hata:
        _saglayici(handler).chat([{"role": "user", "content": "x"}])
    assert hata.value.kind == "rate_limit"


def test_413_hala_token_hatasi_olarak_ayrilir():
    """Kota ile "istek çok büyük" karışmamalı; çözümleri farklı."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(413, json={"error": {"message": "too large"}})

    with pytest.raises(AssistantProviderError) as hata:
        _saglayici(handler).chat([{"role": "user", "content": "x"}])
    assert hata.value.kind == "request_too_large"


def test_hata_govdesi_liste_olarak_gelse_de_okunur():
    """Gemini hatayı bazen TEK ELEMANLI LİSTE olarak döndürüyor.

        [{"error": {"code": 429, "message": "...", "details": [...]}}]

    Kod yalnızca sözlük bekliyordu; liste gelince `.get("error")`
    çalışmıyor ve hata SEBEPSİZ görünüyordu. Ekranda "Gemini isteği
    reddetti: [{" diye başlayan ham çıktıların ve boş `error.message`
    şikâyetlerinin kaynağı buydu.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json=[{"error": {
            "code": 429,
            "message": ("Quota exceeded for metric: "
                        "generate_content_free_tier_requests, limit: 20"),
            "details": [{
                "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                "violations": [{
                    "quotaId":
                        "GenerateRequestsPerDayPerProjectPerModel-FreeTier",
                    "quotaValue": "20"}]}]}}])

    with pytest.raises(AssistantProviderError) as hata:
        _saglayici(handler).chat([{"role": "user", "content": "x"}])
    mesaj = str(hata.value)
    assert "GÜNLÜK" in mesaj
    assert "20" in mesaj, "kotanın büyüklüğü söylenmeli"
    assert "gemini-2.5-flash" in mesaj, "çıkış yolu gösterilmeli"


def test_liste_govdeli_400_de_sebebini_soyler():
    """Aynı kusur 400'lerde de mesajı boş gösteriyordu."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json=[{"error": {
            "code": 400,
            "message": ("Function call is missing a thought_signature in "
                        "functionCall parts.")}}])

    with pytest.raises(AssistantProviderError) as hata:
        _saglayici(handler).chat([{"role": "user", "content": "x"}])
    assert "imza" in str(hata.value).lower()
