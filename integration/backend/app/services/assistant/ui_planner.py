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
            # Parasal yön ve "toplam mı" bilgisi de burada tamamlanır:
            # araç bildirmediyse merkezî sınıflandırıcı karar verir. Aksi
            # hâlde şelale kuralı bu alanları hiç göremezdi.
            if metric.get("flow") is None:
                metric["flow"] = metric_semantics.classify_flow(
                    metric.get("key", ""), metric.get("unit", ""),
                    metric.get("label", ""),
                )
            if "is_total" not in metric:
                metric["is_total"] = metric_semantics.looks_like_total(
                    metric.get("key", "")
                )

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
    """Önce–sonra değişimi → dumbbell.

    HAREKET ETMEYEN METRİK GRAFİK ÜRETMEZ: 180 → 180 çizmek ekranda yer
    kaplamaktan başka bir şey yapmaz. Sayım metriği değişmiyorsa parasal bir
    kalemin önce–sonra karşılaştırması kullanılır (maaş senaryosunda
    akademik personel gideri gibi).
    """
    def _moved(metric: Dict[str, Any]) -> bool:
        if not index.has_both(metric):
            return False
        change = metric.get("change")
        if change is None:
            change = index.num(metric, "scenario") - index.num(metric, "baseline")
        return bool(change)

    metric = _pick([m for m in index.by_semantic("count_change") if _moved(m)])
    if metric is None:
        # Parasal kalem: toplam olmayan, gerçek bir bütçe akışı.
        metric = _pick([
            m for m in index.by_semantic("monetary_change")
            if _moved(m) and not m.get("is_total")
            and m.get("flow") in ("inflow", "outflow")
        ])
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
        # Seçilen metriğin GERÇEK anlamı taşınır: sayım da olabilir parasal
        # da. Sabit "count_change" yazmak testleri de yanıltırdı.
        semantic_type=metric.get("semantic_type", "count_change"),
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
    """Net bütçe şelalesi: başlangıç → katkı kalemleri → sonuç.

    GERÇEK KADEMELİ ŞELALE
    ----------------------
    İlk sütun mevcut net bütçedir. Ara sütunlar bu seviyeden başlayarak
    yukarı/aşağı hareket eder. Son sütun senaryo net bütçesidir. Bağımsız üç
    sütun çizmek şelale değil, gruplanmış çubuk grafiğidir.

    ÇİFT SAYMA KORUMASI
    -------------------
    Katkı kalemleri yalnızca `is_total=False` olan gerçek bütçe akışlarıdır.
    "Toplam gider" ile "akademik personel gideri" aynı 612.000 USD'yi taşır;
    ikisi birden katkı sayılsaydı etki iki kez hesaplanırdı.

    Ayrıca katkıların toplamı, net bütçe değişimine EŞİT OLMAK ZORUNDADIR.
    Eşit değilse grafik uydurulmuş bir zincir göstermek yerine iki adımlı
    (başlangıç → net değişim → sonuç) güvenli biçime düşer ve bunu yazar.
    """
    balance = next(
        (m for m in index.by_semantic("monetary_change")
         if m.get("flow") == "balance" and index.has_both(m)),
        None,
    )
    if balance is None:
        return None

    start = index.num(balance, "baseline")
    end = index.num(balance, "scenario")
    if start is None or end is None:
        return None
    net_change = index.num(balance, "change")
    if net_change is None:
        net_change = end - start

    # Katkı adayları: gerçek bütçe akışı olan, toplam OLMAYAN, değişimi
    # sıfırdan farklı kalemler. Sıfır değişimli kalem (bu senaryoda gelir ve
    # idari maaşlar) grafiğe SIFIR SÜTUN olarak konmaz — sıfır bir ölçüm
    # sonucudur, çizilecek bir hareket değildir.
    contributions: List[Dict[str, Any]] = []
    for metric in index.by_semantic("monetary_change"):
        if metric.get("is_total") or metric.get("flow") not in ("inflow", "outflow"):
            continue
        change = index.num(metric, "change")
        if change is None and index.has_both(metric):
            change = index.num(metric, "scenario") - index.num(metric, "baseline")
        if not change:
            continue
        # Gider artışı bütçeyi AZALTIR; işaret burada çevrilir.
        signed = change if metric["flow"] == "inflow" else -change
        contributions.append({"metric": metric, "signed": signed})

    contributions.sort(key=lambda c: -abs(c["signed"]))

    explained = sum(c["signed"] for c in contributions)
    residual = net_change - explained

    note = None
    if not contributions:
        # Hiç kalem yok: net değişim tek adımda gösterilir.
        contributions = [{"metric": None, "signed": net_change, "label": "Net değişim"}]
    elif abs(residual) >= 0.51:  # kuruş yuvarlaması payı
        # Kalemler net değişimi TAM AÇIKLAMIYOR. Farkı görünmez yapmak
        # (veya bir kalemi şişirmek) grafiği yalancı yapardı; fark açıkça
        # "diğer kalemler" olarak yazılır.
        contributions.append(
            {"metric": None, "signed": residual, "label": "Diğer kalemlerin etkisi"}
        )
        note = (
            "«Diğer kalemlerin etkisi» ayrıntılı kalemlerle net bütçe değişimi "
            "arasındaki farktır; tek tek raporlanmayan gider kalemlerini içerir."
        )

    categories = [balance.get("label", "Mevcut net bütçe") + " (mevcut)"]
    values: List[Optional[float]] = [start]
    kinds: List[Optional[str]] = ["total"]
    ids: List[Optional[str]] = [index.address(balance, "baseline")]
    signs: List[Optional[int]] = [1]

    for item in contributions:
        metric = item["metric"]
        categories.append(metric["label"] if metric else item.get("label", "Net değişim"))
        values.append(item["signed"])
        kinds.append("increase" if item["signed"] > 0 else "decrease")
        # Artık kalemin KAYNAK ADRESİ YOKTUR: o bir metrik değil, net
        # değişim ile raporlanan kalemler arasındaki farktır. Buraya net
        # bütçe değişimini yazmak, renderer'ın doğrulama katmanında bu
        # sütunu net değişime "düzeltmesine" ve grafiğin bozulmasına yol
        # açardı.
        ids.append(index.address(metric, "change") if metric else None)
        # Gider kalemi kaynakta POZİTİF durur (gider arttı) ama bütçeyi
        # azaltır; işaret burada bildirilir.
        signs.append(
            -1 if metric and metric.get("flow") == "outflow" else 1
        )

    categories.append(balance.get("label", "Net bütçe") + " (senaryo)")
    values.append(end)
    kinds.append("total")
    ids.append(index.address(balance, "scenario"))
    signs.append(1)

    return Component(
        type="waterfall_chart",
        id="money-waterfall",
        title="Net Bütçe Etkisi",
        subtitle="Mevcut bütçeden senaryo bütçesine",
        unit="USD",
        semantic_type="monetary_change",
        scope_type=balance.get("scope_type"),
        scope_name=balance.get("scope_name"),
        span=SPAN["waterfall_chart"],
        categories=categories,
        data={"start": start, "end": end, "change": net_change},
        data_source_ids={
            "start": index.address(balance, "baseline"),
            "end": index.address(balance, "scenario"),
            "change": index.address(balance, "change"),
        },
        series=[
            ChartSeries(
                label="Net bütçe",
                role="info",
                values=values,
                kinds=kinds,
                value_signs=signs,
                source_metric_ids=ids,
            )
        ],
        source_metric_ids=[i for i in ids if i],
        source_keys=[balance["key"]]
        + [c["metric"]["key"] for c in contributions if c["metric"]],
        note=note,
        aria_label=(
            f"Net bütçe {start:g} USD'den {end:g} USD'ye değişiyor; "
            f"fark {net_change:g} USD"
        ),
    )


