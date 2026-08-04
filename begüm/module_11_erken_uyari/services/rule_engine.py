"""Modül 11 — Risk ve Erken Uyarı kural motoru.

PDF Bölüm 11, üst yönetime KURUM/PROGRAM düzeyinde alarm üretilmesini ister
(bir programın doluluğu eşiğin altına düştüğünde, öğrenci kaybı arttığında vb.),
tek tek öğrencilerin uyarılmasını değil. Bu motor o seviyede çalışır.

TASARIM
-------
Kurallar koda gömülü değildir; `config/rules.json` dosyasında tanımlıdır. Her kural
bir eşik seti, bir kapsam (program/kurum) ve bir önerilen aksiyon taşır. Böylece
PDF'in "senior management shall be able to define additional scenarios" beklentisi
karşılanır: yeni kural eklemek için JSON'a kayıt eklemek yeterlidir.

Diğer modüllerin verisini bekleyen kurallar (bütçe açığı, kapasite yetersizliği,
akreditasyon süresi vb.) `implemented: false` olarak tanımlıdır; motor bunları
çalıştırmaz ama `get_pending_rules()` ile raporlar. Böylece PDF kapsamının tamamı
görünür kalır, hangi alarmın hangi modüle bağlı olduğu belli olur.
"""

import json
from pathlib import Path
from typing import Callable, Dict, List, Optional

from sqlalchemy.orm import Session

from module_03_ogrenci_analitigi.services import student_analytics_service as analytics
from module_07_surdurulebilirlik.services import sustainability_service as sustainability

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "rules.json"

SEVERITY_ORDER = {"kritik": 0, "yuksek": 1, "orta": 2, "dusuk": 3}


def load_rules() -> Dict:
    """Kural tanımlarını dosyadan okur."""
    with CONFIG_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def _previous_academic_year(academic_year: str) -> str:
    """'2026-2027' -> '2025-2026'."""
    start = int(academic_year.split("-")[0])
    return f"{start - 1}-{start}"


def _severity_when_below(value: float, thresholds: Dict) -> Optional[str]:
    """Küçük değerin kötü olduğu göstergeler için önem derecesi belirler."""
    for level in ("kritik", "yuksek", "orta"):
        if level in thresholds and value <= thresholds[level]:
            return level
    return None


def _severity_when_above(value: float, thresholds: Dict) -> Optional[str]:
    """Büyük değerin kötü olduğu göstergeler için önem derecesi belirler."""
    for level in ("kritik", "yuksek", "orta"):
        if level in thresholds and value >= thresholds[level]:
            return level
    return None


def _alert(
    rule: Dict,
    severity: str,
    scope_code: str,
    scope_name: str,
    academic_year: str,
    message: str,
    observed_value: float,
    threshold_value: Optional[float],
) -> Dict:
    """Standart alarm kaydı üretir."""
    return {
        "rule_key": rule["key"],
        "rule_name": rule["name"],
        "pdf_condition": rule["pdf_condition"],
        "severity": severity,
        "scope": rule["scope"],
        "scope_code": scope_code,
        "scope_name": scope_name,
        "academic_year": academic_year,
        "message": message,
        "observed_value": round(observed_value, 2),
        "threshold_value": threshold_value,
        "recommended_action": rule["recommended_action"],
        "data_source": rule["data_source"],
    }


# ---------------------------------------------------------------------------
# KURAL DEĞERLENDİRİCİLERİ
# Her fonksiyon bir kuralı tüm kapsamlar üzerinde çalıştırır ve alarm listesi döner.
# ---------------------------------------------------------------------------


def _rule_program_occupancy_low(rule: Dict, ctx: Dict) -> List[Dict]:
    """Doluluk oranı eşiğin altına düşen programlar için alarm üretir."""
    alerts = []
    for metrics in ctx["current_metrics"]:
        value = metrics["occupancy_rate"]
        severity = _severity_when_below(value, rule["thresholds"])
        if severity is None:
            continue
        alerts.append(
            _alert(
                rule,
                severity,
                metrics["program_code"],
                metrics["program_name"],
                ctx["academic_year"],
                f"{metrics['program_name']} programının doluluk oranı %{value} "
                f"({metrics['enrolled_student_count']}/{metrics['quota']}).",
                value,
                rule["thresholds"][severity],
            )
        )
    return alerts


