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
    ChartSeries,
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


#: Bir pencerede en fazla kaç grafik. Beşinciden sonra pencere okunmaz
#: hâle geliyor; kalanlar tabloda zaten var.
_EN_FAZLA_GRAFIK = 4


def _katalog_sekli(structured: Dict[str, Any]) -> bool:
    """Bu sonuç senaryo değil, birim kırılımı mı?

    Ayırt edici işaret `rows`tır. Senaryo metrikleri `baseline`/`scenario`
    taşır ve `rows` içermez; katalog metrikleri tam tersidir. Şekli
    alanların VARLIĞINDAN anlamak, sonucun `type` etiketine güvenmekten
    sağlamdır — yeni bir araç eklendiğinde etiket yazmayı unutmak
    grafiği sessizce kaybettirirdi.
    """
    for m in structured.get("metrics") or []:
        if m.get("rows"):
            return True
    return False


def _katalog_spec(
    structured: Dict[str, Any],
    *,
    data_sources: Optional[List[str]],
    calculated_at: Optional[datetime],
    interpretation: Optional[str],
) -> Optional[UiSpec]:
    """Birim kırılımından çubuk grafik + KPI kartı üretir."""
    kapsam = {k: v for k, v in (structured.get("scope") or {}).items() if v}
    kapsam_adi = (kapsam.get("program") or kapsam.get("department")
                  or kapsam.get("faculty") or "Üniversite geneli")
    yil = structured.get("academic_year")

    bilesenler: List[Component] = []
    grafik_sayisi = 0

    for m in structured.get("metrics") or []:
        satirlar = [r for r in (m.get("rows") or []) if r.get("value") is not None]
        if not satirlar:
            continue
        etiket = m.get("label") or m.get("canonical_label") or m.get("key") or "Değer"
        birim = m.get("unit") or (satirlar[0].get("unit") if satirlar else None)

        # TEK SATIR → grafik değil KART. Tek çubuklu bir grafik hiçbir
        # karşılaştırma taşımaz; sayının kendisi daha okunur.
        if len(satirlar) == 1:
            r = satirlar[0]
            bilesenler.append(Component(
                type="kpi_card",
                title=etiket,
                value=_bicimle(r.get("value"), birim),
                value_number=_float(r.get("value")),
                unit=birim,
                caption=r.get("label"),
                span=4,
                scope_name=kapsam_adi,
                source_keys=[m.get("key")] if m.get("key") else [],
                aria_label=f"{etiket}: {r.get('value')} {birim or ''}".strip(),
            ))
            continue

        # ÇOK SATIR → büyükten küçüğe çubuk. Sıralamak kıyası okunur
        # kılar; kaynak sırası (kimlik numarası) anlamsızdır.
        sirali = sorted(satirlar, key=lambda r: _float(r.get("value")) or 0,
                        reverse=True)[:14]
        if grafik_sayisi >= _EN_FAZLA_GRAFIK:
            break
        bilesenler.append(Component(
            type="bar_chart",
            title=f"{etiket} — {_kirilim_adi(sirali)}",
            categories=[str(r.get("label") or "?") for r in sirali],
            series=[ChartSeries(
                label=etiket, role="baseline",
                values=[_float(r.get("value")) for r in sirali],
            )],
            unit=birim,
            span=12,
            scope_name=kapsam_adi,
            source_keys=[m.get("key")] if m.get("key") else [],
            note=m.get("note"),
            aria_label=f"{etiket} kırılımı, {len(sirali)} birim",
        ))
        grafik_sayisi += 1

    if not bilesenler:
        return None

    bolumler: List[Section] = []
    kartlar = [c for c in bilesenler if c.type == "kpi_card"]
    grafikler = [c for c in bilesenler if c.type != "kpi_card"]
    if kartlar:
        bolumler.append(Section(type="metric_grid", components=kartlar))
    if grafikler:
        bolumler.append(Section(type="chart_grid", components=grafikler))
    if interpretation:
        bolumler.append(Section(
            type="management_comment",
            components=[Component(type="information_box", body=interpretation)],
        ))

    return UiSpec(
        view_type="summary_dashboard",
        view_id=f"katalog-{abs(hash((kapsam_adi, yil, len(bilesenler)))) % 10**8}",
        title=kapsam_adi,
        subtitle=yil,
        sections=bolumler,
        academic_year=yil,
        scope={k: str(v) for k, v in kapsam.items()},
        calculated_at=calculated_at,
    )


