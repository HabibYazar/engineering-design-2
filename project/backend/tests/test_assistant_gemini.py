"""Akıllı Asistan — Gemini entegrasyonu ve uç nokta davranışı.

Bu dosyadaki testlerin HİÇBİRİ gerçek Gemini çağrısı yapmaz. Gemini'a giden
HTTP çağrıları istemci seviyesinde taklit edilir; testler ağ, geçerli
anahtar ve kota olmadan çalışır.

Ölçülen şey Gemini'un çalışıp çalışmadığı DEĞİL, uç noktaların ve
`chat_service`in sağlayıcı hatalarına, akışa, konuşma geçmişine ve mesaj
doğrulamasına doğru tepki verdiğidir.

Sağlayıcının kendi ayrıntıları (istek gövdesi, araç ayrıştırma, hata
eşlemesi) ayrı dosyada: `tests/test_gemini_provider.py`.
"""

import json
from typing import Any, Dict, List, Optional

import httpx
import pytest
from fastapi.testclient import TestClient

from app.services.assistant import chat_service
from app.services.assistant.gemini_provider import GeminiProvider
from app.services.assistant.provider_shared import (
    AssistantProviderError,
    split_thinking,
)
from app.core.config import settings
from main import app


#: Model adı sabitlenen senaryolar bunu açıkça belirtir. Otomatik seçim
#: devrede olduğu için (`resolve_model`), sabitlemeden "hesapta model yok"
#: ile "istenen model yok" durumları ayırt edilemez.
PINNED_MODEL = "test-model:latest"


@pytest.fixture(autouse=True)
def _gemini_anahtari(monkeypatch):
    """Testler anahtar olmadan da çalışmalı.

    Sağlayıcı anahtarsızken ağa hiç çıkmaz ve `not_configured` hatası
    fırlatır; bu doğru davranış ama burada sınanan şey o değil. Sahte bir
    anahtar konur, gerçek istek zaten taklit katmanında durdurulur.
    """
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "AIza_test")
    GeminiProvider._otomatik_model = None
    GeminiProvider._model_onbellek = None


@pytest.fixture()
def pinned_model(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_MODEL", PINNED_MODEL)
    return PINNED_MODEL


@pytest.fixture(autouse=True)
def _clean_conversations():
    """Her test kendi konuşma geçmişiyle başlasın."""
    chat_service.reset_conversations()
    yield
    chat_service.reset_conversations()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# Gemini'u taklit eden yardımcılar
# ---------------------------------------------------------------------------


class FakeResponse:
    """httpx.Response yerine geçen asgari nesne."""

    def __init__(self, status_code: int = 200, payload: Optional[Dict] = None,
                 lines: Optional[List[str]] = None) -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self._lines = lines or []

    @property
    def text(self) -> str:
        """Sağlayıcı, hata gövdesini GÜNLÜĞE yazarken bu alanı okur."""
        return json.dumps(self._payload, ensure_ascii=False)

    def json(self) -> Any:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "hata", request=None, response=None  # type: ignore[arg-type]
            )

    def iter_lines(self):
        yield from self._lines

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeClient:
    """httpx.Client yerine geçen taklit istemci.

    `behaviour` bir sözlüktür: yol → (yanıt veya fırlatılacak istisna).
    """

    def __init__(self, behaviour: Dict[str, Any]) -> None:
        self.behaviour = behaviour
        self.calls: List[Dict[str, Any]] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def _resolve(self, path: str, **kwargs):
        self.calls.append({"path": path, **kwargs})
        for key, value in self.behaviour.items():
            if path.endswith(key):
                if isinstance(value, Exception):
                    raise value
                return value
        raise AssertionError(f"Taklit edilmemis istek: {path}")

    def get(self, url: str, **kwargs):
        return self._resolve(url, **kwargs)

    def post(self, url: str, **kwargs):
        return self._resolve(url, **kwargs)

    def stream(self, method: str, url: str, **kwargs):
        return self._resolve(url, **kwargs)


def patch_gemini(monkeypatch, behaviour: Dict[str, Any]) -> FakeClient:
    """Sağlayıcının kullandığı HTTP istemcisini taklitle değiştirir.

    `/models` İÇİN VARSAYILAN VERİLİR. Sağlayıcı, sohbetten önce hesabın
    model listesine bakıp kullanılabilir bir model seçiyor
    (`resolve_model`). Her test bunu ayrıca taklit etmek zorunda kalsaydı
    testin konusu ("zaman aşımı nasıl raporlanır") kurulum gürültüsünün
    altında kalırdı.

    Model listesini SINAYAN testler `behaviour` içinde `/models`
    verir; o zaman bu varsayılan kullanılmaz.
    """
    if "/models" not in behaviour:
        behaviour = {"/models": FakeResponse(payload=tags_payload(PINNED_MODEL)),
                     **behaviour}
    fake = FakeClient(behaviour)
    monkeypatch.setattr(GeminiProvider, "_istemci", lambda self: fake)
    # Model önbelleği testler arasında sızmasın: bir testte seçilen model
    # diğerine taşınırsa `/models` hiç sorulmaz ve taklit boşa çıkar.
    GeminiProvider._otomatik_model = None
    GeminiProvider._model_onbellek = None
    return fake


