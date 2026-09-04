"""Akıllı asistan endpoint'leri.

Asistan Gemini API'si üzerinden çalışır. Gemini dışında hiçbir bulut sağlayıcısına
istek gönderilmez, hiçbir API anahtarı kullanılmaz.

Bu router modelle doğrudan konuşmaz: doğrulama ve HTTP çevirisi burada,
yönerge ve konuşma yönetimi `chat_service`'te, ağ çağrısı `gemini_provider`'da
yapılır. Böylece sağlayıcı değişirse router'a dokunmak gerekmez.

BU AŞAMADA araç çağrısı, veritabanı sorgusu ve senaryo motoru bağlantısı
YOKTUR. Model kurum verisine erişemez ve sistem yönergesi ona bunu açıkça
söyler; sayı uydurması engellenir.
"""

import json
import logging
from datetime import datetime
from typing import Iterator, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AcademicProgram, Department, Faculty
from app.services.scope import resolve
from app.services.assistant import chart_builder, chat_service, context_builder
from app.services.assistant.provider_shared import AssistantProviderError
from app.services.assistant.schemas import (
    ArchitectureComponent,
    ArchitectureResponse,
    AssistantStatus,
    ChatRequest,
    ChatResponse,
    ContextRequest,
    ContextResponse,
    SampleQuestion,
    ScreenInsightRequest,
    ScreenInsightResponse,
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
    """Gemini erişilebilir mi ve model kullanılabilir mi?

    Gemini erişilemezken de 200 döner; durum alanları false olur. Bu uç noktanın
    hata fırlatması, asistan kapalıyken tüm arayüzü bozardı.
    """
    return AssistantStatus(**chat_service.status())


def _ui_scope(db: Session, secim) -> Optional[dict]:
    """Arayüzdeki birim seçimini araçların anladığı ada çevirir.

    Kimlikler `scope.resolve()` ile DOĞRULANIR: tutarsız bir kombinasyon
    (başka fakültenin bölümü gibi) 400 ile reddedilir. Araç şemaları ad
    aldığı için burada kimlikten ada tek yönlü çeviri yapılır; ters yönde
    ad tahmini YOKTUR.
    """
    if secim is None:
        return None
    cozulen = resolve(
        db,
        faculty_id=secim.faculty_id,
        department_id=secim.department_id,
        academic_program_id=secim.academic_program_id,
    )
    if cozulen.is_university:
        return None

    kapsam: dict = {}
    if cozulen.academic_program_id is not None:
        program = db.get(AcademicProgram, cozulen.academic_program_id)
        kapsam["program"] = program.name
    elif cozulen.department_id is not None:
        bolum = db.get(Department, cozulen.department_id)
        kapsam["department"] = bolum.name
    elif cozulen.faculty_id is not None:
        fakulte = db.get(Faculty, cozulen.faculty_id)
        kapsam["faculty"] = fakulte.name
    return kapsam or None


def _ui_context(db: Session, secim, academic_year: Optional[str], screen_context: Optional[dict] = None) -> Optional[dict]:
    """Araçların varsayılan kapsamı ve dönemi — tek yapısal bağlam."""
    kapsam = _ui_scope(db, secim) or {}
    if secim is not None:
        if secim.faculty_id:
            kapsam["faculty_id"] = secim.faculty_id
        if secim.department_id:
            kapsam["department_id"] = secim.department_id
        if secim.academic_program_id:
            kapsam["academic_program_id"] = secim.academic_program_id
    if screen_context:
        for k, v in screen_context.items():
            if v is not None and k not in kapsam:
                kapsam[k] = v
    if academic_year:
        kapsam["academic_year"] = academic_year
    return kapsam or None


@router.post(
    "/screen-insight",
    response_model=ScreenInsightResponse,
    summary="Ekran için otomatik yapay zeka analizi ve öneri kartı üret",
)
def screen_insight(payload: ScreenInsightRequest, db: Session = Depends(get_db)) -> ScreenInsightResponse:
    """Verilen ekran bağlamı ve seçili birim için otomatik kurumsal değerlendirme üretir."""
    from app.services.assistant import data_catalog
    ctx_dict = payload.screen_context.model_dump()
    result = data_catalog.generate_screen_auto_insight(db, ctx_dict, payload.academic_year)
    return ScreenInsightResponse(**result)


def grafik_yok_sebebi(*, veri_geldi: bool, zaman_asimi: bool) -> str:
    """Grafik çizilemediğinde kullanıcıya söylenecek GERÇEK sebep.

    Eskiden tek bir cümle vardı — "Bu veri mevcut kaynaklarda
    bulunmuyor." — ve grafiğin çıkmadığı HER durumda yazılıyordu.
    Ölçülen olay: veri araçları 32 + 35 satır döndürmüş, yalnızca
    modelin yorum turu zaman aşımına uğramıştı; kullanıcı buna rağmen
    "veri yok" okuyordu. Doğru veriye sahip bir sistemi yanlış tanıtmak,
    eksik grafikten daha pahalıdır.

    Ayrım tahmine değil turun kendi telemetrisine dayanır: veri geldi mi
    (`data_sources` dolu mu), tur zaman aşımı/kota ile mi bitti.
    """
    if not veri_geldi:
        return "Bu veri mevcut kaynaklarda bulunmuyor."
    # Veri VAR. Kullanıcıya teknik sebep (zaman aşımı / şema uyumsuzluğu)
    # yazılmaz: sunumda "aşama tamamlanamadı" gibi bir cümle sistemin
    # bozuk olduğu izlenimi verir. Sebep günlükte durur.
    return "Bu sonuç için grafik üretilemedi."


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Asistana mesaj gönder",
)
def chat(payload: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    """Yerel modelden cevap alır.

    Modelin düşünme metni cevaba dâhil edilmez. Gemini erişilemez, model kullanılamaz
    değil veya zaman aşımı varsa kullanıcıya anlaşılır bir hata döner —
    uydurma cevap ÜRETİLMEZ.
    """
    try:
        # Yetki listesi şimdilik geçilmiyor: oturum bilgisi sohbet uç noktasına
        # taşınana kadar bütün araçlar açıktır. Yetki KONTROLÜ hazır
        # (ToolSession.permissions); yalnızca kaynağı bağlanacak.
        ui_ctx = _ui_context(db, payload.scope, payload.academic_year, payload.screen_context)
        result = chat_service.answer(
            payload.message, payload.conversation_id, db=db,
            ui_scope=ui_ctx,
        )
    except chat_service.ChatValidationError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.user_message,
        ) from exc
    except AssistantProviderError as exc:
        raise _provider_http_error(exc) from exc

    # ------------------------------------------------------------------
    # GRAFİK — sayılar backend'den, model yalnızca yorum yazar.
    # ------------------------------------------------------------------
    # Grafik üretimi cevaptan SONRA ve modelden BAĞIMSIZ çalışır. Model
    # ne veri gönderir ne de kod; yalnızca konuşma metnini yazar.
    konusma_id = result.get("conversation_id")

    # MODELİN ÇİZDİRDİĞİ GRAFİKLER ÖNCE GELİR.
    # ------------------------------------------------------------------
    # Eskiden grafik konusu, mesajı SEKİZ elle yazılmış regex kalıbıyla
    # eşleştirerek bulunuyordu. Kalıba uymayan her soru — model doğru
    # aracı çağırıp gerçek veriyi almış olsa bile — "Grafik
    # oluşturulamadı" ile bitiyordu. Bir kalıp listesi hiçbir zaman
    # tamamlanmaz; eksik olan da sessizce "veri yok" gibi görünür.
    #
    # Artık ne çizileceğine model karar veriyor (`render_chart`). Değerler
    # yine backend'den gelir: araç yalnızca ALAN ADI kabul eder, sayı
    # kabul etmez.
    grafikler: list = list(result.pop("model_charts", None) or [])
    try:
        # Katalog yolu: `data_catalog` bir veri kümesi çözdüyse grafik
        # ONUN satırlarından çizilir. Bu yol kalıba değil çözülmüş
        # veriye dayanır, dolayısıyla korunur.
        structured = result.get("structured_result")
        katalog_sonucu = (
            structured
            if not grafikler
            and isinstance(structured, dict)
            and structured.get("type") == "catalog_query"
            else None
        )
        if katalog_sonucu is not None:
            # Metin ve grafik AYNI satırları tüketir; burada ikinci bir
            # sorgu çalıştırmak ikisinin ayrışmasına kapı açardı.
            grafik_sonuc = chart_builder.build_dataset_charts(
                katalog_sonucu, payload.message
            )
            grafikler = grafik_sonuc["charts"]
            chart_builder.remember_topic(konusma_id, grafik_sonuc["topic"])

        if (not grafikler
                and chart_builder.wants_chart(payload.message or "")):
            # SAHTE GRAFİK ÇİZİLMEZ — ama SEBEP DOĞRU SÖYLENİR.
            # ----------------------------------------------------------
            # Eskiden buradaki tek cümle "Bu veri mevcut kaynaklarda
            # bulunmuyor." idi ve grafiğin çizilmediği HER durumda
            # yazılıyordu. Ölçülen olay: veri araçları 32 + 35 satır
            # döndürmüş, yalnızca modelin yorum turu zaman aşımına
            # uğramıştı; kullanıcı buna rağmen "veri yok" okuyordu.
            # Bu, doğru veriye sahip bir sistemi yanlış tanıtır.
            #
            # Dört durum artık ayrılıyor. Ayrımın dayanağı tahmin değil,
            # turun kendi telemetrisi: veri geldi mi (`data_sources`),
            # tur zaman aşımıyla mı bitti (`timed_out`).
            # BAŞARILI METİN CEVABI VARSA UYARI HİÇ EKLENMEZ.
            # Kullanıcı sorusunun cevabını almışsa, grafiğin çıkmamış
            # olması ekranın altına bir hata satırı düşürmeyi hak etmez;
            # bu satır sunumda cevabı değil eksiği öne çıkarıyordu.
            # Uyarı yalnızca ELDE BAŞKA HİÇBİR ŞEY YOKKEN anlamlıdır.
            veri_geldi = bool(result.get("data_sources"))
            cevap_var = len((result.get("answer") or "").strip()) > 80
            if veri_geldi and cevap_var:
                sebep = ""
            else:
                sebep = grafik_yok_sebebi(
                    veri_geldi=veri_geldi,
                    zaman_asimi=bool(result.get("timed_out")))
            if sebep and sebep not in result.get("answer", ""):
                result["answer"] = (
                    (result.get("answer") or "").rstrip()
                    + ("\n\n" if result.get("answer") else "")
                    + "Grafik oluşturulamadı: " + sebep)
    except Exception:  # noqa: BLE001
        logger.exception("Grafik uretimi basarisiz")

    # `timed_out` yalnızca yukarıdaki grafik-sebebi ayrımı içindi;
    # yanıt şemasının alanı değil, bu yüzden burada çıkarılır.
    result.pop("timed_out", None)
    return ChatResponse(calculated_at=datetime.now(), charts=grafikler, **result)


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
    scope = resolve(
        db,
        faculty_id=payload.scope.faculty_id if payload.scope else None,
        department_id=payload.scope.department_id if payload.scope else None,
        academic_program_id=(
            payload.scope.academic_program_id if payload.scope else None),
    )
    return context_builder.build_context(
        db, payload.question, scope, payload.academic_year)


@router.get(
    "/architecture",
    response_model=ArchitectureResponse,
    summary="Asistan mimarisi ve sonraki adımlar",
)
def get_architecture() -> ArchitectureResponse:
    """Hangi parçaların hazır olduğunu ve neyin eksik kaldığını gösterir."""
    return ArchitectureResponse(
        summary=(
            "Asistan Gemini API'si üzerinden çalışır; araçlarının tamamı yerel "
            "servisine istek gönderilmez. Sağlayıcı, sohbet servisi ve uç "
            "noktalar hazırdır. Eksik olan parça araç entegrasyonudur: model "
            "henüz veritabanını sorgulayamaz ve senaryo motorunu çalıştıramaz, "
            "bu yüzden kurum verisi gerektiren sorularda sayı üretmez."
        ),
        components=[
            ArchitectureComponent(
                file="app/services/assistant/gemini_provider.py",
                responsibility=(
                    "Gemini sohbet ucuyla konuşur. Anahtar ve model "
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
