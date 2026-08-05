"""İSTEĞE BAĞLI — gerçek Ollama ve gerçek veriyle çalışan canlı testler.

Varsayılan olarak ATLANIR. Çalıştırmak için:

    $env:ASSISTANT_LIVE_TEST="1"
    & ".\\.venv\\Scripts\\python.exe" -m pytest `
      ".\\integration\\backend\\tests\\test_assistant_ollama_live.py" -v -s

Ön koşul yalnızca Ollama'dır:

    ollama serve
    ollama pull qwen3.5:9b

`run_project.ps1` çalıştırılmış olması GEREKMEZ. Bu dosya kendi geçici
veritabanını oluşturur ve demo verisini kendisi yükler.

VERİTABANI — NEDEN AYRI
-----------------------
Önceki sürüm `app.database.SessionLocal` kullanıyordu. O oturum, çalışma
dizinine göre çözülen bir SQLite dosyasına bağlanıyordu; pytest depo kökünden
çalıştırıldığında bu dosya BOŞTU ve testler "Sistemde tanımlı akademik yıl
yok" hatasıyla düşüyordu. Artık:

* Mutlak yollu, geçici bir SQLite dosyası oluşturulur.
* Demo verisi AYRI BİR SÜREÇTE, gerçek `seed_all_demo_data.py` ile yüklenir.
  Ayrı süreç, testin kendi motorunu ve uygulamanın global motorunu birbirine
  karıştırmayı imkânsız kılar.
* Testler bu dosyaya bağlı KENDİ oturum fabrikasını kullanır.
* Üretim/geliştirme veritabanına hiç dokunulmaz.
* Oturum sonunda geçici dizin silinir.
"""

import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Iterator, Set

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.services.assistant import chat_service, entity_resolver, query_policy
from app.services.assistant.ollama_provider import OllamaProvider
from app.services.assistant.tool_registry import registry

# Ortam değişkeni verilmediyse dosyadaki her test atlanır.
pytestmark = pytest.mark.skipif(
    os.getenv("ASSISTANT_LIVE_TEST") != "1",
    reason="Gerçek Ollama testi. Çalıştırmak için: ASSISTANT_LIVE_TEST=1",
)

YEAR = "2025-2026"
PROGRAM = "Bilgisayar Mühendisliği"

# Model diskten yüklenirken uzun sürebilir. Uygulamanın kendi sınırı
# config'te 120 saniye kalır; canlı test bunu yükseltir.
LIVE_TIMEOUT_SECONDS = os.getenv("ASSISTANT_LIVE_TIMEOUT_SECONDS", "300")

_BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[1]


# ===========================================================================
# Geçici, seed edilmiş test veritabanı
# ===========================================================================


PRODUCTION_DB = _BACKEND_ROOT / "university_management.db"


@pytest.fixture(scope="session")
def production_database_fingerprint() -> str:
    """Oturum BAŞINDA üretim veritabanının parmak izini alır.

    Testler bittiğinde bu değer değişmemiş olmalı. Aynı fonksiyon içinde
    ölçüp karşılaştırmak hiçbir şey kanıtlamaz.
    """
    if not PRODUCTION_DB.exists():
        return "yok"
    stat = PRODUCTION_DB.stat()
    return f"{stat.st_size}:{stat.st_mtime_ns}"


