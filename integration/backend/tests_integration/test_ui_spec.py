"""Dinamik analiz paneli (`ui_spec`) testleri — sunucu tarafı.

Arayüz tarafındaki karşılıkları `tests_ui/test_frontend.js` içindedir; her
testin başlığı hangi maddeye karşılık geldiğini söyler.

Testlerin ortak ilkesi: panelde görünen HER SAYI `structured_result`
içindeki bir metrikten gelmelidir. Modelin serbest metni sayı kaynağı
DEĞİLDİR.

Grafik seçimi de test edilir: kural CENG senaryosuna değil, metriğin
ANLAMINA (`semantic_type`) bağlıdır. `test_chart_rules_are_generic_*`
testleri uydurma bir kuruma ait sentetik metriklerle aynı kuralların
işlediğini gösterir.
"""

import re
from datetime import datetime
from typing import Any, Dict, List

import pytest
from pydantic import ValidationError

from app.database import SessionLocal
from app.services.assistant import (
    metric_semantics,
    response_composer,
    ui_planner,
    ui_spec_builder,
)
from app.services.assistant.tool_registry import registry
from app.services.assistant.ui_spec import (
    CHART_TYPES,
    FALLBACK_CHAIN,
    SMALL_MULTIPLE_TYPES,
    Component,
    Theme,
    UiSpec,
    component_types,
)

YEAR = "2025-2026"

# Modelin uydurabileceği sayılar. Hiçbiri structured_result'ta yoktur.
FABRICATED_MARKDOWN = (
    "### Yönetim değerlendirmesi\n"
    "- Talebin %68,42'i karşılanamıyor.\n"
    "- Toplam maliyet 9.876.543 USD olarak hesaplanmıştır.\n"
    "- Öğrenci sayısı 1.111 kişiye çıkacaktır.\n"
) + ("- Ek satır: kapasite planlaması gözden geçirilmelidir.\n" * 30)

FABRICATED_NUMBERS = ["68,42", "9.876.543", "1.111"]


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


def _numbers(text: str) -> List[float]:
    return [
        float(m.group(0).replace(".", "").replace(",", ".").lstrip("+"))
        for m in NUMBER.finditer(text or "")
    ]


def _walk(components: List[Component]) -> List[Component]:
    out: List[Component] = []
    for component in components:
        out.append(component)
        out.extend(_walk(component.components))
    return out


def _all(spec: UiSpec) -> List[Component]:
    out: List[Component] = []
    for section in spec.sections:
        out.extend(_walk(section.components))
    return out


def _section(spec: UiSpec, type_: str):
    return next((s for s in spec.sections if s.type == type_), None)


def _default_view(spec: UiSpec) -> List[Component]:
    """Kullanıcı hiçbir şeye tıklamadan gördüğü bileşenler.

    `expandable_details` kapalı gelir; içindekiler varsayılan görünümün
    parçası DEĞİLDİR.
    """
    out: List[Component] = []
    for section in spec.sections:
        for component in section.components:
            if component.type == "expandable_details":
                continue
            out.extend(_walk([component]))
    return out


def _charts(spec: UiSpec) -> List[Component]:
    return [c for c in _all(spec) if c.type in CHART_TYPES]


def _card_text(c: Component) -> str:
    return " ".join(
        filter(None, [c.value, c.baseline_label, c.scenario_label, c.delta_label])
    )


def _addresses(spec: UiSpec) -> List[str]:
    out: List[str] = []
    for component in _all(spec):
        out.extend(component.source_metric_ids)
        for series in component.series:
            out.extend([i for i in series.source_metric_ids if i])
        for marker in component.markers:
            if marker.source_metric_id:
                out.append(marker.source_metric_id)
    return out


def _resolve(address: str, structured: Dict[str, Any]) -> float:
    """"anahtar.alan" adresini çözer; "a|b" iki kaynağın farkıdır."""
    index = {m["key"]: m for m in structured["metrics"]}

    def one(addr: str) -> float:
        key, field = addr.rsplit(".", 1)
        return float(index[key][field])

    if "|" in address:
        left, right = address.split("|")
        return one(left) - one(right)
    return one(address)


