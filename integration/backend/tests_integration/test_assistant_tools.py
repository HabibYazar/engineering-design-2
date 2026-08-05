"""Akıllı Asistan — araç çağırma (tool calling) testleri.

Hiçbiri gerçek Ollama gerektirmez: modelin araç çağrısı üreten cevapları
taklit edilir. Araçların KENDİSİ gerçek veritabanına bağlanır — sayıların
doğruluğu ancak gerçek servislerle ölçülebilir.

Bu dosya tests_integration/ altındadır çünkü TAM demo veri setine ihtiyaç
duyar (4.000 öğrenci, mali dönemler, mekânlar). tests/ altındaki birim
testlerinin veritabanı yalnızca modül içi örnek kayıtlar taşır.

Gerçek Ollama ile çalışan isteğe bağlı testler:
`tests/test_assistant_ollama_live.py`.
"""

import json
from dataclasses import replace
from decimal import Decimal
from typing import Any, Dict, List, Optional

import httpx
import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.services import finance_service
from app.services import student_analytics_service as students
from app.services.assistant import chat_service, entity_resolver, tools  # noqa: F401
from app.services.assistant.tool_registry import ToolExecutionError, registry
from app.services.assistant.tool_runner import ToolSession
from main import app

YEAR = "2025-2026"


@pytest.fixture(autouse=True)
def _clean():
    chat_service.reset_conversations()
    yield
    chat_service.reset_conversations()


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def call(db, name: str, **kwargs):
    """Bir aracı doğrudan çalıştırır."""
    tool = registry.get(name)
    return tool.handler(db, tool.input_model(**kwargs))


# ---------------------------------------------------------------------------
# Ollama'yı taklit eden altyapı
# ---------------------------------------------------------------------------


class ScriptedOllama:
    """Sırayla verilen cevapları döndüren sahte Ollama istemcisi.

    Her cevap ya araç çağrısı listesi ya da düz metindir. Böylece çok turlu
    araç akışı deterministik olarak sınanabilir.
    """

    def __init__(self, script: List[Any]) -> None:
        self.script = list(script)
        self.requests: List[Dict] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url: str, **kwargs):
        return _Response({"models": [{"name": "qwen3.5:9b"}]})

    def post(self, url: str, **kwargs):
        self.requests.append(kwargs.get("json") or {})
        if not self.script:
            return _Response(_text_message("Başka söyleyecek bir şeyim yok."))
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        if isinstance(step, str):
            return _Response(_text_message(step))
        return _Response(_tool_message(step))


class _Response:
    def __init__(self, payload: Dict, status_code: int = 200) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


def _text_message(text: str) -> Dict:
    return {"message": {"role": "assistant", "content": text}, "done": True}


def _tool_message(calls: List[Dict]) -> Dict:
    return {
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"function": {"name": c["name"], "arguments": c.get("arguments", {})}}
                for c in calls
            ],
        },
        "done": True,
    }


def script_ollama(monkeypatch, script: List[Any]) -> ScriptedOllama:
    fake = ScriptedOllama(script)
    monkeypatch.setattr(
        "app.services.assistant.ollama_provider._local_client", lambda timeout: fake
    )
    return fake


# ===========================================================================
# 1-4) Birim adı çözümleme
# ===========================================================================


def test_resolves_turkish_program_name(db) -> None:
    """Türkçe program adı doğru kayda bağlanmalı."""
    entity = entity_resolver.resolve(db, "program", "Bilgisayar Mühendisliği")
    assert entity.code == "CENG-BSC"
    assert entity.display_name == "Bilgisayar Mühendisliği Lisans Programı"


@pytest.mark.parametrize(
    "query",
    [
        "Bilgisayar Mühendisliği",
        "Computer Engineering",
        "CENG-BSC",
        "CENG",
        "bilgisayar muhendisligi",  # şapkasız yazım
        "BILGISAYAR MÜHENDISLIĞI",
    ],
)
def test_turkish_english_and_code_all_match(db, query: str) -> None:
    """Aynı program Türkçe, İngilizce ve kodla bulunabilmeli."""
    assert entity_resolver.resolve(db, "program", query).code == "CENG-BSC"


def test_ambiguous_program_name_asks_the_user(db) -> None:
    """Birden fazla eşleşmede TAHMİN edilmemeli, seçenek sunulmalı."""
    with pytest.raises(entity_resolver.EntityResolutionError) as exc:
        entity_resolver.resolve(db, "program", "İşletme")

    assert exc.value.kind == "ambiguous"
    assert len(exc.value.candidates) >= 2
    assert "İşletme Lisans Programı" in exc.value.candidates


def test_unknown_program_is_not_guessed(db) -> None:
    """Var olmayan program için en yakın sonuç DÖNDÜRÜLMEMELİ.

    "Uzay Mühendisliği" ile var olan mühendislik programları yalnızca
    "mühendisliği" sözcüğünü paylaşır. Zayıf benzerlikten hareketle bir
    program seçmek, yanlış bölümün verisini doğru cevap gibi sunardı.
    """
    with pytest.raises(entity_resolver.EntityResolutionError) as exc:
        entity_resolver.resolve(db, "program", "Uzay Mühendisliği")

    assert exc.value.kind == "not_found"