def sohbet_cagrilari(fake: FakeClient) -> List[Dict[str, Any]]:
    """Yalnızca `/chat/completions` çağrıları.

    `fake.calls[0]` ARTIK SOHBET DEĞİL: sağlayıcı önce hesabın model
    listesini soruyor. İlk çağrıyı sohbet varsayan testler sessizce
    yanlış şeyi ölçerdi.
    """
    return [c for c in fake.calls if "chat/completions" in c["path"]]


def sse(*paylar: Dict) -> List[str]:
    """Gemini akış cevabı — Sunucu Gönderimli Olay (SSE) satırları.

    Ollama her satırda ham JSON gönderiyordu; Gemini OpenAI biçiminde
    "data: {...}" satırları ve sonda "data: [DONE]" gönderir.
    """
    satirlar = [f"data: {json.dumps(p, ensure_ascii=False)}" for p in paylar]
    satirlar.append("data: [DONE]")
    return satirlar


def akis_parcasi(icerik: str) -> Dict:
    return {"choices": [{"delta": {"content": icerik}}]}


def tags_payload(*names: str) -> Dict:
    """Gemini `/models` cevabı (OpenAI uyumlu)."""
    return {"data": [{"id": name} for name in names]}


def chat_payload(content: str, thinking: str = "") -> Dict:
    """Gemini `/chat/completions` cevabı (OpenAI uyumlu)."""
    message: Dict[str, str] = {"role": "assistant", "content": content}
    if thinking:
        message["reasoning"] = thinking
    return {"choices": [{"message": message, "finish_reason": "stop"}]}


# ---------------------------------------------------------------------------
# 1) Gemini erişilemezken status
# ---------------------------------------------------------------------------


def test_status_when_gemini_is_down(client: TestClient, monkeypatch) -> None:
    """Servis kapalıysa uç nokta 200 döner ama hazır olmadığını söyler.

    Bu uç nokta hata fırlatırsa asistan ekranı hiç açılamaz; uygulamanın geri
    kalanı çalışırken bir ekranın çökmesi kabul edilemez.
    """
    patch_gemini(monkeypatch, {"/models": httpx.ConnectError("baglanti yok")})

    response = client.get("/api/assistant/status")
    assert response.status_code == 200

    body = response.json()
    assert body["service_available"] is False
    assert body["model_available"] is False
    assert body["ready"] is False
    assert body["provider"] == "gemini"
    assert "Gemini" in body["message"]
    assert "ulaşılamıyor" in body["message"]


# ---------------------------------------------------------------------------
# 2) Model kurulu değilken status
# ---------------------------------------------------------------------------


def test_yapilandirilan_model_listede_yoksa_da_kullanilir(
        client: TestClient, monkeypatch, pinned_model) -> None:
    """`.env` içindeki ad, model listesi onu saymasa bile KULLANILIR.

    DAVRANIŞ DEĞİŞTİ. Önceki sürüm listeye bakıp ad yoksa başka bir
    modele düşüyordu. Bu, tek bir model için verilmiş anahtarlarda
    yanlış: `/models` ya boş döner ya da anahtarın erişemediği modelleri
    sayar; her iki durumda da sistem ÇALIŞMAYAN bir modele geçiyordu —
    tam olarak `gemini-3-flash-preview` ile yaşanan buydu.

    Kullanıcı `.env` içine bir ad yazdıysa niyeti bellidir. Liste artık
    yapılandırmayı çürütmez, yalnızca not düşer.
    """
    patch_gemini(
        monkeypatch,
        {"/models": FakeResponse(payload=tags_payload("gemini-2.0-flash"))},
    )

    body = client.get("/api/assistant/status").json()

    assert body["service_available"] is True
    assert body["model_available"] is True
    assert body["ready"] is True
    assert body["model"] == PINNED_MODEL          # .env'deki ad korundu
    # Kullanıcı durumu bilmeli: listede görünmüyor ama kullanılıyor.
    assert "listesinde görünmüyor" in body["message"]