# ===========================================================================
# 1-2. Uzun Markdown ana görünümde YOK, yalnızca accordion içinde
# ===========================================================================


def test_long_markdown_is_absent_from_the_default_view(spec, composed) -> None:
    """40+ satırlık rapor varsayılan görünümde hiç yer almaz."""
    for component in _default_view(spec):
        assert component.markdown is None, (
            f"'{component.title}' varsayılan görünümde ham markdown taşıyor."
        )
        assert component.body is None or len(component.body) < 400, (
            f"'{component.title}' varsayılan görünümde uzun metin taşıyor."
        )


def test_long_report_lives_only_inside_a_closed_accordion(spec, composed) -> None:
    """Tam rapor yalnızca KAPALI bir açılır bölümdedir."""
    accordion = _section(spec, "accordion")
    assert accordion is not None, "Ayrıntı bölümü yok."

    raw = next(c for c in accordion.components if c.title == "Ham asistan cevabı")
    assert raw.type == "expandable_details"
    assert raw.open is False
    assert composed.facts_markdown[:60] in (raw.markdown or "")

    # Bölümün TAMAMI kapalı gelir.
    for component in accordion.components:
        assert component.open is False, f"'{component.title}' açık geliyor."


def test_accordion_carries_every_requested_long_section(spec) -> None:
    """İstenen sekiz uzun bölümün hepsi accordion'dadır."""
    titles = [c.title for c in _section(spec, "accordion").components]
    for expected in (
        "Detaylı yönetim değerlendirmesi",
        "Program kapsamındaki bütün sonuçlar",
        "Üniversite geneli etkiler",
        "Hesaplama yöntemi",
        "Varsayımlar ve hariç tutulan maliyetler",
        "Kullanılan veri kaynakları",
        "Teknik sonuç (structured_result)",
        "Ham asistan cevabı",
    ):
        assert expected in titles, f"Açılır bölüm eksik: {expected}"


# ===========================================================================
# 3. En fazla 5 KPI kartı — ve bilgi hiyerarşisinin geri kalanı
# ===========================================================================


def test_default_view_respects_the_information_hierarchy(spec) -> None:
    """5 KPI, 4 grafik, 3 risk, 4 karar maddesi sınırları."""
    kpis = _section(spec, "metric_grid").components
    assert 0 < len(kpis) <= 5, f"KPI kartı sayısı: {len(kpis)}"
    assert all(c.type == "kpi_card" for c in kpis)

    assert len(_charts(spec)) <= 4, [c.type for c in _charts(spec)]

    risks = _section(spec, "risk_summary")
    assert risks is not None and len(risks.components) <= 3

    decisions = _section(spec, "recommendations").components[0]
    assert len(decisions.items) <= 4
    for item in decisions.items:
        assert len(item) <= 120, f"Karar maddesi iki satırı aşıyor: {item}"


def test_decision_summary_is_one_short_sentence_with_badges(spec) -> None:
    """Üst özet en fazla iki satır ve rozetli."""
    summary = _section(spec, "decision_summary").components[0]
    assert summary.type == "decision_summary"
    assert summary.title and len(summary.title) <= 220, summary.title
    labels = [b.label for b in summary.badges]
    assert YEAR in labels
    assert "Program senaryosu" in labels
    assert any("risk" in label.lower() for label in labels)


# ===========================================================================
# 4-8. Grafik seçimi verinin ANLAMINA göre
# ===========================================================================


def test_no_chart_type_is_repeated_unnecessarily(spec) -> None:
    """Aynı grafik türü art arda gösterilmez."""
    types = [c.type for c in _charts(spec)]
    repeated = [t for t in set(types) if types.count(t) > 1
                and t not in SMALL_MULTIPLE_TYPES]
    assert not repeated, f"Tekrarlanan grafik türü: {repeated}"