def test_unknown_academic_year_is_rejected(db) -> None:
    """Uydurma bir yıl sessizce başka yılın verisine düşmemeli."""
    with pytest.raises(entity_resolver.EntityResolutionError) as exc:
        entity_resolver.resolve_academic_year(db, "2099-2100")
    assert exc.value.kind == "not_found"


def test_scope_is_derived_from_the_program(db) -> None:
    """Program verildiğinde bölüm ve fakülte ondan türetilmeli."""
    year, faculty, department, program = entity_resolver.resolve_scope(
        db, academic_year=YEAR, program="CENG-BSC"
    )
    assert year == YEAR
    assert program.code == "CENG-BSC"
    assert department.code == "CENG"
    assert faculty.code == "FEA"


# ===========================================================================
# 5-8) Veri araçları — sayılar backend ile birebir aynı olmalı
# ===========================================================================


def test_program_summary_matches_the_analytics_service(db) -> None:
    """Araç çıktısı öğrenci analitiği servisiyle birebir aynı olmalı."""
    program = entity_resolver.resolve(db, "program", "Bilgisayar Mühendisliği")
    expected = students.build_program_analytics(
        db, academic_program_id=program.id, academic_year=YEAR
    )[0]

    result = call(db, "get_program_summary", program="Bilgisayar Mühendisliği", academic_year=YEAR)

    assert result.student_count == expected.total_students
    assert result.quota == expected.quota
    assert result.occupancy_rate == expected.occupancy_rate
    assert result.graduation_rate == expected.graduation_rate
    assert result.dropout_rate == expected.attrition_rate
    assert result.scope.academic_year == YEAR
    assert result.scope.program == "Bilgisayar Mühendisliği Lisans Programı"


def test_financial_summary_matches_the_finance_service(db) -> None:
    """Mali araç, mali servisin rakamlarını TAM USD olarak döndürmeli.

    Mali servis tutarları MİLYON USD tutar; araç şeması `..._usd` diyor.
    Dönüşüm yapılmazsa model 50,4 milyon doları "50 dolar" diye okur.
    """
    expected = finance_service.financial_summary(db, YEAR)
    result = call(db, "get_financial_summary", academic_year=YEAR)

    assert result.total_revenue_usd == Decimal(expected["total_revenue"]) * 1_000_000
    assert result.total_expenditure_usd == Decimal(expected["total_expenditure"]) * 1_000_000
    assert result.net_balance_usd == Decimal(expected["balance"]) * 1_000_000
    assert result.cost_per_student_usd == expected["cost_per_student_usd"]
    assert result.currency == "USD"
    # Milyonluk bir bütçe binlik mertebede görünmemeli.
    assert result.total_revenue_usd > 1_000_000


def test_capacity_summary_uses_all_enrolled_students(db) -> None:
    """Eş zamanlı talep KAYITLI TÜM öğrencilerden hesaplanmalı.

    `build_overview(academic_year=...)` yalnızca o yıl kayıt olanları sayıyor
    (800), oysa derslik talebi 4.000 öğrenciden doğar. Yıl filtresi geçilseydi
    kapasite açığı beşte bir görünürdü.
    """
    result = call(db, "get_capacity_summary", academic_year=YEAR)
    total_students = int(students.build_overview(db).total_students)

    assert result.classroom_capacity is not None
    assert result.laboratory_capacity is not None
    # Talep = toplam öğrenci × eş zamanlı kullanım katsayısı.
    from app.services.scenario_engine import SIMULTANEOUS_CLASSROOM_USE

    expected_demand = int((Decimal(total_students) * SIMULTANEOUS_CLASSROOM_USE).to_integral_value())
    assert result.capacity_gap == expected_demand - result.classroom_capacity
    assert result.capacity_status in {"yeterli", "sınırda", "yetersiz"}


def test_staff_summary_cost_matches_the_scenario_engine(db) -> None:
    """Personel maliyeti senaryo motoruyla ÇELİŞMEMELİ.

    Personel tablosunda 88 kayıt var, mali dönem bordrosu 180 kadro üzerinden
    planlanmış. İki farklı sayı aynı cevapta çıkarsa asistan kendisiyle
    çelişir; bu yüzden maliyet mali dönem kaydından alınır ve fark `notes`
    alanında açıkça yazılır.
    """
    from app.schemas.scenarios import ScenarioInputCreate
    from app.services.scenario_baseline_builder import build_from_financial_period
    from app.services.scenario_engine import calculate

    result = call(db, "get_academic_staff_summary", academic_year=YEAR)
    baseline = build_from_financial_period(db, YEAR)
    computation = calculate(baseline, ScenarioInputCreate())

    assert result.annual_salary_cost_usd == computation.baseline_academic_personnel_expense
    assert result.average_salary_usd == computation.baseline_average_academic_salary
    assert any("bordro" in note for note in result.notes), (
        "İki farklı kadro sayısı var ama kullanıcı bundan haberdar edilmiyor."
    )