def _rate_increase_rule(rule: Dict, ctx: Dict, rate_key: str, label: str) -> List[Dict]:
    """Bir oranın önceki yıla göre artışını değerlendiren ortak mantık."""
    alerts = []
    thresholds = rule["thresholds"]
    min_rate = thresholds.get("min_rate", 0)

    for metrics in ctx["current_metrics"]:
        code = metrics["program_code"]
        previous = ctx["previous_metrics"].get(code)
        if previous is None:
            continue

        current_rate = metrics[rate_key]
        previous_rate = previous[rate_key]

        # Çok küçük oranlardaki dalgalanmalar alarm üretmemeli.
        if current_rate < min_rate or previous_rate <= 0:
            continue

        relative_increase = (current_rate - previous_rate) / previous_rate * 100
        severity = _severity_when_above(relative_increase, thresholds)
        if severity is None:
            continue

        alerts.append(
            _alert(
                rule,
                severity,
                code,
                metrics["program_name"],
                ctx["academic_year"],
                f"{metrics['program_name']} programında {label} "
                f"%{previous_rate} → %{current_rate} "
                f"(göreli artış %{round(relative_increase, 1)}).",
                relative_increase,
                thresholds[severity],
            )
        )
    return alerts


def _rule_attrition_increase(rule: Dict, ctx: Dict) -> List[Dict]:
    """Öğrenci kaybı oranı artan programlar için alarm üretir."""
    return _rate_increase_rule(rule, ctx, "attrition_rate", "öğrenci kaybı oranı")


def _rule_non_renewal_increase(rule: Dict, ctx: Dict) -> List[Dict]:
    """Kayıt yenilememe oranı artan programlar için alarm üretir."""
    return _rate_increase_rule(rule, ctx, "non_renewal_rate", "kayıt yenilememe oranı")


def _rule_academic_performance_decline(rule: Dict, ctx: Dict) -> List[Dict]:
    """Ortalama GNO'su düşen programlar için alarm üretir."""
    alerts = []
    for trend in ctx["performance_trends"]:
        change = trend["gpa_change"]
        severity = _severity_when_below(change, rule["thresholds"])
        if severity is None:
            continue
        first = trend["series"][0]
        last = trend["series"][-1]
        alerts.append(
            _alert(
                rule,
                severity,
                trend["program_code"],
                trend["program_name"],
                ctx["academic_year"],
                f"{trend['program_name']} programında ortalama dönem GNO'su "
                f"{first['average_semester_gpa']} ({first['academic_year']}) → "
                f"{last['average_semester_gpa']} ({last['academic_year']}) seviyesine düştü.",
                change,
                rule["thresholds"][severity],
            )
        )
    return alerts


def _rule_admission_score_below_national(rule: Dict, ctx: Dict) -> List[Dict]:
    """Taban puanı Türkiye ortalamasının altında kalan programlar için alarm üretir."""
    alerts = []
    for metrics in ctx["current_metrics"]:
        gap = metrics["national_score_gap"]
        if gap is None:
            continue
        severity = _severity_when_below(gap, rule["thresholds"])
        if severity is None:
            continue
        alerts.append(
            _alert(
                rule,
                severity,
                metrics["program_code"],
                metrics["program_name"],
                ctx["academic_year"],
                f"{metrics['program_name']} taban puanı {metrics['minimum_admission_score']}, "
                f"Türkiye ortalamasının {abs(round(gap, 1))} puan altında.",
                gap,
                rule["thresholds"][severity],
            )
        )
    return alerts


def _rule_demand_sharp_decline(rule: Dict, ctx: Dict) -> List[Dict]:
    """Doluluk oranı yıllar içinde keskin düşen programlar için alarm üretir."""
    alerts = []
    for trend in ctx["demand_trends"]:
        change = trend["occupancy_change_points"]
        severity = _severity_when_below(change, rule["thresholds"])
        if severity is None:
            continue
        first = trend["series"][0]
        last = trend["series"][-1]
        alerts.append(
            _alert(
                rule,
                severity,
                trend["program_code"],
                trend["program_name"],
                ctx["academic_year"],
                f"{trend['program_name']} doluluk oranı %{first['occupancy_rate']} "
                f"({first['academic_year']}) → %{last['occupancy_rate']} "
                f"({last['academic_year']}) — {abs(change)} puan düşüş.",
                change,
                rule["thresholds"][severity],
            )
        )
    return alerts


def _rule_sustainability_score_low(rule: Dict, ctx: Dict) -> List[Dict]:
    """Sürdürülebilirlik puanı düşük programlar için alarm üretir."""
    alerts = []
    for result in ctx["sustainability"]:
        score = result["sustainability_score"]
        severity = _severity_when_below(score, rule["thresholds"])
        if severity is None:
            continue
        alerts.append(
            _alert(
                rule,
                severity,
                result["program_code"],
                result["program_name"],
                ctx["academic_year"],
                f"{result['program_name']} sürdürülebilirlik puanı {score} "
                f"(kategori: {result['category']}). "
                f"Puan %{result['data_completeness_percent']} veri tamlığıyla hesaplandı.",
                score,
                rule["thresholds"][severity],
            )
        )
    return alerts


