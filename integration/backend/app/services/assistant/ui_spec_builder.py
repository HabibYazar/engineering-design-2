"""`structured_result` → `ui_spec` deterministik dönüşümü.

BU DOSYA HESAP YAPMAZ ve METİNDEN SAYI AYIKLAMAZ.

Her sayı `structured_result["metrics"]` içindeki bir kayıttan gelir ve
üretilen bileşen `source_keys` alanında hangi metrikten geldiğini söyler.
Testler bu bağı doğrular.

BİLGİ HİYERARŞİSİ
-----------------
Varsayılan görünüm en fazla:
  * 5 özet kartı
  * 3 grafik
  * 3 kritik risk
  * kısa yönetim yorumu

Geri kalan her şey (ayrıntılı program/üniversite metrikleri, yöntem,
kullanılan veriler, varsayımlar, teknik çıktı) kapalı açılır bölümlerde
durur. 40 satırlık markdown varsayılan olarak GÖSTERİLMEZ.
"""

import hashlib
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from app.services.assistant.ui_spec import (
    ChartSeries,
    Component,
    Section,
    Theme,
    UiSpec,
)

logger = logging.getLogger(__name__)

# Grafik serilerinin anlamı. Legend YALNIZCA bir kez, grafik bileşeninin
# kendi `legend` alanında tanımlanır.
LEGEND_BASELINE = {"role": "baseline", "label": "Mevcut durum"}
LEGEND_SCENARIO = {"role": "scenario", "label": "Senaryo sonucu"}
LEGEND_CAPACITY = {"role": "capacity", "label": "Kullanılabilir kapasite"}

COST_EXCLUSION_WARNING = (
    "Finansal sonuçlar gerekli yeni personel ve kapasite yatırımlarının "
    "maliyetini içermemektedir."
)


