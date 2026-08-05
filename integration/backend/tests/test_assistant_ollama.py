"""Akıllı Asistan — yerel Ollama entegrasyonu testleri.

Bu dosyadaki testlerin HİÇBİRİ gerçek Ollama gerektirmez. Ollama'ya giden HTTP
çağrıları `httpx.Client` seviyesinde taklit edilir; böylece testler geliştirici
makinesinde model kurulu olmasa da çalışır.

Gerçek Ollama ile çalışan isteğe bağlı test ayrı dosyadadır:
`tests/test_assistant_ollama_live.py`.
"""

import json
from typing import Any, Dict, List, Optional

import httpx
import pytest
from fastapi.testclient import TestClient

from app.services.assistant import chat_service
from app.services.assistant.ollama_provider import (
    AssistantProviderError,
    OllamaProvider,
    split_thinking,
)
from main import app


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
# Ollama'yı taklit eden yardımcılar
# ---------------------------------------------------------------------------


class FakeResponse:
    """httpx.Response yerine geçen asgari nesne."""

    def __init__(self, status_code: int = 200, payload: Optional[Dict] = None,
                 lines: Optional[List[str]] = None) -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self._lines = lines or []

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


def patch_ollama(monkeypatch, behaviour: Dict[str, Any]) -> FakeClient:
    """Sağlayıcının kullandığı HTTP istemcisini taklitle değiştirir."""
    fake = FakeClient(behaviour)
    monkeypatch.setattr(
        "app.services.assistant.ollama_provider._local_client",
        lambda timeout: fake,
    )
    return fake


def tags_payload(*names: str) -> Dict:
    return {"models": [{"name": name} for name in names]}


def chat_payload(content: str, thinking: str = "") -> Dict:
    message: Dict[str, str] = {"role": "assistant", "content": content}
    if thinking:
        message["thinking"] = thinking
    return {"message": message, "done": True}


# ---------------------------------------------------------------------------
# 1) Ollama servisi kapalıyken status
# ---------------------------------------------------------------------------


def test_status_when_ollama_is_down(client: TestClient, monkeypatch) -> None:
    """Servis kapalıysa uç nokta 200 döner ama hazır olmadığını söyler.

    Bu uç nokta hata fırlatırsa asistan ekranı hiç açılamaz; uygulamanın geri
    kalanı çalışırken bir ekranın çökmesi kabul edilemez.
    """
    patch_ollama(monkeypatch, {"/api/tags": httpx.ConnectError("baglanti yok")})

    response = client.get("/api/assistant/status")
    assert response.status_code == 200

    body = response.json()
    assert body["service_available"] is False
    assert body["model_available"] is False
    assert body["ready"] is False
    assert body["provider"] == "ollama"
    assert "Ollama" in body["message"]
    assert "çalıştığından emin olun" in body["message"]


# ---------------------------------------------------------------------------
# 2) Model kurulu değilken status
# ---------------------------------------------------------------------------


def test_status_when_model_is_not_installed(client: TestClient, monkeypatch) -> None:
    """Servis ayakta ama model yoksa 'model bulunamadı' mesajı verilmeli."""
    patch_ollama(
        monkeypatch,
        {"/api/tags": FakeResponse(payload=tags_payload("llama3:8b", "mistral:7b"))},
    )

    body = client.get("/api/assistant/status").json()

    assert body["service_available"] is True
    assert body["model_available"] is False
    assert body["ready"] is False
    # Kullanıcı ne yapacağını bilmeli: kurulum komutu mesajda geçmeli.
    assert "ollama pull" in body["message"]
    assert body["model"] in body["message"]
    # Kurulu modeller bilgilendirme amacıyla döndürülür.
    assert body["installed_models"] == ["llama3:8b", "mistral:7b"]


# ---------------------------------------------------------------------------
# 3) Model hazırken status
# ---------------------------------------------------------------------------