def test_model_bos_birakilirsa_otomatik_secim_devreye_girer(
        client: TestClient, monkeypatch) -> None:
    """Otomatik keşif yalnızca yapılandırma BOŞ olduğunda çalışır."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "GEMINI_MODEL", "")
    patch_gemini(
        monkeypatch,
        {"/models": FakeResponse(payload=tags_payload(
            "text-embedding-004", "gemini-2.0-flash"))},
    )

    body = client.get("/api/assistant/status").json()
    assert body["ready"] is True
    assert body["model"] == "gemini-2.0-flash"    # gömme modeli elendi


def test_model_bos_ve_uygun_model_yoksa_durulur(
        client: TestClient, monkeypatch) -> None:
    """Yapılandırma boş VE tanınan model yoksa sistem durur, uydurmaz."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "GEMINI_MODEL", "")
    patch_gemini(
        monkeypatch,
        {"/models": FakeResponse(payload=tags_payload(
            "text-embedding-004", "imagen-3.0"))},
    )

    body = client.get("/api/assistant/status").json()
    assert body["ready"] is False
    assert "araç çağırabilen" in body["message"]


# ---------------------------------------------------------------------------
# 3) Model hazırken status
# ---------------------------------------------------------------------------


def test_status_when_model_is_ready(client: TestClient, monkeypatch, pinned_model) -> None:
    """Servis ayakta ve model kuruluysa ready=True olmalı."""
    from app.core.config import settings

    patch_gemini(
        monkeypatch, {"/models": FakeResponse(payload=tags_payload(PINNED_MODEL))}
    )

    body = client.get("/api/assistant/status").json()

    assert body["service_available"] is True
    assert body["model_available"] is True
    assert body["ready"] is True
    assert body["message"] == f"Yapay zekâ hazır — {PINNED_MODEL}"


# ---------------------------------------------------------------------------
# 4) Boş mesaj doğrulaması
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("message", ["", "   ", "\n\t "])
def test_empty_message_is_rejected(client: TestClient, message: str) -> None:
    """Boş veya yalnızca boşluktan oluşan mesaj kabul edilmemeli."""
    response = client.post("/api/assistant/chat", json={"message": message})
    assert response.status_code == 422


def test_empty_message_never_reaches_the_model(monkeypatch) -> None:
    """Doğrulama sağlayıcıdan ÖNCE çalışmalı; boşuna model çağrılmamalı."""
    fake = patch_gemini(monkeypatch, {"/chat/completions": FakeResponse(payload=chat_payload("x"))})

    with pytest.raises(chat_service.ChatValidationError):
        chat_service.answer("   ")

    assert fake.calls == [], "Boş mesaj için modele istek gönderilmiş."


# ---------------------------------------------------------------------------
# 5) Çok uzun mesaj doğrulaması
# ---------------------------------------------------------------------------


def test_too_long_message_is_rejected(client: TestClient) -> None:
    """Üst sınırın üzerindeki mesaj reddedilmeli."""
    from app.core.config import settings

    long_message = "a" * (settings.ASSISTANT_MAX_MESSAGE_LENGTH + 1)
    response = client.post("/api/assistant/chat", json={"message": long_message})
    assert response.status_code == 422


def test_service_layer_also_enforces_length_limit() -> None:
    """Sınır yalnızca şemada değil, serviste de olmalı.

    Servis doğrudan çağrıldığında (ör. ileride bir arka plan görevinden)
    HTTP katmanı devrede olmaz; koruma orada da bulunmalı.
    """
    from app.core.config import settings

    with pytest.raises(chat_service.ChatValidationError) as exc:
        chat_service.validate_message("a" * (settings.ASSISTANT_MAX_MESSAGE_LENGTH + 1))
    assert "çok uzun" in exc.value.user_message.lower()


# ---------------------------------------------------------------------------
# 6) Sağlayıcı zaman aşımı
# ---------------------------------------------------------------------------


def test_provider_timeout_returns_controlled_answer(client: TestClient, monkeypatch) -> None:
    """Model yanıt vermezse kullanıcı 504 değil, açıklayıcı bir cevap alır.

    DAVRANIŞ BİLEREK DEĞİŞTİ. Eskiden bu durum 504 Gateway Timeout
    üretiyordu; arayüzde bekleme göstergesi dönmeye devam ediyor,
    kullanıcı ekranda hiçbir şey görmüyordu. Üstelik o ana kadar
    veritabanından okunmuş araç sonuçları da istisnayla birlikte
    kayboluyordu.

    Artık istek normal biçimde tamamlanır: gösterge kapanır, kullanıcı
    ne olduğunu okur ve varsa getirilmiş veriler cevabın içinde kalır.
    """
    patch_gemini(monkeypatch, {"/chat/completions": httpx.ReadTimeout("cok uzun surdu")})

    response = client.post("/api/assistant/chat", json={"message": "Merhaba"})

    assert response.status_code == 200
    cevap = response.json()["answer"].lower()
    # Kullanıcı boş ekranla kalmaz AMA teknik ayrıntı da görmez:
    # "zaman aşımı", "timeout", "Gemini" gibi ifadeler sunumda sistemin
    # çöktüğü izlenimi veriyordu. Sebep yalnızca günlükte durur.
    assert cevap.strip(), "boş cevap"
    assert "tekrar" in cevap
    for yasak in ("zaman aşımı", "timeout", "gemini"):
        assert yasak not in cevap