def _index(structured: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {m["key"]: m for m in structured.get("metrics", [])}


def _num(metric: Optional[Dict[str, Any]], field: str) -> Optional[float]:
    if metric is None:
        return None
    value = metric.get(field)
    return None if value is None else float(value)


def _fmt_count(value: Optional[float], unit: str = "") -> str:
    if value is None:
        return "Veri bulunamadı"
    text = f"{int(round(value)):,}".replace(",", ".")
    return f"{text} {unit}".strip()


def _fmt_decimal(value: Optional[float], unit: str = "") -> str:
    if value is None:
        return "Veri bulunamadı"
    number = Decimal(str(value))
    if number == number.to_integral_value():
        text = f"{number:,.0f}".replace(",", ".")
    else:
        text = f"{number:,.2f}".replace(",", "#").replace(".", ",").replace("#", ".")
    return f"{text} {unit}".strip()


def _fmt_usd(value: Optional[float]) -> str:
    if value is None:
        return "Veri bulunamadı"
    number = Decimal(str(value))
    if abs(number) < 1000 and number != number.to_integral_value():
        text = f"{number:,.2f}".replace(",", "#").replace(".", ",").replace("#", ".")
    else:
        text = f"{number:,.0f}".replace(",", ".")
    return f"{text} USD"


def _fmt_percent(value: Optional[float]) -> str:
    if value is None:
        return "Veri bulunamadı"
    text = f"{Decimal(str(value)):.2f}".rstrip("0").rstrip(".").replace(".", ",")
    return f"%{text}"


def _signed(value: Optional[float], formatter) -> str:
    if value is None:
        return "Veri bulunamadı"
    prefix = "+" if value > 0 else ""
    return f"{prefix}{formatter(value)}"


def _trend(value: Optional[float]) -> Optional[str]:
    if value is None:
        return None
    if value > 0:
        return "up"
    if value < 0:
        return "down"
    return "flat"


def _view_id(structured: Dict[str, Any], calculated_at: Optional[datetime]) -> str:
    """Pencere kimliği. Scoped CSS ve aynı konuşmada birden çok pencere için."""
    seed = "|".join(
        [
            str(structured.get("type")),
            str(structured.get("academic_year")),
            str(sorted(structured.get("scope", {}).items())),
            (calculated_at or datetime.now()).isoformat(),
        ]
    )
    return "aiv-" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Öğrenci senaryosu penceresi
# ---------------------------------------------------------------------------


def _enrollment_cards(index: Dict[str, Dict[str, Any]]) -> List[Component]:
    """En fazla 5 özet kartı. Her değer bir metrikten gelir."""
    cards: List[Component] = []

    students = index.get("program_student_count")
    if students:
        cards.append(
            Component(
                type="comparison_metric",
                title="Öğrenci sayısı",
                baseline_label=_fmt_count(_num(students, "baseline"), "öğrenci"),
                scenario_label=_fmt_count(_num(students, "scenario"), "öğrenci"),
                delta_label=_signed(
                    _num(students, "change"), lambda v: _fmt_count(v, "öğrenci")
                ),
                trend=_trend(_num(students, "change")),
                scope_type=students.get("scope_type"),
                scope_name=students.get("scope_name"),
                source_keys=["program_student_count"],
            )
        )

    baseline_gap = index.get("program_baseline_fte_gap")
    scenario_gap = index.get("program_scenario_fte_gap")
    marginal = index.get("program_marginal_fte")
    if baseline_gap and scenario_gap:
        cards.append(
            Component(
                type="comparison_metric",
                title="Program FTE açığı",
                baseline_label=_fmt_decimal(_num(baseline_gap, "baseline"), "FTE"),
                scenario_label=_fmt_decimal(_num(scenario_gap, "scenario"), "FTE"),
                delta_label=(
                    "Senaryonun etkisi: "
                    + _signed(_num(marginal, "change"), lambda v: _fmt_decimal(v, "FTE"))
                ),
                trend=_trend(_num(marginal, "change")),
                scope_type=baseline_gap.get("scope_type"),
                scope_name=baseline_gap.get("scope_name"),
                source_keys=[
                    "program_baseline_fte_gap",
                    "program_scenario_fte_gap",
                    "program_marginal_fte",
                ],
                note="Mevcut açık senaryodan bağımsızdır.",
            )
        )

    revenue = index.get("program_revenue_effect")
    if revenue:
        cards.append(
            Component(
                type="metric_card",
                title="Ek gelir etkisi",
                value=_signed(_num(revenue, "change"), _fmt_usd),
                trend=_trend(_num(revenue, "change")),
                scope_type=revenue.get("scope_type"),
                scope_name=revenue.get("scope_name"),
                source_keys=["program_revenue_effect"],
                note="Yatırım ve yeni personel maliyetleri hariç.",
            )
        )

    for key, title in (
        ("program_classroom_coverage", "Derslik karşılama oranı"),
        ("program_laboratory_coverage", "Laboratuvar karşılama oranı"),
    ):
        metric = index.get(key)
        if not metric:
            continue
        cards.append(
            Component(
                type="comparison_metric",
                title=title,
                baseline_label=_fmt_percent(_num(metric, "baseline")),
                scenario_label=_fmt_percent(_num(metric, "scenario")),
                trend=_trend(
                    None
                    if _num(metric, "scenario") is None or _num(metric, "baseline") is None
                    else _num(metric, "scenario") - _num(metric, "baseline")
                ),
                scope_type=metric.get("scope_type"),
                scope_name=metric.get("scope_name"),
                source_keys=[key],
                formula=metric.get("formula"),
            )
        )

    # Varsayılan görünümde en fazla beş kart.
    return cards[:5]


def _enrollment_charts(index: Dict[str, Dict[str, Any]]) -> List[Component]:
    """En fazla 3 grafik.

    RENK ANLAMI HER GRAFİKTE AYNIDIR: mavi = mevcut durum, turuncu = senaryo
    sonucu, gri = kullanılabilir kapasite. Bu yüzden legend açıklaması
    penceredeki İLK grafiğe bir kez konur; sonraki grafikler aynı renk
    sözlüğünü kullanır ve legend'i TEKRAR ETMEZ.
    """
    charts: List[Component] = []

    students = index.get("program_student_count")
    if students:
        charts.append(
            Component(
                type="bar_chart",
                title="Öğrenci sayısı",
                unit="öğrenci",
                categories=["Öğrenci sayısı"],
                series=[
                    ChartSeries(
                        label="Mevcut durum",
                        role="baseline",
                        values=[_num(students, "baseline")],
                    ),
                    ChartSeries(
                        label="Senaryo sonucu",
                        role="scenario",
                        values=[_num(students, "scenario")],
                    ),
                ],
                source_keys=["program_student_count"],
            )
        )

    fte = index.get("program_staff_fte")
    required = index.get("program_required_fte")
    if fte and required:
        charts.append(
            Component(
                type="bar_chart",
                title="Akademik kapasite",
                unit="FTE",
                categories=["Akademik kapasite (FTE)"],
                series=[
                    ChartSeries(
                        label="Kullanılabilir kapasite",
                        role="capacity",
                        values=[_num(fte, "baseline")],
                    ),
                    ChartSeries(
                        label="Mevcut gerekli",
                        role="baseline",
                        values=[_num(required, "baseline")],
                    ),
                    ChartSeries(
                        label="Senaryo gerekli",
                        role="scenario",
                        values=[_num(required, "scenario")],
                    ),
                ],
                source_keys=["program_staff_fte", "program_required_fte"],
            )
        )

    classroom_capacity = index.get("program_classroom_capacity")
    classroom_demand = index.get("program_classroom_demand")
    lab_capacity = index.get("program_laboratory_capacity")
    lab_demand = index.get("program_laboratory_demand")
    if classroom_capacity and classroom_demand:
        categories = ["Derslik (koltuk-saat)"]
        capacity_values = [_num(classroom_capacity, "baseline")]
        baseline_values = [_num(classroom_demand, "baseline")]
        scenario_values = [_num(classroom_demand, "scenario")]
        source_keys = ["program_classroom_capacity", "program_classroom_demand"]

        if lab_capacity and lab_demand and _num(lab_capacity, "baseline") is not None:
            categories.append("Laboratuvar (istasyon-saat)")
            capacity_values.append(_num(lab_capacity, "baseline"))
            baseline_values.append(_num(lab_demand, "baseline"))
            scenario_values.append(_num(lab_demand, "scenario"))
            source_keys += ["program_laboratory_capacity", "program_laboratory_demand"]

        charts.append(
            Component(
                type="bar_chart",
                title="Fiziksel kapasite",
                subtitle="Kapasite ve haftalık ihtiyaç",
                categories=categories,
                series=[
                    ChartSeries(label="Kullanılabilir kapasite", role="capacity",
                                values=capacity_values),
                    ChartSeries(label="Mevcut talep", role="baseline",
                                values=baseline_values),
                    ChartSeries(label="Senaryo talebi", role="scenario",
                                values=scenario_values),
                ],
                source_keys=source_keys,
            )
        )

    charts = charts[:3]

    # Legend YALNIZCA bir kez: penceredeki ilk grafiğe, o pencerede kullanılan
    # bütün rollerin açıklaması konur. Diğer grafiklerin legend'i boş kalır.
    if charts:
        roles = {series.role for chart in charts for series in chart.series}
        legend = [
            entry
            for entry, role in (
                (LEGEND_BASELINE, "baseline"),
                (LEGEND_SCENARIO, "scenario"),
                (LEGEND_CAPACITY, "capacity"),
            )
            if role in roles
        ]
        charts[0].legend = legend
        for chart in charts[1:]:
            chart.legend = []

    return charts


def _risk_components(
    structured: Dict[str, Any], index: Dict[str, Dict[str, Any]]
) -> List[Component]:
    """Mevcut risk ile senaryonun eklediği etki AYRI kartlarda."""
    components: List[Component] = []

    baseline_risks = list(structured.get("baseline_risks", []) or [])
    if baseline_risks:
        components.append(
            Component(
                type="risk_card",
                title="Mevcut durumdaki riskler",
                subtitle="Senaryodan bağımsız",
                level="warning",
                items=baseline_risks[:3],
                source_keys=["baseline_risks"],
            )
        )

    # Senaryonun EKLEDİĞİ etki: toplam açık değil, marjinal değişim.
    incremental: List[str] = []
    for key, label, formatter in (
        ("program_classroom_demand", "Program derslik ihtiyacı",
         lambda v: _fmt_decimal(v, "koltuk-saat")),
        ("program_laboratory_demand", "Program laboratuvar ihtiyacı",
         lambda v: _fmt_decimal(v, "istasyon-saat")),
        ("program_marginal_fte", "Program FTE açığı",
         lambda v: _fmt_decimal(v, "FTE")),
    ):
        metric = index.get(key)
        change = _num(metric, "change")
        if change:
            incremental.append(f"{label}: {_signed(change, formatter)}")

    for key, label in (
        ("university_classroom_gap", "Üniversite derslik açığı"),
        ("university_laboratory_gap", "Üniversite laboratuvar açığı"),
    ):
        metric = index.get(key)
        baseline = _num(metric, "baseline")
        scenario = _num(metric, "scenario")
        if baseline is None or scenario is None:
            continue
        added = scenario - baseline
        incremental.append(
            f"{label}: {_fmt_count(baseline)} → {_fmt_count(scenario)} "
            f"eş zamanlı kişi (senaryonun eklediği: {_signed(added, _fmt_count)})"
        )

    if incremental:
        components.append(
            Component(
                type="risk_card",
                title="Senaryonun eklediği etki",
                level="critical",
                items=incremental,
                source_keys=[
                    "program_classroom_demand",
                    "program_laboratory_demand",
                    "program_marginal_fte",
                    "university_classroom_gap",
                    "university_laboratory_gap",
                ],
                note=(
                    "Kurumun toplam kapasite açığı senaryodan önce de vardı; "
                    "burada yalnızca senaryonun eklediği fark gösterilir."
                ),
            )
        )

    return components


def _detail_components(
    structured: Dict[str, Any], index: Dict[str, Dict[str, Any]], markdown: str
) -> List[Component]:
    """Kapalı açılır bölümler. Varsayılan görünümde YER ALMAZ."""
    program_rows = [
        f"{m['label']}: "
        + (
            f"{_fmt_decimal(m.get('baseline'), m.get('unit', ''))} → "
            f"{_fmt_decimal(m.get('scenario'), m.get('unit', ''))}"
            if m.get("baseline") is not None and m.get("scenario") is not None
            else _fmt_decimal(
                m.get("scenario") if m.get("scenario") is not None else m.get("baseline"),
                m.get("unit", ""),
            )
        )
        for m in structured.get("metrics", [])
        if m.get("scope_type") == "program"
    ]
    university_rows = [
        f"{m['label']}: "
        + (
            f"{_fmt_decimal(m.get('baseline'), m.get('unit', ''))} → "
            f"{_fmt_decimal(m.get('scenario'), m.get('unit', ''))}"
            if m.get("baseline") is not None and m.get("scenario") is not None
            else _fmt_decimal(
                m.get("scenario") if m.get("scenario") is not None else m.get("baseline"),
                m.get("unit", ""),
            )
        )
        for m in structured.get("metrics", [])
        if m.get("scope_type") == "university"
    ]
    formulas = [
        f"{m['label']}: {m['formula']}"
        for m in structured.get("metrics", [])
        if m.get("formula")
    ]

    details: List[Component] = []
    if program_rows:
        details.append(
            Component(
                type="expandable_details",
                title="Ayrıntılı program sonuçları",
                components=[
                    Component(type="recommendation_list", items=program_rows)
                ],
            )
        )
    if university_rows:
        details.append(
            Component(
                type="expandable_details",
                title="Üniversite geneli etkiler",
                components=[
                    Component(type="recommendation_list", items=university_rows)
                ],
            )
        )
    if formulas:
        details.append(
            Component(
                type="expandable_details",
                title="Hesaplama yöntemi",
                components=[Component(type="recommendation_list", items=formulas)],
            )
        )
    if markdown:
        details.append(
            Component(
                type="expandable_details",
                title="Tam metin rapor",
                markdown=markdown,
            )
        )
    return details


def build_ui_spec(
    structured: Optional[Dict[str, Any]],
    *,
    data_sources: Optional[List[str]] = None,
    calculated_at: Optional[datetime] = None,
    interpretation: Optional[str] = None,
    markdown: str = "",
) -> Optional[UiSpec]:
    """`structured_result`tan dinamik pencere tanımı üretir.

    Yapılandırılmış sonuç yoksa None döner; arayüz o zaman yalnızca sohbet
    balonunu gösterir.
    """
    if not structured or not structured.get("metrics"):
        return None

    index = _index(structured)
    scope = structured.get("scope", {}) or {}
    scope_name = scope.get("program") or scope.get("department") or scope.get("faculty")
    academic_year = structured.get("academic_year")

    result_type = structured.get("type")
    if result_type == "enrollment_change_scenario":
        view_type = "scenario_dashboard"
        students = index.get("program_student_count")
        change = _num(students, "change") if students else None
        base = _num(students, "baseline") if students else None
        percent = (
            f"%{round(change / base * 100)}" if change and base else "Senaryo"
        )
        title = f"{scope_name or 'Senaryo'} — {percent} Öğrenci Değişimi"
        cards = _enrollment_cards(index)
        charts = _enrollment_charts(index)
    elif result_type == "staff_salary_scenario":
        view_type = "financial_dashboard"
        title = "Akademik Personel Maaş Senaryosu"
        cards = [
            Component(
                type="comparison_metric",
                title=metric["label"],
                baseline_label=_fmt_usd(metric.get("baseline")),
                scenario_label=_fmt_usd(metric.get("scenario")),
                delta_label=_signed(metric.get("change"), _fmt_usd),
                trend=_trend(metric.get("change")),
                scope_type=metric.get("scope_type"),
                scope_name=metric.get("scope_name"),
                source_keys=[metric["key"]],
            )
            for metric in structured["metrics"][:5]
        ]
        charts = []
    else:
        view_type = "summary_dashboard"
        title = scope_name or "Kurumsal Özet"
        cards = [
            Component(
                type="metric_card",
                title=metric["label"],
                value=_fmt_decimal(
                    metric.get("scenario")
                    if metric.get("scenario") is not None
                    else metric.get("baseline"),
                    metric.get("unit", ""),
                ),
                scope_type=metric.get("scope_type"),
                scope_name=metric.get("scope_name"),
                source_keys=[metric["key"]],
            )
            for metric in structured["metrics"][:5]
        ]
        charts = []

    sections: List[Section] = [
        Section(type="metric_grid", title="Temel Sonuçlar", components=cards)
    ]
    if charts:
        sections.append(Section(type="chart_grid", components=charts))

    risks = _risk_components(structured, index)
    if risks:
        sections.append(Section(type="risk_summary", components=risks))

    if interpretation:
        sections.append(
            Section(
                type="management_comment",
                title="Yönetim değerlendirmesi",
                components=[
                    Component(type="information_box", level="info", body=interpretation)
                ],
            )
        )

    # --- İzlenebilirlik ve varsayımlar ---
    detail_components = _detail_components(structured, index, markdown)
    detail_components.append(
        Component(
            type="data_source_panel",
            title="Kullanılan veriler",
            items=list(data_sources or []),
            source_keys=["data_sources"],
        )
    )
    detail_components.append(
        Component(
            type="assumptions_panel",
            title="Varsayımlar ve hariç tutulan maliyetler",
            items=list(structured.get("notes", []) or [])
            + [COST_EXCLUSION_WARNING],
        )
    )
    sections.append(Section(type="details", components=detail_components))

    return UiSpec(
        view_type=view_type,
        view_id=_view_id(structured, calculated_at),
        title=title,
        subtitle=f"{academic_year} Akademik Yılı" if academic_year else None,
        theme=Theme(),
        sections=sections,
        academic_year=academic_year,
        scope={k: v for k, v in scope.items() if v},
        calculated_at=calculated_at,
    )