def _float(v: Any) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _bicimle(v: Any, birim: Optional[str]) -> str:
    f = _float(v)
    if f is None:
        return "—"
    metin = f"{f:,.0f}".replace(",", ".") if abs(f) >= 1000 or f == int(f) \
        else f"{f:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{metin} {birim}".strip() if birim else metin


def _kirilim_adi(satirlar: List[Dict[str, Any]]) -> str:
    """Kırılımın ne olduğunu satırların kendi türünden okur."""
    turler = {r.get("entity_type_label") or r.get("entity_type")
              for r in satirlar if r.get("entity_type_label") or r.get("entity_type")}
    return f"{turler.pop()} kırılımı" if len(turler) == 1 else "birim kırılımı"


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
    # Maaş senaryosunun kendi karar cümlesi. "Kurum için hesaplanan sonuçlar
    # aşağıdadır" bir karar özeti değil, bir dolgu cümlesidir.
    if structured.get("type") == "staff_salary_scenario":
        return _salary_decision_summary(structured, index, scope_name)

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
    level, reason = _risk_assessment(index)

    return Component(
        type="decision_summary",
        id="decision-summary",
        title=sentence,
        subtitle=reason,   # risk seviyesinin gerekçesi burada görünür
        span=12,
        level=level,
        badges=badges,
        aria_label="Karar özeti: " + sentence + " " + reason,
    )


def _salary_decision_summary(
    structured: Dict[str, Any], index: Dict[str, Dict[str, Any]], scope_name: str
) -> Component:
    """Maaş senaryosunun karar cümlesi — doğrulanmış metriklerden kurulur."""
    academic = index.get("annual_staff_cost")
    balance = index.get("university_net_balance")
    ratio = index.get("academic_personnel_expense_ratio")

    cost_change = _num(academic, "change")
    balance_change = _num(balance, "change")

    percent_text = ""
    baseline_cost = _num(academic, "baseline")
    if cost_change and baseline_cost:
        percent_text = f"%{round(cost_change / baseline_cost * 100)} akademik maaş artışı "

    parts: List[str] = []
    if cost_change is not None:
        parts.append(
            f"yıllık akademik personel giderini {_fmt_usd(abs(cost_change))} "
            + ("artırıyor" if cost_change > 0 else "azaltıyor")
        )
    if balance_change is not None:
        same = (
            cost_change is not None
            and abs(abs(balance_change) - abs(cost_change)) < 0.51
        )
        parts.append(
            ("ve net bütçeyi aynı tutarda " if same else "ve net bütçeyi ")
            + ("azaltıyor" if balance_change < 0 else "artırıyor")
            + ("" if same else f" ({_fmt_usd(abs(balance_change))})")
        )
    if ratio is not None and _num(ratio, "scenario") is not None:
        parts.append(
            "personel gideri payı "
            + _fmt_percent(_num(ratio, "baseline")) + " → "
            + _fmt_percent(_num(ratio, "scenario"))
        )

    # "artırıyor, ve net bütçeyi" olmasın: ikinci parça zaten "ve" ile
    # başlıyor, araya virgül girmemeli.
    sentence = (percent_text + " ".join(parts[:2])).strip()
    if len(parts) > 2:
        sentence += "; " + parts[2]
    if not sentence:
        sentence = "Maaş senaryosunun hesaplanan sonuçları aşağıdadır"
    sentence = sentence[0].upper() + sentence[1:] + "."

    badges = [Badge(label=b, tone=t) for b, t in _badges(structured, index, scope_name)]
    level, reason = _risk_assessment(index)
    return Component(
        type="decision_summary",
        id="decision-summary",
        title=sentence,
        subtitle=reason,   # risk seviyesinin gerekçesi burada görünür
        span=12,
        level=level,
        badges=badges,
        aria_label="Karar özeti: " + sentence + " " + reason,
    )


