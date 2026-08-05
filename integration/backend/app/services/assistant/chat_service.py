"""Asistan sohbet servisi.

Sorumluluk: sistem yönergesini hazırlamak, konuşma geçmişini tutmak ve
sağlayıcıyı çağırmak. HTTP ayrıntısı bilmez (o router'ın işi), Ollama
ayrıntısı bilmez (o sağlayıcının işi).

BU AŞAMADA ARAÇ ÇAĞRISI YOKTUR. Model veritabanına erişemez, senaryo motorunu
çalıştıramaz. Sistem yönergesi modele bunu açıkça söyler; böylece model
"Bilgisayar Mühendisliği'nde 400 öğrenci var" gibi bir sayı UYDURMAZ, veriye
erişimi olmadığını belirtir.

Konuşmalar bellekte tutulur, veritabanına yazılmaz. Sunucu yeniden başlarsa
geçmiş silinir; bu bilinçli bir tercihtir — kullanıcı mesajlarını kalıcı
saklamak ayrı bir gizlilik kararı gerektirir.
"""

import logging
import uuid
from collections import OrderedDict
from typing import Dict, Iterator, List, Optional, Tuple

from app.core.config import settings
from app.services.assistant.ollama_provider import (
    AssistantProviderError,
    OllamaProvider,
)

logger = logging.getLogger(__name__)

# Modelin rolünü ve sınırlarını tanımlayan yönerge. Türkçe yazılmıştır çünkü
# kullanıcı arayüzü ve kurum dili Türkçedir; İngilizce yönerge modelin İngilizce
# cevap verme eğilimini artırıyor.
SYSTEM_PROMPT = """Sen, Ankara Bilim Üniversitesi Stratejik Yönetim ve Karar Destek Sistemi içinde çalışan bir yönetim asistanısın.

Görevin, üniversite üst yönetimine stratejik konularda yardımcı olmaktır.

Uyman gereken kurallar:

1. Kullanıcıya her zaman Türkçe cevap ver.
2. Şu anda üniversitenin veritabanına, raporlarına veya hesaplama motorlarına ERİŞİMİN YOK. Araç entegrasyonu henüz etkin değil.
3. Bir soru kurumun kendi verisini gerektiriyorsa (öğrenci sayısı, bütçe rakamı, doluluk oranı, personel sayısı, program başarısı gibi), sayı UYDURMA. Bunun yerine hangi verilere erişmen gerektiğini açıkça söyle ve araç entegrasyonunun henüz etkin olmadığını belirt.
4. Genel bilgi ile kurum verisini birbirine karıştırma. Genel bir yöntem, tanım veya yaklaşım anlatıyorsan bunun genel bilgi olduğunu belirt.
5. Cevaplarını yönetici odaklı ver: kısa, açık, düzenli ve eyleme dönük olsun. Gerektiğinde madde işaretleri kullan.
6. Emin olmadığın konularda tahmin yürütmek yerine belirsizliği açıkça söyle.

Örnek doğru davranış:
Kullanıcı: "Bilgisayar Mühendisliği öğrenci sayısı %15 artarsa ne olur?"
Sen: "Bu soruyu kurum verileriyle hesaplamak için öğrenci, mali durum, personel ve kapasite verilerine erişmem gerekiyor. Araç entegrasyonu henüz etkin değil." — ardından hangi göstergelerin bakılması gerektiğini genel olarak açıklayabilirsin, ancak somut sayı veremezsin."""


class ChatValidationError(ValueError):
    """Kullanıcı mesajı kurallara uymuyor."""

    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


class ConversationStore:
    """Bellekte tutulan konuşma geçmişi.

    Sınırsız büyüyen bir sözlük, uzun süre açık kalan sunucuda belleği
    tüketirdi. En eski konuşma, sınır aşılınca düşürülür (LRU).
    """

    def __init__(self, max_conversations: int, max_messages: int) -> None:
        self._data: "OrderedDict[str, List[Dict[str, str]]]" = OrderedDict()
        self.max_conversations = max_conversations
        self.max_messages = max_messages

    def get(self, conversation_id: Optional[str]) -> List[Dict[str, str]]:
        if not conversation_id:
            return []
        history = self._data.get(conversation_id)
        if history is None:
            return []
        self._data.move_to_end(conversation_id)
        return list(history)

    def append(self, conversation_id: str, role: str, content: str) -> None:
        history = self._data.setdefault(conversation_id, [])
        history.append({"role": role, "content": content})
        # Yalnızca son N mesaj tutulur; bağlam penceresi sınırsız değil.
        if len(history) > self.max_messages:
            del history[: len(history) - self.max_messages]
        self._data.move_to_end(conversation_id)
        while len(self._data) > self.max_conversations:
            self._data.popitem(last=False)

    def clear(self) -> None:
        self._data.clear()

    def __len__(self) -> int:
        return len(self._data)