# ===========================================================================
# 9-10) Senaryo araçları
# ===========================================================================


def test_enrollment_scenario_scales_program_change_to_the_university(db) -> None:
    """Program düzeyindeki %15 artış kurum geneline doğru oranla yansımalı.

    Senaryo motoru kurum geneli çalışır. 370 öğrencilik bir programdaki %15
    artış 56 öğrenci demektir; bu 4.000 öğrencilik üniversitede %1,4'tür.
    Payda yanlış alınırsa (o yıl kayıt olan 800 öğrenci) mali etki beş kat
    abartılı çıkar.
    """
    result = call(
        db,
        "run_enrollment_change_scenario",
        program="Bilgisayar Mühendisliği",
        academic_year=YEAR,
        student_change_percentage=15,
    )

    program_baseline = result.baseline.program_student_count
    added = round(program_baseline * 0.15)
    assert result.scenario.program_student_count == program_baseline + added

    university_baseline = result.baseline.university_student_count
    assert university_baseline == int(students.build_overview(db).total_students)
    # Kurum geneli artış, eklenen öğrenci kadar olmalı (±1 yuvarlama).
    assert abs(result.scenario.university_student_count - university_baseline - added) <= 1
    assert "%1.40" in result.method_note or "1.40" in result.method_note


def test_enrollment_scenario_numbers_come_from_the_engine(db) -> None:
    """Senaryo rakamları motorun ürettiğiyle birebir aynı olmalı."""
    from app.schemas.scenarios import ScenarioInputCreate
    from app.services.scenario_baseline_builder import build_from_financial_period
    from app.services.scenario_engine import calculate

    result = call(
        db,
        "run_enrollment_change_scenario",
        program="Bilgisayar Mühendisliği",
        academic_year=YEAR,
        student_change_percentage=15,
    )

    baseline = build_from_financial_period(db, YEAR)
    computation = calculate(baseline, ScenarioInputCreate())
    assert result.baseline.total_revenue_usd == computation.baseline_revenue
    assert result.baseline.net_balance_usd == computation.baseline_balance
    assert result.risks, "Kapasite açığı varken risk listesi boş dönmemeli."


def test_salary_scenario_two_percent_raise(db) -> None:
    """%2 zam personel giderini tam %2 artırmalı; kadro sayısı değişmemeli."""
    result = call(db, "run_staff_salary_scenario", academic_year=YEAR, salary_change_percentage=2)

    previous = result.previous_annual_staff_cost_usd
    new = result.new_annual_staff_cost_usd
    assert previous and new
    assert new == (previous * Decimal("1.02")).quantize(Decimal("0.01"))
    assert result.cost_change_usd == new - previous
    # Gider artışı bütçe dengesini aynı miktarda düşürmeli.
    assert result.net_balance_change_usd == -result.cost_change_usd
    # Trilyonluk saçma bir rakam çıkmamalı (birim dönüşümü hatası kontrolü).
    assert previous < Decimal("1000000000")


def test_salary_scenario_does_not_change_headcount(db) -> None:
    """Zam kadro sayısını değiştirmez; yalnızca ortalama maaşı değiştirir."""
    result = call(db, "run_staff_salary_scenario", academic_year=YEAR, salary_change_percentage=2)
    assert "kadro sayısı sabit" in result.method_note


# ===========================================================================
# 11-17) Güvenlik ve dayanıklılık
# ===========================================================================


def test_model_cannot_produce_numbers_without_tools(monkeypatch, db) -> None:
    """Model araç çağırmadan kurumsal sayı yazarsa cevabı KULLANICIYA VERİLMEZ.

    Bu davranış canlı testte bulunan bir hatanın sonucudur: model
    "Bilgisayar Mühendisliği'nin öğrenci sayısı nedir?" sorusuna hiç araç
    çağırmadan cevap üretti ve sistem bunu genel bilgi etiketiyle kullanıcıya
    sundu. Artık sunucu tarafında engelleniyor.
    """
    from app.services.assistant import query_policy

    # Model iki turda da araç çağırmıyor.
    script_ollama(
        monkeypatch,
        [
            "Bilgisayar Mühendisliği'nde 9999 öğrenci var.",
            "Yine de 9999 öğrenci olduğunu düşünüyorum.",
        ],
    )

    result = chat_service.answer("Kaç öğrenci var?", db=db)

    assert result["used_tools"] == []
    assert result["data_sources"] == []
    assert result["data_source"] == query_policy.SOURCE_UNAVAILABLE
    assert result["answer"] == query_policy.NO_TOOL_RESULT_MESSAGE
    assert "9999" not in result["answer"], "Uydurma sayı kullanıcıya sızmış."