def _rule_university_occupancy_low(rule: Dict, ctx: Dict) -> List[Dict]:
    """Üniversite geneli doluluk oranı için alarm üretir."""
    overview = ctx["overview"]
    value = overview["overall_occupancy_rate"]
    severity = _severity_when_below(value, rule["thresholds"])
    if severity is None:
        return []
    return [
        _alert(
            rule,
            severity,
            "UNIVERSITE",
            "Üniversite geneli",
            ctx["academic_year"],
            f"Üniversite geneli doluluk oranı %{value} "
            f"({overview['total_enrolled_student_count']}/{overview['total_quota']}).",
            value,
            rule["thresholds"][severity],
        )
    ]


# Kural anahtarı -> değerlendirici eşlemesi.
RULE_EVALUATORS: Dict[str, Callable[[Dict, Dict], List[Dict]]] = {
    "program_occupancy_low": _rule_program_occupancy_low,
    "attrition_rate_increase": _rule_attrition_increase,
    "non_renewal_rate_increase": _rule_non_renewal_increase,
    "academic_performance_decline": _rule_academic_performance_decline,
    "admission_score_below_national": _rule_admission_score_below_national,
    "demand_sharp_decline": _rule_demand_sharp_decline,
    "sustainability_score_low": _rule_sustainability_score_low,
    "university_occupancy_low": _rule_university_occupancy_low,
}


def _build_context(db: Session, academic_year: str) -> Dict:
    """Kuralların ihtiyaç duyduğu tüm veriyi tek seferde hazırlar."""
    previous_year = _previous_academic_year(academic_year)
    available = analytics.get_available_academic_years(db)

    previous_metrics = {}
    if previous_year in available:
        previous_metrics = {
            m["program_code"]: m
            for m in analytics.get_program_metrics(db, previous_year)
        }

    return {
        "academic_year": academic_year,
        "previous_academic_year": previous_year if previous_year in available else None,
        "current_metrics": analytics.get_program_metrics(db, academic_year),
        "previous_metrics": previous_metrics,
        "overview": analytics.get_university_overview(db, academic_year),
        "demand_trends": analytics.get_demand_trends(db),
        "performance_trends": analytics.get_academic_performance_trend(db),
        "sustainability": sustainability.evaluate_all(db, academic_year),
    }


def evaluate(
    db: Session,
    academic_year: str,
    severity_filter: Optional[str] = None,
    program_code: Optional[str] = None,
) -> List[Dict]:
    """Tüm uygulanmış kuralları çalıştırır ve alarmları önem sırasına göre döndürür."""
    config = load_rules()
    ctx = _build_context(db, academic_year)

    alerts: List[Dict] = []
    for rule in config["rules"]:
        if not rule.get("implemented"):
            continue
        evaluator = RULE_EVALUATORS.get(rule["key"])
        if evaluator is None:
            continue
        alerts.extend(evaluator(rule, ctx))

    if severity_filter:
        alerts = [a for a in alerts if a["severity"] == severity_filter]
    if program_code:
        alerts = [a for a in alerts if a["scope_code"].upper() == program_code.upper()]

    return sorted(
        alerts,
        key=lambda a: (SEVERITY_ORDER.get(a["severity"], 99), a["scope_code"]),
    )


def summarize(alerts: List[Dict]) -> Dict:
    """Alarmları önem derecesi ve kapsam bazında özetler (yönetici paneli için)."""
    by_severity: Dict[str, int] = {}
    by_program: Dict[str, int] = {}

    for alert in alerts:
        by_severity[alert["severity"]] = by_severity.get(alert["severity"], 0) + 1
        by_program[alert["scope_code"]] = by_program.get(alert["scope_code"], 0) + 1

    riskiest = sorted(by_program.items(), key=lambda item: item[1], reverse=True)

    return {
        "total_alerts": len(alerts),
        "by_severity": by_severity,
        "by_scope": by_program,
        "most_at_risk": [
            {"scope_code": code, "alert_count": count} for code, count in riskiest[:5]
        ],
    }


def get_rule_catalog() -> List[Dict]:
    """Tanımlı tüm kuralları (uygulanmış ve bekleyen) listeler."""
    config = load_rules()
    return [
        {
            "key": rule["key"],
            "name": rule["name"],
            "pdf_condition": rule["pdf_condition"],
            "scope": rule["scope"],
            "implemented": rule.get("implemented", False),
            "data_source": rule["data_source"],
            "thresholds": rule.get("thresholds", {}),
        }
        for rule in config["rules"]
    ]


def get_pending_rules() -> List[Dict]:
    """Henüz veri kaynağı bağlanmamış kuralları döndürür."""
    return [rule for rule in get_rule_catalog() if not rule["implemented"]]
