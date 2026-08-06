"""Dinamik sonuç penceresi (`ui_spec`) testleri.

Bu dosya, kullanıcının istediği 15 kontrolün SUNUCU TARAFINDAKİ kısmını
doğrular. Arayüz tarafındaki kısımlar (düğme, açılır bölüm, XSS, global CSS)
`tests_ui/test_frontend.js` içindedir; her testin başlığında hangi maddeye
karşılık geldiği yazar.

Testlerin ortak ilkesi: pencerede görünen HER SAYI `structured_result`
içindeki bir metrikten gelmelidir. Modelin serbest metni sayı kaynağı
DEĞİLDİR.
"""

import re
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List

import pytest
from pydantic import ValidationError

from app.database import SessionLocal
from app.services.assistant import response_composer, ui_spec_builder
from app.services.assistant.tool_registry import registry
from app.services.assistant.ui_spec import Component, Theme, UiSpec, component_types

YEAR = "2025-2026"

# Modelin uydurabileceği sayılar. Hiçbiri structured_result'ta yoktur; bu
# yüzden hiçbir kartta veya grafikte görünmemelidir.
FABRICATED_MARKDOWN = (
    "### Yönetim değerlendirmesi\n"
    "- Talebin %68,42'i karşılanamıyor.\n"
    "- Toplam maliyet 9.876.543 USD olarak hesaplanmıştır.\n"
    "- Öğrenci sayısı 1.111 kişiye çıkacaktır.\n"
) + ("- Ek satır: kapasite planlaması gözden geçirilmelidir.\n" * 30)


@pytest.fixture(scope="module")
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="module")
def enrollment_output(db):
    tool = registry.get("run_enrollment_change_scenario")
    return tool.handler(
        db,
        tool.input_model(
            program="CENG-BSC", academic_year=YEAR, student_change_percentage=15
        ),
    )


@pytest.fixture(scope="module")
def composed(enrollment_output):
    return response_composer.compose(
        "run_enrollment_change_scenario", enrollment_output
    )


@pytest.fixture(scope="module")
def structured(composed) -> Dict[str, Any]:
    return composed.structured_result


@pytest.fixture(scope="module")
def spec(structured, composed) -> UiSpec:
    built = ui_spec_builder.build_ui_spec(
        structured,
        data_sources=["Öğrenci kayıtları", "Mali dönem kayıtları"],
        calculated_at=datetime(2026, 1, 1, 12, 0, 0),
        interpretation=(
            "### Program değerlendirmesi\n- Kapasite zorlanıyor.\n"
            "### Üniversite düzeyindeki etki\n- Bütçe olumlu."
        ),
        markdown=composed.facts_markdown + "\n" + FABRICATED_MARKDOWN,
    )
    assert built is not None
    return built


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------

NUMBER = re.compile(r"-?\d[\d.]*(?:,\d+)?")


def _numbers(text: str) -> List[str]:
    """Metindeki sayı belirteçlerini noktalama olmadan döndürür."""
    return [
        m.group(0).replace(".", "").replace(",", ".").lstrip("+")
        for m in NUMBER.finditer(text or "")
    ]


def _walk(components: List[Component]) -> List[Component]:
    out: List[Component] = []
    for component in components:
        out.append(component)
        out.extend(_walk(component.components))
    return out


def _all_components(spec: UiSpec) -> List[Component]:
    out: List[Component] = []
    for section in spec.sections:
        out.extend(_walk(section.components))
    return out


def _section(spec: UiSpec, type_: str):
    return next((s for s in spec.sections if s.type == type_), None)


def _default_view_components(spec: UiSpec) -> List[Component]:
    """Varsayılan görünümde okunan bileşenler.

    `expandable_details` kapalı gelir; içindekiler varsayılan görünüme
    dâhil sayılmaz.
    """
    out: List[Component] = []
    for section in spec.sections:
        for component in section.components:
            if component.type == "expandable_details":
                continue
            out.append(component)
    return out


def _card_text(component: Component) -> str:
    return " ".join(
        filter(
            None,
            [
                component.value,
                component.baseline_label,
                component.scenario_label,
                component.delta_label,
            ],
        )
    )