def test_student_change_uses_a_dumbbell_or_valid_fallback(spec) -> None:
    """Öğrenci değişimi önce–sonra grafiğiyle gösterilir."""
    chart = next(
        (c for c in _charts(spec) if c.semantic_type == "count_change"), None
    )
    assert chart is not None, "Öğrenci değişimi grafiği üretilmemiş."
    assert chart.type in _accepted("dumbbell_chart")
    assert {s.role for s in chart.series} == {"baseline", "scenario"}
    assert chart.data["baseline"] == 370
    assert chart.data["scenario"] == 426
    assert chart.data["delta"] == 56


def test_fte_comparison_uses_a_bullet_or_valid_fallback(spec) -> None:
    """Kapasite / mevcut ihtiyaç / senaryo ihtiyacı aynı eksende."""
    chart = next(
        (c for c in _charts(spec) if c.semantic_type == "target_comparison"), None
    )
    assert chart is not None, "Kapasite karşılaştırma grafiği üretilmemiş."
    assert chart.type in _accepted("bullet_chart")
    assert chart.data == {"capacity": 18.0, "baseline": 18.5, "scenario": 21.3}
    assert [s.role for s in chart.series] == ["capacity", "baseline", "scenario"]
    assert chart.markers and chart.markers[0].value == 18.0


def test_coverage_uses_gauges_or_valid_fallback(spec) -> None:
    """Derslik ve laboratuvar karşılama oranları gauge ile gösterilir."""
    group = next(
        (c for c in _charts(spec) if c.semantic_type == "capacity_coverage"), None
    )
    assert group is not None, "Kapasite karşılama grafiği üretilmemiş."
    assert group.type in _accepted("gauge_group")

    gauges = group.components
    assert len(gauges) == 2
    assert all(g.type == "radial_gauge" for g in gauges)
    values = {round(g.data["scenario"], 2) for g in gauges}
    assert values == {38.96, 65.87}
    # Merkezdeki büyük değer senaryo oranıdır; mevcut oran da kartta durur.
    for gauge in gauges:
        assert gauge.percent == gauge.data["scenario"]
        assert gauge.data["baseline"] is not None


def test_financial_impact_uses_a_waterfall_or_valid_fallback(spec) -> None:
    """Gelir → operasyonel etki → net bütçe zinciri."""
    chart = next(
        (c for c in _charts(spec) if c.semantic_type == "monetary_change"), None
    )
    assert chart is not None, "Mali etki grafiği üretilmemiş."
    assert chart.type in _accepted("waterfall_chart")
    assert chart.categories == [
        "Ek brüt gelir", "Ek operasyonel etki", "Net bütçe değişimi"
    ]
    series = chart.series[0]
    assert series.kinds == ["increase", "decrease", "total"]
    assert series.values[0] == 329840.0
    assert series.values[2] == 257040.0
    # Ortadaki kalem TÜRETİLMİŞ: net − brüt.
    assert series.derivation == "difference"
    assert "|" in series.source_metric_ids[1]


def _accepted(preferred: str) -> set:
    """Tercih edilen tür ve geçerli fallback zinciri."""
    accepted = {preferred}
    current = preferred
    while current in FALLBACK_CHAIN:
        current = FALLBACK_CHAIN[current]
        accepted.add(current)
    return accepted


# --- kuralların GENELLİĞİ: uydurma bir kuruma ait sentetik metrikler ---


def _metric(key, label, unit, baseline=None, scenario=None, change=None,
            scope_type="program", scope_name="Deneme Programı"):
    return {
        "key": key, "label": label, "unit": unit,
        "scope_type": scope_type, "scope_name": scope_name,
        "baseline": baseline, "scenario": scenario, "change": change,
        "semantic_type": metric_semantics.classify(key, unit, label),
        "formula": None, "note": None,
    }


