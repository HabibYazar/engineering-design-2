"""Hangi veriyi hangi grafik anlatır — semantik grafik seçimi.

Bu dosya HİÇBİR senaryoya gömülü değildir. "Bilgisayar Mühendisliği" veya
"%15 artış" gibi bir bilgi geçmez. Kurallar metriklerin ANLAM türüne
(`semantic_type`) ve verinin şekline bakar; hangi araç çalışmış olursa olsun
aynı kurallar işler.

KURALLAR
--------
| Veri anlamı                          | Grafik                          |
|--------------------------------------|---------------------------------|
| önce → sonra değişimi                | dumbbell_chart / slope_chart    |
| kapasite ↔ ihtiyaç ↔ hedef           | bullet_chart                    |
| talebin karşılanma oranı             | radial_gauge (gauge_group)      |
| gelir / gider / net etki             | waterfall_chart                 |
| yıllara göre seyir                   | line_chart / stacked_area_chart |
| gelecek tahmini                      | forecast_line_chart             |
| birim karşılaştırması                | radar_chart / heatmap / grouped |
| olasılık × etki                      | risk_matrix                     |
| kaynak dağılımı                      | treemap                         |
| haftalık kapasite talebi             | horizontal_comparison_bar       |

Her kural sırayla denenir; verisi olmayan kural sessizce atlanır. Toplam
grafik sayısı `MAX_CHARTS` ile sınırlıdır ve aynı grafik türü — küçük
çoklular dışında — iki kez kullanılmaz.
"""

import logging
from typing import Any, Callable, Dict, List, Optional

from app.services.assistant import metric_semantics
from app.services.assistant.ui_spec import (
    ChartSeries,
    Component,
    Marker,
    SMALL_MULTIPLE_TYPES,
)

logger = logging.getLogger(__name__)

MAX_CHARTS = 4

#: Grafiklerin 12 kolonluk gridde kapladığı yer.
SPAN = {
    "dumbbell_chart": 6,
    "slope_chart": 6,
    "bullet_chart": 6,
    "gauge_group": 6,
    "waterfall_chart": 6,
    "forecast_line_chart": 8,
    "stacked_area_chart": 8,
    "line_chart": 6,
    "grouped_bar_chart": 6,
    "horizontal_comparison_bar": 6,
    "heatmap": 8,
    "risk_matrix": 6,
    "treemap": 6,
    "radar_chart": 6,
}


# ---------------------------------------------------------------------------
# Metrik dizini
# ---------------------------------------------------------------------------


class MetricIndex:
    """Metrikleri anlam türüne, birime ve kapsama göre sorgulanabilir kılar."""

    def __init__(self, metrics: List[Dict[str, Any]]):
        self.all = [m for m in metrics if isinstance(m, dict) and m.get("key")]
        self.by_key = {m["key"]: m for m in self.all}
        for metric in self.all:
            metric.setdefault("semantic_type", metric_semantics.resolve(metric))

    # --- sorgular ---

    def by_semantic(self, *types: str) -> List[Dict[str, Any]]:
        wanted = set(types)
        return [m for m in self.all if m.get("semantic_type") in wanted]

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        return self.by_key.get(key)

    @staticmethod
    def num(metric: Optional[Dict[str, Any]], field: str) -> Optional[float]:
        if not metric:
            return None
        value = metric.get(field)
        return None if value is None else float(value)

    @staticmethod
    def address(metric: Dict[str, Any], field: str) -> str:
        """`structured_result` içindeki adres."""
        return f"{metric['key']}.{field}"

    @staticmethod
    def has_both(metric: Dict[str, Any]) -> bool:
        return metric.get("baseline") is not None and metric.get("scenario") is not None

    @staticmethod
    def scope_rank(metric: Dict[str, Any]) -> int:
        """En özel kapsam önce gelsin: program > bölüm > fakülte > üniversite."""
        return {
            "program": 0,
            "department": 1,
            "faculty": 2,
            "university": 3,
        }.get(metric.get("scope_type", "university"), 4)