def test_institutional_question_retries_before_giving_up(monkeypatch, db) -> None:
    """İlk turda araç çağırmayan model ikinci bir şans almalı.

    Soru bilinçli olarak ZORUNLU ARACI OLMAYAN bir kurumsal sorudur; zorunlu
    aracı olan sorularda backend aracı kendisi çalıştırdığı için retry yolu
    hiç devreye girmez.
    """
    from app.services.assistant import query_policy

    question = "Mekânların doluluk oranı ne kadar?"
    assert query_policy.classify(question).required_tool is None

    fake = script_ollama(
        monkeypatch,
        [
            # 1. tur: araç yok
            "Sanırım %500 civarı.",
            # 2. tur: uyarı sonrası aracı çağırıyor
            [{"name": "get_capacity_summary", "arguments": {"academic_year": YEAR}}],
            "2025-2026 · mekân doluluğu %73,93.",
        ],
    )

    result = chat_service.answer(question, db=db)

    assert len(fake.requests) == 3, "Zorunlu ikinci deneme yapılmadı."
    # İkinci istekte modele uyarı gönderilmiş olmalı.
    from app.services.assistant import query_policy

    second = fake.requests[1]["messages"]
    assert any(query_policy.RETRY_INSTRUCTION in m.get("content", "") for m in second)
    assert result["data_source"] == query_policy.SOURCE_INSTITUTIONAL
    assert "73,93" in result["answer"]


def test_general_chat_is_not_forced_to_use_tools(monkeypatch, db) -> None:
    """Genel sohbette araç zorunluluğu uygulanmamalı."""
    from app.services.assistant import query_policy

    fake = script_ollama(monkeypatch, ["Merhaba! Nasıl yardımcı olabilirim?"])

    result = chat_service.answer("Merhaba", db=db)

    assert len(fake.requests) == 1, "Genel sohbette gereksiz ikinci tur yapılmış."
    assert result["data_source"] == query_policy.SOURCE_GENERAL
    assert result["answer"] == "Merhaba! Nasıl yardımcı olabilirim?"


def test_institutional_question_without_database_skips_the_model(monkeypatch, db) -> None:
    """db=None ise kurumsal soruda model HİÇ çağrılmamalı."""
    from app.services.assistant import query_policy

    fake = script_ollama(monkeypatch, ["Bu cevap hiç üretilmemeli."])

    result = chat_service.answer("Toplam öğrenci sayısı kaç?", db=None)

    assert fake.requests == [], "Veri oturumu yokken model çağrılmış."
    assert result["data_source"] == query_policy.SOURCE_UNAVAILABLE
    assert result["answer"] == query_policy.NO_DATABASE_MESSAGE


def test_query_policy_classifies_questions_correctly() -> None:
    """Kurumsal soru tespiti doğru çalışmalı."""
    from app.services.assistant import query_policy

    institutional = [
        "Bilgisayar Mühendisliği kaç öğrencisi var?",
        "Toplam gelir ne kadar?",
        "Laboratuvar kapasitesi yeterli mi?",
        "Mezuniyet oranı nedir?",
        "Maaşlara %2 zam yapılırsa ne olur?",
        "Öğrenci sayısı %15 artarsa bütçe nasıl etkilenir?",
    ]
    general = ["Merhaba", "Teşekkürler", "Sen kimsin?", "İyi günler"]

    for message in institutional:
        assert query_policy.is_institutional_query(message), f"Kurumsal sayılmadı: {message}"
    for message in general:
        assert not query_policy.is_institutional_query(message), (
            f"Genel sohbet kurumsal sayıldı: {message}"
        )


def test_system_prompt_forbids_inventing_numbers() -> None:
    """Sistem yönergesi sayı uydurmayı ve kendi kendine hesabı yasaklamalı."""
    prompt = chat_service.SYSTEM_PROMPT
    assert "YALNIZCA araç sonuçlarından" in prompt
    assert "UYDURMA" in prompt
    assert "Kendi kafandan hesap YAPMA" in prompt
    # Teknik araç adı gösterme yasağı
    assert "get_program_summary" in prompt and "YAZMA" in prompt


def test_unknown_tool_name_is_never_executed(monkeypatch, db) -> None:
    """Kayıt defterinde olmayan ad çalıştırılmamalı."""
    script_ollama(
        monkeypatch,
        [[{"name": "drop_all_tables", "arguments": {}}], "İşlem yapılamadı."],
    )

    result = chat_service.answer("bilinmeyen araç", db=db)

    assert result["used_tools"] == [{"name": "drop_all_tables", "success": False}]
    assert result["data_sources"] == []
    assert result["data_source"] == "general_model_knowledge"


def test_unknown_tool_is_rejected_by_the_registry() -> None:
    """Kayıt defteri bilinmeyen adı doğrudan reddetmeli."""
    with pytest.raises(ToolExecutionError) as exc:
        registry.get("rm_-rf")
    assert exc.value.kind == "unknown_tool"


def test_invalid_tool_arguments_are_rejected(db) -> None:
    """Şemaya uymayan parametre aracı çalıştırmamalı."""
    session = ToolSession(db=db)
    record = session.run("get_program_summary", {"program": 123, "yil": "2025"})

    assert record.success is False
    assert record.error_kind == "invalid_arguments"
    assert "error" in json.loads(record.content)