def test_status_when_model_is_ready(client: TestClient, monkeypatch) -> None:
    """Servis ayakta ve model kuruluysa ready=True olmalı."""
    from app.core.config import settings

    patch_ollama(
        monkeypatch, {"/api/tags": FakeResponse(payload=tags_payload(settings.OLLAMA_MODEL))}
    )

    body = client.get("/api/assistant/status").json()

    assert body["service_available"] is True
    assert body["model_available"] is True
    assert body["ready"] is True
    assert body["message"] == f"Yapay zekâ hazır — {settings.OLLAMA_MODEL}"


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
    fake = patch_ollama(monkeypatch, {"/api/chat": FakeResponse(payload=chat_payload("x"))})

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


def test_provider_timeout_returns_gateway_timeout(client: TestClient, monkeypatch) -> None:
    """Model yanıt vermezse 504 ve anlaşılır bir mesaj dönmeli."""
    patch_ollama(monkeypatch, {"/api/chat": httpx.ReadTimeout("cok uzun surdu")})

    response = client.post("/api/assistant/chat", json={"message": "Merhaba"})

    assert response.status_code == 504
    assert "zaman aşımı" in response.json()["detail"].lower()


def test_timeout_uses_configured_value(monkeypatch) -> None:
    """Zaman aşımı süresi yapılandırmadan gelmeli, koda gömülü olmamalı."""
    from app.core.config import settings

    provider = OllamaProvider()
    assert provider.timeout_seconds == settings.OLLAMA_TIMEOUT_SECONDS


# ---------------------------------------------------------------------------
# 7) Ollama hata cevabı
# ---------------------------------------------------------------------------


def test_ollama_404_is_reported_as_missing_model(client: TestClient, monkeypatch) -> None:
    """Ollama kurulu olmayan model için 404 döner; bunu kullanıcıya çevirmeliyiz."""
    patch_ollama(monkeypatch, {"/api/chat": FakeResponse(status_code=404)})

    response = client.post("/api/assistant/chat", json={"message": "Merhaba"})

    assert response.status_code == 503
    assert "ollama pull" in response.json()["detail"]


def test_ollama_500_is_reported_as_bad_gateway(client: TestClient, monkeypatch) -> None:
    """Sunucu hatası kullanıcıya kontrollü biçimde bildirilmeli."""
    patch_ollama(monkeypatch, {"/api/chat": FakeResponse(status_code=500)})

    response = client.post("/api/assistant/chat", json={"message": "Merhaba"})

    assert response.status_code == 502
    assert response.json()["detail"]


def test_malformed_ollama_payload_is_rejected(client: TestClient, monkeypatch) -> None:
    """Beklenen alanları taşımayan cevap sessizce boş cevaba dönüşmemeli."""
    patch_ollama(monkeypatch, {"/api/chat": FakeResponse(payload={"beklenmeyen": True})})

    response = client.post("/api/assistant/chat", json={"message": "Merhaba"})

    assert response.status_code == 502


def test_connection_error_returns_service_unavailable(client: TestClient, monkeypatch) -> None:
    """Ollama kapalıyken sohbet isteği 503 dönmeli."""
    patch_ollama(monkeypatch, {"/api/chat": httpx.ConnectError("kapali")})

    response = client.post("/api/assistant/chat", json={"message": "Merhaba"})

    assert response.status_code == 503
    assert "Ollama" in response.json()["detail"]


# ---------------------------------------------------------------------------
# 8) Normal sohbet cevabı
# ---------------------------------------------------------------------------


def test_successful_chat_returns_model_answer(client: TestClient, monkeypatch) -> None:
    """Başarılı çağrıda modelin cevabı ve künye bilgileri dönmeli."""
    from app.core.config import settings

    patch_ollama(
        monkeypatch,
        {"/api/chat": FakeResponse(payload=chat_payload("Merhaba, nasıl yardımcı olabilirim?"))},
    )

    body = client.post("/api/assistant/chat", json={"message": "Merhaba"}).json()

    assert body["answer"] == "Merhaba, nasıl yardımcı olabilirim?"
    assert body["provider"] == "ollama"
    assert body["model"] == settings.OLLAMA_MODEL
    assert body["conversation_id"]
    # Bu aşamada araç çağrısı yok; alan boş kalmalı ki sonraki aşama fark edilsin.
    assert body["used_tools"] == []
    assert body["data_source"] == "general_model_knowledge"