# ---------------------------------------------------------------------------
# 1. Kartlardaki bütün sayılar structured_result ile aynıdır
# ---------------------------------------------------------------------------


def test_every_card_number_comes_from_structured_result(spec, structured) -> None:
    """Her kart sayısı, kartın `source_keys` metriklerinden birine eşit olmalı."""
    index = {m["key"]: m for m in structured["metrics"]}

    checked = 0
    for component in _all_components(spec):
        if component.type not in {"metric_card", "comparison_metric"}:
            continue
        assert component.source_keys, f"Kaynak metrik bildirilmemiş: {component.title}"

        allowed: set = set()
        for key in component.source_keys:
            metric = index.get(key)
            if metric is None:
                continue
            for field in ("baseline", "scenario", "change"):
                value = metric.get(field)
                if value is None:
                    continue
                allowed.add(round(float(value), 2))
                allowed.add(round(abs(float(value)), 2))
                allowed.add(float(int(round(float(value)))))
                allowed.add(float(abs(int(round(float(value))))))

        for token in _numbers(_card_text(component)):
            checked += 1
            assert round(float(token), 2) in allowed, (
                f"'{component.title}' kartındaki {token} sayısı "
                f"structured_result'ta yok. İzinli: {sorted(allowed)}"
            )

    assert checked >= 10, "Yeterli sayıda kart sayısı doğrulanmadı."


def test_every_chart_value_comes_from_structured_result(spec, structured) -> None:
    """Grafik serilerindeki her değer bir metriğe eşit olmalı."""
    index = {m["key"]: m for m in structured["metrics"]}

    charts = [c for c in _all_components(spec) if c.series]
    assert charts, "Hiç grafik üretilmemiş."

    for chart in charts:
        allowed = set()
        for key in chart.source_keys:
            metric = index.get(key)
            if metric is None:
                continue
            for field in ("baseline", "scenario", "change"):
                if metric.get(field) is not None:
                    allowed.add(round(float(metric[field]), 2))
        for series in chart.series:
            for value in series.values:
                if value is None:
                    continue
                assert round(float(value), 2) in allowed, (
                    f"'{chart.title}' grafiğindeki {value} değeri "
                    f"structured_result'ta yok."
                )


# ---------------------------------------------------------------------------
# 2. Serbest metinden sayı ayrıştırılmaz
# ---------------------------------------------------------------------------


def test_no_number_is_parsed_from_free_text(spec) -> None:
    """Modelin uydurduğu sayılar kart, grafik ve risklerde GÖRÜNMEZ.

    Uydurma sayılar yalnızca 'Tam metin rapor' açılır bölümünde, ham metnin
    içinde kalabilir — orası modelin cevabının arşividir, veri kaynağı değil.
    """
    fabricated = ["68,42", "9.876.543", "1.111"]

    for component in _all_components(spec):
        if component.type == "expandable_details":
            continue  # ham metin arşivi
        haystack = " ".join(
            filter(
                None,
                [
                    _card_text(component),
                    component.title,
                    component.subtitle,
                    component.note,
                    " ".join(component.items),
                ],
            )
        )
        for number in fabricated:
            assert number not in haystack, (
                f"Serbest metindeki {number} sayısı '{component.title}' "
                f"bileşenine sızmış."
            )


def test_builder_ignores_markdown_when_structured_result_is_missing() -> None:
    """structured_result yoksa markdown ne kadar dolu olursa olsun pencere üretilmez."""
    assert ui_spec_builder.build_ui_spec(None, markdown=FABRICATED_MARKDOWN) is None
    assert ui_spec_builder.build_ui_spec({}, markdown=FABRICATED_MARKDOWN) is None
    assert (
        ui_spec_builder.build_ui_spec({"metrics": []}, markdown=FABRICATED_MARKDOWN)
        is None
    )


# ---------------------------------------------------------------------------
# 3. Bilinmeyen component type reddedilir
# ---------------------------------------------------------------------------