def test_tools_expose_no_free_form_sql_field() -> None:
    """Hiçbir araç girdisinde serbest SQL / sorgu alanı olmamalı."""
    forbidden = {"sql", "query", "statement", "where", "filter", "raw", "url", "endpoint"}
    for tool in registry.all():
        fields = set(tool.input_model.model_fields)
        assert not (fields & forbidden), f"{tool.name} tehlikeli alan taşıyor: {fields & forbidden}"


def test_tool_inputs_forbid_unknown_fields() -> None:
    """Bilinmeyen alan sessizce yok sayılmamalı."""
    for tool in registry.all():
        assert tool.input_model.model_config.get("extra") == "forbid", (
            f"{tool.name} girdi şeması bilinmeyen alanları yok sayıyor."
        )


def test_duplicate_tool_call_is_not_executed_twice(db) -> None:
    """Aynı araç aynı parametrelerle ikinci kez çalıştırılmamalı."""
    session = ToolSession(db=db)
    first = session.run("get_financial_summary", {"academic_year": YEAR})
    second = session.run("get_financial_summary", {"academic_year": YEAR})
    third = session.run("get_financial_summary", {"academic_year": "2024-2025"})

    assert first.error_kind is None
    assert second.error_kind == "duplicate"
    assert third.error_kind is None, "Farklı parametre tekrar sayılmamalı."
    # Tekrarlanan çağrı kullanıcıya gösterilen listede iki kez görünmemeli.
    assert len(session.used_tools()) == 2


def test_argument_order_does_not_create_a_false_duplicate(db) -> None:
    """Aynı parametreler farklı sırada gelse de tek çağrı sayılmalı."""
    session = ToolSession(db=db)
    session.run("get_program_summary", {"program": "CENG-BSC", "academic_year": YEAR})
    repeat = session.run("get_program_summary", {"academic_year": YEAR, "program": "CENG-BSC"})
    assert repeat.error_kind == "duplicate"


def test_tool_step_limit_is_enforced(monkeypatch, db) -> None:
    """Model sonsuza kadar araç çağıramamalı."""
    # Her turda FARKLI parametreyle çağırıyor ki tekrar filtresine takılmasın.
    years = ["2025-2026", "2024-2025", "2023-2024", "2022-2023", "2021-2022"]
    script: List[Any] = [
        [{"name": "get_financial_summary", "arguments": {"academic_year": y}}] for y in years
    ]
    # Sınırdan sonra model bir tur daha araç çağırmayı denerse bile
    # araç listesi gönderilmediği için düz metin döner.
    script.append("Elimdeki verilerle özetliyorum.")
    fake = script_ollama(monkeypatch, script)

    result = chat_service.answer("beş yılı karşılaştır", db=db)

    assert len(result["used_tools"]) <= chat_service.MAX_TOOL_STEPS
    # Son istekte araç listesi GÖNDERİLMEMELİ.
    assert "tools" not in fake.requests[-1]
    assert result["answer"]


def test_tool_timeout_is_reported_without_numbers(db) -> None:
    """Araç zaman aşımına uğrarsa sonuç yerine hata dönmeli.

    ToolDefinition dondurulmuş (frozen) olduğu için mevcut bir aracın
    handler'ı değiştirilemez — bu bilinçli bir tasarım: kayıt defteri
    çalışma zamanında kurcalanamaz. Bu yüzden test kendi yavaş aracını
    ayrı bir kayıt defterine kaydeder.
    """
    import time

    from app.services.assistant.tool_registry import ToolDefinition, ToolRegistry
    from app.services.assistant.tool_schemas import (
        FinancialSummaryInput,
        FinancialSummaryOutput,
    )

    def slow(_db, _payload):
        time.sleep(5)

    isolated = ToolRegistry()
    isolated.register(
        ToolDefinition(
            name="slow_tool",
            description="Test için yavaş araç.",
            input_model=FinancialSummaryInput,
            output_model=FinancialSummaryOutput,
            handler=slow,
            timeout_seconds=0.2,
            required_permission=None,
            data_source="Mali dönem kayıtları",
        )
    )

    session = ToolSession(db=db, registry=isolated)
    record = session.run("slow_tool", {"academic_year": YEAR})

    assert record.success is False
    assert record.error_kind == "timeout"
    payload = json.loads(record.content)
    assert "zamanında yanıt vermedi" in payload["error"]
    assert not any(ch.isdigit() for ch in payload["error"]), (
        "Zaman aşımı mesajında sayı olmamalı; model onu veri sanabilir."
    )


def test_missing_data_returns_null_not_zero(db) -> None:
    """Veri yoksa sıfır değil None dönmeli ve sebebi yazmalı."""
    result = call(db, "get_capacity_summary", academic_year=YEAR, department="Psikoloji")

    if result.classroom_capacity is None:
        assert result.capacity_status in (None, "veri yok")
        assert result.notes, "Veri yokken sebep açıklanmamış."
    else:
        # Veri varsa da alt kapsamda açık hesaplanmadığı belirtilmeli.
        assert result.capacity_gap is None
        assert any("alt kapsam" in n or "yalnızca üniversite geneli" in n for n in result.notes)


