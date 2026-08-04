"""Sağlayıcı seçimi ve durum bildirimi.

Bu dosya hiçbir dil modeli sağlayıcısını içe aktarmaz, hiçbir API paketine
bağımlı değildir ve hiçbir ağ çağrısı yapmaz. Yaptığı tek iş, ortam
değişkenlerini okuyup "hangi sağlayıcı seçilmiş, kullanılabilir mi" sorusunu
cevaplamaktır.

Şu anda kayıtlı sağlayıcı yoktur; her yapılandırma NoProviderConfigured
döndürür. Bu bilinçli bir tercihtir: model seçimi proje ekibine aittir.
"""

import os
from typing import Dict, Optional, Type

from app.services.assistant.base import AssistantProvider, NoProviderConfigured
from app.services.assistant.schemas import AssistantStatus

# Sağlayıcı kayıt defteri. Bir model bağlandığında ilgili sınıf buraya
# eklenecek; başka hiçbir yeri değiştirmek gerekmeyecek.
PROVIDER_REGISTRY: Dict[str, Type[AssistantProvider]] = {}


def _env(name: str) -> Optional[str]:
    """Ortam değişkenini okur; boş string None sayılır."""
    value = (os.getenv(name) or "").strip()
    return value or None


def get_provider() -> AssistantProvider:
    """Yapılandırmaya göre sağlayıcıyı döndürür.

    Kayıt defteri boş olduğu için her durumda NoProviderConfigured döner.
    """
    provider_name = (_env("LLM_PROVIDER") or "").lower()
    provider_class = PROVIDER_REGISTRY.get(provider_name)
    if provider_class is None:
        return NoProviderConfigured()
    return provider_class()


def get_status() -> AssistantStatus:
    """Asistanın kullanıcıya gösterilecek durumu.

    API anahtarının kendisi asla döndürülmez; yalnızca tanımlı olup olmadığı
    bildirilir. Anahtarı cevaba koymak onu tarayıcı geçmişine ve günlüklere
    sızdırırdı.
    """
    enabled = (os.getenv("ASSISTANT_ENABLED") or "false").strip().lower() in (
        "1",
        "true",
        "yes",
        "evet",
    )
    provider_name = _env("LLM_PROVIDER")
    model = _env("LLM_MODEL")
    api_key_set = _env("LLM_API_KEY") is not None
    provider = get_provider()

    if not enabled:
        message = (
            "Asistan devre dışı (ASSISTANT_ENABLED=false). Sisteme bağlı bir dil "
            "modeli yoktur ve sistem cevap üretmez. Bu ekran yalnızca soruya "
            "ilişkin kurumsal verinin nasıl toplandığını gösterir."
        )
    elif not provider.is_available():
        message = (
            "Asistan etkin görünüyor ancak kullanılabilir bir sağlayıcı yok. "
            f"Seçilen sağlayıcı: {provider_name or 'tanımsız'}. "
            "Sistem uydurma cevap üretmemek için isteği reddeder."
        )
    else:
        message = f"Asistan hazır. Sağlayıcı: {provider.name}."

    return AssistantStatus(
        enabled=enabled,
        provider=provider_name,
        model=model,
        base_url=_env("LLM_BASE_URL"),
        api_key_configured=api_key_set,
        message=message,
    )