def test_chart_rules_are_generic_for_an_unrelated_dataset() -> None:
    """Kurallar CENG'e değil, metriğin anlamına bağlıdır.

    Hiç görülmemiş anahtarlarla, hiç görülmemiş bir kurum için aynı grafik
    türleri seçilmeli.
    """
    metrics = [
        _metric("program_trainee_count", "Kursiyer sayısı", "öğrenci", 90, 120, 30),
        _metric("program_instructor_fte", "Eğitmen kapasitesi", "FTE", 6),
        _metric("program_required_instructor_fte", "Gerekli eğitmen", "FTE", 6.4, 8.2, 1.8),
        _metric("program_studio_coverage", "Stüdyo karşılama oranı", "%", 80.0, 61.5),
        _metric("program_grant_effect", "Ek hibe etkisi", "USD", change=125000),
        _metric("university_net_balance", "Net bütçe", "USD", 1000, 1080, 80,
                scope_type="university", scope_name="Üniversite geneli"),
    ]
    charts = ui_planner.plan_charts(metrics)
    by_semantic = {c.semantic_type: c.type for c in charts}

    assert by_semantic.get("count_change") == "dumbbell_chart"
    assert by_semantic.get("target_comparison") == "bullet_chart"
    assert by_semantic.get("capacity_coverage") == "gauge_group"
    assert by_semantic.get("monetary_change") == "waterfall_chart"
    # Hiçbir sayı uydurulmadı: hepsi verilen metriklerden.
    change_chart = next(c for c in charts if c.semantic_type == "count_change")
    assert change_chart.data == {"baseline": 90.0, "scenario": 120.0, "delta": 30.0}


def test_planner_picks_other_chart_families_for_other_semantics() -> None:
    """Sıralama, dağılım ve risk verileri kendi grafiklerini seçer."""
    ranking = [
        dict(_metric(f"faculty_score_{i}", f"Fakülte {i}", "%", 60 + i * 4,
                     scope_type="faculty", scope_name=f"Fakülte {i}"),
             semantic_type="ranking")
        for i in range(4)
    ]
    assert ui_planner.plan_charts(ranking)[0].type == "radar_chart"

    distribution = [
        dict(_metric(f"budget_share_{i}", f"Kalem {i}", "USD", 100 * (i + 1)),
             semantic_type="distribution")
        for i in range(3)
    ]
    assert ui_planner.plan_charts(distribution)[0].type == "treemap"

    risks = [
        dict(_metric(f"risk_{i}", f"Risk {i}", "%", 40 + i * 10, 70 + i * 5),
             semantic_type="risk_score")
        for i in range(3)
    ]
    assert ui_planner.plan_charts(risks)[0].type == "risk_matrix"


def test_planner_never_exceeds_the_chart_budget() -> None:
    """Ne kadar metrik gelirse gelsin ana ekranda dört grafikten fazlası yok."""
    metrics = []
    for i in range(30):
        metrics.append(_metric(f"program_thing_{i}", f"Gösterge {i}", "öğrenci",
                               10 + i, 20 + i, 10))
        metrics.append(_metric(f"program_thing_{i}_coverage", f"Oran {i}", "%",
                               80 - i, 70 - i))
    assert len(ui_planner.plan_charts(metrics)) <= ui_planner.MAX_CHARTS


def test_semantic_classification_is_driven_by_unit_and_key() -> None:
    """Sınıflandırma kuralları — yeni metrikler de doğru sınıflanır."""
    cases = [
        ("anything_revenue", "USD", "monetary_change"),
        ("program_x_coverage", "%", "capacity_coverage"),
        ("program_x_utilization", "%", "utilization"),
        ("program_x_fte_gap", "FTE", "staffing_gap"),
        ("program_required_fte", "FTE", "target_comparison"),
        ("program_x_demand", "koltuk-saat", "capacity_demand"),
        ("program_x_capacity", "istasyon-saat", "target_comparison"),
        ("university_staff_gap", "kişi", "staffing_gap"),
        ("program_student_count", "öğrenci", "count_change"),
        ("university_capacity_status", "durum", "status"),
    ]
    for key, unit, expected in cases:
        assert metric_semantics.classify(key, unit, "") == expected, key


