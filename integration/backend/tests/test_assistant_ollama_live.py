"""İSTEĞE BAĞLI — gerçek Ollama ile çalışan entegrasyon testi.

Bu testler varsayılan olarak ATLANIR. Çalıştırmak için Ollama'nın açık ve
modelin kurulu olması gerekir:

    ollama serve
    ollama pull qwen3.5:9b
    ASSISTANT_LIVE_TEST=1 pytest tests/test_assistant_ollama_live.py -v

Neden ayrı dosyada: bu testler yavaştır (model belleğe yüklenir) ve modelin
üreteceği metin her çalıştırmada farklıdır. Sürekli entegrasyonda çalışan
testler deterministik olmalı; o yüzden asıl doğrulamalar taklit istemciyle
`test_assistant_ollama.py` içinde yapılır.
"""

import os

import pytest

from app.core.config import settings
from app.services.assistant import chat_service
from app.services.assistant.ollama_provider import OllamaProvider

# Ortam değişkeni verilmediyse dosyadaki her test atlanır.
pytestmark = pytest.mark.skipif(
    os.getenv("ASSISTANT_LIVE_TEST") != "1",
    reason="Gerçek Ollama testi. Çalıştırmak için: ASSISTANT_LIVE_TEST=1",
)


@pytest.fixture(autouse=True)
def _clean_conversations():
    chat_service.reset_conversations()
    yield
    chat_service.reset_conversations()


def test_live_service_is_reachable() -> None:
    """Ollama gerçekten ayakta ve istenen model kurulu olmalı."""
    health = OllamaProvider().health()

    assert health.service_available, (
        "Ollama'ya ulaşılamadı. `ollama serve` ile başlatın."
    )
    assert health.model_available, (
        f"{settings.OLLAMA_MODEL} kurulu değil. "
        f"`ollama pull {settings.OLLAMA_MODEL}` çalıştırın. "
        f"Kurulu modeller: {list(health.installed_models)}"
    )


def test_live_model_answers_in_turkish() -> None:
    """Model Türkçe cevap vermeli ve düşünme metni sızmamalı."""
    result = chat_service.answer("Kendini bir cümleyle tanıt.")

    answer = result["answer"]
    assert answer.strip(), "Model boş cevap döndürdü."
    assert "<think" not in answer.lower(), "Düşünme metni cevaba karışmış."
    assert result["provider"] == "ollama"
    assert result["model"] == settings.OLLAMA_MODEL
    assert result["used_tools"] == []

    # Türkçe karakterlerden en az biri geçmeli; model İngilizceye kaymamalı.
    assert any(ch in answer for ch in "çğıöşüÇĞİÖŞÜ"), (
        f"Cevap Türkçe görünmüyor: {answer[:200]}"
    )


def test_live_model_does_not_invent_institutional_numbers() -> None:
    """Kurum verisi istendiğinde model sayı uydurmamalı.

    Bu, sistem yönergesinin gerçekten işe yarayıp yaramadığını ölçen tek
    testtir. Model, veriye erişimi olmadığını belirtmeli.
    """
    result = chat_service.answer(
        "Bilgisayar Mühendisliği öğrenci sayısı %15 artarsa ne olur?"
    )
    answer = result["answer"].lower()

    # Cevap, veri erişimi olmadığını bir biçimde belirtmeli.
    disclaimers = ("erişim", "erisim", "veri", "entegrasyon", "hesaplayamam", "bilgim yok")
    assert any(word in answer for word in disclaimers), (
        f"Model veri erişimi olmadığını belirtmedi: {result['answer'][:300]}"
    )


def test_live_streaming_produces_text() -> None:
    """Akışlı üretim gerçek modelde de metin döndürmeli."""
    _, pieces = chat_service.stream_answer("Merhaba de.")
    output = "".join(pieces)

    assert output.strip(), "Akıştan hiç metin gelmedi."
    assert "<think" not in output.lower(), "Akışta düşünme metni sızmış."


# ---------------------------------------------------------------------------
# Araç çağırma — gerçek model, gerçek veritabanı
# ---------------------------------------------------------------------------
#
# Bu üç test, kullanıcının istediği canlı doğrulama sorularını çalıştırır ve
# cevaptaki HER SAYIYI ilgili backend servisinin sonucuyla karşılaştırır.
# Modelin uydurduğu bir rakam bu testlerde yakalanır.


def _live_db():
    from app.database import SessionLocal

    return SessionLocal()