# Kurumun tanımlı risk eşikleri. Sabit metin yerine SAYISAL EŞİK: seviye
# değiştiğinde neden değiştiği de gösterilebilsin diye eşikler burada,
# tek yerde duruyor.
RISK_THRESHOLDS = {
    # Talebin karşılanan oranı bu değerin altına inerse
    "coverage_critical": 50.0,
    "coverage_warning": 80.0,
    # Net bütçe bu oranda gerilerse (yüzde)
    "budget_drop_critical": 20.0,
    "budget_drop_warning": 10.0,
    # Personel gideri toplam harcamanın bu payını aşarsa
    "personnel_ratio_critical": 40.0,
    "personnel_ratio_warning": 30.0,
}


def _risk_assessment(index: Dict[str, Dict[str, Any]]) -> Tuple[str, str]:
    """Panelin risk seviyesi ve SEBEBİ.

    Seviye sabit değil, doğrulanmış metriklerden ve `RISK_THRESHOLDS`
    eşiklerinden türetilir. Sebep metni kullanıcıya gösterilir; "Düşük risk"
    yazıp gerekçesini saklamak bir karar destek sisteminde işe yaramaz.
    """
    reasons: List[Tuple[str, str]] = []  # (seviye, sebep)

    # --- Kapasite karşılama oranı ---
    coverages = [
        (key, _num(index.get(key), "scenario"))
        for key in index
        if key.endswith("_coverage") and _num(index.get(key), "scenario") is not None
    ]
    if coverages:
        key, worst = min(coverages, key=lambda pair: pair[1])
        label = index[key].get("label", key)
        if worst < RISK_THRESHOLDS["coverage_critical"]:
            reasons.append(("critical", f"{label} " + _fmt_percent(worst) + " — eşik "
                            + _fmt_percent(RISK_THRESHOLDS["coverage_critical"])))
        elif worst < RISK_THRESHOLDS["coverage_warning"]:
            reasons.append(("warning", f"{label} " + _fmt_percent(worst) + " — eşik "
                            + _fmt_percent(RISK_THRESHOLDS["coverage_warning"])))

    # --- Kadro açığının büyümesi ---
    if _num(index.get("program_marginal_fte"), "change"):
        reasons.append(
            ("critical", "senaryo mevcut akademik kadro açığını büyütüyor")
        )

    # --- Net bütçedeki gerileme ve bütçenin işareti ---
    balance = index.get("university_net_balance")
    baseline_balance = _num(balance, "baseline")
    scenario_balance = _num(balance, "scenario")
    if scenario_balance is not None and scenario_balance < 0:
        reasons.append(("critical", "senaryo sonrası bütçe açık veriyor"))
    elif baseline_balance and scenario_balance is not None:
        drop = (baseline_balance - scenario_balance) / abs(baseline_balance) * 100
        if drop >= RISK_THRESHOLDS["budget_drop_critical"]:
            reasons.append(("critical", "net bütçe " + _fmt_percent(drop) + " geriliyor — eşik "
                            + _fmt_percent(RISK_THRESHOLDS["budget_drop_critical"])))
        elif drop >= RISK_THRESHOLDS["budget_drop_warning"]:
            reasons.append(("warning", "net bütçe " + _fmt_percent(drop) + " geriliyor — eşik "
                            + _fmt_percent(RISK_THRESHOLDS["budget_drop_warning"])))

    # --- Personel giderinin toplam harcamadaki payı ---
    ratio = _num(index.get("total_personnel_expense_ratio"), "scenario")
    if ratio is None:
        ratio = _num(index.get("academic_personnel_expense_ratio"), "scenario")
    if ratio is not None:
        if ratio >= RISK_THRESHOLDS["personnel_ratio_critical"]:
            reasons.append(("critical", "personel gideri payı " + _fmt_percent(ratio) + " — eşik "
                            + _fmt_percent(RISK_THRESHOLDS["personnel_ratio_critical"])))
        elif ratio >= RISK_THRESHOLDS["personnel_ratio_warning"]:
            reasons.append(("warning", "personel gideri payı " + _fmt_percent(ratio) + " — eşik "
                            + _fmt_percent(RISK_THRESHOLDS["personnel_ratio_warning"])))

    if not reasons:
        return "info", "Tanımlı risk eşiklerinin hiçbiri aşılmadı."

    order = {"critical": 0, "warning": 1, "info": 2}
    reasons.sort(key=lambda pair: order[pair[0]])
    level = reasons[0][0]
    matching = [text for lvl, text in reasons if lvl == level]
    return level, "Sebep: " + "; ".join(matching[:2]) + "."