def test_every_structured_metric_carries_a_semantic_type(structured) -> None:
    """Grafik seçimi ancak her metrik anlamını bildirirse çalışır."""
    for metric in structured["metrics"]:
        assert metric.get("semantic_type") in metric_semantics.SEMANTIC_TYPES, metric["key"]


# ===========================================================================
# 9-10. Sayının kaynağı
# ===========================================================================


def test_every_number_in_the_panel_resolves_to_structured_result(spec, structured) -> None:
    """Panelin taşıdığı her adres çözülebilir ve değere eşittir."""
    addresses = _addresses(spec)
    assert len(addresses) >= 15, "Yeterli sayıda kaynak adresi yok."
    for address in addresses:
        _resolve(address, structured)  # çözülemezse KeyError ile düşer


def test_chart_values_equal_their_declared_sources(spec, structured) -> None:
    for chart in _charts(spec) + [c for c in _all(spec) if c.type == "radial_gauge"]:
        for series in chart.series:
            for i, value in enumerate(series.values):
                address = (series.source_metric_ids or [None] * len(series.values))[i]
                if not address or value is None:
                    continue
                expected = _resolve(address, structured)
                assert abs(value - expected) < 0.005, (
                    f"{chart.type} → {address}: {value} ≠ {expected}"
                )


def test_kpi_card_values_equal_their_declared_sources(spec, structured) -> None:
    """KPI kartındaki her sayı kaynağıyla birebir aynı."""
    checked = 0
    for card in _section(spec, "metric_grid").components:
        assert card.source_metric_ids, f"Kaynak bildirilmemiş: {card.title}"
        allowed = {round(_resolve(a, structured), 2) for a in card.source_metric_ids}
        # Kart farkı da gösterebilir; fark iki kaynaktan türetilir.
        if len(card.source_metric_ids) >= 2:
            values = [_resolve(a, structured) for a in card.source_metric_ids[:2]]
            allowed.add(round(values[1] - values[0], 2))
            allowed.add(round(abs(values[1] - values[0]), 2))
        for number in _numbers(_card_text(card)):
            checked += 1
            assert round(number, 2) in allowed or round(-number, 2) in allowed, (
                f"'{card.title}' kartındaki {number} kaynağa bağlanamıyor. "
                f"İzinli: {sorted(allowed)}"
            )
    assert checked >= 10


def test_no_number_is_parsed_from_the_raw_model_text(spec) -> None:
    """Modelin uydurduğu sayılar hiçbir kart, grafik veya riske sızmaz."""
    for component in _default_view(spec):
        haystack = " ".join(
            filter(
                None,
                [
                    _card_text(component), component.title, component.subtitle,
                    component.caption, component.note, " ".join(component.items),
                ],
            )
        )
        for number in FABRICATED_NUMBERS:
            assert number not in haystack, (
                f"Serbest metindeki {number} '{component.title}' bileşenine sızmış."
            )


def test_builder_ignores_markdown_when_structured_result_is_missing() -> None:
    assert ui_spec_builder.build_ui_spec(None, markdown=FABRICATED_MARKDOWN) is None
    assert ui_spec_builder.build_ui_spec({}, markdown=FABRICATED_MARKDOWN) is None
    assert (
        ui_spec_builder.build_ui_spec({"metrics": []}, markdown=FABRICATED_MARKDOWN)
        is None
    )


# ===========================================================================
# 11. Hesaplanmayan maliyetler sıfır DEĞİLDİR
# ===========================================================================


