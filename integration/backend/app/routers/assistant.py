"""Akıllı asistan endpoint'leri.

ÖNEMLİ: Bu router hiçbir dil modeline istek göndermez ve cevap üretmez.
Sağladığı şey, bir soruya cevap verilebilmesi için gereken kurumsal verinin
toplanması ve asistan altyapısının durumunun şeffaf biçimde bildirilmesidir.

Bir dil modeli bağlanana kadar /answer benzeri bir endpoint bilinçli olarak
YOKTUR. Böyle bir endpoint eklenip kural tabanlı metin döndürseydi, kullanıcı
bunun bir yapay zekâ cevabı olduğunu sanırdı.
"""

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.assistant import context_builder, provider_factory
from app.services.assistant.schemas import (
    ArchitectureComponent,
    ArchitectureResponse,
    AssistantStatus,
    ContextRequest,
    ContextResponse,
    SampleQuestion,
)

router = APIRouter(prefix="/api/assistant", tags=["Akıllı Asistan (altyapı)"])


@router.get(
    "/status",
    response_model=AssistantStatus,
    summary="Asistan yapılandırma durumu",
)
def get_status() -> AssistantStatus:
    """Asistanın etkin olup olmadığını ve hangi sağlayıcının seçildiğini bildirir.

    API anahtarı hiçbir zaman döndürülmez; yalnızca tanımlı olup olmadığı
    bilgisi verilir.
    """
    return provider_factory.get_status()


@router.get(
    "/sample-questions",
    response_model=List[SampleQuestion],
    summary="Örnek sorular",
)
def get_sample_questions() -> List[SampleQuestion]:
    """Sistemin doğru veriyi toplayabildiği örnek sorular."""
    return context_builder.sample_questions()


@router.post(
    "/prepare-context",
    response_model=ContextResponse,
    summary="Soru için kurumsal bağlamı hazırla",
)
def prepare_context(
    payload: ContextRequest, db: Session = Depends(get_db)
) -> ContextResponse:
    """Soruya ilişkin kurumsal verileri toplar; CEVAP ÜRETMEZ.

    Dönen cevaptaki `notice` alanı, bunun bir dil modeli çıktısı olmadığını
    açıkça belirtir ve arayüzde de bu şekilde gösterilir.
    """
    return context_builder.build_context(db, payload.question)


@router.get(
    "/architecture",
    response_model=ArchitectureResponse,
    summary="Asistan mimarisi ve bağlanma adımları",
)
def get_architecture() -> ArchitectureResponse:
    """Altyapının hangi parçalarının hazır olduğunu ve ne eksik olduğunu gösterir."""
    return ArchitectureResponse(
        summary=(
            "Asistan katmanı dört parçadan oluşur. Veri erişimi, bağlam derleme ve "
            "sağlayıcı seçimi hazırdır. Eksik olan tek parça, AssistantProvider "
            "arayüzünü uygulayan somut bir dil modeli sağlayıcısıdır. Bu sınıf "
            "yazılana kadar sistem bilinçli olarak cevap üretmez."
        ),
        components=[
            ArchitectureComponent(
                file="app/services/assistant/schemas.py",
                responsibility="Asistan katmanının veri sözleşmeleri.",
                status="hazır",
            ),
            ArchitectureComponent(
                file="app/services/assistant/data_access.py",
                responsibility=(
                    "Kurumsal veriye salt okunur erişim. Her modülün servisini "
                    "çağırır, hassas alanları dışarıda bırakır."
                ),
                status="hazır",
            ),
            ArchitectureComponent(
                file="app/services/assistant/context_builder.py",
                responsibility=(
                    "Soruyu anahtar kelimelerle bir konuya eşler ve o konu için "
                    "gereken verileri derler. Yapay zekâ değildir."
                ),
                status="hazır",
            ),
            ArchitectureComponent(
                file="app/services/assistant/provider_factory.py",
                responsibility=(
                    "Ortam değişkenlerinden sağlayıcıyı seçer. Kayıt defteri boş "
                    "olduğu için şu anda daima 'sağlayıcı yok' döner."
                ),
                status="hazır",
            ),
            ArchitectureComponent(
                file="app/services/assistant/base.py",
                responsibility=(
                    "Sağlayıcı arayüzü (soyut sınıf). Somut bir uygulaması yok."
                ),
                status="eksik — somut sağlayıcı yazılmadı",
            ),
        ],
        next_steps=[
            "Ekip olarak bir dil modeli sağlayıcısına karar verin. Bu karar bu "
            "projede bilinçli olarak verilmemiştir.",
            "Seçilen sağlayıcının istemci paketini requirements.txt dosyasına ekleyin.",
            "AssistantProvider arayüzünü uygulayan bir sınıf yazın ve "
            "provider_factory.PROVIDER_REGISTRY sözlüğüne kaydedin.",
            ".env dosyasına LLM_PROVIDER, LLM_MODEL ve LLM_API_KEY değerlerini "
            "girin. Anahtarı asla kaynak koda veya Git deposuna yazmayın.",
            "ASSISTANT_ENABLED=true yapın ve /api/assistant/status ile "
            "sağlayıcının kullanılabilir göründüğünü doğrulayın.",
            "Cevap üreten endpoint'i (ör. POST /api/assistant/ask) ancak bu "
            "adımlardan sonra ekleyin.",
        ],
    )