def _risk_level(index: Dict[str, Dict[str, Any]]) -> str:
    """Geriye dönük uyumluluk için yalnızca seviye."""
    return _risk_assessment(index)[0]


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


# ---------------------------------------------------------------------------
# Maaş senaryosu KPI kartları
# ---------------------------------------------------------------------------


def _money_kpi(
    metric: Optional[Dict[str, Any]], *, title: str, icon: str, caption: str,
    good_when: str = "up", percent_of: Optional[Dict[str, Any]] = None,
) -> Optional[Component]:
    """Parasal bir kalemin mevcut → senaryo kartı."""
    if metric is None:
        return None
    baseline = _num(metric, "baseline")
    scenario = _num(metric, "scenario")
    delta = _num(metric, "change")
    if delta is None and None not in (baseline, scenario):
        delta = round(scenario - baseline, 2)

    # Değişmeyen kalemde "0 USD" yazmak okuyucuya bir hesap yapılmış gibi
    # gelir; "Değişmedi" ne olduğunu söyler.
    delta_text = "Değişmedi" if delta == 0 else _signed(delta, _fmt_usd)
    # Yüzdesel değişim de yazılır: "+612.000 USD" tek başına büyüklüğü
    # anlatmıyor, "%10" anlatıyor. İşaret zaten tutarda var; yüzde mutlak
    # değerle ve yön kelimesiyle yazılır ("%-21,1" okunmuyor).
    if delta and baseline:
        ratio = abs(delta / baseline * 100)
        direction = "artış" if delta > 0 else "azalış"
        delta_text += f" ({_fmt_percent(ratio)} {direction})"

    sentiment = "neutral"
    if delta:
        sentiment = "positive" if (delta > 0) == (good_when == "up") else "negative"

    return Component(
        type="kpi_card",
        id="kpi-" + metric["key"],
        title=title,
        icon=icon,
        span=12,
        unit="USD",
        value=_fmt_usd(scenario),
        value_number=scenario,
        baseline_label=_fmt_usd(baseline),
        scenario_label=_fmt_usd(scenario),
        delta_label=delta_text,
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
                "scenario": _addr(metric, "scenario"),
                "delta": _addr(metric, "change"),
            }.items() if v
        },
        source_metric_ids=_ids((metric, "baseline"), (metric, "scenario")),
        source_keys=[metric["key"]],
        formula=metric.get("formula"),
        note=metric.get("note"),
        aria_label=(
            f"{title}: mevcut {_fmt_usd(baseline)}, senaryo {_fmt_usd(scenario)}"
        ),
    )