def test_timeout_uses_configured_value(monkeypatch) -> None:
    """Zaman aşımı süresi yapılandırmadan gelmeli, koda gömülü olmamalı."""
    from app.core.config import settings

    provider = GeminiProvider()
    assert provider.timeout_seconds == settings.GEMINI_TIMEOUT_SECONDS


# ---------------------------------------------------------------------------
# 7) Gemini hata cevabı
# ---------------------------------------------------------------------------


def test_gemini_404_is_reported_as_missing_model(client: TestClient, monkeypatch) -> None:
    """Gemini kurulu olmayan model için 404 döner; bunu kullanıcıya çevirmeliyiz."""
    patch_gemini(monkeypatch, {"/chat/completions": FakeResponse(status_code=404)})

    response = client.post("/api/assistant/chat", json={"message": "Merhaba"})

    assert response.status_code == 503
    assert "kullanılamıyor" in response.json()["detail"]


def test_gemini_500_kontrollu_cevaba_donusur(client: TestClient, monkeypatch) -> None:
    """Sağlayıcı 500 dönse bile istek 502 ile ölmez.

    SÖZLEŞME DEĞİŞTİ. Eskiden burada 502 bekleniyordu. Ölçüldü ki bu,
    veri araçları çalışmış olsa dahi kullanıcıyı "Bad Gateway" ekranıyla
    baş başa bırakıyordu. Sağlayıcının susması bir ağ geçidi arızası
    değildir; istek kontrollü bir uygulama cevabıyla 200 döner.

    Testin KORUDUĞU DEĞER aynı kalır: bozuk cevap sessizce uydurma bir
    sonuca dönüşmez. Bunu artık durum kodu değil, cevabın KENDİSİ
    kanıtlar — kurumsal veri iddiası taşımaz.
    """
    patch_gemini(monkeypatch, {"/chat/completions": FakeResponse(status_code=500)})

    response = client.post("/api/assistant/chat", json={"message": "Merhaba"})

    assert response.status_code == 200, response.text
    govde = response.json()
    assert govde["answer"].strip()
    assert "Modelden geçerli bir yanıt alınamadı" not in govde["answer"]
    # Veri yokken kurumsal veri iddiası edilmez.
    assert govde["data_source"] != "institutional_data"


def test_malformed_gemini_payload_uydurma_cevaba_donusmez(
        client: TestClient, monkeypatch) -> None:
    """Beklenen alanları taşımayan cevap sessizce uydurma sonuca dönüşmemeli.

    Durum kodu artık 200 (yukarıdaki gerekçe). Asıl korunan şey, gövdenin
    veri iddiası taşımaması ve kullanıcının ne yapacağını bilmesidir.
    """
    patch_gemini(monkeypatch, {"/chat/completions": FakeResponse(payload={"beklenmeyen": True})})

    response = client.post("/api/assistant/chat", json={"message": "Merhaba"})

    assert response.status_code == 200, response.text
    govde = response.json()
    assert govde["answer"].strip()
    assert govde["data_source"] != "institutional_data"
    assert not govde.get("used_tools")


def test_connection_error_returns_service_unavailable(client: TestClient, monkeypatch) -> None:
    """Gemini kapalıyken sohbet isteği 503 dönmeli."""
    patch_gemini(monkeypatch, {"/chat/completions": httpx.ConnectError("kapali")})

    response = client.post("/api/assistant/chat", json={"message": "Merhaba"})

    assert response.status_code == 503
    assert "Gemini" in response.json()["detail"]


# ---------------------------------------------------------------------------
# 8) Normal sohbet cevabı
# ---------------------------------------------------------------------------


def test_successful_chat_returns_model_answer(client: TestClient, monkeypatch, pinned_model) -> None:
    """Başarılı çağrıda modelin cevabı ve künye bilgileri dönmeli."""
    from app.core.config import settings

    patch_gemini(
        monkeypatch,
        {"/chat/completions": FakeResponse(payload=chat_payload("Merhaba, nasıl yardımcı olabilirim?"))},
    )

    body = client.post("/api/assistant/chat", json={"message": "Merhaba"}).json()

    assert body["answer"] == "Merhaba, nasıl yardımcı olabilirim?"
    assert body["provider"] == "gemini"
    assert body["model"] == PINNED_MODEL
    assert body["conversation_id"]
    # Bu aşamada araç çağrısı yok; alan boş kalmalı ki sonraki aşama fark edilsin.
    assert body["used_tools"] == []
    assert body["data_source"] == "general_model_knowledge"


