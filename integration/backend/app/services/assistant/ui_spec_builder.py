"""`structured_result` → `ui_spec` deterministik dönüşümü.

BU DOSYA HESAP YAPMAZ ve METİNDEN SAYI AYIKLAMAZ.

Her sayı `structured_result["metrics"]` içindeki bir kayıttan gelir ve
üretilen bileşen `source_metric_ids` alanında hangi metriğin hangi
alanından geldiğini söyler (`"<anahtar>.<baseline|scenario|change>"`).
Renderer bu adresleri çözüp karşılaştırır.

BİLGİ HİYERARŞİSİ — ANA EKRAN
-----------------------------
    1. Karar özeti (tek cümle + rozetler)
    2. En fazla 5 KPI kartı
    3. En fazla 4 grafik            ← ui_planner, anlama göre seçer
    4. En kritik 3 risk
    5. En fazla 4 maddelik karar önerisi

Uzun her şey — yönetim değerlendirmesi, ayrıntılı metrikler, yöntem,
varsayımlar, kaynaklar, teknik çıktı, ham cevap — en altta KAPALI
açılır bölümlerdedir. Kullanıcı açmadıkça görünmez.
"""

import hashlib
import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from app.services.assistant import ui_planner
from app.services.assistant.ui_spec import (
    Badge,
    Component,
    Section,
    Theme,
    UiSpec,
)

logger = logging.getLogger(__name__)

# Legend YALNIZCA panel düzeyinde, bir kez tanımlanır. Her grafiğin altına
# aynı açıklamayı koymak ekranı kalabalıklaştırmaktan başka bir şey yapmaz.
PANEL_LEGEND = [
    {"role": "baseline", "label": "Mevcut durum"},
    {"role": "scenario", "label": "Senaryo sonucu"},
    {"role": "capacity", "label": "Kapasite / hedef"},
]

COST_EXCLUSION_WARNING = (
    "Finansal sonuçlar gerekli yeni personel ve kapasite yatırımlarının "
    "maliyetini içermemektedir."
)

UNCALCULATED_COSTS = [
    "Ek personel maliyeti hesaplanmadı",
    "Fiziksel yatırım maliyeti hesaplanmadı",
]

# Karşılama oranı eşikleri. Renk TEK BAŞINA anlam taşımaz; her seviyenin
# metin karşılığı da vardır.
LEVEL_LABELS = {"critical": "Kritik", "warning": "Yüksek", "info": "İzlenmeli",
                "positive": "Uygun"}


