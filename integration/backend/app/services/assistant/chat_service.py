"""Asistan sohbet servisi.

Sorumluluk: sistem yönergesini hazırlamak, konuşma geçmişini tutmak, ARAÇ
ÇAĞRI DÖNGÜSÜNÜ yürütmek ve sağlayıcıyı çağırmak. HTTP ayrıntısı bilmez (o
router'ın işi), Ollama ayrıntısı bilmez (o sağlayıcının işi), araç
doğrulaması yapmaz (o `tool_runner`ın işi).

ARAÇ ÇAĞRI DÖNGÜSÜ
------------------
1. Kullanıcı mesajı + sistem yönergesi + araç tanımları modele gönderilir.
2. Model bir veya birden fazla araç çağırır.
3. Her çağrı `tool_runner` tarafından doğrulanıp çalıştırılır.
4. Sonuçlar `tool` rolüyle konuşmaya eklenir.
5. Model gerekiyorsa başka araç çağırır (en fazla MAX_TOOL_STEPS tur).
6. Adım ya da süre sınırına gelinirse model araçsız olarak son cevabı yazar.

Model kurumsal bir sayıyı yalnızca araç sonucundan alabilir. Sistem yönergesi
bunu dayatır; araç sonucu yoksa "veri bulunamadı" demesi beklenir.

Konuşmalar bellekte tutulur, veritabanına yazılmaz.
"""

import logging
import time
import uuid
from collections import OrderedDict
from typing import Any, Dict, Iterator, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.assistant.ollama_provider import (
    AssistantProviderError,
    OllamaProvider,
)
from app.services.assistant import tools as _tools  # noqa: F401  (kayıt için)
from app.services.assistant.tool_registry import registry
from app.services.assistant.tool_runner import ToolSession

logger = logging.getLogger(__name__)

# Modelin bir soruda yapabileceği en fazla araç turu.
MAX_TOOL_STEPS = 5

# Bütün araç turlarının toplam süre sınırı (saniye). Tek tek araçların kendi
# sınırı var; bu sınır beş turun toplamda kullanıcıyı dakikalarca bekletmesini
# engeller.
MAX_TOOL_WALL_SECONDS = 90.0

SYSTEM_PROMPT = """Sen, Ankara Bilim Üniversitesi Stratejik Yönetim ve Karar Destek Sistemi içinde çalışan bir yönetim asistanısın.

Görevin, üniversite üst yönetimine kurum verisine dayalı, doğrulanabilir cevaplar vermektir.

VERİ KULLANIMI — EN ÖNEMLİ KURALLAR

1. Kurumsal sayıları YALNIZCA araç sonuçlarından al. Öğrenci sayısı, bütçe, doluluk oranı, personel sayısı, kapasite gibi her rakam bir araç çıktısından gelmelidir.
2. Araç sonucu yoksa sayı UYDURMA. "Bu bilgi için gerekli veriye ulaşamadım" de.
3. Kendi kafandan hesap YAPMA. Toplama, çıkarma, yüzde hesabı gerekiyorsa ilgili aracı çağır. Araçların döndürdüğü değerleri olduğu gibi aktar.
4. Bir araç hata döndürürse o konuda sayı verme; hatanın sebebini kullanıcıya sade bir dille açıkla.
5. Araç çıktısındaki "notes" alanında yazan uyarıları cevabına taşı. Örneğin bir değer üniversite geneli ise bunu belirt.

NE ZAMAN SENARYO ÇALIŞTIRILIR

6. Kullanıcı "artarsa", "azalırsa", "zam yapılırsa", "ne olur" gibi bir VARSAYIM soruyorsa ilgili senaryo aracını çağır.
7. Kullanıcı yalnızca mevcut durumu soruyorsa (kaç öğrenci var, bütçe ne kadar) SENARYO ÇALIŞTIRMA; yalnızca özet araçlarını kullan.

CEVAP BİÇİMİ

8. Her zaman Türkçe cevap ver.
9. Cevabın başında hangi akademik yıla ve hangi kapsama (üniversite geneli / fakülte / bölüm / program) ait olduğunu belirt.
10. Para değerlerini USD olarak ve okunabilir biçimde yaz (örnek: 35.960.000 USD).
11. Veri eksikse açıkça "veri bulunamadı" de; sıfır yazma.
12. Hesaplanmış sonuç ile genel bilgiyi birbirinden ayır. Genel bir yöntem anlatıyorsan bunun kurum verisi olmadığını söyle.
13. Kullanıcıya teknik araç adlarını (get_program_summary gibi) YAZMA. Bunun yerine "öğrenci kayıtları", "mali dönem kayıtları" gibi anlaşılır kaynak adları kullan.
14. Cevabı yönetici odaklı ver: kısa, düzenli, madde işaretli ve eyleme dönük.

BİRİM ADLARI

15. Kullanıcı bir bölüm veya program adını Türkçe, İngilizce ya da kod olarak yazabilir. Araçlara kullanıcının yazdığı adı olduğu gibi ver; eşleştirmeyi sistem yapar.
16. Bir araç "birden fazla eşleşme" hatası döndürürse kullanıcıya seçenekleri sun ve hangisini kastettiğini sor. Kendin seçme."""


