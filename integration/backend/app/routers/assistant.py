"""Akıllı asistan endpoint'leri.

Asistan YEREL bir dil modeliyle (Ollama) çalışır. Hiçbir bulut sağlayıcısına
istek gönderilmez, hiçbir API anahtarı kullanılmaz.

Bu router modelle doğrudan konuşmaz: doğrulama ve HTTP çevirisi burada,
yönerge ve konuşma yönetimi `chat_service`'te, ağ çağrısı `ollama_provider`'da
yapılır. Böylece sağlayıcı değişirse router'a dokunmak gerekmez.

BU AŞAMADA araç çağrısı, veritabanı sorgusu ve senaryo motoru bağlantısı
YOKTUR. Model kurum verisine erişemez ve sistem yönergesi ona bunu açıkça
söyler; sayı uydurması engellenir.
"""

import json
import logging
from typing import Iterator, List

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.assistant import chat_service, context_builder
from app.services.assistant.ollama_provider import AssistantProviderError
from app.services.assistant.schemas import (
    ArchitectureComponent,
    ArchitectureResponse,
    AssistantStatus,
    ChatRequest,
    ChatResponse,
    ContextRequest,
    ContextResponse,
    SampleQuestion,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/assistant", tags=["Akıllı Asistan"])

# Sağlayıcı hatasının HTTP karşılığı. Zaman aşımı ve "servis kapalı" istemci
# hatası değildir; 5xx dönmek istemcinin "sonra tekrar dene" demesini sağlar.
STATUS_BY_KIND = {
    "service_down": http_status.HTTP_503_SERVICE_UNAVAILABLE,
    "model_missing": http_status.HTTP_503_SERVICE_UNAVAILABLE,
    "timeout": http_status.HTTP_504_GATEWAY_TIMEOUT,
    "invalid_response": http_status.HTTP_502_BAD_GATEWAY,
}


def _provider_http_error(exc: AssistantProviderError) -> HTTPException:
    """Sağlayıcı hatasını kullanıcıya gösterilebilir HTTP hatasına çevirir."""
    return HTTPException(
        status_code=STATUS_BY_KIND.get(exc.kind, http_status.HTTP_502_BAD_GATEWAY),
        detail=exc.user_message,
    )


@router.get(
    "/status",
    response_model=AssistantStatus,
    summary="Yerel yapay zekâ servisinin durumu",
)
def get_status() -> AssistantStatus:
    """Ollama ayakta mı ve model kurulu mu?

    Ollama kapalıyken de 200 döner; durum alanları false olur. Bu uç noktanın
    hata fırlatması, asistan kapalıyken tüm arayüzü bozardı.
    """
    return AssistantStatus(**chat_service.status())


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Asistana mesaj gönder",
)
def chat(payload: ChatRequest) -> ChatResponse:
    """Yerel modelden cevap alır.

    Modelin düşünme metni cevaba dâhil edilmez. Ollama kapalı, model kurulu
    değil veya zaman aşımı varsa kullanıcıya anlaşılır bir hata döner —
    uydurma cevap ÜRETİLMEZ.
    """
    try:
        result = chat_service.answer(payload.message, payload.conversation_id)
    except chat_service.ChatValidationError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.user_message,
        ) from exc
    except AssistantProviderError as exc:
        raise _provider_http_error(exc) from exc

    return ChatResponse(**result)


