"""Tek çağrıda çok programlı / çok metrikli sorgu ve çok serili grafik.

NE EKLENDİ
----------
Bir kullanıcı sorusu "Bilgisayar ve Elektrik-Elektronik Mühendisliğinin
2021-2026 kontenjan ve yerleşen sayıları" gibi birden çok bölümü,
metriği ve yılı birlikte istediğinde model bunları TEK
`query_canonical_data` çağrısında toplayabiliyor. Veri bütçesi tur
başına iki çağrı olduğu için bu, üç ayrı sorgu gerektiren bir soruyu
bütçeye sığdırır.

NE EKLENMEDİ
------------
Zorunluluk yok. Model isterse yine tek programlı, tek metrikli sorgular
yapabilir; alanlar boş bırakıldığında davranış eskisiyle birebir aynıdır.
Veri yetmediğinde grafik üretilemez ve mevcut nazik geri dönüş korunur —
bu bir başarısızlık sayılmaz.

GERÇEK GEMINI İSTEĞİ YAPILMAZ; araç işlevleri doğrudan çağrılır.
"""

from __future__ import annotations

import pytest

from app.services.assistant import chat_service  # noqa: F401  (araç kaydı)
from app.services.assistant.tool_runner import ToolSession

PROGRAMLAR = ["Bilgisayar Mühendisliği", "Elektrik-Elektronik Mühendisliği"]
YILLAR = ["2021-2022", "2023-2024", "2025-2026"]
TEST_UNI = "TEST BİLEŞİK SORGU ÜNİVERSİTESİ"
KAYNAK = "yok_atlas_benchmark_metrics"


def _sorgu(oturum: ToolSession, metrikler):
    return oturum.run("query_canonical_data", {
        "source": KAYNAK,
        "fields": ["academic_year", "program_name", "metric", "value"],
        "filters": {"university_name": TEST_UNI},
        "filters_any": {"program_name": PROGRAMLAR, "metric": metrikler},
        "filters_range": {"academic_year": ["2021-2022", "2026-2027"]},
        "limit": 200,
    })


@pytest.fixture
def oturum(db_session):
    """Bu testin verisini kendisi kurar.

    `yok_atlas_benchmark_metrics` test veritabanında boştur; testin
    üretim verisinin içeriğine bağlanması onu kırılgan yapardı (bir
    bölümün adı değişince test kırılır, oysa ölçtüğü şey SORGU
    YETENEĞİ). Burada iki bölüm × iki metrik × üç yıl = 12 satırlık
    küçük ve deterministik bir küme yazılır; beklenen seri sayıları
    bu kümeden aritmetikle çıkar.
    """
    from datetime import datetime

    from app.models.yok_atlas_metric import YokAtlasBenchmarkMetric
    from app.services.program_equivalence import canonical_program_key

    db_session.query(YokAtlasBenchmarkMetric).filter(
        YokAtlasBenchmarkMetric.university_name == TEST_UNI).delete()
    for kod, program in enumerate(PROGRAMLAR):
        for metrik, taban in (("quota", 100), ("placed", 90),
                              ("base_score", 450)):
            for i, yil in enumerate(YILLAR):
                db_session.add(YokAtlasBenchmarkMetric(
                    university_name=TEST_UNI,
                    faculty_name="Mühendislik Fakültesi",
                    program_name=program,
                    canonical_program_key=canonical_program_key(program),
                    city="ANKARA",
                    source_year=int(yil[:4]),
                    academic_year=yil,
                    metric=metrik,
                    value=taban + i,
                    unit="count",
                    source_dataset="test",
                    source_file="test",
                    # Benzersizlik anahtarı (source_file, source_program_code,
                    # source_year, metric) olduğu için program başına ayrı kod
                    # gerekiyor; aksi halde iki bölüm aynı satıra çakışır.
                    source_program_code=f"T{kod}",
                    source_row_identity=f"{program}|{metrik}|{yil}",
                    derived=False,
                    methodology="test fixture",
                    created_at=datetime.utcnow()))
    db_session.flush()
    return ToolSession(db_session)


def test_iki_program_tek_metrik_tek_cagri(oturum):
    """1) İki bölüm + base_score tek çağrıda gelir."""
    kayit = _sorgu(oturum, ["base_score"])
    assert kayit.success
    satirlar = kayit.output.model_dump()["rows"]
    assert {s["program_name"] for s in satirlar} == set(PROGRAMLAR)
    assert {s["metric"] for s in satirlar} == {"base_score"}