def test_uncalculated_costs_never_appear_as_zero(spec) -> None:
    """Hesaplanmamış maliyet şelaleye sıfır kalem olarak konmaz."""
    waterfall = next(c for c in _charts(spec) if c.type == "waterfall_chart")
    for value in waterfall.series[0].values:
        assert value not in (0, 0.0), "Şelalede sıfır değerli kalem var."
    assert len(waterfall.categories) == 3, "Beklenmeyen kalem eklenmiş."
    assert not any("personel maliyeti" in c.lower() for c in waterfall.categories)
    assert not any("yatırım" in c.lower() for c in waterfall.categories)


def test_uncalculated_costs_are_shown_as_a_visible_warning(spec) -> None:
    """Uyarı ana ekranda, grafiğin yanında ve açılır bölümün DIŞINDA."""
    warning = next(
        c for c in _default_view(spec)
        if c.type == "information_box" and c.id == "cost-warning"
    )
    assert warning.level == "warning"
    assert warning.items == ui_spec_builder.UNCALCULATED_COSTS
    assert ui_spec_builder.COST_EXCLUSION_WARNING in (warning.note or "")

    # Grafiğin kendisi de aynı uyarıyı taşır.
    waterfall = next(c for c in _charts(spec) if c.type == "waterfall_chart")
    assert "HESAPLANMADI" in (waterfall.note or "")


# ===========================================================================
# 12-13. Legend
# ===========================================================================


def test_legend_is_defined_exactly_once_in_the_whole_panel(spec) -> None:
    """Renk açıklaması panelde tek bir yerde durur."""
    with_legend = [c for c in _all(spec) if c.legend]
    assert len(with_legend) == 1, [c.type for c in with_legend]
    assert with_legend[0].type == "legend_panel"

    roles = [entry["role"] for entry in with_legend[0].legend]
    assert roles == list(dict.fromkeys(roles)), "Legend rolleri tekrarlıyor."
    assert {"baseline", "scenario"} <= set(roles)


def test_colour_meaning_is_consistent_across_every_chart(spec) -> None:
    """Bir renk iki grafikte farklı anlam taşıyamaz.

    Renk doğrudan seçilemiyor; yalnızca `role` seçiliyor ve rengi renderer
    sabit sözlükten veriyor. Bu test rollerin anlamlı kullanıldığını
    doğrular: "baseline" hep mevcut değerden, "scenario" hep senaryo
    değerinden beslenir.
    """
    for chart in _charts(spec):
        for series in chart.series:
            for address in series.source_metric_ids:
                if not address or "|" in address:
                    continue
                field = address.rsplit(".", 1)[1]
                if series.role == "baseline":
                    assert field in {"baseline", "change"}, (
                        f"{chart.type}: mavi seri {field} alanından besleniyor."
                    )
                elif series.role == "scenario":
                    assert field in {"scenario", "change"}, (
                        f"{chart.type}: turuncu seri {field} alanından besleniyor."
                    )
                elif series.role == "capacity":
                    assert "capacity" in address or "fte" in address, (
                        f"{chart.type}: gri seri kapasite dışı bir kaynaktan."
                    )


def test_legend_covers_every_role_used_by_the_charts(spec) -> None:
    legend = next(c for c in _all(spec) if c.type == "legend_panel")
    explained = {entry["role"] for entry in legend.legend}
    used = {s.role for c in _charts(spec) for s in c.series
            if s.role in {"baseline", "scenario", "capacity"}}
    assert used <= explained, f"Açıklanmayan rol: {used - explained}"


# ===========================================================================
# 14-15. Güvenlik
# ===========================================================================


def test_unknown_chart_type_is_rejected() -> None:
    """Katalog dışı bir tür şemadan geçemez."""
    for bogus in ("script_block", "iframe", "html", "sankey_chart", "3d_globe"):
        with pytest.raises(ValidationError):
            Component(type=bogus)
    assert "script_block" not in component_types()
    # Katalogda istenen bütün gelişmiş grafikler var.
    for expected in (
        "dumbbell_chart", "slope_chart", "bullet_chart", "radial_gauge",
        "semi_circle_gauge", "waterfall_chart", "forecast_line_chart",
        "stacked_area_chart", "heatmap", "risk_matrix", "treemap",
        "radar_chart", "sparkline", "progress_ring",
        "horizontal_comparison_bar",
    ):
        assert expected in component_types(), expected


