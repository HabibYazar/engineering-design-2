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
from datetime import datetime
from collections import OrderedDict
from typing import Any, Dict, Iterator, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.assistant.ollama_provider import (
    AssistantProviderError,
    OllamaProvider,
)
from app.services.assistant import (
    entity_resolver,
    query_policy,
    response_composer,
    ui_spec_builder,
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

# Senaryo sonucu zorunlu alanları taşımıyorsa kullanıcıya gösterilen metin.
MISSING_METRIC_MESSAGE = (
    "Senaryo sonucu eksik üretildi; bazı zorunlu göstergeler hesaplanamadı. "
    "Güvenilir olmayan bir sonuç göstermemek için sayısal cevap "
    "oluşturulmadı."
)

SYSTEM_PROMPT = """Sen, Ankara Bilim Üniversitesi Stratejik Yönetim ve Karar Destek Sistemi içinde çalışan bir yönetim asistanısın.

Görevin, üniversite üst yönetimine kurum verisine dayalı, doğrulanabilir cevaplar vermektir.

VERİ KULLANIMI — EN ÖNEMLİ KURALLAR

1. Kurumsal sayıları YALNIZCA araç sonuçlarından al. Öğrenci sayısı, bütçe, doluluk oranı, personel sayısı, kapasite gibi her rakam bir araç çıktısından gelmelidir.
2. Araç sonucu yoksa sayı UYDURMA. "Bu bilgi için gerekli veriye ulaşamadım" de.
3. Kendi kafandan hesap YAPMA. Toplama, çıkarma, yüzde hesabı gerekiyorsa ilgili aracı çağır. Araçların döndürdüğü değerleri olduğu gibi aktar.
4. Bir araç hata döndürürse o konuda sayı verme; hatanın sebebini kullanıcıya sade bir dille açıkla.
5. Araç çıktısındaki "notes" alanında yazan uyarıları cevabına taşı. Örneğin bir değer üniversite geneli ise bunu belirt.

NE ZAMAN SENARYO ÇALIŞTIRILIR

6. Kullanıcı "artarsa", "azalırsa", "zam yapılırsa", "ne olur" gibi bir VARSAYIM soruyorsa ilgili SENARYO aracını çağır. Mevcut durumu döndüren özet araçları (gelir, gider, öğrenci sayısı) bir senaryo sorusunu CEVAPLAMAZ; onlar değişimin etkisini hesaplamaz.
7. Kullanıcı yalnızca mevcut durumu soruyorsa (kaç öğrenci var, bütçe ne kadar) SENARYO ÇALIŞTIRMA; yalnızca özet araçlarını kullan.
7a. Bir senaryo sonucu sana hazır olarak verilmişse yeni araç çağırma; o sonucu yorumla.
7b. "Hesaplanan sonuçlar" bölümü backend tarafından hazırlanır ve kullanıcıya aynen gösterilir. O bölümdeki değerleri değiştirme, yeniden hesaplama, yuvarlama veya farklı birimle tekrar yazma. Sayıları tekrar listeleme; yalnızca etkilerini yorumla.

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

    KURUMSAL SORU POLİTİKASI
    ------------------------
    Soru kurum verisi gerektiriyorsa araç sonucu olmadan üretilen cevap
    kullanıcıya VERİLMEZ. Sistem yönergesine güvenmek yetmiyor: canlı testte
    model kurumsal bir soruya hiç araç çağırmadan cevap üretti. Kural artık
    sunucu tarafında uygulanıyor.
    """
    conversation, messages = _prepare(message, conversation_id)
    user_content = messages[-1]["content"]
    institutional = query_policy.is_institutional_query(user_content)

    # Veri oturumu yoksa kurumsal soru için MODEL HİÇ ÇAĞRILMAZ. Modelden
    # "genel bilgi" cevabı istemek, kullanıcıya kurum verisi gibi görünen bir
    # metin üretme riskini boşuna alır.
    if institutional and db is None:
        logger.warning("Kurumsal soru veri oturumu olmadan geldi; model cagrilmadi.")
        _store.append(conversation, "user", user_content)
        _store.append(conversation, "assistant", query_policy.NO_DATABASE_MESSAGE)
        provider = get_provider()
        return {
            "conversation_id": conversation,
            "answer": query_policy.NO_DATABASE_MESSAGE,
            "provider": provider.name,
            "model": provider.model,
            "used_tools": [],
            "data_sources": [],
            "academic_year": None,
            "scope": {},
            "data_source": query_policy.SOURCE_UNAVAILABLE,
            "structured_result": None,
            "ui_spec": None,
        }

    provider = get_provider()

    session: Optional[ToolSession] = None
    tool_schemas: Optional[List[Dict]] = None
    if db is not None:
        session = ToolSession(db=db, permissions=permissions, registry=registry)
        tool_schemas = registry.schemas(permissions)

    # ------------------------------------------------------------------
    # ZORUNLU SENARYO ARACI — karar modele bırakılmaz.
    #
    # Canlı testte model "maaşlara %2 zam yapılırsa" sorusuna mevcut bütçeyi
    # döndüren aracı çağırdı; o araç zammın etkisini hesaplamaz. Araç seçimi
    # bir muhakeme işi değil yönlendirme işidir: backend niyeti belirler,
    # parametreleri metinden çıkarır ve aracı KENDİSİ çalıştırır. Model
    # yalnızca sonucu yorumlar.
    # ------------------------------------------------------------------
    intent = query_policy.classify(user_content)
    forced_tool: Optional[str] = None
    composed: Optional[response_composer.ComposedResponse] = None

    # Kullanıcı adını verdiği bir birim sistemde yoksa MODELE HİÇ SORULMAZ.
    # Aksi halde model soruyu alakasız bir araçla cevaplayabiliyor ve
    # başarılı bir araç çağrısı olduğu için sistem bunu kabul ediyordu.
    if session is not None and intent.institutional:
        missing_unit = entity_resolver.unresolved_unit_in_text(db, user_content)
        if missing_unit:
            logger.info("Bulunamayan birim adi: %s", missing_unit)
            message_text = (
                f"'{missing_unit}' adında bir program, bölüm veya fakülte "
                f"sistemde bulunamadı. Lütfen adı kontrol edip yeniden sorun."
            )
            _store.append(conversation, "user", user_content)
            _store.append(conversation, "assistant", message_text)
            return {
                "conversation_id": conversation,
                "answer": message_text,
                "provider": provider.name,
                "model": provider.model,
                "used_tools": [],
                "data_sources": [],
                "academic_year": None,
                "scope": {},
                "data_source": query_policy.SOURCE_UNAVAILABLE,
                "structured_result": None,
                "ui_spec": None,
            }

    # Program özeti zorunluluğu, cümlede GERÇEKTEN bir program adı geçmesine
    # bağlıdır. "Mekânların doluluk oranı ne kadar?" bir program sorusu
    # değildir; zorunlu kılınırsa model hiç cevaplayamaz.
    if (
        session is not None
        and intent.required_tool == "get_program_summary"
        and entity_resolver.find_in_text(db, "program", user_content) is None
    ):
        intent.required_tool = None

    if session is not None and intent.required_tool:
        forced_tool = intent.required_tool
        arguments = _build_forced_arguments(db, intent, user_content)
        if arguments is not None:
            record = session.run(forced_tool, arguments)
            messages.append(
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {"function": {"name": forced_tool, "arguments": arguments}}
                    ],
                }
            )
            messages.append(
                {"role": "tool", "name": record.name, "content": record.content}
            )
            if record.success and response_composer.supports(forced_tool):
                # ZORUNLU GERÇEKLER burada üretilir. Model bir metriği
                # atlarsa cevap eksik kalmasın diye bu bölüm backend
                # tarafından yazılır ve final cevaba mutlaka eklenir.
                try:
                    composed = response_composer.compose(forced_tool, record.output)
                except response_composer.MissingMetricError as exc:
                    logger.error("Senaryo sonucu eksik uretildi: %s", exc.missing)
                    _store.append(conversation, "user", user_content)
                    _store.append(conversation, "assistant", MISSING_METRIC_MESSAGE)
                    return {
                        "conversation_id": conversation,
                        "answer": MISSING_METRIC_MESSAGE,
                        "provider": provider.name,
                        "model": provider.model,
                        "used_tools": session.used_tools(),
                        "data_sources": session.data_sources(),
                        "academic_year": session.academic_year(),
                        "scope": session.scope(),
                        "data_source": query_policy.SOURCE_UNAVAILABLE,
                        "structured_result": None,
                        "ui_spec": None,
                    }

                messages.append(
                    {
                        "role": "system",
                        "content": (
                            response_composer.COMPOSER_INSTRUCTION
                            + "\n\n"
                            + composed.facts_markdown
                        ),
                    }
                )
                tool_schemas = None
            elif record.success:
                messages.append(
                    {
                        "role": "system",
                        "content": (
                            "Senaryo sonucu yukarıda hazır. Yeni araç çağırma; "
                            "bu sonucu kullanıcıya Türkçe olarak yorumla. "
                            "Kullandığın akademik yılı ve kapsamı belirt."
                        ),
                    }
                )
                tool_schemas = None
        else:
            # Parametreler metinden çıkarılamadı: modele YALNIZCA gerekli araç
            # sunulur, başka araç seçemez.
            logger.info("Zorunlu arac parametreleri cikarilamadi: %s", forced_tool)
            tool_schemas = [
                schema
                for schema in (tool_schemas or [])
                if schema["function"]["name"] == forced_tool
            ]
            messages.append(
                {
                    "role": "system",
                    "content": query_policy.REQUIRED_TOOL_INSTRUCTION.format(
                        tool=forced_tool
                    ),
                }
            )

    started = time.monotonic()
    steps = 0
    visible = ""
    # Kurumsal soruda modele araçsız cevap için verilen ikinci şans.
    forced_retry_used = False

    while True:
        elapsed = time.monotonic() - started
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

        try:
            tool_calls, visible, thinking = provider.chat_with_tools(messages, offered_tools)
        except AssistantProviderError:
            # Hesaplanan sonuçlar hazırsa modelin yorumu olmadan da cevap
            # verilir. Model boş metin döndürdü diye doğru hesaplanmış bir
            # senaryoyu kullanıcıdan saklamak yanlış olur.
            if composed is None:
                raise
            logger.warning(
                "Model yorum uretemedi; yalnizca hesaplanan sonuclar donuluyor."
            )
            tool_calls, visible, thinking = [], "", ""
        if thinking:
            logger.debug(
                "Model dusunme metni uretti (%d karakter), kullaniciya gonderilmedi",
                len(thinking),
            )

        if tool_calls and session is not None and offered_tools is not None:
            steps += 1
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
            continue

        # --- Araç çağrısı yok. Kurumsal soruda bu yeterli değil. ---
        needs_tool_result = (
            institutional
            and session is not None
            and not session.any_success()
            and offered_tools is not None
        )
        if needs_tool_result and not forced_retry_used:
            logger.info("Kurumsal soruya aracsiz cevap uretildi; ikinci sans veriliyor.")
            forced_retry_used = True
            # Modelin araçsız metni ATILIR: kullanıcıya gösterilmeyecek bir
            # cevabı konuşma geçmişine koymak modeli aynı hataya iter.
            messages.append(
                {"role": "system", "content": query_policy.RETRY_INSTRUCTION}
            )
            visible = ""
            continue

        break

    used_tools = session.used_tools() if session else []
    data_sources = session.data_sources() if session else []
    scope = session.scope() if session else {}
    academic_year = session.academic_year() if session else None
    tool_data_available = session is not None and session.any_success()

    # ZORUNLU ARAÇ KONTROLÜ: gerekli senaryo aracı başarıyla çalışmadıysa
    # modelin serbest metni kullanıcıya GÖSTERİLMEZ. Yanlış araçla üretilmiş
    # bir "mevcut bütçe" özeti, senaryo sorusunun cevabı değildir.
    required_tool_ran = True
    if forced_tool is not None and session is not None:
        required_tool_ran = any(
            record.name == forced_tool and record.success for record in session.records
        )
        if not required_tool_ran:
            logger.warning(
                "Zorunlu arac calismadi (%s); model metni reddedildi.", forced_tool
            )

    # Kurumsal soru + araç sonucu yok → modelin metni KULLANICIYA VERİLMEZ.
    if institutional and (not tool_data_available or not required_tool_ran):
        logger.warning(
            "Kurumsal soru arac sonucu olmadan cevaplandi; model metni reddedildi."
        )
        visible = query_policy.NO_TOOL_RESULT_MESSAGE
        data_source = query_policy.SOURCE_UNAVAILABLE
    elif tool_data_available:
        data_source = query_policy.SOURCE_INSTITUTIONAL
    else:
        data_source = query_policy.SOURCE_GENERAL

    # ZORUNLU GERÇEKLER + MODEL YORUMU.
    #
    # Model yorumu boş olsa bile hesaplanan sonuçlar kullanıcıya ulaşır:
    # canlı testte model 370 → 426 değişimini yazmayı atlamıştı.
    structured_result: Optional[Dict[str, Any]] = None
    ui_spec_payload: Optional[Dict[str, Any]] = None
    if composed is not None and data_source == query_policy.SOURCE_INSTITUTIONAL:
        structured_result = composed.structured_result
        interpretation = _clean_interpretation(visible, composed.facts_markdown)
        visible = composed.facts_markdown
        if interpretation:
            visible += "\n\n" + interpretation

        # DİNAMİK SONUÇ PENCERESİ.
        # Kartlar ve grafikler modelin metninden DEĞİL, structured_result'tan
        # üretilir. Üretim başarısız olursa sohbet cevabı yine gösterilir;
        # pencere isteğe bağlı bir katmandır.
        try:
            spec = ui_spec_builder.build_ui_spec(
                structured_result,
                data_sources=data_sources,
                calculated_at=datetime.now(),
                interpretation=interpretation,
                markdown=composed.facts_markdown,
            )
            ui_spec_payload = spec.model_dump(mode="json") if spec else None
        except Exception:  # noqa: BLE001
            logger.exception("Dinamik pencere tanimi uretilemedi")
            ui_spec_payload = None

    if not visible:
        raise AssistantProviderError(
            "Yerel modelden geçerli bir yanıt alınamadı. Ollama günlüklerini kontrol edin.",
            kind="invalid_response",
        )

    _store.append(conversation, "user", user_content)
    _store.append(conversation, "assistant", visible)

    return {
        "conversation_id": conversation,
        "answer": visible,
        "provider": provider.name,
        "model": provider.model,
        "used_tools": used_tools,
        "data_sources": data_sources,
        "academic_year": academic_year,
        "scope": scope,
        "data_source": data_source,
        "structured_result": structured_result,
        "ui_spec": ui_spec_payload,
    }