def test_unknown_component_type_is_rejected() -> None:
    """Katalog dışı bir tür şemadan geçemez; arayüze hiç ulaşmaz."""
    with pytest.raises(ValidationError):
        Component(type="script_block")
    with pytest.raises(ValidationError):
        Component(type="iframe")
    with pytest.raises(ValidationError):
        Component(type="html")

    # Kapalı katalog: 12 bileşen.
    assert len(component_types()) == 12
    assert "script_block" not in component_types()


def test_unknown_component_type_is_rejected_inside_a_ui_spec(spec) -> None:
    """Geçerli bir pencereye sonradan sahte bileşen eklenemez."""
    payload = spec.model_dump(mode="json")
    payload["sections"][0]["components"].append(
        {"type": "script_block", "title": "zararlı"}
    )
    with pytest.raises(ValidationError):
        UiSpec.model_validate(payload)


def test_extra_fields_are_rejected() -> None:
    """Şemada olmayan alan (ör. ham HTML) kabul edilmez."""
    with pytest.raises(ValidationError):
        Component(type="metric_card", html="<script>alert(1)</script>")
    with pytest.raises(ValidationError):
        Component(type="metric_card", on_click="fetch('/admin')")


# ---------------------------------------------------------------------------
# 4. Global CSS üretilemez
# ---------------------------------------------------------------------------


def test_theme_only_accepts_closed_tokens() -> None:
    """Tema serbest CSS taşıyamaz; yalnızca beş belirteçten oluşur."""
    with pytest.raises(ValidationError):
        Theme(css="body{display:none}")
    with pytest.raises(ValidationError):
        Theme(accent="red; background:url(x)")
    with pytest.raises(ValidationError):
        Theme(style_sheet="* { color: red }")

    assert set(Theme().model_dump()) == {
        "accent",
        "density",
        "card_radius",
        "chart_emphasis",
        "risk_emphasis",
    }


def test_ui_spec_carries_no_css_or_markup(spec) -> None:
    """Üretilen pencerede stil bloğu, seçici veya etiket bulunmaz."""
    payload = str(spec.model_dump(mode="json"))
    for forbidden in ("<style", "</style", "body{", "body {", "html{", "* {", "#sidebar"):
        assert forbidden not in payload, f"Pencere tanımında yasak parça: {forbidden}"

    # Tema yalnızca belirteç adları taşır.
    assert spec.theme.accent in {"indigo", "teal", "amber", "slate", "rose"}


def test_view_id_is_selector_safe(spec) -> None:
    """view_id doğrudan CSS seçicisine girdiği için yalnızca güvenli karakterler taşır."""
    assert re.fullmatch(r"aiv-[0-9a-f]{12}", spec.view_id), spec.view_id


# ---------------------------------------------------------------------------
# 5. Program ve üniversite metrikleri ayrı bölümlerde
# ---------------------------------------------------------------------------


def test_program_and_university_metrics_stay_in_separate_sections(spec) -> None:
    """Özet kartları program kapsamındadır; üniversite etkileri ayrı bölümdedir."""
    cards = _section(spec, "metric_grid").components
    assert cards, "Özet kartı üretilmemiş."
    scopes = {c.scope_type for c in cards if c.scope_type}
    assert scopes == {"program"}, f"Özet kartlarında karışık kapsam: {scopes}"
    # Kapsam adı her kartta yazıyor — etiketsiz sayı kalmıyor.
    assert all(c.scope_name for c in cards if c.scope_type)

    detail_titles = [
        c.title for c in _section(spec, "details").components
        if c.type == "expandable_details"
    ]
    assert "Ayrıntılı program sonuçları" in detail_titles
    assert "Üniversite geneli etkiler" in detail_titles

    program_block = next(
        c for c in _section(spec, "details").components
        if c.title == "Ayrıntılı program sonuçları"
    )
    university_block = next(
        c for c in _section(spec, "details").components
        if c.title == "Üniversite geneli etkiler"
    )
    program_rows = " ".join(program_block.components[0].items)
    university_rows = " ".join(university_block.components[0].items)

    assert "Üniversite" not in program_rows
    assert "Üniversite" in university_rows