def test_iki_program_iki_metrik_tek_cagri(oturum):
    """2) İki bölüm × quota+placed tek çağrıda gelir."""
    kayit = _sorgu(oturum, ["quota", "placed"])
    assert kayit.success
    satirlar = kayit.output.model_dump()["rows"]
    seriler = {(s["program_name"], s["metric"]) for s in satirlar}
    assert len(seriler) == 4          # 2 program × 2 metrik
    assert len({s["academic_year"] for s in satirlar}) == len(YILLAR)


def test_yil_araligi_tek_kosulda_calisir(oturum):
    """3) Aralık: yılları tek tek saymaya gerek yok."""
    kayit = _sorgu(oturum, ["quota"])
    yillar = {s["academic_year"] for s in kayit.output.model_dump()["rows"]}
    assert yillar
    assert all("2021-2022" <= y <= "2026-2027" for y in yillar)


def test_bilesik_seri_ile_cok_serili_grafik(oturum):
    """4) Aynı sonuçtan 4 ayrı seri çizilir — yeni DB sorgusu yok."""
    _sorgu(oturum, ["quota", "placed"])
    onceki = len(oturum.records)

    grafik = oturum.run("render_chart", {
        "source_tool": "query_canonical_data",
        "x_field": "academic_year", "y_field": "value",
        "series_fields": ["program_name", "metric"],
        "chart_type": "line", "title": "Kontenjan ve yerleşen"})
    assert grafik.success
    cikti = grafik.output.model_dump()
    assert cikti["series_count"] == 4
    # Grafik yalnızca kendi kaydını ekledi; yeni veri çağrısı yapmadı.
    assert len(oturum.records) == onceki + 1


def test_tek_seri_alani_davranisi_degismedi(oturum):
    """`series_fields` verilmezse eski davranış birebir korunur."""
    _sorgu(oturum, ["quota", "placed"])
    grafik = oturum.run("render_chart", {
        "source_tool": "query_canonical_data",
        "x_field": "academic_year", "y_field": "value",
        "series_field": "program_name",
        "chart_type": "line", "title": "Eski yol"})
    assert grafik.success
    assert grafik.output.model_dump()["series_count"] == 2


def test_veri_yoksa_nazik_geri_donus_korunur(oturum):
    """5) Grafik için veri yoksa çökme değil, açıklayıcı sonuç döner."""
    grafik = oturum.run("render_chart", {
        "source_tool": "query_canonical_data",
        "x_field": "academic_year", "y_field": "value", "title": "Veri yok"})
    assert not grafik.success            # model bunu okuyup açıklar
    assert "query_canonical_data" in grafik.content
    assert grafik.error_kind             # yapısal hata, istisna değil


def test_gecersiz_seri_alani_eski_yola_duser(oturum):
    """Var olmayan `series_fields` grafiği bozmaz."""
    _sorgu(oturum, ["quota"])
    grafik = oturum.run("render_chart", {
        "source_tool": "query_canonical_data",
        "x_field": "academic_year", "y_field": "value",
        "series_fields": ["olmayan_alan"], "title": "Geçersiz alan"})
    assert grafik.success
    assert grafik.output.model_dump()["series_count"] >= 1


def test_araliğa_iki_deger_verilmezse_anlasilir_hata(oturum):
    """Yanlış kullanım sessizce yanlış sonuç üretmez."""
    kayit = oturum.run("query_canonical_data", {
        "source": KAYNAK, "fields": ["academic_year", "value"],
        "filters": {"university_name": TEST_UNI},
        "filters_range": {"academic_year": ["2021-2022"]}, "limit": 10})
    assert not kayit.success
    assert kayit.error_kind == "invalid_arguments"


def test_butceler_degismedi():
    """Bu yetenek bütçeleri gevşetmez."""
    assert chat_service.MAX_LLM_ROUNDS_PER_USER_MESSAGE == 3
    assert chat_service.MAX_DATA_TOOL_CALLS == 2
    assert chat_service.GEMINI_ROUND_TIMEOUT_SECONDS >= 40.0
    assert chat_service.MAX_USER_TURN_SECONDS >= 90.0