def _salary_kpis(index: Dict[str, Dict[str, Any]]) -> List[Component]:
    """Sorulan bütün göstergeler: gider, net bütçe, oran, toplam harcama.

    Sıra sorunun sırasıdır. "Toplam personel gideri" ile "akademik personel
    gideri" AYRI kartlardır: yalnızca akademik gideri "toplam" diye
    etiketlemek yöneticiyi 2,09 milyon USD yanıltırdı.
    """
    cards: List[Component] = []

    cards.append(
        _money_kpi(
            index.get("annual_staff_cost"),
            title="Akademik personel gideri", icon="staff",
            caption="Zam yalnızca bu kaleme uygulandı", good_when="down",
        )
    )
    cards.append(
        _money_kpi(
            index.get("university_net_balance"),
            title="Net bütçe", icon="money",
            caption="Toplam gelir − toplam harcama", good_when="up",
        )
    )

    ratio = index.get("academic_personnel_expense_ratio")
    if ratio:
        baseline = _num(ratio, "baseline")
        scenario = _num(ratio, "scenario")
        delta = None if None in (baseline, scenario) else round(scenario - baseline, 2)
        cards.append(
            Component(
                type="kpi_card",
                id="kpi-" + ratio["key"],
                title="Personel gideri payı",
                icon="metric",
                span=12,
                unit="%",
                value=_fmt_percent(scenario),
                value_number=scenario,
                baseline_label=_fmt_percent(baseline),
                scenario_label=_fmt_percent(scenario),
                delta_label=_fmt_points(delta),
                trend=_trend(delta),
                sentiment="negative" if (delta or 0) > 0 else "positive",
                caption="Akademik gider / toplam harcama",
                level=(
                    "critical"
                    if (scenario or 0) >= RISK_THRESHOLDS["personnel_ratio_critical"]
                    else "warning"
                    if (scenario or 0) >= RISK_THRESHOLDS["personnel_ratio_warning"]
                    else None
                ),
                semantic_type=ratio.get("semantic_type"),
                scope_type=ratio.get("scope_type"),
                scope_name=ratio.get("scope_name"),
                data={"baseline": baseline, "scenario": scenario, "delta": delta},
                data_source_ids={
                    "baseline": _addr(ratio, "baseline"),
                    "scenario": _addr(ratio, "scenario"),
                    "delta": f"{_addr(ratio, 'scenario')}|{_addr(ratio, 'baseline')}",
                },
                source_metric_ids=_ids((ratio, "baseline"), (ratio, "scenario")),
                source_keys=[ratio["key"]],
                formula=ratio.get("formula"),
                aria_label=(
                    f"Personel gideri payı: mevcut yüzde {baseline}, "
                    f"senaryo yüzde {scenario}"
                ),
            )
        )

    cards.append(
        _money_kpi(
            index.get("total_expenditure"),
            title="Toplam kurum harcaması", icon="university",
            caption="Bütün gider kalemlerinin toplamı", good_when="down",
        )
    )
    cards.append(
        _money_kpi(
            index.get("administrative_staff_cost"),
            title="İdari personel gideri", icon="staff",
            caption="Bu senaryoda değişmedi", good_when="down",
        )
    )

    return [c for c in cards if c is not None][:5]


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