def test_unknown_component_type_is_rejected_inside_a_ui_spec(spec) -> None:
    payload = spec.model_dump(mode="json")
    payload["sections"][1]["components"].append(
        {"type": "script_block", "title": "zararlı"}
    )
    with pytest.raises(ValidationError):
        UiSpec.model_validate(payload)


def test_extra_fields_and_free_css_are_rejected() -> None:
    """Ham HTML, JavaScript veya CSS taşıyacak bir alan yok."""
    with pytest.raises(ValidationError):
        Component(type="kpi_card", html="<script>alert(1)</script>")
    with pytest.raises(ValidationError):
        Component(type="kpi_card", on_click="fetch('/admin')")
    with pytest.raises(ValidationError):
        Component(type="kpi_card", style="position:fixed")
    with pytest.raises(ValidationError):
        Theme(css="body{display:none}")
    with pytest.raises(ValidationError):
        Theme(accent="red; background:url(x)")

    assert set(Theme().model_dump()) == {
        "accent", "density", "card_radius", "chart_emphasis", "risk_emphasis"
    }


def test_ui_spec_carries_no_css_or_markup(spec) -> None:
    payload = str(spec.model_dump(mode="json"))
    for forbidden in ("<style", "</style", "body{", "body {", "html{", "* {",
                      "#sidebar", "<script"):
        assert forbidden not in payload, f"Yasak parça: {forbidden}"


def test_view_id_is_selector_safe(spec) -> None:
    assert re.fullmatch(r"aiv-[0-9a-f]{12}", spec.view_id), spec.view_id


def test_malicious_interpretation_stays_plain_text(structured, composed) -> None:
    """Zararlı içerik metin alanında kalır; yapıyı hiç etkilemez."""
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

    block = next(
        c for c in _all(built) if c.title == "Detaylı yönetim değerlendirmesi"
    )
    assert "<script>" in (block.body or "")   # metin olarak duruyor
    assert block.type == "expandable_details"  # yapı değişmedi
    assert block.open is False
    assert built.theme.accent == "indigo"
    for component in _all(built):
        assert component.type in component_types()


# ===========================================================================
# 19. KPI kartlarının birim ve kapsam bilgisi
# ===========================================================================


def test_kpi_cards_carry_unit_and_scope(spec) -> None:
    """Etiketsiz sayı kalmaz: her kartta birim ve kapsam yazar."""
    for card in _section(spec, "metric_grid").components:
        assert card.unit, f"Birim yok: {card.title}"
        assert card.scope_type == "program", f"Kapsam yanlış: {card.title}"
        assert card.scope_name, f"Kapsam adı yok: {card.title}"
        assert card.icon, f"İkon yok: {card.title}"
        assert card.aria_label, f"aria-label yok: {card.title}"
        if card.caption:
            assert len(card.caption) <= 70, f"Açıklama bir satırı aşıyor: {card.title}"


def test_expected_kpi_cards_for_an_enrollment_scenario(spec) -> None:
    """İstenen beş göstergenin değerleri."""
    cards = {c.title: c for c in _section(spec, "metric_grid").components}
    assert set(cards) == {
        "Öğrenci sayısı", "Program FTE açığı", "Ek gelir etkisi",
        "Derslik karşılama oranı", "Laboratuvar karşılama oranı",
    }

    students = cards["Öğrenci sayısı"]
    assert (students.baseline_label, students.scenario_label) == (
        "370 öğrenci", "426 öğrenci"
    )
    assert students.delta_label == "+56 öğrenci"

    fte = cards["Program FTE açığı"]
    assert (fte.baseline_label, fte.scenario_label) == ("0,50 FTE", "3,30 FTE")
    assert fte.delta_label == "Senaryonun etkisi: +2,80 FTE"

    revenue = cards["Ek gelir etkisi"]
    assert revenue.value == "+329.840 USD"
    assert "maliyetleri hariç" in revenue.caption

    classroom = cards["Derslik karşılama oranı"]
    assert (classroom.baseline_label, classroom.scenario_label) == ("%44,86", "%38,96")
    assert classroom.delta_label == "Azalış: -5,90 puan"
    assert classroom.level == "critical"

    lab = cards["Laboratuvar karşılama oranı"]
    assert (lab.baseline_label, lab.scenario_label) == ("%75,84", "%65,87")
    assert lab.delta_label == "Azalış: -9,97 puan"