def _index(structured: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {m["key"]: m for m in structured.get("metrics", []) if m.get("key")}


def _num(metric: Optional[Dict[str, Any]], field: str) -> Optional[float]:
    if metric is None:
        return None
    value = metric.get(field)
    return None if value is None else float(value)


def _addr(metric: Optional[Dict[str, Any]], field: str) -> Optional[str]:
    return None if metric is None else f"{metric['key']}.{field}"


def _ids(*pairs: Tuple[Optional[Dict[str, Any]], str]) -> List[str]:
    return [a for a in (_addr(m, f) for m, f in pairs) if a]


# ---------------------------------------------------------------------------
# Biçimlendirme
# ---------------------------------------------------------------------------


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


def _fmt_points(value: Optional[float]) -> str:
    """Yüzde farkı PUAN cinsindendir; "%-5,90" yazmak yanlış olurdu."""
    if value is None:
        return "Veri bulunamadı"
    text = f"{abs(Decimal(str(value))):.2f}".replace(".", ",")
    word = "Azalış" if value < 0 else "Artış"
    return f"{word}: {'-' if value < 0 else '+'}{text} puan"


def _signed(value: Optional[float], formatter) -> str:
    if value is None:
        return "Veri bulunamadı"
    return f"{'+' if value > 0 else ''}{formatter(value)}"


def _trend(value: Optional[float]) -> Optional[str]:
    if value is None:
        return None
    return "up" if value > 0 else "down" if value < 0 else "flat"


def _view_id(structured: Dict[str, Any], calculated_at: Optional[datetime]) -> str:
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
# 1) Karar özeti
# ---------------------------------------------------------------------------


def _decision_summary(
    structured: Dict[str, Any], index: Dict[str, Dict[str, Any]], scope_name: str
) -> Component:
    """En fazla iki satırlık karar cümlesi ve rozetler.

    Cümle şablondan değil, VERİDEN kurulur: hangi yönde değişim var, mali
    etki olumlu mu, kapasite açığı büyüyor mu. Metrikleri olmayan bir
    senaryoda ilgili cümle parçası hiç yazılmaz.
    """
    clauses: List[str] = []

    students = index.get("program_student_count")
    if students and _num(students, "baseline") and _num(students, "change") is not None:
        percent = round(_num(students, "change") / _num(students, "baseline") * 100)
        direction = "artışı" if _num(students, "change") > 0 else "azalışı"
        clauses.append(f"%{abs(percent)} öğrenci {direction}")

    net = index.get("university_net_balance")
    revenue = index.get("program_revenue_effect") or index.get("university_total_revenue")
    money_change = _num(net, "change")
    if money_change is None:
        money_change = _num(revenue, "change")
    if money_change is not None:
        clauses.append(
            "ek gelir oluşturuyor" if money_change > 0 else "bütçeyi olumsuz etkiliyor"
        )

    # Kapasite yönü: karşılama oranları düşüyor mu, kadro açığı büyüyor mu?
    worsening: List[str] = []
    for key, name in (
        ("program_classroom_coverage", "fiziksel"),
        ("program_laboratory_coverage", "fiziksel"),
    ):
        metric = index.get(key)
        if metric and _num(metric, "scenario") is not None and _num(metric, "baseline") is not None:
            if _num(metric, "scenario") < _num(metric, "baseline"):
                worsening.append(name)
    if _num(index.get("program_marginal_fte"), "change"):
        worsening.append("akademik")

    if worsening:
        order = [w for w in ("akademik", "fiziksel") if w in worsening]
        clauses.append(
            "ancak programın mevcut "
            + " ve ".join(order)
            + " kapasite açığını önemli ölçüde büyütüyor"
        )

    sentence = (scope_name + ": " if scope_name else "") + ", ".join(clauses[:1])
    if len(clauses) > 1:
        sentence = (
            (scope_name + ": " if scope_name else "")
            + clauses[0] + " " + " ".join(clauses[1:])
        )
    if not clauses:
        sentence = f"{scope_name or 'Kurum'} için hesaplanan sonuçlar aşağıdadır."
    if not sentence.endswith("."):
        sentence += "."

    badges = [Badge(label=b, tone=t) for b, t in _badges(structured, index, scope_name)]

    return Component(
        type="decision_summary",
        id="decision-summary",
        title=sentence,
        span=12,
        badges=badges,
        aria_label="Karar özeti: " + sentence,
    )


def _risk_level(index: Dict[str, Dict[str, Any]]) -> str:
    """Panelin genel risk seviyesi. Metriklerden türetilir, tahmin edilmez."""
    coverages = [
        _num(index.get(k), "scenario")
        for k in index
        if k.endswith("_coverage") and _num(index.get(k), "scenario") is not None
    ]
    if coverages and min(coverages) < 50:
        return "critical"
    if _num(index.get("program_marginal_fte"), "change"):
        return "critical"
    if coverages and min(coverages) < 80:
        return "warning"
    return "info"


def _badges(
    structured: Dict[str, Any], index: Dict[str, Dict[str, Any]], scope_name: str
) -> List[Tuple[str, str]]:
    kind = {
        "enrollment_change_scenario": "Program senaryosu",
        "staff_salary_scenario": "Personel senaryosu",
    }.get(structured.get("type"), "Kurumsal analiz")

    level = _risk_level(index)
    level_text = {"critical": "Yüksek risk", "warning": "Orta risk",
                  "info": "Düşük risk"}[level]

    badges: List[Tuple[str, str]] = []
    if structured.get("academic_year"):
        badges.append((structured["academic_year"], "info"))
    badges.append((kind, "info"))
    if scope_name:
        badges.append((scope_name, "baseline"))
    badges.append((level_text, level))
    return badges


# ---------------------------------------------------------------------------
# 2) KPI kartları
# ---------------------------------------------------------------------------


def _kpi_comparison(
    metric: Dict[str, Any], *, title: str, icon: str, formatter,
    caption: str = "", delta_metric: Optional[Dict[str, Any]] = None,
    delta_label: Optional[str] = None, good_when: str = "up",
    scenario_metric: Optional[Dict[str, Any]] = None,
) -> Component:
    """Mevcut → senaryo karşılaştırması taşıyan KPI kartı."""
    scenario_metric = scenario_metric or metric
    baseline = _num(metric, "baseline")
    scenario = _num(scenario_metric, "scenario")
    delta = _num(delta_metric, "change") if delta_metric else None
    if delta is None and baseline is not None and scenario is not None:
        delta = round(scenario - baseline, 2)

    sentiment = "neutral"
    if delta:
        rising_is_good = good_when == "up"
        sentiment = "positive" if (delta > 0) == rising_is_good else "negative"

    return Component(
        type="kpi_card",
        id="kpi-" + metric["key"],
        title=title,
        icon=icon,
        span=12,
        unit=metric.get("unit"),
        value=formatter(scenario),
        value_number=scenario,
        baseline_label=formatter(baseline),
        scenario_label=formatter(scenario),
        delta_label=delta_label if delta_label is not None else _signed(delta, formatter),
        trend=_trend(delta),
        sentiment=sentiment,
        caption=caption,
        semantic_type=metric.get("semantic_type"),
        scope_type=metric.get("scope_type"),
        scope_name=metric.get("scope_name"),
        data={"baseline": baseline, "scenario": scenario, "delta": delta},
        data_source_ids={
            k: v for k, v in {
                "baseline": _addr(metric, "baseline"),
                "scenario": _addr(scenario_metric, "scenario"),
                "delta": _addr(delta_metric, "change") if delta_metric else None,
            }.items() if v
        },
        source_metric_ids=_ids((metric, "baseline"), (scenario_metric, "scenario")),
        source_keys=sorted({metric["key"], scenario_metric["key"]}),
        formula=metric.get("formula"),
        aria_label=(
            f"{title}: mevcut {formatter(baseline)}, senaryo {formatter(scenario)}"
        ),
    )


def _enrollment_kpis(index: Dict[str, Dict[str, Any]]) -> List[Component]:
    """En fazla 5 KPI kartı. Her değer bir metrikten gelir."""
    cards: List[Component] = []

    students = index.get("program_student_count")
    if students:
        cards.append(
            _kpi_comparison(
                students,
                title="Öğrenci sayısı",
                icon="students",
                formatter=lambda v: _fmt_count(v, "öğrenci"),
                caption="Program kaydı",
                delta_metric=students,
                good_when="up",
            )
        )

    baseline_gap = index.get("program_baseline_fte_gap")
    scenario_gap = index.get("program_scenario_fte_gap")
    marginal = index.get("program_marginal_fte")
    if baseline_gap and scenario_gap:
        card = _kpi_comparison(
            baseline_gap,
            title="Program FTE açığı",
            icon="staff",
            formatter=lambda v: _fmt_decimal(v, "FTE"),
            caption="Mevcut açık senaryodan bağımsızdır",
            delta_metric=marginal,
            delta_label="Senaryonun etkisi: "
            + _signed(_num(marginal, "change"), lambda v: _fmt_decimal(v, "FTE")),
            good_when="down",
            scenario_metric=scenario_gap,
        )
        card.source_metric_ids = _ids(
            (baseline_gap, "baseline"), (scenario_gap, "scenario"), (marginal, "change")
        )
        card.source_keys = [baseline_gap["key"], scenario_gap["key"], marginal["key"]]
        cards.append(card)

    revenue = index.get("program_revenue_effect")
    if revenue:
        change = _num(revenue, "change")
        cards.append(
            Component(
                type="kpi_card",
                id="kpi-" + revenue["key"],
                title="Ek gelir etkisi",
                icon="money",
                span=12,
                unit="USD",
                value=_signed(change, _fmt_usd),
                value_number=change,
                delta_label=None,
                trend=_trend(change),
                sentiment="positive" if (change or 0) > 0 else "negative",
                caption="Personel ve yatırım maliyetleri hariç",
                semantic_type=revenue.get("semantic_type"),
                scope_type=revenue.get("scope_type"),
                scope_name=revenue.get("scope_name"),
                data={"value": change},
                data_source_ids={"value": _addr(revenue, "change")},
                source_metric_ids=_ids((revenue, "change")),
                source_keys=[revenue["key"]],
                aria_label=f"Ek gelir etkisi {_signed(change, _fmt_usd)}",
            )
        )

    for key, title in (
        ("program_classroom_coverage", "Derslik karşılama oranı"),
        ("program_laboratory_coverage", "Laboratuvar karşılama oranı"),
    ):
        metric = index.get(key)
        if not metric:
            continue
        baseline = _num(metric, "baseline")
        scenario = _num(metric, "scenario")
        delta = None if None in (baseline, scenario) else round(scenario - baseline, 2)
        cards.append(
            Component(
                type="kpi_card",
                id="kpi-" + key,
                title=title,
                icon="classroom" if "classroom" in key else "laboratory",
                span=12,
                unit="%",
                value=_fmt_percent(scenario),
                value_number=scenario,
                baseline_label=_fmt_percent(baseline),
                scenario_label=_fmt_percent(scenario),
                delta_label=_fmt_points(delta),
                trend=_trend(delta),
                sentiment="negative" if (delta or 0) < 0 else "positive",
                caption="Talebin karşılanabilen bölümü",
                level="critical" if (scenario or 100) < 50 else
                      "warning" if (scenario or 100) < 80 else None,
                semantic_type=metric.get("semantic_type"),
                scope_type=metric.get("scope_type"),
                scope_name=metric.get("scope_name"),
                data={"baseline": baseline, "scenario": scenario, "delta": delta},
                data_source_ids={
                    "baseline": _addr(metric, "baseline"),
                    "scenario": _addr(metric, "scenario"),
                    "delta": f"{_addr(metric, 'scenario')}|{_addr(metric, 'baseline')}",
                },
                source_metric_ids=_ids((metric, "baseline"), (metric, "scenario")),
                source_keys=[key],
                formula=metric.get("formula"),
                aria_label=(
                    f"{title}: mevcut yüzde {baseline}, senaryo yüzde {scenario}"
                ),
            )
        )

    return cards[:5]


def _generic_kpis(structured: Dict[str, Any]) -> List[Component]:
    """Senaryo dışındaki sonuç türleri için genel KPI kartları."""
    cards: List[Component] = []
    for metric in structured.get("metrics", [])[:5]:
        scenario = metric.get("scenario")
        baseline = metric.get("baseline")
        value = scenario if scenario is not None else baseline
        field = "scenario" if scenario is not None else "baseline"
        if value is None:
            continue
        unit = metric.get("unit", "")
        formatter = (
            _fmt_usd if unit == "USD"
            else _fmt_percent if unit == "%"
            else (lambda v, u=unit: _fmt_decimal(v, u))
        )
        cards.append(
            Component(
                type="kpi_card",
                id="kpi-" + metric["key"],
                title=metric["label"],
                icon="metric",
                span=12,
                unit=unit,
                value=formatter(float(value)),
                value_number=float(value),
                baseline_label=formatter(float(baseline)) if baseline is not None else None,
                scenario_label=formatter(float(scenario)) if scenario is not None else None,
                semantic_type=metric.get("semantic_type"),
                scope_type=metric.get("scope_type"),
                scope_name=metric.get("scope_name"),
                data={"value": float(value)},
                data_source_ids={"value": f"{metric['key']}.{field}"},
                source_metric_ids=[f"{metric['key']}.{field}"],
                source_keys=[metric["key"]],
                aria_label=f"{metric['label']}: {formatter(float(value))}",
            )
        )
    return cards[:5]


# ---------------------------------------------------------------------------
# 4) Riskler — kompakt kartlar
# ---------------------------------------------------------------------------


def _capacity_families(index: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Karşılama oranı ile talebi aynı "aile" altında eşleştirir.

    Eşleşme anahtar KÖKÜNE bakar: `program_classroom_coverage` ile
    `program_classroom_demand` aynı köke sahiptir. Yarın eklenecek
    `program_workshop_*` metrikleri de aynı kuralla eşleşir.
    """
    families: List[Dict[str, Any]] = []
    for key, metric in index.items():
        if not key.endswith("_coverage"):
            continue
        stem = key[: -len("_coverage")]
        demand = index.get(stem + "_demand")
        if demand is None:
            continue
        families.append({"stem": stem, "coverage": metric, "demand": demand})
    # En özel kapsam önce.
    rank = {"program": 0, "department": 1, "faculty": 2, "university": 3}
    families.sort(key=lambda f: (rank.get(f["coverage"].get("scope_type"), 4),
                                 _num(f["coverage"], "scenario") or 100))
    if families:
        best = rank.get(families[0]["coverage"].get("scope_type"), 4)
        families = [f for f in families if rank.get(f["coverage"].get("scope_type"), 4) == best]
    return families


def _family_title(stem: str, label: str) -> str:
    if "classroom" in stem:
        return "Derslik kapasitesi"
    if "laborator" in stem:
        return "Laboratuvar kapasitesi"
    return label.replace("talebinin karşılanan oranı", "kapasitesi").strip().capitalize()


def _risk_cards(index: Dict[str, Dict[str, Any]]) -> List[Component]:
    """En kritik üç risk. Paragraf yok; ikon, rozet, büyük metrik, tek cümle."""
    cards: List[Component] = []

    marginal = index.get("program_marginal_fte")
    scenario_gap = index.get("program_scenario_fte_gap")
    if marginal and scenario_gap and _num(marginal, "change"):
        cards.append(
            Component(
                type="risk_summary_card",
                id="risk-staffing",
                title="Akademik kapasite",
                icon="staff",
                level="critical",
                span=4,
                value=_signed(_num(marginal, "change"), lambda v: _fmt_decimal(v, "FTE")),
                caption=(
                    "Senaryo sonrası toplam açık: "
                    + _fmt_decimal(_num(scenario_gap, "scenario"), "FTE")
                ),
                subtitle="Senaryonun eklediği açık",
                data={
                    "marginal": _num(marginal, "change"),
                    "total": _num(scenario_gap, "scenario"),
                },
                data_source_ids={
                    "marginal": _addr(marginal, "change"),
                    "total": _addr(scenario_gap, "scenario"),
                },
                source_metric_ids=_ids((marginal, "change"), (scenario_gap, "scenario")),
                source_keys=[marginal["key"], scenario_gap["key"]],
                aria_label=(
                    "Akademik kapasite riski kritik. Senaryonun eklediği açık "
                    + _fmt_decimal(_num(marginal, "change"), "FTE")
                ),
            )
        )

    for family in _capacity_families(index):
        coverage, demand = family["coverage"], family["demand"]
        scenario_coverage = _num(coverage, "scenario")
        extra = _num(demand, "change")
        if extra is None and None not in (_num(demand, "baseline"), _num(demand, "scenario")):
            extra = _num(demand, "scenario") - _num(demand, "baseline")
        level = ("critical" if (scenario_coverage or 100) < 50
                 else "warning" if (scenario_coverage or 100) < 80 else "info")
        title = _family_title(family["stem"], coverage["label"])
        cards.append(
            Component(
                type="risk_summary_card",
                id="risk-" + family["stem"],
                title=title,
                icon="classroom" if "classroom" in family["stem"] else "laboratory",
                level=level,
                span=4,
                value=_signed(extra, lambda v: _fmt_decimal(v, demand.get("unit", ""))),
                subtitle="Ek haftalık ihtiyaç",
                caption="Karşılama oranı: " + _fmt_percent(scenario_coverage),
                data={"extra": extra, "coverage": scenario_coverage},
                data_source_ids={
                    k: v for k, v in {
                        "extra": _addr(demand, "change"),
                        "coverage": _addr(coverage, "scenario"),
                    }.items() if v
                },
                source_metric_ids=_ids((demand, "change"), (coverage, "scenario")),
                source_keys=[demand["key"], coverage["key"]],
                aria_label=(
                    f"{title} riski {LEVEL_LABELS[level].lower()}. Ek haftalık "
                    f"ihtiyaç {_fmt_decimal(extra, demand.get('unit', ''))}, "
                    f"karşılama oranı yüzde {scenario_coverage}"
                ),
            )
        )

    order = {"critical": 0, "warning": 1, "info": 2, "positive": 3}
    cards.sort(key=lambda c: order.get(c.level or "info", 3))
    return cards[:3]


# ---------------------------------------------------------------------------
# 5) Karar önerileri
# ---------------------------------------------------------------------------


def _decisions(index: Dict[str, Dict[str, Any]]) -> List[str]:
    """En fazla dört, ikişer satırı geçmeyen karar maddesi."""
    items: List[str] = []

    marginal = _num(index.get("program_marginal_fte"), "change")
    if marginal:
        items.append(
            f"Akademik kadro: En az {_fmt_decimal(marginal, 'FTE')} ek kapasite "
            "planlanmalı."
        )

    for family in _capacity_families(index):
        coverage = family["coverage"]
        title = _family_title(family["stem"], coverage["label"])
        baseline = _num(coverage, "baseline")
        if baseline is not None and baseline < 100:
            items.append(
                f"{title}: Mevcut tahsis öğrenci artışından önce de yetersiz."
            )
        else:
            items.append(
                f"{title}: Senaryo sonrası tahsis yetersiz kalıyor; artırılmalı."
            )

    if index.get("university_net_balance") or index.get("program_revenue_effect"):
        items.append(
            "Finans: Ek gelir olumlu ancak personel ve yatırım maliyetleri "
            "ayrıca hesaplanmalı."
        )

    return items[:4]


# ---------------------------------------------------------------------------
# 6) Açılır bölümler — hepsi KAPALI
# ---------------------------------------------------------------------------


def _metric_rows(structured: Dict[str, Any], scope_type: str) -> List[str]:
    rows = []
    for m in structured.get("metrics", []):
        if m.get("scope_type") != scope_type:
            continue
        unit = m.get("unit", "")
        if m.get("baseline") is not None and m.get("scenario") is not None:
            rows.append(
                f"{m['label']}: {_fmt_decimal(m['baseline'], unit)} → "
                f"{_fmt_decimal(m['scenario'], unit)}"
            )
        else:
            value = m.get("scenario") if m.get("scenario") is not None else m.get("baseline")
            rows.append(f"{m['label']}: {_fmt_decimal(value, unit)}")
    return rows


def _accordion(
    structured: Dict[str, Any],
    index: Dict[str, Dict[str, Any]],
    *,
    interpretation: Optional[str],
    markdown: str,
    data_sources: List[str],
) -> List[Component]:
    """Uzun içerik yalnızca burada. Hepsi `open=False`."""
    blocks: List[Component] = []

    def block(title: str, *, items: List[str] = None, body: str = None,
              markdown_text: str = None, icon: str = "detail") -> None:
        if not (items or body or markdown_text):
            return
        children = []
        if items:
            children.append(Component(type="recommendation_list", items=items))
        blocks.append(
            Component(
                type="expandable_details",
                id="acc-" + str(len(blocks)),
                title=title,
                icon=icon,
                span=12,
                open=False,
                components=children,
                body=body,
                markdown=markdown_text,
            )
        )

    block("Detaylı yönetim değerlendirmesi", body=interpretation, icon="comment")
    block("Program kapsamındaki bütün sonuçlar",
          items=_metric_rows(structured, "program"), icon="program")
    block("Üniversite geneli etkiler",
          items=_metric_rows(structured, "university"), icon="university")
    block(
        "Hesaplama yöntemi",
        items=[f"{m['label']}: {m['formula']}"
               for m in structured.get("metrics", []) if m.get("formula")]
        + ([structured["method_note"]] if structured.get("method_note") else []),
        icon="formula",
    )
    block(
        "Varsayımlar ve hariç tutulan maliyetler",
        items=list(structured.get("notes", []) or [])
        + UNCALCULATED_COSTS
        + [COST_EXCLUSION_WARNING],
        icon="assumption",
    )
    block("Kullanılan veri kaynakları", items=list(data_sources or []), icon="source")
    block(
        "Teknik sonuç (structured_result)",
        markdown_text=json.dumps(structured, ensure_ascii=False, indent=2),
        icon="code",
    )
    block("Ham asistan cevabı", markdown_text=markdown, icon="raw")
    return blocks


# ---------------------------------------------------------------------------
# Ana giriş
# ---------------------------------------------------------------------------


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
    scope = {k: v for k, v in (structured.get("scope") or {}).items() if v}
    scope_name = scope.get("program") or scope.get("department") or scope.get("faculty") or ""
    academic_year = structured.get("academic_year")
    result_type = structured.get("type")

    if result_type == "enrollment_change_scenario":
        view_type = "scenario_dashboard"
        students = index.get("program_student_count")
        change = _num(students, "change") if students else None
        base = _num(students, "baseline") if students else None
        percent = f"%{round(change / base * 100)}" if change and base else "Senaryo"
        title = f"{scope_name or 'Senaryo'} — {percent} Öğrenci Değişimi"
        kpis = _enrollment_kpis(index)
    elif result_type == "staff_salary_scenario":
        view_type = "financial_dashboard"
        title = "Akademik Personel Maaş Senaryosu"
        kpis = _generic_kpis(structured)
    else:
        view_type = "summary_dashboard"
        title = scope_name or "Kurumsal Özet"
        kpis = _generic_kpis(structured)

    # KPI kartları 12 kolonluk gridi eşit paylaşır.
    for card in kpis:
        card.span = max(2, 12 // max(len(kpis), 1))

    sections: List[Section] = [
        Section(
            type="decision_summary",
            components=[_decision_summary(structured, index, scope_name)],
        ),
        Section(type="metric_grid", title="Temel Göstergeler", components=kpis),
    ]

    # --- grafikler: türü VERİNİN ANLAMI seçer ---
    charts = ui_planner.plan_charts(structured.get("metrics", []))
    if charts:
        # Legend tek yerde: panel düzeyinde, ilk grafiğin üstünde.
        legend = Component(
            type="legend_panel",
            id="legend",
            span=12,
            legend=[e for e in PANEL_LEGEND
                    if any(s.role == e["role"] for c in charts for s in c.series)
                    or e["role"] == "capacity" and any(c.markers for c in charts)],
        )
        components: List[Component] = [legend] + charts

        # Hesaplanmayan maliyetler grafiğe SIFIR olarak konmaz; ayrı uyarı.
        if any(c.type == "waterfall_chart" for c in charts):
            components.append(
                Component(
                    type="information_box",
                    id="cost-warning",
                    level="warning",
                    icon="warning",
                    span=6,
                    title="Hesaplanmayan maliyetler",
                    items=UNCALCULATED_COSTS,
                    note=COST_EXCLUSION_WARNING,
                    aria_label="Uyarı: " + COST_EXCLUSION_WARNING,
                )
            )
        sections.append(Section(type="chart_grid", components=components))

    risks = _risk_cards(index)
    if risks:
        sections.append(
            Section(type="risk_summary", title="En Kritik Riskler", components=risks)
        )

    decisions = _decisions(index)
    if decisions:
        sections.append(
            Section(
                type="recommendations",
                title="Karar Önerileri",
                components=[
                    Component(
                        type="decision_list",
                        id="decisions",
                        span=12,
                        items=decisions,
                        aria_label="Karar önerileri",
                    )
                ],
            )
        )

    sections.append(
        Section(
            type="accordion",
            title="Ayrıntılar",
            subtitle="Uzun metinler yalnızca açtığınızda görünür",
            components=_accordion(
                structured, index,
                interpretation=interpretation,
                markdown=markdown,
                data_sources=list(data_sources or []),
            ),
        )
    )

    return UiSpec(
        view_type=view_type,
        view_id=_view_id(structured, calculated_at),
        title=title,
        subtitle=f"{academic_year} Akademik Yılı" if academic_year else None,
        theme=Theme(),
        sections=sections,
        academic_year=academic_year,
        scope=scope,
        calculated_at=calculated_at,
    )