def test_metric_cards_do_not_mix_scopes_within_one_card(spec) -> None:
    """Tek bir kart iki kapsamdan sayı taşımaz."""
    for component in _all_components(spec):
        if component.type not in {"metric_card", "comparison_metric"}:
            continue
        if component.scope_name:
            assert component.scope_type is not None


# ---------------------------------------------------------------------------
# 6-7-8. Açıklar: mevcut → senaryo ve marjinal etki
# ---------------------------------------------------------------------------


def _incremental_card(spec: UiSpec) -> Component:
    return next(
        c for c in _all_components(spec) if c.title == "Senaryonun eklediği etki"
    )


def test_classroom_gap_is_shown_as_380_to_400_with_plus_20(spec, structured) -> None:
    """Derslik açığı 380 → 400, senaryonun eklediği 20."""
    index = {m["key"]: m for m in structured["metrics"]}
    gap = index["university_classroom_gap"]
    assert gap["baseline"] == 380
    assert gap["scenario"] == 400

    line = next(
        item
        for item in _incremental_card(spec).items
        if item.startswith("Üniversite derslik açığı")
    )
    assert "380" in line and "400" in line
    assert "senaryonun eklediği: +20" in line
    # Toplam açık senaryoya yazılmıyor.
    assert "400 eş zamanlı kişi oluşuyor" not in line


def test_laboratory_gap_is_shown_as_392_to_402_with_plus_10(spec, structured) -> None:
    """Laboratuvar açığı 392 → 402, senaryonun eklediği 10."""
    index = {m["key"]: m for m in structured["metrics"]}
    gap = index["university_laboratory_gap"]
    assert gap["baseline"] == 392
    assert gap["scenario"] == 402

    line = next(
        item
        for item in _incremental_card(spec).items
        if item.startswith("Üniversite laboratuvar açığı")
    )
    assert "392" in line and "402" in line
    assert "senaryonun eklediği: +10" in line


def test_fte_gap_card_shows_zero_fifty_to_three_thirty_and_marginal(spec) -> None:
    """Program FTE açığı 0,50 → 3,30; marjinal +2,80."""
    card = next(
        c for c in _all_components(spec) if c.title == "Program FTE açığı"
    )
    assert card.baseline_label == "0,50 FTE"
    assert card.scenario_label == "3,30 FTE"
    assert card.delta_label == "Senaryonun etkisi: +2,80 FTE"
    assert "senaryodan bağımsız" in (card.note or "").lower()
    assert set(card.source_keys) == {
        "program_baseline_fte_gap",
        "program_scenario_fte_gap",
        "program_marginal_fte",
    }


def test_baseline_risks_are_a_separate_card_from_scenario_effect(spec) -> None:
    """Mevcut riskler ile senaryonun eklediği etki ayrı kartlarda durur."""
    risk_section = _section(spec, "risk_summary")
    assert risk_section is not None
    titles = [c.title for c in risk_section.components]
    assert "Mevcut durumdaki riskler" in titles
    assert "Senaryonun eklediği etki" in titles

    baseline_card = next(
        c for c in risk_section.components if c.title == "Mevcut durumdaki riskler"
    )
    assert baseline_card.subtitle == "Senaryodan bağımsız"
    assert len(baseline_card.items) <= 3


# ---------------------------------------------------------------------------
# 9. Legend yalnızca bir kez
# ---------------------------------------------------------------------------


def test_legend_is_defined_exactly_once_for_the_whole_view(spec) -> None:
    """Mavi/turuncu/gri açıklaması pencerede bir kez tanımlanır."""
    charts = [c for c in _all_components(spec) if c.series]
    with_legend = [c for c in charts if c.legend]
    assert len(with_legend) == 1, (
        "Legend birden fazla grafikte tanımlanmış: "
        + ", ".join(c.title or "?" for c in with_legend)
    )

    legend = with_legend[0].legend
    roles = [entry["role"] for entry in legend]
    assert roles == sorted(set(roles), key=roles.index), "Legend rolleri tekrarlıyor."
    assert {"baseline", "scenario"} <= set(roles)
    labels = [entry["label"] for entry in legend]
    assert "Mevcut durum" in labels and "Senaryo sonucu" in labels