def test_unknown_unit_short_circuits_before_the_model(client: TestClient, monkeypatch) -> None:
    """Sistemde olmayan bir birim adı modele hiç gönderilmemeli.

    Model bu soruyu alakasız bir araçla cevaplayabiliyordu ("toplam gelir
    50,4 milyon USD"); başarılı ama konuyla ilgisiz bir araç çağrısı kapıyı
    geçiyordu. Artık birim adı çözülemezse model çağrılmaz.
    """
    from app.services.assistant import query_policy

    fake = script_ollama(monkeypatch, ["Bu cevap hiç üretilmemeli."])

    response = client.post(
        "/api/assistant/chat", json={"message": "Uzay Mühendisliği programında kaç kişi var?"}
    )

    assert response.status_code == 200
    body = response.json()
    assert fake.requests == [], "Bulunamayan birim için model çağrılmış."
    assert body["used_tools"] == []
    assert body["data_sources"] == []
    assert body["data_source"] == query_policy.SOURCE_UNAVAILABLE
    assert "Uzay Mühendisliği" in body["answer"]
    assert "bulunamadı" in body["answer"]


# ===========================================================================
# 18-20) Sonuçların cevaba ve metadata'ya aktarılması
# ===========================================================================


def test_tool_results_are_sent_back_to_the_model(monkeypatch, db) -> None:
    """Araç sonucu modele `tool` rolüyle geri verilmeli.

    Bu soruda araç backend tarafından çalıştırılır; model yalnızca sonucu
    yorumlar. Sonucun modele gerçekten ulaştığı doğrulanır.
    """
    fake = script_ollama(
        monkeypatch, ["2025-2026 · Bilgisayar Mühendisliği: 370 öğrenci."]
    )

    result = chat_service.answer("Bilgisayar Mühendisliği kaç öğrencisi var?", db=db)

    assert fake.requests, "Model hiç çağrılmamış."
    first_request = fake.requests[0]
    tool_messages = [m for m in first_request["messages"] if m.get("role") == "tool"]
    assert tool_messages, "Araç sonucu modele geri verilmemiş."

    payload = json.loads(tool_messages[0]["content"])
    assert payload["student_count"] == 370
    # Model yorumu araç sonucuyla aynı sayıyı taşımalı.
    assert "370" in result["answer"]
    # Sonuç hazır olduğu için modele yeni araç sunulmamalı.
    assert "tools" not in first_request


def test_metadata_reports_turkish_data_sources(monkeypatch, db) -> None:
    """Kullanılan veri kaynakları Türkçe adlarıyla dönmeli."""
    script_ollama(
        monkeypatch,
        [
            [
                {"name": "get_program_summary",
                 "arguments": {"program": "CENG-BSC", "academic_year": YEAR}},
                {"name": "get_financial_summary", "arguments": {"academic_year": YEAR}},
            ],
            "Özet hazır.",
        ],
    )

    result = chat_service.answer("program ve mali özet", db=db)

    assert result["data_sources"] == ["Öğrenci kayıtları", "Mali dönem kayıtları"]
    assert result["academic_year"] == YEAR
    assert result["scope"]["program"] == "Bilgisayar Mühendisliği Lisans Programı"
    assert result["data_source"] == "institutional_data"
    # Teknik adlar metadata'da var ama arayüz bunları göstermiyor.
    assert {t["name"] for t in result["used_tools"]} == {
        "get_program_summary",
        "get_financial_summary",
    }


def test_chat_endpoint_returns_full_metadata(client: TestClient, monkeypatch) -> None:
    """Uç nokta genişletilmiş metadata'yı döndürmeli."""
    script_ollama(
        monkeypatch,
        [
            [{"name": "get_financial_summary", "arguments": {"academic_year": YEAR}}],
            "2025-2026 mali özeti hazır.",
        ],
    )

    body = client.post("/api/assistant/chat", json={"message": "bütçe nedir"}).json()

    for field in (
        "conversation_id", "answer", "provider", "model", "used_tools",
        "data_sources", "academic_year", "scope", "calculated_at", "data_source",
    ):
        assert field in body, f"Cevapta eksik alan: {field}"
    assert body["data_sources"] == ["Mali dönem kayıtları"]
    assert body["calculated_at"]


def test_thinking_never_reaches_the_answer(monkeypatch, db) -> None:
    """Araç akışında da muhakeme metni cevaba karışmamalı."""
    script_ollama(
        monkeypatch,
        [
            [{"name": "get_financial_summary", "arguments": {"academic_year": YEAR}}],
            "<think>Once butceyi kontrol edeyim, sonra ozetleyeyim.</think>"
            "2025-2026 bütçesi dengede.",
        ],
    )

    result = chat_service.answer("bütçe nasıl?", db=db)

    assert result["answer"] == "2025-2026 bütçesi dengede."
    assert "<think" not in result["answer"]
    assert "kontrol edeyim" not in json.dumps(result, ensure_ascii=False, default=str)