_store = ConversationStore(
    max_conversations=settings.ASSISTANT_MAX_CONVERSATIONS,
    max_messages=settings.ASSISTANT_MAX_HISTORY_MESSAGES,
)


def get_provider() -> OllamaProvider:
    """Yapılandırılmış sağlayıcıyı döndürür."""
    return OllamaProvider()


def validate_message(message: str) -> str:
    """Kullanıcı mesajını doğrular ve temizler."""
    cleaned = (message or "").strip()
    if not cleaned:
        raise ChatValidationError("Mesaj boş olamaz.")
    limit = settings.ASSISTANT_MAX_MESSAGE_LENGTH
    if len(cleaned) > limit:
        raise ChatValidationError(
            f"Mesaj çok uzun. En fazla {limit} karakter gönderebilirsiniz "
            f"(gönderilen: {len(cleaned)})."
        )
    return cleaned


def build_messages(user_message: str, history: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Modele gönderilecek mesaj listesini kurar: system + geçmiş + yeni soru."""
    messages: List[Dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    # Geçmişte yalnızca user/assistant rolleri taşınır; eski bir system
    # mesajının tekrar eklenmesi yönergeyi çelişkili hale getirirdi.
    messages.extend(
        {"role": item["role"], "content": item["content"]}
        for item in history
        if item.get("role") in ("user", "assistant")
    )
    messages.append({"role": "user", "content": user_message})
    return messages


def _prepare(message: str, conversation_id: Optional[str]) -> Tuple[str, List[Dict[str, str]]]:
    """Doğrulama + geçmiş + konuşma kimliği."""
    cleaned = validate_message(message)
    conversation = conversation_id or str(uuid.uuid4())
    history = _store.get(conversation_id)
    # Günlüğe mesajın tamamı yazılmaz; yalnızca uzunluğu.
    logger.info(
        "Asistan istegi: konusma=%s gecmis=%d mesaj_uzunlugu=%d",
        conversation[:8],
        len(history),
        len(cleaned),
    )
    return conversation, build_messages(cleaned, history)


def answer(message: str, conversation_id: Optional[str] = None) -> Dict[str, object]:
    """Tek seferde cevap üretir.

    AssistantProviderError router tarafından yakalanıp kullanıcıya anlaşılır
    hata olarak döndürülür. Bu katman hatayı yutmaz ve sahte cevap üretmez.
    """
    conversation, messages = _prepare(message, conversation_id)
    provider = get_provider()

    visible, thinking = provider.chat(messages)
    if thinking:
        # Düşünme metni yalnızca günlükte, uzunluğu kadar. İçeriği yazılmaz.
        logger.debug("Model dusunme metni uretti (%d karakter), kullaniciya gonderilmedi", len(thinking))

    _store.append(conversation, "user", messages[-1]["content"])
    _store.append(conversation, "assistant", visible)

    return {
        "conversation_id": conversation,
        "answer": visible,
        "provider": provider.name,
        "model": provider.model,
        "used_tools": [],
        # Bu aşamada model yalnızca kendi genel bilgisini kullanır.
        "data_source": "general_model_knowledge",
    }


def stream_answer(
    message: str, conversation_id: Optional[str] = None
) -> Tuple[str, Iterator[str]]:
    """Cevabı parça parça üretir. (konuşma kimliği, parça üreteci) döndürür."""
    conversation, messages = _prepare(message, conversation_id)
    provider = get_provider()
    user_content = messages[-1]["content"]

    def generate() -> Iterator[str]:
        collected: List[str] = []
        for piece in provider.stream_chat(messages):
            collected.append(piece)
            yield piece
        full = "".join(collected).strip()
        if full:
            _store.append(conversation, "user", user_content)
            _store.append(conversation, "assistant", full)

    return conversation, generate()


def status() -> Dict[str, object]:
    """Asistanın kullanıcıya gösterilecek durumu.

    Hata FIRLATMAZ: Ollama kapalıyken bile ekran açılabilmelidir.
    """
    provider = get_provider()

    if not settings.ASSISTANT_ENABLED:
        return {
            "provider": provider.name,
            "model": provider.model,
            "enabled": False,
            "service_available": False,
            "model_available": False,
            "ready": False,
            "message": "Akıllı Asistan yapılandırmada devre dışı bırakıldı.",
            "installed_models": [],
        }

    health = provider.health()
    return {
        "provider": provider.name,
        "model": provider.model,
        "enabled": True,
        "service_available": health.service_available,
        "model_available": health.model_available,
        "ready": health.ready,
        "message": health.message,
        "installed_models": list(health.installed_models),
    }


# Testlerin konuşma geçmişini sıfırlayabilmesi için.
def reset_conversations() -> None:
    """Bellekteki tüm konuşmaları siler."""
    _store.clear()


__all__ = [
    "AssistantProviderError",
    "ChatValidationError",
    "SYSTEM_PROMPT",
    "answer",
    "build_messages",
    "reset_conversations",
    "status",
    "stream_answer",
    "validate_message",
]