def _rule_expense_composition(index: MetricIndex) -> Optional[Component]:
    """Gider kalemlerinin dağılımı → yatay karşılaştırma çubuğu.

    Toplam kalemler dışarıda bırakılır: "toplam personel gideri" ile onun
    bileşenlerini aynı grafikte göstermek okuyucuya iki kez saydırır.
    """
    outflows = [
        m for m in index.by_semantic("monetary_change")
        if m.get("flow") == "outflow" and not m.get("is_total") and index.has_both(m)
    ]
    if len(outflows) < 2:
        return None
    outflows.sort(key=lambda m: -(index.num(m, "baseline") or 0))
    outflows = outflows[:4]

    return Component(
        type="horizontal_comparison_bar",
        id="expense-composition",
        title="Gider Kalemlerinin Dağılımı",
        subtitle="Mevcut ve senaryo değerleri",
        unit="USD",
        semantic_type="distribution",
        scope_type=outflows[0].get("scope_type"),
        scope_name=outflows[0].get("scope_name"),
        span=SPAN["horizontal_comparison_bar"],
        categories=[m["label"] for m in outflows],
        series=[
            ChartSeries(
                label="Mevcut", role="baseline",
                values=[index.num(m, "baseline") for m in outflows],
                source_metric_ids=[index.address(m, "baseline") for m in outflows],
            ),
            ChartSeries(
                label="Senaryo", role="scenario",
                values=[index.num(m, "scenario") for m in outflows],
                source_metric_ids=[index.address(m, "scenario") for m in outflows],
            ),
        ],
        source_metric_ids=[index.address(m, "baseline") for m in outflows]
        + [index.address(m, "scenario") for m in outflows],
        source_keys=[m["key"] for m in outflows],
        aria_label="Gider kalemlerinin mevcut ve senaryo değerleri",
    )


def _rule_ratio(index: MetricIndex) -> Optional[Component]:
    """Bir bütünün içindeki pay (%) → gauge grubu.

    Karşılama oranından farkı: bu oran bir talebin karşılanmasını değil, bir
    toplamın içindeki payı ölçer. Yine de görsel dili aynıdır.
    """
    metrics = [
        m for m in index.by_semantic("utilization")
        if index.has_both(m) and (index.num(m, "scenario") or 0) <= 100
    ]
    if not metrics:
        return None

    metrics.sort(key=lambda m: (index.scope_rank(m), m["key"]))
    metrics = metrics[:2]

    gauges: List[Component] = []
    for metric in metrics:
        baseline = index.num(metric, "baseline")
        scenario = index.num(metric, "scenario")
        gauges.append(
            Component(
                type="radial_gauge",
                id="ratio-" + metric["key"],
                title=metric["label"],
                unit="%",
                percent=scenario,
                semantic_type="utilization",
                scope_type=metric.get("scope_type"),
                scope_name=metric.get("scope_name"),
                tone="critical" if scenario > 60 else
                     "warning" if scenario > 40 else "info",
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
        id="ratio-group",
        title="Gider İçindeki Pay",
        subtitle="Ortadaki büyük değer senaryo sonucudur",
        span=SPAN["gauge_group"],
        semantic_type="utilization",
        components=gauges,
        source_metric_ids=[i for g in gauges for i in g.source_metric_ids],
        source_keys=[k for g in gauges for k in g.source_keys],
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
    _rule_ratio,
    _rule_forecast,
    _rule_trend,
    _rule_risk_matrix,
    _rule_ranking,
    _rule_distribution,
    _rule_demand,
    _rule_expense_composition,
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