def _pick(candidates: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """En özel kapsamlı, en büyük hareketi olan metriği seçer."""
    if not candidates:
        return None
    def weight(m: Dict[str, Any]):
        change = m.get("change")
        if change is None and MetricIndex.has_both(m):
            change = float(m["scenario"]) - float(m["baseline"])
        return (MetricIndex.scope_rank(m), -abs(float(change or 0)))
    return sorted(candidates, key=weight)[0]


# ---------------------------------------------------------------------------
# Kurallar
# ---------------------------------------------------------------------------


def _rule_change(index: MetricIndex) -> Optional[Component]:
    """Önce–sonra değişimi → dumbbell."""
    metric = _pick(
        [m for m in index.by_semantic("count_change") if index.has_both(m)]
    )
    if metric is None:
        return None

    baseline = index.num(metric, "baseline")
    scenario = index.num(metric, "scenario")
    delta = index.num(metric, "change")
    if delta is None:
        delta = scenario - baseline

    return Component(
        type="dumbbell_chart",
        id="change-" + metric["key"],
        # Başlık teknik değil, okunur olmalı: "Öğrenci sayısı — Mevcut ve
        # Senaryo". Metrik etiketi hangi dilde/biçimde gelirse gelsin çalışır.
        title=f"{metric['label']} — Mevcut ve Senaryo",
        # Alt başlık legend metnini TEKRAR ETMEZ; legend panelde bir kez
        # yazılır, kartlar kendi kısa açıklamalarını kullanır.
        subtitle="Senaryo öncesi ve sonrası",
        unit=metric.get("unit"),
        semantic_type="count_change",
        scope_type=metric.get("scope_type"),
        scope_name=metric.get("scope_name"),
        span=SPAN["dumbbell_chart"],
        categories=[metric["label"]],
        data={"baseline": baseline, "scenario": scenario, "delta": delta},
        data_source_ids={
            "baseline": index.address(metric, "baseline"),
            "scenario": index.address(metric, "scenario"),
            "delta": index.address(metric, "change")
            if metric.get("change") is not None
            else f"{index.address(metric, 'scenario')}|{index.address(metric, 'baseline')}",
        },
        series=[
            ChartSeries(
                label="Mevcut", role="baseline", values=[baseline],
                source_metric_ids=[index.address(metric, "baseline")],
            ),
            ChartSeries(
                label="Senaryo", role="scenario", values=[scenario],
                source_metric_ids=[index.address(metric, "scenario")],
            ),
        ],
        source_metric_ids=[
            index.address(metric, "baseline"),
            index.address(metric, "scenario"),
        ],
        source_keys=[metric["key"]],
        aria_label=(
            f"{metric['label']}: mevcut {baseline:g}, senaryo {scenario:g} "
            f"{metric.get('unit', '')}"
        ),
    )


def _rule_target(index: MetricIndex) -> Optional[Component]:
    """Sabit kapasite + hareketli ihtiyaç → bullet chart.

    Eşleştirme veriye bakar, isme değil: aynı birimdeki metriklerden
    senaryosu OLMAYAN biri sabit kapasitedir, hem mevcut hem senaryo değeri
    OLAN biri hareketli ihtiyaçtır.
    """
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for metric in index.by_semantic("target_comparison", "staffing_gap"):
        groups.setdefault(metric.get("unit", ""), []).append(metric)

    for unit, metrics in groups.items():
        capacity = next(
            (m for m in metrics
             if m.get("baseline") is not None and m.get("scenario") is None
             and "gap" not in m["key"] and "marginal" not in m["key"]),
            None,
        )
        requirement = next((m for m in metrics if index.has_both(m)), None)
        if capacity is None or requirement is None:
            continue

        available = index.num(capacity, "baseline")
        needed_now = index.num(requirement, "baseline")
        needed_scenario = index.num(requirement, "scenario")

        return Component(
            type="bullet_chart",
            id="target-" + requirement["key"],
            title="Akademik Kapasite ve İhtiyaç" if unit == "FTE"
            else f"{capacity['label']} ve İhtiyaç",
            subtitle="Aynı eksende kapasite, mevcut ihtiyaç ve senaryo ihtiyacı",
            unit=unit,
            semantic_type="target_comparison",
            scope_type=requirement.get("scope_type"),
            scope_name=requirement.get("scope_name"),
            span=SPAN["bullet_chart"],
            data={
                "capacity": available,
                "baseline": needed_now,
                "scenario": needed_scenario,
            },
            data_source_ids={
                "capacity": index.address(capacity, "baseline"),
                "baseline": index.address(requirement, "baseline"),
                "scenario": index.address(requirement, "scenario"),
            },
            series=[
                ChartSeries(
                    label="Kullanılabilir kapasite", role="capacity",
                    values=[available],
                    source_metric_ids=[index.address(capacity, "baseline")],
                ),
                ChartSeries(
                    label="Mevcut ihtiyaç", role="baseline", values=[needed_now],
                    source_metric_ids=[index.address(requirement, "baseline")],
                ),
                ChartSeries(
                    label="Senaryo ihtiyacı", role="scenario",
                    values=[needed_scenario],
                    source_metric_ids=[index.address(requirement, "scenario")],
                ),
            ],
            markers=[
                Marker(
                    label="Kapasite sınırı", value=available, tone="capacity",
                    source_metric_id=index.address(capacity, "baseline"),
                )
            ],
            source_metric_ids=[
                index.address(capacity, "baseline"),
                index.address(requirement, "baseline"),
                index.address(requirement, "scenario"),
            ],
            source_keys=[capacity["key"], requirement["key"]],
            aria_label=(
                f"Kapasite {available:g} {unit}, mevcut ihtiyaç {needed_now:g}, "
                f"senaryo ihtiyacı {needed_scenario:g}"
            ),
        )
    return None


def _rule_coverage(index: MetricIndex) -> Optional[Component]:
    """Talebin karşılanma oranı → gauge grubu."""
    metrics = [
        m for m in index.by_semantic("capacity_coverage")
        if index.has_both(m) and "shortfall" not in m["key"]
    ]
    if not metrics:
        return None

    metrics.sort(key=lambda m: (index.scope_rank(m), m["key"]))
    best_scope = index.scope_rank(metrics[0])
    metrics = [m for m in metrics if index.scope_rank(m) == best_scope][:3]

    gauges: List[Component] = []
    for metric in metrics:
        baseline = index.num(metric, "baseline")
        scenario = index.num(metric, "scenario")
        gauges.append(
            Component(
                type="radial_gauge",
                id="gauge-" + metric["key"],
                title=metric["label"],
                unit="%",
                percent=scenario,
                semantic_type="capacity_coverage",
                scope_type=metric.get("scope_type"),
                scope_name=metric.get("scope_name"),
                tone="critical" if scenario < 50 else
                     "warning" if scenario < 80 else "positive",
                data={
                    "baseline": baseline,
                    "scenario": scenario,
                    "delta": round(scenario - baseline, 2),
                },
                data_source_ids={
                    "baseline": index.address(metric, "baseline"),
                    "scenario": index.address(metric, "scenario"),
                    "delta": f"{index.address(metric, 'scenario')}|"
                             f"{index.address(metric, 'baseline')}",
                },
                source_metric_ids=[
                    index.address(metric, "baseline"),
                    index.address(metric, "scenario"),
                ],
                source_keys=[metric["key"]],
                formula=metric.get("formula"),
                aria_label=(
                    f"{metric['label']}: mevcut yüzde {baseline}, "
                    f"senaryo yüzde {scenario}"
                ),
            )
        )

    return Component(
        type="gauge_group",
        id="coverage-group",
        title="Fiziksel Kapasitenin Talebi Karşılama Oranı",
        subtitle="Ortadaki büyük değer senaryo sonucudur",
        span=SPAN["gauge_group"],
        semantic_type="capacity_coverage",
        components=gauges,
        source_metric_ids=[i for g in gauges for i in g.source_metric_ids],
        source_keys=[k for g in gauges for k in g.source_keys],
    )


def _rule_money(index: MetricIndex) -> Optional[Component]:
    """Gelir → operasyonel etki → net bütçe zinciri → şelale grafiği.

    Hesaplanmamış maliyetler grafiğe SIFIR olarak konmaz; grafiğin yanındaki
    uyarı alanında ayrıca yazılır (bkz. `ui_spec_builder`).
    """
    money = [m for m in index.by_semantic("monetary_change")
             if m.get("change") not in (None, 0)]
    if not money:
        return None

    # Zincirin SONU: net/bakiye metriği. Zincirin BAŞI: en özel kapsamdaki
    # diğer parasal kalem. Belirli bir gelir kaleminin adı aranmaz — "hibe",
    # "bağış", "proje geliri" gibi yeni kalemler de zinciri kurabilsin.
    net = next(
        (m for m in money if any(w in m["key"] for w in ("net", "balance", "bakiye"))),
        None,
    )
    inflows = [m for m in money if m is not net]
    gross = _pick(inflows) if inflows else None
    if net is None or gross is None:
        # Zincir kurulamıyor: tek kalemlik şelale bilgi taşımaz.
        return None

    gross_change = index.num(gross, "change")
    net_change = index.num(net, "change")

    categories = ["Ek brüt gelir", "Ek operasyonel etki", "Net bütçe değişimi"]
    return Component(
        type="waterfall_chart",
        id="money-waterfall",
        title="Mali Etki Zinciri",
        subtitle="Brüt gelirden net bütçe değişimine",
        unit="USD",
        semantic_type="monetary_change",
        scope_type=net.get("scope_type"),
        scope_name=net.get("scope_name"),
        span=SPAN["waterfall_chart"],
        categories=categories,
        data={"gross": gross_change, "net": net_change},
        data_source_ids={
            "gross": index.address(gross, "change"),
            "net": index.address(net, "change"),
        },
        series=[
            ChartSeries(
                label="Mali etki",
                role="positive" if net_change and net_change > 0 else "critical",
                values=[gross_change, net_change - gross_change, net_change],
                kinds=["increase", "decrease", "total"],
                # Ortadaki kalem TÜRETİLMİŞTİR: net ile brüt farkı. Renderer
                # bu farkı iki kaynaktan yeniden hesaplar.
                derivation="difference",
                source_metric_ids=[
                    index.address(gross, "change"),
                    f"{index.address(net, 'change')}|{index.address(gross, 'change')}",
                    index.address(net, "change"),
                ],
            )
        ],
        source_metric_ids=[
            index.address(gross, "change"),
            index.address(net, "change"),
        ],
        source_keys=[gross["key"], net["key"]],
        note=(
            "Ek personel alımı ve fiziksel yatırım maliyetleri HESAPLANMADI; "
            "bu kalemler grafiğe sıfır olarak konmamıştır."
        ),
        aria_label=(
            f"Ek brüt gelir {gross_change:g} USD, net bütçe değişimi "
            f"{net_change:g} USD"
        ),
    )


def _rule_trend(index: MetricIndex) -> Optional[Component]:
    """Yıllara göre seyir → çizgi veya yığılmış alan grafiği."""
    metrics = [m for m in index.by_semantic("historical_trend") if m.get("series")]
    if not metrics:
        return None
    stacked = len(metrics) > 1
    series = []
    categories: List[str] = []
    for metric in metrics[:4]:
        points = metric.get("series") or []
        categories = [str(p.get("label", "")) for p in points] or categories
        series.append(
            ChartSeries(
                label=metric["label"],
                role="baseline" if len(series) == 0 else "scenario",
                values=[float(p["value"]) for p in points if p.get("value") is not None],
                source_metric_ids=[index.address(metric, "baseline")] * len(points),
            )
        )
    return Component(
        type="stacked_area_chart" if stacked else "line_chart",
        id="trend",
        title="Yıllara Göre Seyir",
        unit=metrics[0].get("unit"),
        semantic_type="historical_trend",
        span=SPAN["stacked_area_chart" if stacked else "line_chart"],
        categories=categories,
        series=series,
        source_keys=[m["key"] for m in metrics[:4]],
    )


def _rule_forecast(index: MetricIndex) -> Optional[Component]:
    """Gelecek tahmini → güven aralıklı çizgi."""
    metrics = [m for m in index.by_semantic("forecast") if m.get("series")]
    if not metrics:
        return None
    metric = metrics[0]
    points = metric.get("series") or []
    return Component(
        type="forecast_line_chart",
        id="forecast-" + metric["key"],
        title=metric["label"],
        subtitle="Kesikli bölüm tahmindir",
        unit=metric.get("unit"),
        semantic_type="forecast",
        span=SPAN["forecast_line_chart"],
        categories=[str(p.get("label", "")) for p in points],
        series=[
            ChartSeries(
                label=metric["label"],
                role="scenario",
                dashed=True,
                values=[p.get("value") for p in points],
                lower=[p.get("lower") for p in points],
                upper=[p.get("upper") for p in points],
                source_metric_ids=[index.address(metric, "scenario")] * len(points),
            )
        ],
        source_keys=[metric["key"]],
    )


def _rule_risk_matrix(index: MetricIndex) -> Optional[Component]:
    """Olasılık × etki → risk matrisi."""
    metrics = index.by_semantic("risk_score")
    cells = [
        {
            "label": m["label"],
            "probability": m.get("baseline"),
            "impact": m.get("scenario"),
            "source_metric_ids": [
                index.address(m, "baseline"), index.address(m, "scenario")
            ],
        }
        for m in metrics
        if m.get("baseline") is not None and m.get("scenario") is not None
    ]
    if not cells:
        return None
    return Component(
        type="risk_matrix",
        id="risk-matrix",
        title="Olasılık ve Etki Matrisi",
        semantic_type="risk_score",
        span=SPAN["risk_matrix"],
        cells=cells,
        source_keys=[m["key"] for m in metrics],
    )


def _rule_distribution(index: MetricIndex) -> Optional[Component]:
    """Kaynak veya bütçe dağılımı → treemap."""
    metrics = [m for m in index.by_semantic("distribution")
               if m.get("baseline") is not None]
    if len(metrics) < 2:
        return None
    return Component(
        type="treemap",
        id="distribution",
        title="Kaynak Dağılımı",
        unit=metrics[0].get("unit"),
        semantic_type="distribution",
        span=SPAN["treemap"],
        cells=[
            {
                "label": m["label"],
                "value": float(m["baseline"]),
                "source_metric_ids": [index.address(m, "baseline")],
            }
            for m in metrics
        ],
        source_keys=[m["key"] for m in metrics],
    )


def _rule_ranking(index: MetricIndex) -> Optional[Component]:
    """Birimler arası karşılaştırma → radar (az birim) veya ısı haritası."""
    metrics = [m for m in index.by_semantic("ranking")
               if m.get("baseline") is not None]
    if len(metrics) < 3:
        return None
    use_radar = len(metrics) <= 6
    return Component(
        type="radar_chart" if use_radar else "heatmap",
        id="ranking",
        title="Birim Karşılaştırması",
        unit=metrics[0].get("unit"),
        semantic_type="ranking",
        span=SPAN["radar_chart" if use_radar else "heatmap"],
        categories=[m["label"] for m in metrics],
        series=[
            ChartSeries(
                label="Mevcut durum",
                role="baseline",
                values=[float(m["baseline"]) for m in metrics],
                source_metric_ids=[index.address(m, "baseline") for m in metrics],
            )
        ],
        cells=[
            {
                "label": m["label"],
                "value": float(m["baseline"]),
                "source_metric_ids": [index.address(m, "baseline")],
            }
            for m in metrics
        ],
        source_keys=[m["key"] for m in metrics],
    )


def _rule_demand(index: MetricIndex) -> Optional[Component]:
    """Haftalık kapasite talebi → yatay karşılaştırma çubuğu."""
    metrics = [m for m in index.by_semantic("capacity_demand")
               if index.has_both(m) and "gap" not in m["key"]]
    if not metrics:
        return None
    metrics.sort(key=lambda m: (index.scope_rank(m), m["key"]))
    best = index.scope_rank(metrics[0])
    metrics = [m for m in metrics if index.scope_rank(m) == best][:3]

    return Component(
        type="horizontal_comparison_bar",
        id="demand",
        title="Haftalık Kapasite İhtiyacı",
        subtitle="Mevcut ihtiyaç ve senaryo ihtiyacı",
        unit=metrics[0].get("unit"),
        semantic_type="capacity_demand",
        scope_type=metrics[0].get("scope_type"),
        scope_name=metrics[0].get("scope_name"),
        span=SPAN["horizontal_comparison_bar"],
        categories=[m["label"] for m in metrics],
        series=[
            ChartSeries(
                label="Mevcut durum", role="baseline",
                values=[index.num(m, "baseline") for m in metrics],
                source_metric_ids=[index.address(m, "baseline") for m in metrics],
            ),
            ChartSeries(
                label="Senaryo sonucu", role="scenario",
                values=[index.num(m, "scenario") for m in metrics],
                source_metric_ids=[index.address(m, "scenario") for m in metrics],
            ),
        ],
        source_keys=[m["key"] for m in metrics],
    )


#: Kural sırası = öncelik sırası.
RULES: List[Callable[[MetricIndex], Optional[Component]]] = [
    _rule_change,
    _rule_target,
    _rule_coverage,
    _rule_money,
    _rule_forecast,
    _rule_trend,
    _rule_risk_matrix,
    _rule_ranking,
    _rule_distribution,
    _rule_demand,
]


def plan_charts(metrics: List[Dict[str, Any]], limit: int = MAX_CHARTS) -> List[Component]:
    """Metriklerin anlamına göre en fazla `limit` grafik seçer.

    Bir kuralın çökmesi bütün planı düşürmez; o kural atlanır. Panelin
    tamamını tek bir grafik yüzünden kaybetmek, o grafiği kaybetmekten çok
    daha kötüdür.
    """
    index = MetricIndex(metrics)
    charts: List[Component] = []
    used_types = set()

    for rule in RULES:
        if len(charts) >= limit:
            break
        try:
            component = rule(index)
        except Exception:
            logger.exception("Grafik kuralı atlandı: %s", getattr(rule, "__name__", "?"))
            continue
        if component is None:
            continue
        if component.type in used_types and component.type not in SMALL_MULTIPLE_TYPES:
            continue
        used_types.add(component.type)
        component.fallback = component.fallback or None
        charts.append(component)

    return charts