def test_every_chart_series_role_is_explained_by_the_legend(spec) -> None:
    """Grafikte kullanılan her rol legend'de açıklanmış olmalı."""
    charts = [c for c in _all_components(spec) if c.series]
    explained = {entry["role"] for c in charts for entry in c.legend}
    used = {series.role for c in charts for series in c.series}
    assert used <= explained, f"Açıklanmayan seri rolü: {used - explained}"


# ---------------------------------------------------------------------------
# 10. Uzun markdown varsayılan görünümde yok
# ---------------------------------------------------------------------------


def test_long_markdown_is_not_part_of_the_default_view(spec, composed) -> None:
    """40+ satırlık rapor yalnızca kapalı açılır bölümde durur."""
    visible = _default_view_components(spec)
    for component in visible:
        assert component.markdown is None, (
            f"'{component.title}' bileşeni varsayılan görünümde ham markdown taşıyor."
        )

    archive = next(
        c for c in _all_components(spec) if c.title == "Tam metin rapor"
    )
    assert archive.type == "expandable_details"
    assert archive.open is False, "Tam metin rapor varsayılan olarak açık geliyor."
    assert composed.facts_markdown[:60] in (archive.markdown or "")


def test_default_view_respects_the_information_hierarchy(spec) -> None:
    """En fazla 5 kart, 3 grafik, 3 risk maddesi."""
    assert len(_section(spec, "metric_grid").components) <= 5
    charts = _section(spec, "chart_grid")
    assert charts is not None and len(charts.components) <= 3
    for card in _section(spec, "risk_summary").components:
        assert len(card.items) <= 3 or card.title == "Senaryonun eklediği etki"


def test_details_section_components_are_collapsed(spec) -> None:
    """Ayrıntı bölümündeki açılır kutular kapalı gelir."""
    for component in _section(spec, "details").components:
        if component.type == "expandable_details":
            assert component.open is False


# ---------------------------------------------------------------------------
# 13. Finansal maliyet hariç uyarısı
# ---------------------------------------------------------------------------


def test_cost_exclusion_warning_is_visible_by_default(spec) -> None:
    """Maliyet hariç uyarısı açılır bölümün İÇİNDE saklanmaz."""
    assumptions = next(
        c for c in _default_view_components(spec) if c.type == "assumptions_panel"
    )
    assert ui_spec_builder.COST_EXCLUSION_WARNING in assumptions.items

    revenue_card = next(
        c for c in _all_components(spec) if c.title == "Ek gelir etkisi"
    )
    assert "maliyet" in (revenue_card.note or "").lower()


def test_data_source_panel_uses_turkish_names(spec) -> None:
    """Kullanılan veriler paneli teknik araç adı göstermez."""
    panel = next(
        c for c in _default_view_components(spec) if c.type == "data_source_panel"
    )
    assert panel.items == ["Öğrenci kayıtları", "Mali dönem kayıtları"]
    for item in panel.items:
        assert "get_" not in item and "run_" not in item


# ---------------------------------------------------------------------------
# 14. Zararlı içerik metin olarak kalır
# ---------------------------------------------------------------------------


def test_malicious_interpretation_stays_plain_text(structured, composed) -> None:
    """Modelin yorumu HTML/CSS taşısa bile şema onu metin alanında tutar.

    Kaçırma (escaping) arayüzde yapılır; burada doğrulanan şey, zararlı
    içeriğin ASLA bir yapı alanına (tür, tema, seçici) dönüşemediğidir.
    """
    poisoned = (
        "<script>fetch('/api/users')</script>"
        "<style>body{display:none}</style>"
        "### Program değerlendirmesi\n- normal metin"
    )
    built = ui_spec_builder.build_ui_spec(
        structured,
        data_sources=["Öğrenci kayıtları"],
        calculated_at=datetime(2026, 1, 1),
        interpretation=poisoned,
        markdown=composed.facts_markdown,
    )
    assert built is not None

    box = next(
        c for c in _all_components(built) if c.type == "information_box"
    )
    # İçerik body alanında METİN olarak duruyor.
    assert "<script>" in (box.body or "")
    # Ama yapıyı hiç etkilememiş.
    assert box.type == "information_box"
    assert built.theme.accent == "indigo"
    assert re.fullmatch(r"aiv-[0-9a-f]{12}", built.view_id)
    for component in _all_components(built):
        assert component.type in component_types()