def test_system_prompt_is_sent_with_every_request(monkeypatch) -> None:
    """Modele her istekte Türkçe sistem yönergesi gitmeli."""
    fake = patch_ollama(
        monkeypatch, {"/api/chat": FakeResponse(payload=chat_payload("Tamam."))}
    )

    chat_service.answer("Merhaba")

    sent = fake.calls[0]["json"]["messages"]
    assert sent[0]["role"] == "system"
    assert "Ankara Bilim Üniversitesi" in sent[0]["content"]
    assert "Türkçe" in sent[0]["content"]
    # Yönerge modele veri erişimi olmadığını söylemeli; yoksa sayı uydurur.
    assert "ERİŞİMİN YOK" in sent[0]["content"]
    assert "UYDURMA" in sent[0]["content"]


def test_conversation_history_is_carried_over(monkeypatch) -> None:
    """Aynı konuşma kimliğiyle gönderilen ikinci mesaj geçmişi taşımalı."""
    fake = patch_ollama(
        monkeypatch, {"/api/chat": FakeResponse(payload=chat_payload("İlk cevap."))}
    )

    first = chat_service.answer("Birinci soru")
    chat_service.answer("İkinci soru", first["conversation_id"])

    second_request = fake.calls[1]["json"]["messages"]
    contents = [m["content"] for m in second_request]
    assert "Birinci soru" in contents
    assert "İlk cevap." in contents
    assert contents[-1] == "İkinci soru"


def test_new_conversation_starts_clean(monkeypatch) -> None:
    """Konuşma kimliği verilmezse geçmiş taşınmamalı."""
    fake = patch_ollama(
        monkeypatch, {"/api/chat": FakeResponse(payload=chat_payload("Cevap."))}
    )

    chat_service.answer("Birinci soru")
    chat_service.answer("Bağımsız soru")

    second_request = fake.calls[1]["json"]["messages"]
    assert len(second_request) == 2, "Yeni konuşmaya eski geçmiş sızmış."
    assert second_request[0]["role"] == "system"
    assert second_request[1]["content"] == "Bağımsız soru"


def test_request_uses_configured_options(monkeypatch) -> None:
    """Sıcaklık ve bağlam uzunluğu yapılandırmadan gelmeli."""
    from app.core.config import settings

    fake = patch_ollama(
        monkeypatch, {"/api/chat": FakeResponse(payload=chat_payload("Tamam."))}
    )

    chat_service.answer("Merhaba")

    payload = fake.calls[0]["json"]
    assert payload["model"] == settings.OLLAMA_MODEL
    assert payload["options"]["temperature"] == settings.OLLAMA_TEMPERATURE
    assert payload["options"]["num_ctx"] == settings.OLLAMA_CONTEXT_LENGTH
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
    patch_ollama(monkeypatch, {"/api/chat": FakeResponse(payload=chat_payload(raw))})

    body = client.post("/api/assistant/chat", json={"message": "Merhaba"}).json()

    assert body["answer"] == "Merhaba! Size nasıl yardımcı olabilirim?"
    assert "<think>" not in body["answer"]
    assert "Kullanici selam verdi" not in body["answer"]