class ChatValidationError(ValueError):
    """Kullanıcı mesajı kurallara uymuyor."""

    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


class ConversationStore:
    """Bellekte tutulan konuşma geçmişi (LRU)."""

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


def answer(
    message: str,
    conversation_id: Optional[str] = None,
    db: Optional[Session] = None,
    permissions: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Araç çağrı döngüsünü yürütür ve son cevabı üretir.

    `db` verilmezse araçlar devre dışıdır; model yalnızca genel bilgiyle
    cevap verir ve sistem yönergesi gereği kurumsal sayı üretmez.
    """
    conversation, messages = _prepare(message, conversation_id)
    provider = get_provider()
    user_content = messages[-1]["content"]

    session: Optional[ToolSession] = None
    tool_schemas: Optional[List[Dict]] = None
    if db is not None:
        session = ToolSession(db=db, permissions=permissions, registry=registry)
        tool_schemas = registry.schemas(permissions)

    started = time.monotonic()
    steps = 0
    visible = ""

    while True:
        elapsed = time.monotonic() - started
        # Süre veya adım sınırına gelindiyse araçsız son tur: model eldeki
        # sonuçlarla cevabı yazar, yeni araç çağıramaz.
        out_of_budget = steps >= MAX_TOOL_STEPS or elapsed >= MAX_TOOL_WALL_SECONDS
        offered_tools = None if (out_of_budget or not tool_schemas) else tool_schemas

        if out_of_budget and session is not None and steps > 0:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "Araç kullanım sınırına ulaşıldı. Yeni araç çağırma; "
                        "eldeki sonuçlarla son cevabı yaz. Eksik kalan bilgi "
                        "varsa bunu açıkça belirt."
                    ),
                }
            )

        tool_calls, visible, thinking = provider.chat_with_tools(messages, offered_tools)
        if thinking:
            logger.debug(
                "Model dusunme metni uretti (%d karakter), kullaniciya gonderilmedi",
                len(thinking),
            )

        if not tool_calls or session is None or offered_tools is None:
            break

        steps += 1
        # Modelin araç çağrısı konuşmaya eklenir; sonuçların hangi çağrıya ait
        # olduğu böylece belli olur.
        messages.append(
            {
                "role": "assistant",
                "content": visible,
                "tool_calls": [
                    {"function": {"name": c["name"], "arguments": c["arguments"]}}
                    for c in tool_calls
                ],
            }
        )

        for call in tool_calls:
            record = session.run(call["name"], call.get("arguments"))
            messages.append(
                {"role": "tool", "name": record.name, "content": record.content}
            )

    if not visible:
        raise AssistantProviderError(
            "Yerel modelden geçerli bir yanıt alınamadı. Ollama günlüklerini kontrol edin.",
            kind="invalid_response",
        )

    _store.append(conversation, "user", user_content)
    _store.append(conversation, "assistant", visible)

    used_tools = session.used_tools() if session else []
    data_sources = session.data_sources() if session else []
    scope = session.scope() if session else {}
    academic_year = session.academic_year() if session else None

    return {
        "conversation_id": conversation,
        "answer": visible,
        "provider": provider.name,
        "model": provider.model,
        "used_tools": used_tools,
        "data_sources": data_sources,
        "academic_year": academic_year,
        "scope": scope,
        # Araç kullanıldıysa cevap kurum verisine, kullanılmadıysa modelin
        # genel bilgisine dayanır. Bu ayrım kullanıcıya gösterilir.
        "data_source": (
            "institutional_data"
            if session is not None and session.any_success()
            else "general_model_knowledge"
        ),
    }


def stream_answer(
    message: str, conversation_id: Optional[str] = None
) -> Tuple[str, Iterator[str]]:
    """Cevabı parça parça üretir.

    NOT: Akış modunda araç çağrısı YAPILMAZ. Araç turları arasında akışı
    bölmek kullanıcıya yarım cümleler gösterirdi; araçlı sorular tek seferlik
    `/chat` uç noktasından cevaplanır.
    """
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


def status() -> Dict[str, Any]:
    """Asistanın kullanıcıya gösterilecek durumu. Hata FIRLATMAZ."""
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
            "tool_count": len(registry.names()),
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
        "tool_count": len(registry.names()),
    }


def reset_conversations() -> None:
    """Bellekteki tüm konuşmaları siler."""
    _store.clear()


__all__ = [
    "AssistantProviderError",
    "ChatValidationError",
    "MAX_TOOL_STEPS",
    "MAX_TOOL_WALL_SECONDS",
    "SYSTEM_PROMPT",
    "answer",
    "build_messages",
    "reset_conversations",
    "status",
    "stream_answer",
    "validate_message",
]