@router.post(
    "/chat/stream",
    summary="Asistana mesaj gönder (akışlı)",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
def chat_stream(payload: ChatRequest) -> StreamingResponse:
    """Cevabı Server-Sent Events olarak parça parça yayınlar.

    Olay biçimi:
        data: {"type": "chunk", "text": "..."}
        data: {"type": "done", "conversation_id": "..."}
        data: {"type": "error", "message": "..."}

    Düşünme metni akışta da filtrelenir; kullanıcı muhakeme satırlarını görmez.
    """
    try:
        conversation_id, pieces = chat_service.stream_answer(
            payload.message, payload.conversation_id
        )
    except chat_service.ChatValidationError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.user_message,
        ) from exc

    def event_stream() -> Iterator[str]:
        def event(data: dict) -> str:
            return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

        try:
            for piece in pieces:
                yield event({"type": "chunk", "text": piece})
            yield event({"type": "done", "conversation_id": conversation_id})
        except AssistantProviderError as exc:
            # Akış başladıktan sonra HTTP durum kodu değiştirilemez; hata
            # olayı akışın içinde bildirilir.
            yield event({"type": "error", "message": exc.user_message})
        except Exception:  # noqa: BLE001 - akış istemciyi asla asılı bırakmamalı
            logger.exception("Asistan akisi beklenmedik sekilde sonlandi")
            yield event(
                {
                    "type": "error",
                    "message": "Yanıt üretilirken beklenmeyen bir hata oluştu.",
                }
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get(
    "/sample-questions",
    response_model=List[SampleQuestion],
    summary="Örnek sorular",
)
def get_sample_questions() -> List[SampleQuestion]:
    """Arayüzde gösterilen örnek sorular."""
    return context_builder.sample_questions()


@router.post(
    "/prepare-context",
    response_model=ContextResponse,
    summary="Soru için kurumsal bağlamı hazırla",
)
def prepare_context(
    payload: ContextRequest, db: Session = Depends(get_db)
) -> ContextResponse:
    """Soruya ilişkin kurumsal verileri toplar; MODELE GÖNDERMEZ.

    Bu katman bir sonraki aşamada (araç entegrasyonu) modele bağlanacaktır.
    Şu an ayrı durur ve toplanan veriyi kullanıcıya gösterir.
    """
    return context_builder.build_context(db, payload.question)


@router.get(
    "/architecture",
    response_model=ArchitectureResponse,
    summary="Asistan mimarisi ve sonraki adımlar",
)
def get_architecture() -> ArchitectureResponse:
    """Hangi parçaların hazır olduğunu ve neyin eksik kaldığını gösterir."""
    return ArchitectureResponse(
        summary=(
            "Asistan yerel bir dil modeliyle (Ollama) çalışır; hiçbir bulut "
            "servisine istek gönderilmez. Sağlayıcı, sohbet servisi ve uç "
            "noktalar hazırdır. Eksik olan parça araç entegrasyonudur: model "
            "henüz veritabanını sorgulayamaz ve senaryo motorunu çalıştıramaz, "
            "bu yüzden kurum verisi gerektiren sorularda sayı üretmez."
        ),
        components=[
            ArchitectureComponent(
                file="app/services/assistant/ollama_provider.py",
                responsibility=(
                    "Yerel Ollama sunucusuyla konuşur. Bağlantı ve model "
                    "kontrolü, akışlı üretim, zaman aşımı yönetimi ve düşünme "
                    "metninin ayıklanması."
                ),
                status="hazır",
            ),
            ArchitectureComponent(
                file="app/services/assistant/chat_service.py",
                responsibility=(
                    "Türkçe sistem yönergesi, konuşma geçmişi ve mesaj "
                    "doğrulaması. Sağlayıcıyı çağıran tek katman."
                ),
                status="hazır",
            ),
            ArchitectureComponent(
                file="app/routers/assistant.py",
                responsibility="HTTP uç noktaları ve hata çevirisi.",
                status="hazır",
            ),
            ArchitectureComponent(
                file="app/services/assistant/data_access.py",
                responsibility="Kurumsal veriye salt okunur erişim.",
                status="hazır",
            ),
            ArchitectureComponent(
                file="app/services/assistant/context_builder.py",
                responsibility=(
                    "Soruyu bir konuya eşler ve o konu için gereken verileri "
                    "derler. Henüz modele bağlı değildir."
                ),
                status="eksik — modele bağlanmadı",
            ),
        ],
        next_steps=[
            "Araç çağrısı (tool calling) katmanını ekleyin: modelin öğrenci, "
            "mali, personel ve kapasite verilerini gerçek uç noktalardan "
            "okuyabilmesi için.",
            "context_builder çıktısını modele bağlayın; böylece model kurum "
            "verisiyle cevap verebilsin.",
            "Senaryo motorunu araç olarak tanımlayın; 'öğrenci sayısı %15 "
            "artarsa' türü sorular gerçek hesapla cevaplansın.",
            "Cevapların hangi veriye dayandığını gösteren kaynak gösterimi ekleyin.",
        ],
    )