def test_frontend_does_not_display_technical_tool_names() -> None:
    """Arayüz teknik araç adlarını göstermemeli."""
    import pathlib

    source = (
        pathlib.Path(__file__).resolve().parents[2]
        / "frontend" / "assets" / "views-assistant.js"
    ).read_text(encoding="utf-8")

    # Yorum satırları hariç tutulur: açıklama metni "teknik araç adlarını
    # göstermeyin" derken o adı örnek olarak yazabilmeli.
    code_lines = []
    in_block = False
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("/*"):
            in_block = True
        if in_block:
            if "*/" in stripped:
                in_block = False
            continue
        if stripped.startswith("//") or stripped.startswith("*"):
            continue
        code_lines.append(line)
    code = "\n".join(code_lines)
    for tool in registry.names():
        assert tool not in code, f"Arayüzde teknik araç adı görünüyor: {tool}"
    # Kullanıcıya gösterilen başlık.
    assert "Kullanılan veriler" in code
    assert "data_sources" in code


# ===========================================================================
# SENARYO INTENT ROUTER VE DÖNEM POLİTİKASI
#
# Bu bölüm, canlı testte bulunan iki hatanın tekrar etmemesi için var:
#   1. Model maaş senaryosu sorusuna get_financial_summary çağırdı.
#   2. Sistem varsayılan akademik yıl olarak planlama dönemini (2026-2027) seçti.
# ===========================================================================


def test_salary_raise_is_classified_as_salary_scenario() -> None:
    """Maaş zammı ifadesi staff_salary_scenario sınıfına girmeli."""
    from app.services.assistant import query_policy

    for message in (
        "Akademik personel maaşlarına %2 zam yapılırsa bütçe nasıl etkilenir?",
        "Personel ücretleri %5 artarsa ne olur?",
        "Maaş giderleri azaltılırsa bütçe nasıl etkilenir?",
    ):
        intent = query_policy.classify(message)
        assert intent.intent == query_policy.INTENT_STAFF_SALARY, message
        assert intent.required_tool == "run_staff_salary_scenario", message


def test_enrollment_change_is_classified_as_enrollment_scenario() -> None:
    """Öğrenci artışı enrollment_change_scenario sınıfına girmeli."""
    from app.services.assistant import query_policy

    for message in (
        "Bilgisayar Mühendisliği öğrenci sayısı %15 artarsa mali durum nasıl etkilenir?",
        "Kayıt sayısı azalırsa ne olur?",
        "Program kontenjanı değişirse ne olur?",
    ):
        intent = query_policy.classify(message)
        assert intent.intent == query_policy.INTENT_ENROLLMENT_CHANGE, message
        assert intent.required_tool == "run_enrollment_change_scenario", message


def test_current_state_questions_are_classified_correctly() -> None:
    """Mevcut durum soruları current_state_query sınıfına girmeli.

    Bir PROGRAMIN öğrenci göstergesi soruluyorsa araç yine bellidir; genel
    kurum soruları serbest bırakılır.
    """
    from app.services.assistant import query_policy

    for message in (
        "Mevcut gelir ne kadar?",
        "Laboratuvar kapasitesi kaç kişilik?",
        "Akademik personel sayısı nedir?",
        "Mekânların doluluk oranı ne kadar?",
    ):
        intent = query_policy.classify(message)
        assert intent.intent == query_policy.INTENT_CURRENT_STATE, message
        assert intent.required_tool is None, message
        assert intent.institutional is True, message

    program_question = "Bilgisayar Mühendisliği programının mevcut öğrenci sayısı nedir?"
    intent = query_policy.classify(program_question)
    assert intent.intent == query_policy.INTENT_CURRENT_STATE
    assert intent.required_tool == "get_program_summary"
    # Senaryo aracı ASLA seçilmemeli: mevcut durum soruluyor.
    assert "scenario" not in (intent.required_tool or "")


@pytest.mark.parametrize(
    "message,expected",
    [
        ("maaşlara %2 zam", 2.0),
        ("maaşlara yüzde 5 zam", 5.0),
        ("öğrenci sayısı 15 oranında artarsa", 15.0),
        ("maaşlara yüzde iki zam yapılırsa", 2.0),
        ("öğrenci sayısı %10 azalırsa", -10.0),
    ],
)
def test_percentage_extraction(message: str, expected: float) -> None:
    """Yüzde değeri backend tarafında güvenli biçimde çıkarılmalı."""
    from app.services.assistant import query_policy

    assert query_policy.extract_percentage(message) == expected


def test_default_year_is_current_not_planning(db) -> None:
    """Kullanıcı yıl belirtmezse current dönem seçilmeli."""
    from app.services.assistant import entity_resolver

    year = entity_resolver.default_academic_year(db)
    assert year == YEAR
    types = entity_resolver.academic_year_types(db)
    assert types[year] in ("current", "actual")


