"""Deterministic Derivation Registry for Executive AI Decision Support.

Architecture:
REQUESTED CONCEPT
→ direct metric exists?
→ if not, is it derivable from available trusted metrics?
→ determine required inputs
→ retrieve required inputs
→ calculate deterministically (no eval(), closed Python functions)
→ continue analysis / visualization

Only declare "data unavailable" if:
1. no direct trusted metric exists
AND
2. no valid derivation is possible from available trusted inputs.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)


@dataclass
class DerivationRule:
    key: str
    label: str
    unit: str
    measure_type: str  # "ratio", "percentage", "count", "currency"
    additive: bool  # False for ratios/percentages; True for counts
    required_inputs: List[str]  # Raw metric keys in data catalog
    calculate: Callable[..., Optional[float]]
    patterns: List[re.Pattern]
    description: str = ""
    formula_template: str = ""


# ---------------------------------------------------------------------------
# Closed Deterministic Formulas (NO eval())
# ---------------------------------------------------------------------------

def _calc_students_per_academic(inputs: Dict[str, Any]) -> Optional[float]:
    st = inputs.get("student_count")
    stf = inputs.get("academic_staff_count")
    if st is None or stf is None or stf <= 0:
        return None
    return round(float(st) / float(stf), 1)


def _calc_academics_per_student(inputs: Dict[str, Any]) -> Optional[float]:
    stf = inputs.get("academic_staff_count")
    st = inputs.get("student_count")
    if stf is None or st is None or st <= 0:
        return None
    return round(float(stf) / float(st), 4)


def _calc_academics_per_100_students(inputs: Dict[str, Any]) -> Optional[float]:
    stf = inputs.get("academic_staff_count")
    st = inputs.get("student_count")
    if stf is None or st is None or st <= 0:
        return None
    return round(float(stf) / float(st) * 100.0, 2)


def _calc_unused_capacity(inputs: Dict[str, Any]) -> Optional[float]:
    cap = inputs.get("total_capacity")
    st = inputs.get("student_count")
    if cap is None or st is None:
        return None
    return float(max(int(cap) - int(st), 0))


def _calc_capacity_excess(inputs: Dict[str, Any]) -> Optional[float]:
    st = inputs.get("student_count")
    cap = inputs.get("total_capacity")
    if st is None or cap is None:
        return None
    return float(max(int(st) - int(cap), 0))


def _calc_capacity_utilization(inputs: Dict[str, Any]) -> Optional[float]:
    st = inputs.get("student_count")
    cap = inputs.get("total_capacity")
    if st is None or cap is None or cap <= 0:
        return None
    return round(float(st) / float(cap) * 100.0, 1)


def _calc_peer_difference_percent(inputs: Dict[str, Any]) -> Optional[float]:
    st = inputs.get("student_count")
    atl = inputs.get("yokatlas_total_students")
    if st is None or atl is None or atl <= 0:
        return None
    return round((float(st) - float(atl)) / float(atl) * 100.0, 1)


def _calc_peer_difference(inputs: Dict[str, Any]) -> Optional[float]:
    st = inputs.get("student_count")
    atl = inputs.get("yokatlas_total_students")
    if st is None or atl is None:
        return None
    return float(int(st) - int(atl))


# ---------------------------------------------------------------------------
# Registered Derivation Rules
# ---------------------------------------------------------------------------

DERIVATION_RULES: Dict[str, DerivationRule] = {
    "academics_per_100_students": DerivationRule(
        key="academics_per_100_students",
        label="100 Öğrenci Başına Akademisyen",
        unit="akademisyen / 100 öğrenci",
        measure_type="ratio",
        additive=False,
        required_inputs=["academic_staff_count", "student_count"],
        calculate=_calc_academics_per_100_students,
        patterns=[
            re.compile(r"100\s*öğrenci(?:ye|de| başına)?\s*(?:kaç\s*)?akademisyen", re.I),
            re.compile(r"yüz\s*öğrenciye\s*(?:kaç\s*)?akademisyen", re.I),
            re.compile(r"100\s*öğrenci\s*başına\s*(?:düşen\s*)?(?:akademisyen|hoca|öğretim\s*üyesi)", re.I),
        ],
        description="100 kayıtlı öğrenci başına düşen akademik personel sayısı.",
        formula_template="({academic_staff_count} / {student_count}) * 100",
    ),
    "academics_per_student": DerivationRule(
        key="academics_per_student",
        label="Akademisyen / Öğrenci Oranı",
        unit="akademisyen/öğrenci",
        measure_type="ratio",
        additive=False,
        required_inputs=["academic_staff_count", "student_count"],
        calculate=_calc_academics_per_student,
        patterns=[
            re.compile(r"akademisyen\s*/\s*öğrenci", re.I),
            re.compile(r"akademisyen\s*öğrenci\s*oran", re.I),
            re.compile(r"öğrenci\s+başına\s+(?:düşen\s+)?akademisyen", re.I),
            re.compile(r"öğrenci\s+başına\s+kaç\s+akademisyen", re.I),
        ],
        description="Öğrenci başına düşen akademik personel oranı.",
        formula_template="{academic_staff_count} / {student_count}",
    ),
    "students_per_academic": DerivationRule(
        key="students_per_academic",
        label="Öğrenci / Akademisyen Oranı",
        unit="öğrenci/akademisyen",
        measure_type="ratio",
        additive=False,
        required_inputs=["student_count", "academic_staff_count"],
        calculate=_calc_students_per_academic,
        patterns=[
            re.compile(r"öğrenci\s*/\s*akademisyen", re.I),
            re.compile(r"öğrenci\s*akademisyen\s*oran", re.I),
            re.compile(r"öğrenci\s*ve\s*akademisyen\s*oran", re.I),
            re.compile(r"akademisyen\s+başına\s+(?:düşen\s+)?öğrenci", re.I),
            re.compile(r"hoca\s+başına\s+(?:düşen\s+)?öğrenci", re.I),
            re.compile(r"akademik\s*(?:personel\s*)?yükü?|yük\s*yoğunluğu", re.I),
            re.compile(r"öğretim\s+üyesi\s+başına\s+öğrenci", re.I),
        ],
        description="Akademisyen başına düşen öğrenci yükü.",
        formula_template="{student_count} / {academic_staff_count}",
    ),
    "unused_capacity": DerivationRule(
        key="unused_capacity",
        label="Boş Kapasite",
        unit="koltuk",
        measure_type="count",
        additive=True,
        required_inputs=["total_capacity", "student_count"],
        calculate=_calc_unused_capacity,
        patterns=[
            re.compile(r"boş\s+kapasite", re.I),
            re.compile(r"kullanılmayan\s+kapasite", re.I),
            re.compile(r"atıl\s+kapasite", re.I),
            re.compile(r"kalan\s+kapasite", re.I),
            re.compile(r"boş\s+(?:yer|koltuk)", re.I),
            re.compile(r"kapasite\s+boşluğu", re.I),
        ],
        description="Fiziksel kapasiteden öğrenci sayısı çıkarılarak kalan boş koltuk sayısı.",
        formula_template="max({total_capacity} - {student_count}, 0)",
    ),
    "capacity_excess": DerivationRule(
        key="capacity_excess",
        label="Kapasite Aşımı / Ek İhtiyaç",
        unit="öğrenci",
        measure_type="count",
        additive=True,
        required_inputs=["student_count", "total_capacity"],
        calculate=_calc_capacity_excess,
        patterns=[
            re.compile(r"kapasite\s+aşım", re.I),
            re.compile(r"kapasiteyi\s+aşan", re.I),
            re.compile(r"kapasite\s+fazlası", re.I),
            re.compile(r"ek\s+(?:derslik|koltuk|kapasite)\s*ihtiyac", re.I),
            re.compile(r"kapasite\s+ne\s+kadar\s+aşılmış", re.I),
        ],
        description="Fiziksel kapasiteyi aşan öğrenci sayısı.",
        formula_template="max({student_count} - {total_capacity}, 0)",
    ),
    "capacity_utilization": DerivationRule(
        key="capacity_utilization",
        label="Fiziksel Kapasite Kullanım Oranı",
        unit="%",
        measure_type="percentage",
        additive=False,
        required_inputs=["student_count", "total_capacity"],
        calculate=_calc_capacity_utilization,
        patterns=[
            re.compile(r"kapasite\s+kullanım(?:ı|\s*oranı)?", re.I),
            re.compile(r"fiziksel\s+doluluk", re.I),
            re.compile(r"fiziksel\s+kapasiteye\s+yaklaşım", re.I),
        ],
        description="Öğrenci sayısının toplam fiziksel koltuk kapasitesine oranı.",
        formula_template="({student_count} / {total_capacity}) * 100",
    ),
    "peer_difference_percent": DerivationRule(
        key="peer_difference_percent",
        label="YÖK Atlas Medyan Farkı (%)",
        unit="%",
        measure_type="percentage",
        additive=False,
        required_inputs=["student_count", "yokatlas_total_students"],
        calculate=_calc_peer_difference_percent,
        patterns=[
            re.compile(r"(?:atlas|yök\s*atlas|medyan|benzer\s*program).*(?:yüzde\s*kaç\s*(?:fark|farklı|düşük|yüksek)|yüzde\s*fark)", re.I),
            re.compile(r"yüzde\s*kaç\s*(?:fark|farklı).*(?:atlas|yök\s*atlas|medyan)", re.I),
        ],
        description="Program öğrenci sayısının YÖK Atlas medyanına göre yüzdesel farkı.",
        formula_template="({student_count} - {yokatlas_total_students}) / {yokatlas_total_students} * 100",
    ),
    "peer_difference": DerivationRule(
        key="peer_difference",
        label="YÖK Atlas Sayısal Farkı",
        unit="öğrenci",
        measure_type="count",
        additive=False,
        required_inputs=["student_count", "yokatlas_total_students"],
        calculate=_calc_peer_difference,
        patterns=[
            re.compile(r"(?:atlas|yök\s*atlas|medyan|benzer\s*program).*(?:kaç\s*öğrenci\s*fark|sayısal\s*fark|farkı\s*kaç)", re.I),
        ],
        description="Program öğrenci sayısının YÖK Atlas medyanından kişi bazında farkı.",
        formula_template="{student_count} - {yokatlas_total_students}",
    ),
}


def resolve_derived_metric(message: str) -> Optional[DerivationRule]:
    """Resolves a natural language analytical concept to its canonical derivation rule."""
    if not message:
        return None
    norm = message.strip().lower()
    for rule in DERIVATION_RULES.values():
        for pat in rule.patterns:
            if pat.search(norm):
                return rule
    return None


def resolve_all_derived_metrics(message: str) -> List[DerivationRule]:
    """Finds all distinct derivable metrics referenced in a message."""
    if not message:
        return []
    norm = message.strip().lower()
    found: List[DerivationRule] = []
    seen_keys = set()
    for rule in DERIVATION_RULES.values():
        for pat in rule.patterns:
            if pat.search(norm) and rule.key not in seen_keys:
                found.append(rule)
                seen_keys.add(rule.key)
                break
    return found