@pytest.fixture(scope="session")
def live_database(production_database_fingerprint: str) -> Iterator[sessionmaker]:
    """Demo verisiyle dolu, izole ve geçici bir veritabanı üretir.

    Seed işlemi bir kez, oturum başında çalışır.
    """
    os.environ.setdefault("ASSISTANT_LIVE_TIMEOUT_SECONDS", LIVE_TIMEOUT_SECONDS)

    temp_dir = tempfile.mkdtemp(prefix="assistant_live_")
    db_path = pathlib.Path(temp_dir) / "live_assistant.db"
    # Mutlak yol: çalışma dizini ne olursa olsun aynı dosyaya bağlanılır.
    database_url = f"sqlite:///{db_path.as_posix()}"

    print(f"\n[canlı test] Geçici veritabanı: {db_path}")
    print("[canlı test] Demo verisi yükleniyor (bu işlem birkaç saniye sürer)…")

    environment = dict(os.environ)
    environment["DATABASE_URL"] = database_url
    # Seed betiği kendi süreçinde çalışır; uygulamanın global motoru
    # etkilenmez ve üretim veritabanına dokunulmaz.
    completed = subprocess.run(
        [sys.executable, "seed_all_demo_data.py"],
        cwd=str(_BACKEND_ROOT),
        env=environment,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        shutil.rmtree(temp_dir, ignore_errors=True)
        pytest.fail(
            "Demo verisi yüklenemedi.\n"
            f"stdout:\n{completed.stdout[-2000:]}\n"
            f"stderr:\n{completed.stderr[-2000:]}"
        )

    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    try:
        yield factory
    finally:
        engine.dispose()
        shutil.rmtree(temp_dir, ignore_errors=True)
        print(f"[canlı test] Geçici veritabanı silindi: {db_path}")


@pytest.fixture(scope="session", autouse=True)
def seeded_data_is_complete(live_database: sessionmaker) -> None:
    """Seed sonrası verinin gerçekten yüklendiğini doğrular.

    Bu kontrol olmadan, boş bir veritabanıyla çalışan testler "model yanlış
    cevap verdi" gibi görünen ama aslında veri eksikliğinden kaynaklanan
    hatalar üretiyordu.
    """
    from app.models import (
        AcademicProgram,
        AcademicStaff,
        FinancialPeriod,
        PhysicalFacility,
        Student,
    )

    session: Session = live_database()
    try:
        years = [
            row
            for row in session.execute(select(FinancialPeriod.academic_year)).scalars()
        ]
        assert YEAR in years, f"{YEAR} akademik yılı seed edilmemiş. Bulunan: {years}"

        student_count = len(list(session.execute(select(Student.id)).scalars()))
        assert student_count > 0, "Öğrenci verisi yüklenmemiş."

        program = entity_resolver.resolve(session, "program", PROGRAM)
        assert program.code == "CENG-BSC", f"Program çözümlenemedi: {program}"

        period = session.execute(
            select(FinancialPeriod).where(FinancialPeriod.academic_year == YEAR)
        ).scalars().first()
        assert period is not None, f"{YEAR} mali dönemi yok."

        staff_count = len(
            list(
                session.execute(
                    select(AcademicStaff.id).where(AcademicStaff.academic_year == YEAR)
                ).scalars()
            )
        )
        assert staff_count > 0, f"{YEAR} için akademik personel verisi yok."

        facility_count = len(list(session.execute(select(PhysicalFacility.id)).scalars()))
        assert facility_count > 0, "Fiziksel kapasite verisi yok."

        print(
            f"[canlı test] Veri doğrulandı: {student_count} öğrenci, "
            f"{staff_count} personel ({YEAR}), {facility_count} mekân, "
            f"{len(years)} mali dönem."
        )
    finally:
        session.close()


@pytest.fixture
def db(live_database: sessionmaker) -> Iterator[Session]:
    """Test başına veritabanı oturumu."""
    session = live_database()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def _clean_conversations() -> Iterator[None]:
    chat_service.reset_conversations()
    yield
    chat_service.reset_conversations()


@pytest.fixture(scope="session", autouse=True)
def warmed_up_model(seeded_data_is_complete: None) -> None:
    """Modeli belleğe yükler.

    İlk gerçek soruda model diskten yükleniyor ve 9B'lik bir model için bu
    tek başına dakikalar sürebiliyor; önceki canlı testlerdeki 120 saniyelik
    zaman aşımının başlıca sebebi buydu. Isınma oturum başında bir kez
    yapılır ve `keep_alive` sayesinde model bellekte kalır.
    """
    provider = OllamaProvider()
    health = provider.health()
    if not health.ready:
        pytest.skip(f"Ollama hazır değil: {health.message}")

    print(f"[canlı test] Model ısıtılıyor ({provider.model}, keep_alive={provider.keep_alive})…")
    if provider.warm_up():
        print("[canlı test] Model bellekte.")
    else:
        print("[canlı test] Isıtma başarısız oldu; testler yine de denenecek.")


# ===========================================================================
# Yardımcılar
# ===========================================================================


# Bir sayının ondalık kısmı: sondaki nokta/virgül + en fazla 2 rakam.
_DECIMAL_TAIL = re.compile(r"[.,]\d{1,2}$")


def numbers_in(text: str) -> Set[int]:
    """Metindeki sayıların TAM SAYI kısmını ayrıştırır.

    Hem Türkçe (6.242.400,00) hem makine biçimi (6242400.00) desteklenir.
    Ondalık ayracı önce atılır; bütün ayraçları körlemesine silmek
    "6120000.00" değerini 612000000'a çeviriyor ve doğru cevabı yanlış
    gösteriyordu.
    """
    found: Set[int] = set()
    for raw in re.findall(r"\d[\d.,]*\d|\d", text):
        cleaned = _DECIMAL_TAIL.sub("", raw)
        cleaned = cleaned.replace(".", "").replace(",", "")
        if cleaned.isdigit():
            found.add(int(cleaned))
    return found


def close_to_any(numbers: Set[int], target: int, tolerance: float = 0.02) -> bool:
    """Hedefe yakın bir sayı var mı? Model yuvarlama yapabilir."""
    if target in numbers:
        return True
    margin = max(abs(target) * tolerance, 1)
    return any(abs(n - target) <= margin for n in numbers)


def tool_names(result: dict) -> Set[str]:
    return {t["name"] for t in result["used_tools"]}


# ===========================================================================
# 1) Ollama ulaşılabilir
# ===========================================================================


def test_live_service_is_reachable() -> None:
    """Ollama ayakta ve istenen model kurulu olmalı."""
    health = OllamaProvider().health()

    assert health.service_available, "Ollama'ya ulaşılamadı. `ollama serve` ile başlatın."
    assert health.model_available, (
        f"Model kurulu değil. `ollama pull {OllamaProvider().model}` çalıştırın. "
        f"Kurulu modeller: {list(health.installed_models)}"
    )


def test_live_timeout_is_raised_for_live_tests() -> None:
    """Canlı testte zaman aşımı config değerinden yüksek olmalı."""
    from app.core.config import settings

    provider = OllamaProvider()
    assert provider.timeout_seconds >= settings.OLLAMA_TIMEOUT_SECONDS
    assert provider.timeout_seconds >= 300, (
        "ASSISTANT_LIVE_TIMEOUT_SECONDS uygulanmamış; model yüklenirken test düşebilir."
    )


def test_live_thinking_is_disabled() -> None:
    """Muhakeme üretimi kapalı olmalı; hesabı araçlar yapıyor."""
    provider = OllamaProvider()
    assert provider.think is False
    assert provider.keep_alive, "keep_alive tanımsız; model her istekte yeniden yüklenir."


# ===========================================================================
# 2) Türkçe cevap (genel sohbet, araç gerektirmez)
# ===========================================================================


def test_live_model_answers_in_turkish(db: Session) -> None:
    """Genel sohbette model Türkçe cevap vermeli ve muhakeme sızmamalı."""
    result = chat_service.answer("Merhaba, kendini bir cümleyle tanıt.", db=db)

    answer = result["answer"]
    assert answer.strip(), "Model boş cevap döndürdü."
    assert "<think" not in answer.lower(), "Düşünme metni cevaba karışmış."
    assert any(ch in answer for ch in "çğıöşüÇĞİÖŞÜ"), (
        f"Cevap Türkçe görünmüyor: {answer[:200]}"
    )


def test_live_greeting_is_not_treated_as_institutional() -> None:
    """"Merhaba" kurumsal soru sayılmamalı; araç zorunluluğu uygulanmamalı."""
    assert query_policy.is_institutional_query("Merhaba") is False
    assert query_policy.is_institutional_query("Teşekkürler") is False


# ===========================================================================
# 3) Kurumsal soru + veri oturumu YOK
# ===========================================================================


def test_live_institutional_question_without_database_never_calls_the_model(
    monkeypatch,
) -> None:
    """db=None ise model HİÇ çağrılmamalı ve sayı üretilmemeli.

    Modelden "genel bilgi" cevabı istemek, kullanıcıya kurum verisi gibi
    görünen bir metin üretme riskini boşuna alır. Ayrıca test 120 saniye
    boyunca model beklemez.
    """
    called = {"value": False}

    def explode(*args, **kwargs):
        called["value"] = True
        raise AssertionError("Veri oturumu yokken model çağrıldı.")

    monkeypatch.setattr(OllamaProvider, "chat_with_tools", explode)

    result = chat_service.answer(
        "Bilgisayar Mühendisliği programının mevcut öğrenci sayısı nedir?", db=None
    )

    assert called["value"] is False
    assert result["data_source"] == query_policy.SOURCE_UNAVAILABLE
    assert result["used_tools"] == []
    assert not numbers_in(result["answer"]), (
        f"Veri yokken sayı üretilmiş: {result['answer']}"
    )


# ===========================================================================
# 4) Akış (genel sohbet)
# ===========================================================================


def test_live_streaming_produces_text() -> None:
    """Akışlı üretim gerçek modelde de metin döndürmeli."""
    _, pieces = chat_service.stream_answer("Merhaba de.")
    output = "".join(pieces)

    assert output.strip(), "Akıştan hiç metin gelmedi."
    assert "<think" not in output.lower(), "Akışta düşünme metni sızmış."


# ===========================================================================
# 5) Mevcut öğrenci sayısı
# ===========================================================================


def test_live_current_student_count_comes_from_tools(db: Session) -> None:
    """Soru 1: mevcut öğrenci sayısı — rakam araç çıktısıyla aynı olmalı."""
    from app.services import student_analytics_service as students

    result = chat_service.answer(
        f"{PROGRAM} programının mevcut öğrenci sayısı nedir?", db=db
    )

    program = entity_resolver.resolve(db, "program", PROGRAM)
    expected = int(
        students.build_program_analytics(
            db, academic_program_id=program.id, academic_year=YEAR
        )[0].total_students
    )

    assert result["used_tools"], (
        f"Model araç çağırmadan cevap üretti: {result['answer'][:300]}"
    )
    assert result["data_source"] == query_policy.SOURCE_INSTITUTIONAL
    assert "get_program_summary" in tool_names(result), (
        f"Program özeti aracı çağrılmadı. Çağrılanlar: {tool_names(result)}"
    )
    assert expected in numbers_in(result["answer"]), (
        f"Cevapta gerçek öğrenci sayısı ({expected}) geçmiyor: {result['answer'][:400]}"
    )
    # Mevcut durum soruldu; senaryo motoru çalıştırılmamalı.
    assert not any("scenario" in name for name in tool_names(result)), (
        "Mevcut durum sorusuna senaryo motoru çalıştırılmış."
    )
    assert "Öğrenci kayıtları" in result["data_sources"]


# ===========================================================================
# 6) %2 maaş senaryosu
# ===========================================================================


def test_live_salary_scenario_numbers_match_the_engine(db: Session) -> None:
    """Soru 2: %2 zam — rakamlar senaryo motoruyla aynı olmalı."""
    result = chat_service.answer(
        "Akademik personel maaşlarına %2 zam yapılırsa bütçe nasıl etkilenir?", db=db
    )

    tool = registry.get("run_staff_salary_scenario")
    expected = tool.handler(
        db, tool.input_model(academic_year=YEAR, salary_change_percentage=2)
    )

    assert result["used_tools"], (
        f"Model araç çağırmadan cevap üretti: {result['answer'][:300]}"
    )
    assert result["data_source"] == query_policy.SOURCE_INSTITUTIONAL
    assert "run_staff_salary_scenario" in tool_names(result), (
        f"Maaş senaryosu çağrılmadı. Çağrılanlar: {tool_names(result)}"
    )
    assert "Senaryo motoru" in result["data_sources"]

    numbers = numbers_in(result["answer"])
    expected_change = int(expected.cost_change_usd)
    expected_new = int(expected.new_annual_staff_cost_usd)
    assert close_to_any(numbers, expected_change) or close_to_any(numbers, expected_new), (
        f"Maliyet rakamları ({expected_change} artış / {expected_new} yeni toplam) "
        f"cevapta geçmiyor: {result['answer'][:400]}"
    )


# ===========================================================================
# 7) %15 öğrenci senaryosu (çok araçlı)
# ===========================================================================


def test_live_multi_tool_enrollment_question(db: Session) -> None:
    """Soru 3: %15 artış — senaryo aracı çağrılmalı, sayılar doğrulanmalı."""
    result = chat_service.answer(
        f"{PROGRAM} öğrenci sayısı %15 artarsa mali durum, personel ihtiyacı "
        "ve laboratuvar kapasitesi nasıl etkilenir?",
        db=db,
    )

    tool = registry.get("run_enrollment_change_scenario")
    expected = tool.handler(
        db,
        tool.input_model(
            program=PROGRAM, academic_year=YEAR, student_change_percentage=15
        ),
    )

    assert result["used_tools"], (
        f"Model araç çağırmadan cevap üretti: {result['answer'][:300]}"
    )
    assert result["data_source"] == query_policy.SOURCE_INSTITUTIONAL
    assert result["academic_year"] == YEAR
    assert "run_enrollment_change_scenario" in tool_names(result), (
        f"Senaryo aracı çağrılmadı. Çağrılanlar: {tool_names(result)}"
    )

    numbers = numbers_in(result["answer"])
    projected = expected.scenario.program_student_count
    baseline = expected.baseline.program_student_count
    assert close_to_any(numbers, projected) or close_to_any(numbers, baseline), (
        f"Öğrenci sayısı ({baseline} → {projected}) cevapta geçmiyor: "
        f"{result['answer'][:400]}"
    )
    assert "<think" not in result["answer"].lower()


# ===========================================================================
# 8) Bilinmeyen program
# ===========================================================================


def test_live_unknown_program_is_not_invented(db: Session) -> None:
    """Var olmayan program için sayı uydurulmamalı."""
    result = chat_service.answer("Uzay Mühendisliği programında kaç öğrenci var?", db=db)

    answer = result["answer"].lower()
    assert result["data_source"] != query_policy.SOURCE_GENERAL, (
        "Kurumsal soruya genel bilgi cevabı verilmiş."
    )
    assert any(
        word in answer
        for word in (
            "bulunamadı", "bulamadım", "yok", "mevcut değil", "kayıtlı değil",
            "erişilemedi", "oluşturulmadı", "belirt",
        )
    ), f"Model olmayan program için sayı üretmiş olabilir: {result['answer'][:300]}"


# ===========================================================================
# Zorunlu araç politikası — canlı doğrulama
# ===========================================================================


def test_live_institutional_answer_without_tools_is_blocked(db: Session, monkeypatch) -> None:
    """Model araç çağırmamakta ısrar ederse cevabı kullanıcıya verilmemeli.

    Modelin araçsız metni taklit edilir; iki turda da araç çağrılmazsa
    sistemin kontrollü hata döndürmesi beklenir.
    """
    calls = {"count": 0}

    def never_calls_tools(self, messages, tools=None):
        calls["count"] += 1
        return [], "Bilgisayar Mühendisliği'nde yaklaşık 500 öğrenci var.", ""

    monkeypatch.setattr(OllamaProvider, "chat_with_tools", never_calls_tools)

    result = chat_service.answer(f"{PROGRAM} kaç öğrencisi var?", db=db)

    assert calls["count"] == 2, (
        f"Zorunlu ikinci deneme yapılmadı (model çağrısı: {calls['count']})."
    )
    assert result["data_source"] == query_policy.SOURCE_UNAVAILABLE
    assert result["answer"] == query_policy.NO_TOOL_RESULT_MESSAGE
    assert "500" not in result["answer"], "Modelin uydurduğu sayı kullanıcıya sızmış."


def test_live_general_chat_does_not_force_tools(db: Session, monkeypatch) -> None:
    """Genel sohbette araç zorunluluğu uygulanmamalı."""
    calls = {"count": 0}

    def plain_answer(self, messages, tools=None):
        calls["count"] += 1
        return [], "Merhaba! Size yardımcı olabilirim.", ""

    monkeypatch.setattr(OllamaProvider, "chat_with_tools", plain_answer)

    result = chat_service.answer("Merhaba", db=db)

    assert calls["count"] == 1, "Genel sohbette gereksiz ikinci tur yapılmış."
    assert result["data_source"] == query_policy.SOURCE_GENERAL
    assert result["answer"] == "Merhaba! Size yardımcı olabilirim."


# ===========================================================================
# Veri bütünlüğü — seed edilmiş test DB
# ===========================================================================


def test_live_seeded_database_has_the_expected_year(db: Session) -> None:
    """Seed edilmiş test veritabanında 2025-2026 bulunmalı."""
    years = entity_resolver.available_academic_years(db)
    assert YEAR in years, f"{YEAR} yok. Bulunan yıllar: {years}"


def test_live_tests_do_not_touch_the_production_database(
    production_database_fingerprint: str, db: Session
) -> None:
    """Canlı testler geliştirme/üretim veritabanını değiştirmemeli.

    Parmak izi oturum BAŞINDA, seed çalıştırılmadan önce alınır. Bu testin
    çalıştığı an itibarıyla seed, ısıtma ve bütün sohbet testleri bitmiştir;
    dosya hâlâ aynıysa hiçbiri üretim verisine dokunmamış demektir.
    """
    # Testlerin bağlandığı veritabanı geçici dizinde olmalı.
    bind_url = str(db.get_bind().url)
    assert "assistant_live_" in bind_url, (
        f"Testler geçici veritabanına bağlı değil: {bind_url}"
    )
    assert "university_management.db" not in bind_url

    if production_database_fingerprint == "yok":
        assert not PRODUCTION_DB.exists(), (
            "Canlı testler üretim veritabanını OLUŞTURMUŞ."
        )
        return

    stat = PRODUCTION_DB.stat()
    current = f"{stat.st_size}:{stat.st_mtime_ns}"
    assert current == production_database_fingerprint, (
        "Canlı testler üretim veritabanını değiştirmiş."
    )


def test_live_staffing_numbers_are_consistent(db: Session) -> None:
    """Personel kaydı ile bordro kadrosu artık ayrışmamalı."""
    tool = registry.get("get_academic_staff_summary")
    result = tool.handler(db, tool.input_model(academic_year=YEAR))

    assert result.active_academic_staff_count is not None
    assert result.payroll_academic_positions is not None
    assert result.staffing_data_consistent is True, (
        f"Personel kayıtları ({result.active_academic_staff_count}) ile bordro "
        f"kadrosu ({result.payroll_academic_positions}) hâlâ ayrışıyor."
    )
    assert result.cost_basis, "Maliyetin hangi sayıdan hesaplandığı belirtilmemiş."