def test_planning_period_is_never_the_default(db) -> None:
    """Planlama dönemi varsayılan olarak SEÇİLMEMELİ.

    2026-2027 bir planlama yılıdır; tutarları sıfırdır. Yalnızca "en büyük
    yıl" mantığıyla seçildiğinde asistan "bu dönemde veri bulunamadı" diyor,
    oysa kullanıcı gerçekleşmiş dönemi soruyordu.
    """
    from app.services.assistant import entity_resolver

    types = entity_resolver.academic_year_types(db)
    planning = [year for year, kind in types.items() if kind == "planning"]
    assert planning, "Test anlamsız: veride planlama dönemi yok."

    default = entity_resolver.default_academic_year(db)
    assert default not in planning
    # Yıl verilmeden çağrılan araçlar da planlama dönemine düşmemeli.
    for name in ("get_financial_summary", "get_academic_staff_summary"):
        tool = registry.get(name)
        result = tool.handler(db, tool.input_model())
        assert result.scope.academic_year not in planning, name


def test_explicit_planning_year_is_allowed(db) -> None:
    """Kullanıcı 2026-2027 derse planlama dönemi seçilebilmeli."""
    from app.services.assistant import entity_resolver, query_policy

    intent = query_policy.classify("2026-2027 döneminde maaşlara %2 zam yapılırsa?")
    assert intent.explicit_academic_year == "2026-2027"

    year = entity_resolver.resolve_academic_year(
        db, intent.explicit_academic_year, allow_planning=intent.wants_planning_period
    )
    assert year == "2026-2027"


def test_next_year_phrase_allows_planning_period(db) -> None:
    """Kullanıcı 'gelecek yıl' derse planlama dönemine izin verilmeli."""
    from app.services.assistant import entity_resolver, query_policy

    intent = query_policy.classify("Gelecek yıl öğrenci sayısı %15 artarsa ne olur?")
    assert intent.wants_planning_period is True
    assert entity_resolver.mentions_planning_period("Gelecek yıl ne olur?") is True
    assert entity_resolver.mentions_planning_period("Öğrenci sayısı artarsa?") is False


def test_wrong_tool_is_not_accepted_for_a_salary_scenario(monkeypatch, db) -> None:
    """Maaş senaryosunda get_financial_summary tek başına yeterli olmamalı.

    Model bilinçli olarak yanlış aracı seçse bile backend doğru aracı kendisi
    çalıştırır; cevaptaki araç listesi bunu gösterir.
    """
    script_ollama(monkeypatch, ["2025-2026 personel gideri arttı."])

    result = chat_service.answer(
        "Akademik personel maaşlarına %2 zam yapılırsa bütçe nasıl etkilenir?", db=db
    )

    names = {t["name"] for t in result["used_tools"]}
    assert "run_staff_salary_scenario" in names, (
        f"Zorunlu senaryo aracı çalıştırılmadı. Çağrılanlar: {names}"
    )
    assert result["academic_year"] == YEAR
    assert result["data_source"] == "institutional_data"


def test_enrollment_scenario_tool_is_mandatory(monkeypatch, db) -> None:
    """Öğrenci senaryosunda run_enrollment_change_scenario zorunlu olmalı."""
    script_ollama(monkeypatch, ["Öğrenci sayısı arttı."])

    result = chat_service.answer(
        "Bilgisayar Mühendisliği öğrenci sayısı %15 artarsa mali durum nasıl etkilenir?",
        db=db,
    )

    names = {t["name"] for t in result["used_tools"]}
    assert "run_enrollment_change_scenario" in names, (
        f"Zorunlu senaryo aracı çalıştırılmadı. Çağrılanlar: {names}"
    )
    assert result["academic_year"] == YEAR
    assert result["scope"]["program"] == "Bilgisayar Mühendisliği Lisans Programı"


def test_final_answer_is_blocked_when_required_tool_fails(monkeypatch, db) -> None:
    """Gerekli araç çalışmazsa modelin metni kullanıcıya gösterilmemeli."""
    from app.services.assistant import query_policy
    from app.services.assistant.tool_registry import ToolExecutionError

    def failing(_db, _payload):
        raise ToolExecutionError("Senaryo motoru kullanılamıyor.", kind="no_data")

    tool = registry.get("run_staff_salary_scenario")
    monkeypatch.setitem(registry._tools, "run_staff_salary_scenario", replace(tool, handler=failing))
    script_ollama(monkeypatch, ["Bütçe yaklaşık 6 milyon USD artar."])

    result = chat_service.answer(
        "Akademik personel maaşlarına %2 zam yapılırsa bütçe nasıl etkilenir?", db=db
    )

    assert result["data_source"] == query_policy.SOURCE_UNAVAILABLE
    assert result["answer"] == query_policy.NO_TOOL_RESULT_MESSAGE
    assert "6 milyon" not in result["answer"]


def test_forced_tool_arguments_come_from_the_message(db) -> None:
    """Araç parametreleri metinden çıkarılmalı, modelden değil."""
    from app.services.assistant import query_policy
    from app.services.assistant.chat_service import _build_forced_arguments

    intent = query_policy.classify(
        "Bilgisayar Mühendisliği öğrenci sayısı %15 artarsa ne olur?"
    )
    arguments = _build_forced_arguments(db, intent, intent_message())

    assert arguments == {
        "academic_year": YEAR,
        "program": "CENG-BSC",
        "student_change_percentage": 15.0,
    }


def intent_message() -> str:
    return "Bilgisayar Mühendisliği öğrenci sayısı %15 artarsa ne olur?"