# ---------------------------------------------------------------------------
# API sözleşmesi
# ---------------------------------------------------------------------------


def test_chat_response_carries_ui_spec(db, monkeypatch) -> None:
    """`/assistant/chat` cevabı ui_spec alanını taşır ve şemaya uyar."""
    from tests_integration.test_assistant_tools import script_ollama
    from app.services.assistant import chat_service

    script_ollama(
        monkeypatch,
        [
            "### Program değerlendirmesi\n- Kapasite zorlanıyor.\n"
            "### Üniversite düzeyindeki etki\n- Bütçe olumlu."
        ],
    )
    chat_service.reset_conversations()
    result = chat_service.answer(
        "Bilgisayar Mühendisliği öğrenci sayısı %15 artarsa ne olur?", db=db
    )
    chat_service.reset_conversations()

    assert result["ui_spec"] is not None, "Cevapta dinamik pencere tanımı yok."
    # Geri gelen sözlük şemaya BİREBİR uymalı; uymayan alan sessizce geçmez.
    revalidated = UiSpec.model_validate(result["ui_spec"])
    assert revalidated.view_type == "scenario_dashboard"
    assert revalidated.academic_year == YEAR

    # Aynı sayılar structured_result'ta da var.
    index = {m["key"]: m for m in result["structured_result"]["metrics"]}
    assert index["program_student_count"]["baseline"] == 370
    assert index["program_student_count"]["scenario"] == 426
    card = next(
        c
        for c in _all_components(revalidated)
        if c.title == "Öğrenci sayısı" and c.type == "comparison_metric"
    )
    assert card.baseline_label == "370 öğrenci"
    assert card.scenario_label == "426 öğrenci"


def test_ui_fixture_for_the_frontend_test_is_regenerated(spec, structured) -> None:
    """Arayüz testinin kullandığı örnek pencereyi GERÇEK builder çıktısıyla tazeler.

    Elle yazılmış bir örnek, backend değiştiğinde sessizce eskir ve arayüz
    testi artık üretilmeyen bir yapıyı doğrulamaya devam ederdi. Dosya her
    backend koşusunda yeniden yazılır; böylece `tests_ui/test_frontend.js`
    her zaman bugünün çıktısını çizer.
    """
    import json
    import pathlib

    folder = pathlib.Path(__file__).resolve().parents[2] / "tests_ui" / "fixtures"
    folder.mkdir(parents=True, exist_ok=True)

    def write(name: str, payload) -> None:
        (folder / name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    write("ui_spec_sample.json", spec.model_dump(mode="json"))
    # Arayüz testi "kartlardaki sayılar structured_result ile aynı mı" sorusunu
    # ancak iki dosya da yanındayken sorabilir.
    write("structured_result_sample.json", structured)

    written = json.loads((folder / "ui_spec_sample.json").read_text(encoding="utf-8"))
    # Yazılan dosya şemadan geçmeli — arayüz testi geçersiz veriyle çalışmasın.
    UiSpec.model_validate(written)
    assert written["view_type"] == "scenario_dashboard"


def test_ui_spec_is_absent_for_general_questions(db, monkeypatch) -> None:
    """Yapılandırılmış sonuç yoksa pencere üretilmez; arayüz sohbet balonunda kalır."""
    from tests_integration.test_assistant_tools import script_ollama
    from app.services.assistant import chat_service

    script_ollama(monkeypatch, ["Merhaba, size nasıl yardımcı olabilirim?"])
    chat_service.reset_conversations()
    result = chat_service.answer("Merhaba", db=db)
    chat_service.reset_conversations()

    assert result["structured_result"] is None
    assert result["ui_spec"] is None