def test_system_prompt_is_sent_with_every_request(monkeypatch) -> None:
    """Modele her istekte Türkçe sistem yönergesi gitmeli."""
    fake = patch_gemini(
        monkeypatch, {"/chat/completions": FakeResponse(payload=chat_payload("Tamam."))}
    )

    chat_service.answer("Merhaba")

    sent = sohbet_cagrilari(fake)[0]["json"]["messages"]
    assert sent[0]["role"] == "system"
    assert "Ankara Bilim Üniversitesi" in sent[0]["content"]
    assert "Türkçe" in sent[0]["content"]
    # Yönerge, kurumsal sayıların yalnızca backend bağlamından ya da araç
    # sonuçlarından alınmasını ve ikisi de yokken sayı uydurulmamasını
    # dayatmalı.
    #
    # KELİMESİ KELİMESİNE EŞLEŞME ARANMAZ. Eski hâli "YALNIZCA araç
    # sonuçlarından" cümlesini birebir arıyordu; yönergeye backend
    # bağlamı eklenince cümle yeniden yazıldı ve test, kural hâlâ
    # yerindeyken kırıldı. Sınanan şey CÜMLE değil KURAL olmalı.
    metin = sent[0]["content"]
    assert "YALNIZCA" in metin
    assert "araç sonuç" in metin
    assert "UYDURMA" in metin
    # Kapalı dünya kuralı da her istekte gitmeli.
    assert "internet" in metin.lower()


def test_conversation_history_is_carried_over(monkeypatch) -> None:
    """Aynı konuşma kimliğiyle gönderilen ikinci mesaj geçmişi taşımalı."""
    fake = patch_gemini(
        monkeypatch, {"/chat/completions": FakeResponse(payload=chat_payload("İlk cevap."))}
    )

    first = chat_service.answer("Birinci soru")
    chat_service.answer("İkinci soru", first["conversation_id"])

    second_request = sohbet_cagrilari(fake)[1]["json"]["messages"]
    contents = [m["content"] for m in second_request]
    assert "Birinci soru" in contents
    assert "İlk cevap." in contents
    assert contents[-1] == "İkinci soru"


def test_new_conversation_starts_clean(monkeypatch) -> None:
    """Konuşma kimliği verilmezse geçmiş taşınmamalı."""
    fake = patch_gemini(
        monkeypatch, {"/chat/completions": FakeResponse(payload=chat_payload("Cevap."))}
    )

    chat_service.answer("Birinci soru")
    chat_service.answer("Bağımsız soru")

    second_request = sohbet_cagrilari(fake)[1]["json"]["messages"]
    assert len(second_request) == 2, "Yeni konuşmaya eski geçmiş sızmış."
    assert second_request[0]["role"] == "system"
    assert second_request[1]["content"] == "Bağımsız soru"


def test_request_uses_configured_options(monkeypatch, pinned_model) -> None:
    """Sıcaklık ve cevap sınırı yapılandırmadan gelmeli.

    Gemini (OpenAI uyumlu) bu değerleri gövdenin KÖKÜNDE bekler; Ollama
    onları `options` sözlüğüne koyuyordu.
    """
    from app.core.config import settings

    fake = patch_gemini(
        monkeypatch, {"/chat/completions": FakeResponse(payload=chat_payload("Tamam."))}
    )

    chat_service.answer("Merhaba")

    payload = sohbet_cagrilari(fake)[0]["json"]
    assert payload["model"] == PINNED_MODEL
    assert payload["temperature"] == settings.GEMINI_TEMPERATURE
    assert payload["max_tokens"] == settings.GEMINI_MAX_TOKENS
    assert payload["stream"] is False


# ---------------------------------------------------------------------------
# 9) Düşünme metninin kullanıcı cevabına karışmaması
# ---------------------------------------------------------------------------


def test_inline_thinking_block_is_stripped(client: TestClient, monkeypatch) -> None:
    """<think> bloğu cevaptan çıkarılmalı."""
    raw = (
        "<think>Kullanici selam verdi. Once nazikce karsilik vermeliyim, "
        "sonra ne yapabilecegimi anlatmaliyim.</think>\n"
        "Merhaba! Size nasıl yardımcı olabilirim?"
    )
    patch_gemini(monkeypatch, {"/chat/completions": FakeResponse(payload=chat_payload(raw))})

    body = client.post("/api/assistant/chat", json={"message": "Merhaba"}).json()

    assert body["answer"] == "Merhaba! Size nasıl yardımcı olabilirim?"
    assert "<think>" not in body["answer"]
    assert "Kullanici selam verdi" not in body["answer"]


