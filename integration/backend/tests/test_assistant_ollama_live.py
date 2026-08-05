"""İSTEĞE BAĞLI — gerçek Ollama ile çalışan entegrasyon testi.

Bu testler varsayılan olarak ATLANIR. Çalıştırmak için Ollama'nın açık ve
modelin kurulu olması gerekir:

    ollama serve
    ollama pull qwen3.5:9b
    ASSISTANT_LIVE_TEST=1 pytest tests/test_assistant_ollama_live.py -v

Neden ayrı dosyada: bu testler yavaştır (model belleğe yüklenir) ve modelin
üreteceği metin her çalıştırmada farklıdır. Sürekli entegrasyonda çalışan
testler deterministik olmalı; o yüzden asıl doğrulamalar taklit istemciyle
`test_assistant_ollama.py` içinde yapılır.
"""

import os

import pytest

from app.core.config import settings
from app.services.assistant import chat_service
from app.services.assistant.ollama_provider import OllamaProvider

# Ortam değişkeni verilmediyse dosyadaki her test atlanır.
pytestmark = pytest.mark.skipif(
    os.getenv("ASSISTANT_LIVE_TEST") != "1",
    reason="Gerçek Ollama testi. Çalıştırmak için: ASSISTANT_LIVE_TEST=1",
)


@pytest.fixture(autouse=True)
def _clean_conversations():
    chat_service.reset_conversations()
    yield
    chat_service.reset_conversations()


def test_live_service_is_reachable() -> None:
    """Ollama gerçekten ayakta ve istenen model kurulu olmalı."""
    health = OllamaProvider().health()

    assert health.service_available, (
        "Ollama'ya ulaşılamadı. `ollama serve` ile başlatın."
    )
    assert health.model_available, (
        f"{settings.OLLAMA_MODEL} kurulu değil. "
        f"`ollama pull {settings.OLLAMA_MODEL}` çalıştırın. "
        f"Kurulu modeller: {list(health.installed_models)}"
    )


def test_live_model_answers_in_turkish() -> None:
    """Model Türkçe cevap vermeli ve düşünme metni sızmamalı."""
    result = chat_service.answer("Kendini bir cümleyle tanıt.")

    answer = result["answer"]
    assert answer.strip(), "Model boş cevap döndürdü."
    assert "<think" not in answer.lower(), "Düşünme metni cevaba karışmış."
    assert result["provider"] == "ollama"
    assert result["model"] == settings.OLLAMA_MODEL
    assert result["used_tools"] == []

    # Türkçe karakterlerden en az biri geçmeli; model İngilizceye kaymamalı.
    assert any(ch in answer for ch in "çğıöşüÇĞİÖŞÜ"), (
        f"Cevap Türkçe görünmüyor: {answer[:200]}"
    )


def test_live_model_does_not_invent_institutional_numbers() -> None:
    """Kurum verisi istendiğinde model sayı uydurmamalı.

    Bu, sistem yönergesinin gerçekten işe yarayıp yaramadığını ölçen tek
    testtir. Model, veriye erişimi olmadığını belirtmeli.
    """
    result = chat_service.answer(
        "Bilgisayar Mühendisliği öğrenci sayısı %15 artarsa ne olur?"
    )
    answer = result["answer"].lower()

    # Cevap, veri erişimi olmadığını bir biçimde belirtmeli.
    disclaimers = ("erişim", "erisim", "veri", "entegrasyon", "hesaplayamam", "bilgim yok")
    assert any(word in answer for word in disclaimers), (
        f"Model veri erişimi olmadığını belirtmedi: {result['answer'][:300]}"
    )


def test_live_streaming_produces_text() -> None:
    """Akışlı üretim gerçek modelde de metin döndürmeli."""
    _, pieces = chat_service.stream_answer("Merhaba de.")
    output = "".join(pieces)

    assert output.strip(), "Akıştan hiç metin gelmedi."
    assert "<think" not in output.lower(), "Akışta düşünme metni sızmış."