def _salary_risk_cards(index: Dict[str, Dict[str, Any]]) -> List[Component]:
    """Maaş senaryosunun kompakt risk kartları."""
    cards: List[Component] = []

    balance = index.get("university_net_balance")
    baseline_balance = _num(balance, "baseline")
    scenario_balance = _num(balance, "scenario")
    change = _num(balance, "change")
    if balance and scenario_balance is not None:
        drop = (
            (baseline_balance - scenario_balance) / abs(baseline_balance) * 100
            if baseline_balance else 0
        )
        level = (
            "critical" if scenario_balance < 0
            or drop >= RISK_THRESHOLDS["budget_drop_critical"]
            else "warning" if drop >= RISK_THRESHOLDS["budget_drop_warning"]
            else "info"
        )
        cards.append(
            Component(
                type="risk_summary_card",
                id="risk-balance",
                title="Net bütçe",
                icon="money",
                level=level,
                span=4,
                value=_signed(change, _fmt_usd),
                subtitle="Senaryonun bütçeye etkisi",
                caption=f"Senaryo sonrası: {_fmt_usd(scenario_balance)}",
                data={"change": change, "scenario": scenario_balance},
                data_source_ids={
                    k: v for k, v in {
                        "change": _addr(balance, "change"),
                        "scenario": _addr(balance, "scenario"),
                    }.items() if v
                },
                source_metric_ids=_ids((balance, "change"), (balance, "scenario")),
                source_keys=[balance["key"]],
                aria_label=(
                    f"Net bütçe riski {LEVEL_LABELS[level].lower()}. Etki "
                    f"{_signed(change, _fmt_usd)}"
                ),
            )
        )

    ratio = index.get("total_personnel_expense_ratio") or index.get(
        "academic_personnel_expense_ratio"
    )
    if ratio and _num(ratio, "scenario") is not None:
        value = _num(ratio, "scenario")
        level = (
            "critical" if value >= RISK_THRESHOLDS["personnel_ratio_critical"]
            else "warning" if value >= RISK_THRESHOLDS["personnel_ratio_warning"]
            else "info"
        )
        cards.append(
            Component(
                type="risk_summary_card",
                id="risk-personnel-ratio",
                # Başlık metriğin KENDİ etiketinden gelir: akademik payı ile
                # toplam payı aynı başlıkla göstermek yanıltırdı.
                title=ratio.get("label", "Personel gideri payı"),
                icon="staff",
                level=level,
                span=4,
                value=_fmt_percent(value),
                subtitle="Toplam harcama içindeki pay",
                caption=f"Mevcut: {_fmt_percent(_num(ratio, 'baseline'))}",
                data={"baseline": _num(ratio, "baseline"), "scenario": value},
                data_source_ids={
                    "baseline": _addr(ratio, "baseline"),
                    "scenario": _addr(ratio, "scenario"),
                },
                source_metric_ids=_ids((ratio, "baseline"), (ratio, "scenario")),
                source_keys=[ratio["key"]],
                aria_label=(
                    f"Personel gideri payı riski {LEVEL_LABELS[level].lower()}. "
                    f"Senaryo yüzde {value}"
                ),
            )
        )

    cost = index.get("annual_staff_cost")
    if cost and _num(cost, "change"):
        cards.append(
            Component(
                type="risk_summary_card",
                id="risk-staff-cost",
                title="Akademik personel gideri",
                icon="metric",
                level="warning",
                span=4,
                value=_signed(_num(cost, "change"), _fmt_usd),
                subtitle="Yıllık ek yük",
                caption=f"Senaryo sonrası: {_fmt_usd(_num(cost, 'scenario'))}",
                data={"change": _num(cost, "change"), "scenario": _num(cost, "scenario")},
                data_source_ids={
                    "change": _addr(cost, "change"),
                    "scenario": _addr(cost, "scenario"),
                },
                source_metric_ids=_ids((cost, "change"), (cost, "scenario")),
                source_keys=[cost["key"]],
                aria_label=(
                    "Akademik personel gideri riski yüksek. Yıllık ek yük "
                    + _signed(_num(cost, "change"), _fmt_usd)
                ),
            )
        )

    order = {"critical": 0, "warning": 1, "info": 2}
    cards.sort(key=lambda c: order.get(c.level or "info", 3))
    return cards[:3]


def _salary_decisions(index: Dict[str, Dict[str, Any]]) -> List[str]:
    """Maaş senaryosunun karar maddeleri."""
    items: List[str] = []

    cost_change = _num(index.get("annual_staff_cost"), "change")
    if cost_change:
        items.append(
            f"Bütçe: Yıllık {_fmt_usd(abs(cost_change))} ek personel gideri için "
            "kaynak planlanmalı."
        )

    balance = index.get("university_net_balance")
    scenario_balance = _num(balance, "scenario")
    if scenario_balance is not None:
        items.append(
            "Net bütçe: Senaryo sonrası bütçe açık veriyor; gelir artırıcı "
            "önlem gerekiyor."
            if scenario_balance < 0
            else f"Net bütçe: {_fmt_usd(scenario_balance)} ile pozitif kalıyor; "
                 "zam bütçeyi açığa düşürmüyor."
        )

    ratio = index.get("academic_personnel_expense_ratio")
    if ratio and _num(ratio, "scenario") is not None:
        items.append(
            "Personel payı: Akademik gider payı "
            + _fmt_percent(_num(ratio, "baseline")) + " → "
            + _fmt_percent(_num(ratio, "scenario"))
            + "; eşik takibi sürdürülmeli."
        )

    items.append(
        "Kapsam: Yan haklar, işveren yükleri ve ek ders ödemeleri bu hesaba "
        "dâhil değildir."
    )
    return items[:4]


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