def test_separate_thinking_field_is_not_returned(client: TestClient, monkeypatch) -> None:
    """Ollama muhakemeyi ayrı alanda dönerse o alan da sızmamalı."""
    patch_ollama(
        monkeypatch,
        {
            "/api/chat": FakeResponse(
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


def test_answer_with_only_thinking_is_an_error(client: TestClient, monkeypatch) -> None:
    """Yalnızca muhakeme üretilmişse boş balon değil, kontrollü hata dönmeli."""
    patch_ollama(
        monkeypatch, {"/api/chat": FakeResponse(payload=chat_payload("<think>sadece dusunce</think>"))}
    )

    response = client.post("/api/assistant/chat", json={"message": "Merhaba"})

    assert response.status_code == 502


def test_streaming_filters_thinking(monkeypatch) -> None:
    """Akışta da muhakeme parçaları yayınlanmamalı."""
    lines = [
        json.dumps({"message": {"content": "<thi"}}),
        json.dumps({"message": {"content": "nk>gizli muhakeme"}}),
        json.dumps({"message": {"content": " devam ediyor</think>"}}),
        json.dumps({"message": {"content": "Görünen "}}),
        json.dumps({"message": {"content": "cevap."}}),
    ]
    patch_ollama(monkeypatch, {"/api/chat": FakeResponse(lines=lines)})

    provider = OllamaProvider()
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
        "Ollama servisine ulaşılamıyor",
        "Model kurulu değil",
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


def test_no_cloud_llm_provider_is_used() -> None:
    """Hiçbir bulut LLM istemcisi projeye girmemiş olmalı."""
    import pathlib
    import re

    backend = pathlib.Path(__file__).resolve().parents[1]
    forbidden = re.compile(
        r"(?i)\b(import\s+openai|from\s+openai|import\s+anthropic|from\s+anthropic|"
        r"google\.generativeai|api\.openai\.com|generativelanguage\.googleapis\.com|"
        r"api\.anthropic\.com)\b"
    )
    findings = []
    for path in backend.rglob("*.py"):
        if ".venv" in str(path) or "__pycache__" in str(path):
            continue
        if forbidden.search(path.read_text(encoding="utf-8", errors="ignore")):
            findings.append(str(path.relative_to(backend)))
    assert not findings, f"Bulut LLM sağlayıcısı kullanımı: {findings}"


def test_ollama_base_url_is_local() -> None:
    """Varsayılan adres yerel olmalı; veri makine dışına çıkmamalı."""
    from app.core.config import settings

    assert settings.OLLAMA_BASE_URL.startswith(("http://127.0.0.1", "http://localhost"))


def test_local_client_ignores_proxy_environment() -> None:
    """Yerel istekler proxy üzerinden gitmemeli.

    Makinede HTTP_PROXY tanımlıysa httpx varsayılan olarak onu kullanır ve
    127.0.0.1'e giden istek bile dışarı yönlenir. Bu hem bağlantıyı kırar
    hem de "veri yerelde kalır" güvencesini bozar.
    """
    from app.services.assistant.ollama_provider import _local_client

    with _local_client(1.0) as client:
        assert client.trust_env is False


# ---------------------------------------------------------------------------
# 12) Asistan uç noktalarının uygulamayı çökertmemesi
# ---------------------------------------------------------------------------


def test_status_survives_unexpected_provider_failure(client: TestClient, monkeypatch) -> None:
    """Beklenmeyen bir hata durum ekranını çökertmemeli."""

    def explode(timeout):
        raise ImportError("eksik bir eklenti")

    monkeypatch.setattr(
        "app.services.assistant.ollama_provider._local_client", explode
    )

    response = client.get("/api/assistant/status")

    assert response.status_code == 200
    assert response.json()["ready"] is False


def test_other_endpoints_still_work_when_ollama_is_down(client: TestClient, monkeypatch) -> None:
    """Asistan bozukken uygulamanın geri kalanı çalışmaya devam etmeli."""
    patch_ollama(monkeypatch, {"/api/tags": httpx.ConnectError("kapali")})

    assert client.get("/health").status_code == 200
    assert client.get("/api/assistant/status").status_code == 200
    assert client.get("/api/faculties").status_code == 200


def test_streaming_endpoint_reports_errors_inside_the_stream(
    client: TestClient, monkeypatch
) -> None:
    """Akış başladıktan sonra oluşan hata, akışın içinde bildirilmeli."""
    patch_ollama(monkeypatch, {"/api/chat": httpx.ConnectError("kapali")})

    with client.stream(
        "POST", "/api/assistant/chat/stream", json={"message": "Merhaba"}
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    assert '"type": "error"' in body
    assert "Ollama" in body


def test_streaming_endpoint_emits_chunks_and_done(client: TestClient, monkeypatch) -> None:
    """Normal akışta parçalar ve bitiş olayı gönderilmeli."""
    lines = [
        json.dumps({"message": {"content": "Merhaba "}}),
        json.dumps({"message": {"content": "dünya."}}),
    ]
    patch_ollama(monkeypatch, {"/api/chat": FakeResponse(lines=lines)})

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