def _digits(text: str) -> set:
    """Metindeki sayıları ayrıştırır (binlik ayraçları temizlenmiş)."""
    import re

    found = set()
    for raw in re.findall(r"\d[\d.,]*", text):
        cleaned = raw.replace(".", "").replace(",", "")
        if cleaned.isdigit():
            found.add(int(cleaned))
    return found


def test_live_current_student_count_comes_from_tools() -> None:
    """Soru 1: mevcut öğrenci sayısı — rakam araç çıktısıyla aynı olmalı."""
    from app.services.assistant import entity_resolver
    from app.services import student_analytics_service as students

    db = _live_db()
    try:
        result = chat_service.answer(
            "Bilgisayar Mühendisliği programının mevcut öğrenci sayısı nedir?", db=db
        )
        program = entity_resolver.resolve(db, "program", "Bilgisayar Mühendisliği")
        expected = int(
            students.build_program_analytics(
                db, academic_program_id=program.id, academic_year="2025-2026"
            )[0].total_students
        )
    finally:
        db.close()

    assert result["used_tools"], "Model araç çağırmadan cevap üretti."
    assert result["data_source"] == "institutional_data"
    assert expected in _digits(result["answer"]), (
        f"Cevapta gerçek öğrenci sayısı ({expected}) geçmiyor: {result['answer'][:400]}"
    )
    # Senaryo sorulmadı; senaryo aracı çağrılmamalı.
    assert not any("scenario" in t["name"] for t in result["used_tools"]), (
        "Mevcut durum sorusuna senaryo motoru çalıştırılmış."
    )


def test_live_salary_scenario_numbers_match_the_engine() -> None:
    """Soru 2: %2 zam — rakamlar senaryo motoruyla aynı olmalı."""
    from app.services.assistant.tool_registry import registry

    db = _live_db()
    try:
        result = chat_service.answer(
            "Akademik personel maaşlarına %2 zam yapılırsa bütçe nasıl etkilenir?", db=db
        )
        tool = registry.get("run_staff_salary_scenario")
        expected = tool.handler(
            db, tool.input_model(academic_year="2025-2026", salary_change_percentage=2)
        )
    finally:
        db.close()

    assert result["used_tools"], "Model araç çağırmadan cevap üretti."
    assert "Senaryo motoru" in result["data_sources"]

    numbers = _digits(result["answer"])
    expected_change = int(expected.cost_change_usd)
    # Model sayıyı yuvarlayabilir; ±%1 tolerans ile en az bir eşleşme aranır.
    assert any(abs(n - expected_change) <= expected_change * 0.01 for n in numbers), (
        f"Maliyet artışı ({expected_change} USD) cevapta geçmiyor: {result['answer'][:400]}"
    )


def test_live_multi_tool_enrollment_question() -> None:
    """Soru 3: %15 artış — birden fazla araç çağrılmalı, sayılar doğrulanmalı."""
    from app.services.assistant.tool_registry import registry

    db = _live_db()
    try:
        result = chat_service.answer(
            "Bilgisayar Mühendisliği öğrenci sayısı %15 artarsa mali durum, "
            "personel ihtiyacı ve laboratuvar kapasitesi nasıl etkilenir?",
            db=db,
        )
        tool = registry.get("run_enrollment_change_scenario")
        expected = tool.handler(
            db,
            tool.input_model(
                program="Bilgisayar Mühendisliği",
                academic_year="2025-2026",
                student_change_percentage=15,
            ),
        )
    finally:
        db.close()

    assert result["used_tools"], "Model araç çağırmadan cevap üretti."
    assert result["data_source"] == "institutional_data"
    assert result["academic_year"] == "2025-2026"

    numbers = _digits(result["answer"])
    projected = expected.scenario.program_student_count
    assert projected in numbers, (
        f"Senaryo sonrası öğrenci sayısı ({projected}) cevapta geçmiyor: "
        f"{result['answer'][:400]}"
    )
    assert "<think" not in result["answer"].lower()


def test_live_unknown_program_is_not_invented() -> None:
    """Var olmayan program için model sayı uydurmamalı."""
    db = _live_db()
    try:
        result = chat_service.answer(
            "Uzay Mühendisliği programında kaç öğrenci var?", db=db
        )
    finally:
        db.close()

    answer = result["answer"].lower()
    assert any(
        word in answer
        for word in ("bulunamadı", "bulamadım", "yok", "mevcut değil", "kayıtlı değil")
    ), f"Model olmayan program için sayı üretmiş olabilir: {result['answer'][:300]}"