def _scenario_scope_box(structured: Dict[str, Any]) -> Optional[Component]:
    """Grafiğin yanındaki görünür kapsam/uyarı kutusu.

    ÖĞRENCİ ARTIŞI: hesaplanmayan personel ve yatırım maliyetleri.
    MAAŞ SENARYOSU: neyin sabit tutulduğu ve neyin kapsam dışı olduğu.
    İki senaryoya aynı kutuyu koymak, olmayan bir maliyeti varmış gibi
    göstermek olurdu.
    """
    result_type = structured.get("type")

    if result_type == "staff_salary_scenario":
        items = list(structured.get("assumptions", []) or [])
        if not items:
            return None
        return Component(
            type="information_box",
            id="scenario-assumptions",
            level="info",
            icon="assumption",
            span=6,
            title="Senaryonun kapsamı",
            items=items,
            note=(
                "Bu değerler yalnızca akademik maaş artışının etkisidir; "
                "kadro sayısı ve idari maaşlar sabit tutulmuştur."
            ),
            aria_label="Senaryonun kapsamı ve varsayımları",
        )

    if result_type == "enrollment_change_scenario":
        return Component(
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

    return None


def _assumptions_for(structured: Dict[str, Any]) -> List[str]:
    """Senaryonun KENDİ varsayımları.

    "Ek personel alımı ve fiziksel yatırım maliyetleri hesaplanmadı" uyarısı
    ÖĞRENCİ ARTIŞI senaryosuna aittir: orada yeni öğrenciler yeni kadro ve
    yeni derslik gerektirir. Maaş senaryosunda kadro da mekân da sabittir;
    o uyarıyı göstermek kullanıcıyı olmayan bir maliyete yönlendirirdi.
    """
    declared = list(structured.get("assumptions", []) or [])
    if declared:
        return declared
    if structured.get("type") == "enrollment_change_scenario":
        return UNCALCULATED_COSTS + [COST_EXCLUSION_WARNING]
    return []


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
        items=list(structured.get("notes", []) or []) + _assumptions_for(structured),
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

    # ------------------------------------------------------------------
    # KATALOG KIRILIMI → GRAFİK
    # ------------------------------------------------------------------
    # Bu dosya senaryo sonucu şekline göre yazılmıştı: her metrikte
    # `baseline` / `scenario` / `change` alanları beklenir. Veri kataloğu
    # ise bambaşka bir şekil üretir — metrik altında `rows` listesi ve her
    # satırda bir birim ile değeri:
    #
    #     {"key": "student_count",
    #      "rows": [{"label": "MÜHENDİSLİK…", "value": 803}, …]}
    #
    # `_index()` bu şekli okuyamadığı için katalogla cevaplanan HİÇBİR
    # soruda bileşen üretilmiyordu; pencere açılıyor ama içi boş kalıyordu.
    # Aşağıdaki dal o boşluğu kapatır: birim kırılımı olan her sonuç —
    # araçtan da gelse katalogdan da gelse — çubuk grafiğe dönüşür.
    if _katalog_sekli(structured):
        return _katalog_spec(
            structured,
            data_sources=data_sources,
            calculated_at=calculated_at,
            interpretation=interpretation,
        )

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
        cost = index.get("annual_staff_cost")
        change = _num(cost, "change")
        base = _num(cost, "baseline")
        percent = f"%{round(change / base * 100)}" if change and base else ""
        title = (
            f"Akademik Personel Maaş Senaryosu — {percent} Zam"
            if percent else "Akademik Personel Maaş Senaryosu"
        )
        kpis = _salary_kpis(index)
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

        # Şelalenin yanındaki kutu SENARYOYA GÖRE değişir. Öğrenci artışında
        # hesaplanmayan yatırım maliyetleri uyarısı, maaş senaryosunda ise
        # neyin sabit tutulduğunu söyleyen varsayım kutusu gösterilir.
        if any(c.type == "waterfall_chart" for c in charts):
            box = _scenario_scope_box(structured)
            if box is not None:
                components.append(box)
        sections.append(Section(type="chart_grid", components=components))

    risks = (
        _salary_risk_cards(index)
        if result_type == "staff_salary_scenario"
        else _risk_cards(index)
    )
    if risks:
        sections.append(
            Section(type="risk_summary", title="En Kritik Riskler", components=risks)
        )

    decisions = (
        _salary_decisions(index)
        if result_type == "staff_salary_scenario"
        else _decisions(index)
    )
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