def test_separate_thinking_field_is_not_returned(client: TestClient, monkeypatch) -> None:
    """Gemini muhakemeyi ayrı alanda dönerse o alan da sızmamalı."""
    patch_gemini(
        monkeypatch,
        {
            "/chat/completions": FakeResponse(
                payload=chat_payload("Kısa cevap.", thinking="Once sunu dusundum...")
            )
        },
    )

    body = client.post("/api/assistant/chat", json={"message": "Merhaba"}).json()

    assert body["answer"] == "Kısa cevap."
    assert "dusundum" not in json.dumps(body, ensure_ascii=False)
    # Cevap gövdesinde düşünme için bir alan hiç bulunmamalı.
    assert "thinking" not in body


def test_unclosed_thinking_block_is_stripped() -> None:
    """Model yarıda kesilirse kalan muhakeme metni gösterilmemeli."""
    visible, thinking = split_thinking("<think>Yarim kalmis muhakeme")
    assert visible == ""
    assert "Yarim kalmis" in thinking


def test_answer_with_only_thinking_bos_balon_birakmaz(
        client: TestClient, monkeypatch) -> None:
    """Yalnızca muhakeme üretilmişse kullanıcı boş balonla kalmamalı.

    Eskiden 502 bekleniyordu; artık kontrollü bir metinle 200 dönülür.
    Korunan davranış aynı: muhakeme metni kullanıcıya SIZMAZ ve ekranda
    boş balon oluşmaz.
    """
    patch_gemini(
        monkeypatch, {"/chat/completions": FakeResponse(payload=chat_payload("<think>sadece dusunce</think>"))}
    )

    response = client.post("/api/assistant/chat", json={"message": "Merhaba"})

    assert response.status_code == 200, response.text
    govde = response.json()
    assert govde["answer"].strip()          # boş balon yok
    assert "sadece dusunce" not in govde["answer"]   # muhakeme sızmadı
    assert "thinking" not in govde


def test_streaming_filters_thinking(monkeypatch) -> None:
    """Akışta da muhakeme parçaları yayınlanmamalı."""
    lines = sse(
        akis_parcasi("<thi"),
        akis_parcasi("nk>gizli muhakeme"),
        akis_parcasi(" devam ediyor</think>"),
        akis_parcasi("Görünen "),
        akis_parcasi("cevap."),
    )
    patch_gemini(monkeypatch, {"/chat/completions": FakeResponse(lines=lines)})

    provider = GeminiProvider()
    output = "".join(provider.stream_chat([{"role": "user", "content": "selam"}]))

    assert output == "Görünen cevap."
    assert "gizli" not in output
    assert "think" not in output


# ---------------------------------------------------------------------------
# 10) Frontend durum metinleri
# ---------------------------------------------------------------------------


def _assistant_view_source() -> str:
    import pathlib

    path = (
        pathlib.Path(__file__).resolve().parents[2]
        / "frontend"
        / "assets"
        / "views-assistant.js"
    )
    return path.read_text(encoding="utf-8")


def test_frontend_has_explicit_status_texts() -> None:
    """Arayüz her durumu ayrı ve anlaşılır bir metinle göstermeli."""
    source = _assistant_view_source()
    for expected in (
        "Bağlantı kuruluyor",
        "Yapay zekâ hazır",
        "Gemini servisine ulaşılamıyor",
        # "Model kurulu değil" → "Model kullanılamıyor": Gemini'ta model
        # KURULMAZ, uzakta durur. Kullanıcıya yapamayacağı bir eylemi
        # ("kur") ima eden metin yanlış yönlendirir.
        "Model kullanılamıyor",
        "Yanıt oluşturuluyor",
        "Hata oluştu",
    ):
        assert expected in source, f"Arayüzde eksik durum metni: {expected}"


def test_frontend_does_not_use_vague_api_connected_text() -> None:
    """Asistan ekranında 'API bağlı' gibi belirsiz metin olmamalı.

    Kontrol yalnızca kullanıcıya GÖSTERİLEN metinde yapılır; yorum satırları
    bu kuralı neden koyduğumuzu anlatabilmeli.
    """
    code = "\n".join(
        line for line in _assistant_view_source().splitlines()
        if not line.strip().startswith("//")
    )
    assert "API bağlı" not in code
    assert "API bagli" not in code


# ---------------------------------------------------------------------------
# 11) Sahte cevap kalmadığının kontrolü
# ---------------------------------------------------------------------------


