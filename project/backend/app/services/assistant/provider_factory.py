"""Sağlayıcı seçimi.

Tek kayıtlı sağlayıcı GEMINI'dir. Ollama ve Groq kaldırıldı.

Kayıt defteri yapısı korundu: ileride başka bir sağlayıcı eklenirse
yalnızca buraya bir satır eklemek yeterli olacak. Bu dosya OpenAI,
Gemini veya Claude istemcisi içe aktarmaz.
"""

from typing import Dict, Type

from app.core.config import settings
from app.services.assistant.base import AssistantProvider, NoProviderConfigured
from app.services.assistant.gemini_provider import GeminiProvider

# Sağlayıcı kayıt defteri — TEK GİRDİ.
# ---------------------------------------------------------------------
# Kayıt defteri yapısı korundu çünkü asıl işi
# hâlâ görüyor: tanınmayan bir ad yazıldığında sistem sessizce başka bir
# sağlayıcıya DÜŞMEZ, `NoProviderConfigured` ile açıkça durur.
PROVIDER_REGISTRY: Dict[str, Type[AssistantProvider]] = {
    "gemini": GeminiProvider,
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
