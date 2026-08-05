"""Sağlayıcı seçimi.

Şu anda tek kayıtlı sağlayıcı YEREL Ollama'dır. Kayıt defteri yapısı korundu:
ileride başka bir yerel çalıştırıcı eklenirse yalnızca buraya bir satır
eklemek yeterli olacak.

Bu dosya hiçbir bulut sağlayıcısını (OpenAI, Gemini, Claude) içe aktarmaz ve
hiçbir API anahtarı okumaz.
"""

from typing import Dict, Type

from app.core.config import settings
from app.services.assistant.base import AssistantProvider, NoProviderConfigured
from app.services.assistant.ollama_provider import OllamaProvider

# Sağlayıcı kayıt defteri.
PROVIDER_REGISTRY: Dict[str, Type[AssistantProvider]] = {
    "ollama": OllamaProvider,
}


def get_provider() -> AssistantProvider:
    """Yapılandırmada seçilen sağlayıcıyı döndürür.

    Tanınmayan bir sağlayıcı adı yazılırsa NoProviderConfigured döner; sistem
    sessizce başka bir sağlayıcıya düşmez ve uydurma cevap üretmez.
    """
    provider_class = PROVIDER_REGISTRY.get((settings.LLM_PROVIDER or "").lower())
    if provider_class is None:
        return NoProviderConfigured()
    return provider_class()