def test_no_mock_provider_remains() -> None:
    """Sahte/mock sağlayıcı veya hard-coded cevap kalmamalı."""
    import pathlib
    import re

    assistant_dir = pathlib.Path(__file__).resolve().parents[1] / "app" / "services" / "assistant"
    forbidden = re.compile(r"(?i)\b(mock|fake|dummy|stub)provider\b|hard[_-]?coded answer")

    findings = []
    for path in assistant_dir.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if forbidden.search(text):
            findings.append(path.name)
    assert not findings, f"Sahte sağlayıcı izi: {findings}"


def test_frontend_has_no_canned_answers() -> None:
    """Arayüzde gömülü örnek cevap bulunmamalı."""
    source = _assistant_view_source()
    for phrase in ("İşte cevabınız", "Örnek cevap", "Merhaba, ben asistanınız"):
        assert phrase not in source, f"Arayüzde gömülü cevap: {phrase}"


def _kaynak_dosyalari(kok):
    """Politika taramasının bakacağı .py dosyaları.

    Gezilen yerler kasıtlı olarak dardır: `app/`, `tests/` ve kök
    dizindeki betikler. Sanal ortam, önbellek ve test artıkları dışarıda
    kalır — oralarda bulunacak bir eşleşme zaten bizim kodumuz olmazdı.
    """
    import pathlib

    for alt in ("app", "tests"):
        d = kok / alt
        if not d.is_dir():
            continue
        for p in d.rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            yield p
    for p in kok.glob("*.py"):
        yield p


def test_gemini_disinda_bulut_saglayicisi_kullanilmaz() -> None:
    """POLİTİKA DEĞİŞTİ, TAMAMEN KALKMADI.

    Eski kural "hiçbir bulut sağlayıcısı" idi ve Gemini'a geçişle bilinçli
    olarak gevşetildi. Ancak gevşeme TEK BİR sağlayıcı içindir: OpenAI,
    Anthropic ve Gemini hâlâ yasak. Bu test o sınırı korur — yoksa
    "zaten buluta çıkıyoruz" gerekçesiyle kapı herkese açılırdı.
    """
    import pathlib
    import re

    backend = pathlib.Path(__file__).resolve().parents[1]
    # GEMINI ARTIK İZİNLİ — LİSTEDEN ÇIKARILDI.
    # Politika "hiçbir bulut" → "yalnızca seçilen bulut" oldu. Gevşeme
    # TEK sağlayıcı içindir: OpenAI ve Anthropic hâlâ yasak. Bu sınır
    # olmasaydı "zaten buluta çıkıyoruz" gerekçesiyle kapı herkese
    # açılırdı.
    forbidden = re.compile(
        r"(?i)\b(import\s+openai|from\s+openai|import\s+anthropic|"
        r"from\s+anthropic|api\.openai\.com|api\.anthropic\.com)\b"
    )
    findings = []

    # TARAMA YALNIZCA KAYNAK AĞACINDA.
    # ------------------------------------------------------------------
    # Eskiden `backend.rglob("*.py")` ile her şey geziliyordu. Test
    # artıkları (`.pytest_data_sources`) bulut eşitlemeli bir diskte
    # okunamayan girdiler bırakabiliyor ve tarama OSError ile ÇÖKÜYOR —
    # üstelik hata "politika ihlali" gibi görünüyor. İhlali kaynak
    # kodunda ararız; geçici dosyalarda değil.
    for path in _kaynak_dosyalari(backend):
        if forbidden.search(path.read_text(encoding="utf-8", errors="ignore")):
            findings.append(str(path.relative_to(backend)))
    assert not findings, f"İzinsiz bulut LLM sağlayıcısı: {findings}"


def test_asistanin_web_erisimi_yoktur() -> None:
    """Modelin erişebildiği araçların hiçbiri ağa çıkmamalı.

    Kullanıcının koyduğu kural: "webe bakması yasak, sadece elimizdeki
    datalara erişebilsin." Modelin kendi başına istek gönderme yeteneği
    yok; ağa çıkma yeteneği ARAÇ KATMANINDA olurdu. O yüzden kontrol
    araç modüllerinde yapılır.

    Sağlayıcı modülleri bu kontrolün DIŞINDADIR: Gemini çağrısı zaten tek
    ve bilinçli dış bağlantıdır.
    """
    import pathlib
    import re

    kok = pathlib.Path(__file__).resolve().parents[1] / "app" / "services" / "assistant"
    arac_modulleri = ["tools.py", "tools_extended.py", "tool_runner.py",
                      "tool_registry.py", "data_access.py", "data_catalog.py"]
    ag = re.compile(
        r"(?m)^\s*(import|from)\s+(httpx|requests|urllib|urllib3|aiohttp|socket|"
        r"http\.client|ftplib|telnetlib)\b")

    bulunan = []
    for ad in arac_modulleri:
        yol = kok / ad
        if yol.exists() and ag.search(yol.read_text(encoding="utf-8", errors="ignore")):
            bulunan.append(ad)
    assert not bulunan, f"Araç katmanında ağ kütüphanesi: {bulunan}"