def test_risk_cards_are_compact_and_levelled(spec) -> None:
    """Üç kompakt risk kartı: ikon, seviye, büyük metrik, tek cümle."""
    cards = _section(spec, "risk_summary").components
    titles = [c.title for c in cards]
    assert titles == ["Akademik kapasite", "Derslik kapasitesi",
                      "Laboratuvar kapasitesi"]

    for card in cards:
        assert card.type == "risk_summary_card"
        assert card.icon and card.level and card.value
        assert card.aria_label, "Ekran okuyucu metni yok."
        assert len(card.caption or "") <= 80, card.caption
        assert not card.items, "Risk kartında uzun paragraf listesi var."

    assert cards[0].level == "critical" and cards[0].value == "+2,80 FTE"
    assert cards[1].level == "critical" and cards[1].value == "+1.008 koltuk-saat"
    assert cards[2].level == "warning" and cards[2].value == "+224 istasyon-saat"


def test_decisions_are_short_and_actionable(spec) -> None:
    items = _section(spec, "recommendations").components[0].items
    assert 0 < len(items) <= 4
    assert any(i.startswith("Akademik kadro:") for i in items)
    assert any(i.startswith("Finans:") for i in items)


# ===========================================================================
# 20. API sözleşmesi ve arayüz örnek dosyaları
# ===========================================================================


def test_chat_response_carries_ui_spec(db, monkeypatch) -> None:
    """`/assistant/chat` cevabı şemaya uyan bir ui_spec taşır."""
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

    assert result["ui_spec"] is not None
    revalidated = UiSpec.model_validate(result["ui_spec"])
    assert revalidated.version == "2.0"
    assert revalidated.view_type == "scenario_dashboard"

    index = {m["key"]: m for m in result["structured_result"]["metrics"]}
    assert index["program_student_count"]["baseline"] == 370
    assert index["program_student_count"]["scenario"] == 426
    card = next(
        c for c in _all(revalidated)
        if c.type == "kpi_card" and c.title == "Öğrenci sayısı"
    )
    assert card.baseline_label == "370 öğrenci"
    assert card.scenario_label == "426 öğrenci"


def test_ui_spec_is_absent_for_general_questions(db, monkeypatch) -> None:
    from tests_integration.test_assistant_tools import script_ollama
    from app.services.assistant import chat_service

    script_ollama(monkeypatch, ["Merhaba, size nasıl yardımcı olabilirim?"])
    chat_service.reset_conversations()
    result = chat_service.answer("Merhaba", db=db)
    chat_service.reset_conversations()

    assert result["structured_result"] is None
    assert result["ui_spec"] is None


def test_ui_fixture_for_the_frontend_test_is_regenerated(spec, structured) -> None:
    """Arayüz testinin örnek dosyalarını GERÇEK builder çıktısıyla tazeler.

    Elle yazılmış bir örnek, backend değiştiğinde sessizce eskir ve arayüz
    testi artık üretilmeyen bir yapıyı doğrulamaya devam ederdi.
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
    write("structured_result_sample.json", structured)

    written = json.loads((folder / "ui_spec_sample.json").read_text(encoding="utf-8"))
    UiSpec.model_validate(written)
    assert written["view_type"] == "scenario_dashboard"