def _clean_interpretation(text: str, facts_markdown: str) -> str:
    """Modelin yorumunu hazırlar.

    Model bazen zorunlu gerçekler bölümünü kopyalıyor; aynı sayılar iki kez
    görünmesin diye tekrar eden satırlar atılır. Model yorumu boşsa boş
    dizge döner — gerçekler bölümü yine de kullanıcıya gider.
    """
    if not text:
        return ""

    fact_lines = {line.strip() for line in facts_markdown.splitlines() if line.strip()}
    kept: List[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and stripped in fact_lines:
            continue
        if stripped.startswith("### Hesaplanan sonuçlar"):
            continue
        kept.append(line)

    cleaned = "\n".join(kept).strip()
    if not cleaned:
        return ""
    # Model başlıkları hiç yazmadıysa en azından bir başlık altına alınır;
    # başlıksız serbest metin, kapsamı belirsiz bir yorum demektir.
    if not any(
        heading in cleaned for heading in response_composer.INTERPRETATION_HEADINGS
    ):
        cleaned = f"{response_composer.INTERPRETATION_HEADING}\n{cleaned}"
    return cleaned


def _build_forced_arguments(
    db: Session, intent: "query_policy.QueryIntent", message: str
) -> Optional[Dict[str, Any]]:
    """Zorunlu senaryo aracının parametrelerini metinden çıkarır.

    Hepsi çıkarılamazsa None döner ve karar modele bırakılır — ama model
    yalnızca gerekli aracı görebilir, başkasını seçemez.

    Akademik yıl POLİTİKAYLA belirlenir: kullanıcı açıkça yazmadıysa
    `current` dönem seçilir, planlama dönemi seçilmez.
    """
    try:
        year = entity_resolver.resolve_academic_year(
            db,
            intent.explicit_academic_year,
            allow_planning=intent.wants_planning_period,
        )
    except entity_resolver.EntityResolutionError:
        return None

    if intent.intent == query_policy.INTENT_STAFF_SALARY:
        percentage = intent.parameters.get("salary_change_percentage")
        if percentage is None:
            return None
        return {"academic_year": year, "salary_change_percentage": percentage}

    if intent.required_tool == "get_program_summary":
        program = entity_resolver.find_in_text(db, "program", message)
        if program is None:
            return None
        return {"academic_year": year, "program": program.code}

    if intent.intent == query_policy.INTENT_ENROLLMENT_CHANGE:
        percentage = intent.parameters.get("student_change_percentage")
        if percentage is None:
            return None
        program = entity_resolver.find_in_text(db, "program", message)
        if program is None:
            return None
        return {
            "academic_year": year,
            "program": program.code,
            "student_change_percentage": percentage,
        }

    return None


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
    "query_policy",
    "MAX_TOOL_WALL_SECONDS",
    "SYSTEM_PROMPT",
    "answer",
    "build_messages",
    "reset_conversations",
    "status",
    "stream_answer",
    "validate_message",
]