def test_kayitli_araclarin_hicbiri_web_araci_degildir() -> None:
    """Kayıt defterinde web arama / sayfa getirme aracı bulunmamalı."""
    from app.services.assistant import tools as _t  # noqa: F401  (kayıt için)
    from app.services.assistant import tools_extended as _te  # noqa: F401
    from app.services.assistant.tool_registry import registry

    araclar = registry.all() if hasattr(registry, "all") else list(registry._tools.values())
    assert araclar, "Kayıt defteri boş: test anlamsız olurdu."

    yasak = ("web", "search_internet", "browse", "fetch_url", "http_get", "url")
    ihlal = [t.name for t in araclar if any(k in t.name.lower() for k in yasak)]
    assert not ihlal, f"Web erişimi ima eden araç: {ihlal}"


def test_sistem_yonergesi_internet_yasagini_soyler() -> None:
    """Kural yalnızca kodda değil, modele verilen yönergede de olmalı.

    Kod katmanı modelin ağa ÇIKMASINI engeller; yönerge ise modelin
    "internetten baktım" diye UYDURMASINI engeller. İkisi farklı hata
    sınıflarıdır ve ikisi de gerekir.
    """
    from app.services.assistant.chat_service import SYSTEM_PROMPT

    metin = SYSTEM_PROMPT.lower()
    assert "internet" in metin
    assert "erişimin yoktur" in metin or "erisimin yoktur" in metin


def test_disari_cikilan_tek_adres_geminitur() -> None:
    """Yapılandırmada Gemini dışında bir dış adres bulunmamalı.

    Eski sürümde bu testin yerinde "adres yerel olmalı" kuralı vardı;
    Gemini'a geçişle o kural anlamını yitirdi. Yerine geçen kural: dışarıya
    açılan TEK kapı Gemini'tur ve adresi değiştirilerek veri başka bir
    yere yönlendirilmiş olmamalı.
    """
    from app.core.config import settings

    assert settings.GEMINI_BASE_URL.startswith("https://generativelanguage.googleapis.com")
    assert settings.LLM_PROVIDER == "gemini"


def test_status_survives_unexpected_provider_failure(client: TestClient, monkeypatch) -> None:
    """Beklenmeyen bir hata durum ekranını çökertmemeli."""

    def explode(self):
        raise ImportError("eksik bir eklenti")

    monkeypatch.setattr(GeminiProvider, "_istemci", explode)

    response = client.get("/api/assistant/status")

    assert response.status_code == 200
    assert response.json()["ready"] is False


def test_other_endpoints_still_work_when_gemini_is_down(client: TestClient, monkeypatch) -> None:
    """Asistan bozukken uygulamanın geri kalanı çalışmaya devam etmeli."""
    patch_gemini(monkeypatch, {"/models": httpx.ConnectError("kapali")})

    assert client.get("/health").status_code == 200
    assert client.get("/api/assistant/status").status_code == 200
    assert client.get("/api/faculties").status_code == 200


def test_streaming_endpoint_reports_errors_inside_the_stream(
    client: TestClient, monkeypatch
) -> None:
    """Akış başladıktan sonra oluşan hata, akışın içinde bildirilmeli."""
    patch_gemini(monkeypatch, {"/chat/completions": httpx.ConnectError("kapali")})

    with client.stream(
        "POST", "/api/assistant/chat/stream", json={"message": "Merhaba"}
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    assert '"type": "error"' in body
    assert "Gemini" in body


def test_streaming_endpoint_emits_chunks_and_done(client: TestClient, monkeypatch) -> None:
    """Normal akışta parçalar ve bitiş olayı gönderilmeli."""
    lines = sse(akis_parcasi("Merhaba "), akis_parcasi("dünya."))
    patch_gemini(monkeypatch, {"/chat/completions": FakeResponse(lines=lines)})

    with client.stream(
        "POST", "/api/assistant/chat/stream", json={"message": "Selam"}
    ) as response:
        body = "".join(response.iter_text())

    assert '"type": "chunk"' in body
    assert "Merhaba" in body
    assert '"type": "done"' in body


def test_chat_request_rejects_unknown_fields(client: TestClient) -> None:
    """Bilinmeyen alan sessizce yok sayılmamalı.

    Sessiz yok sayma, arayüzle backend arasında alan adı uyuşmazlığını gizler;
    bu proje daha önce tam olarak bu hatadan zarar gördü.
    """
    response = client.post(
        "/api/assistant/chat", json={"message": "Merhaba", "temperature": 0.9}
    )
    assert response.status_code == 422
