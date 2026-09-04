"""General Turn-Level Analytical Orchestrator for Executive AI Decision Support.

Reasoning Principles:
1. UNDERSTAND CURRENT REQUEST (Objective, explicit entities, requested metrics, time period).
2. DECIDE RELATION TO HISTORY (new_analysis, follow_up, finding_reference, visual_revision).
3. PLAN ANALYSIS (Scope, required data dimensions, calculations, hierarchy necessity).
4. DISCOVER & RETRIEVE GROUNDED DATA (Trusted catalog services).
5. EXECUTE DERIVED CALCULATIONS & SYNTHESIS (Deterministic math).
6. DESIGN VISUALIZATION (Based on data structure & question).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple
from sqlalchemy.orm import Session

from app.services.assistant import derivation_registry, entity_resolver

logger = logging.getLogger(__name__)


class TurnRelation(str, Enum):
    NEW_ANALYSIS = "new_analysis"
    FOLLOW_UP = "follow_up"
    FINDING_REFERENCE = "finding_reference"
    VISUAL_REVISION = "visual_revision"
    SCENARIO_FOLLOW_UP = "scenario_follow_up"
    CLARIFICATION = "clarification"


@dataclass
class TurnPlan:
    relation: TurnRelation
    objective: str
    explicit_entities: List[Any] = field(default_factory=list)
    inherited_entities: List[Dict[str, Any]] = field(default_factory=list)
    scope_strategy: str = "current_scope"  # "explicit", "dashboard_scope", "university"
    academic_year: str = "2025-2026"
    requested_metrics: List[str] = field(default_factory=list)
    additional_metrics_to_consider: List[str] = field(default_factory=list)
    requested_derived_rules: List[str] = field(default_factory=list)
    required_inputs: List[str] = field(default_factory=list)
    hierarchy_needed: bool = False
    parent_level: Optional[str] = None
    child_level: Optional[str] = None
    calculations: List[str] = field(default_factory=list)
    visual_goal: str = "none"  # "none", "ranked_hbar", "stacked_composition", "benchmark_grouped", "bubble", "grouped_comparison"
    needs_visualization: bool = False
    reference_finding_ids: List[int] = field(default_factory=list)
    is_scenario: bool = False
    notes: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "relation": self.relation.value,
            "objective": self.objective,
            "explicit_entities": [e.as_dict() if hasattr(e, "as_dict") else str(e) for e in self.explicit_entities],
            "inherited_entities": self.inherited_entities,
            "scope_strategy": self.scope_strategy,
            "academic_year": self.academic_year,
            "requested_metrics": self.requested_metrics,
            "additional_metrics_to_consider": self.additional_metrics_to_consider,
            "requested_derived_rules": self.requested_derived_rules,
            "required_inputs": self.required_inputs,
            "hierarchy_needed": self.hierarchy_needed,
            "parent_level": self.parent_level,
            "child_level": self.child_level,
            "calculations": self.calculations,
            "visual_goal": self.visual_goal,
            "needs_visualization": self.needs_visualization,
            "reference_finding_ids": self.reference_finding_ids,
            "is_scenario": self.is_scenario,
            "notes": self.notes,
        }




# ---------------------------------------------------------------------------
# Pattern Definitions
# ---------------------------------------------------------------------------

_CONTEXT_OVERRIDE_PATTERNS = re.compile(
    r"boşver|bosver|bunu\s+geç|yeni\s+soru|bırak|farklı\s+bir\s+konu|sıfırla",
    re.IGNORECASE,
)

_FINDING_REFERENCE_PATTERNS = re.compile(
    r"ikinci\s*(?:bulgu|madde|konu|sıkıntı)|2\.\s*(?:bulgu|madde)|"
    r"üçüncü\s*(?:bulgu|madde|konu|sıkıntı)|3\.\s*(?:bulgu|madde)|"
    r"ilk\s*(?:bulgu|madde|konu|sıkıntı)|1\.\s*(?:bulgu|madde)|"
    r"diğer\s*(?:2|iki)?\s*(?:sıkıntı|sorun|madde|bulgu|konu)|son\s*(?:2|ikisi)|kalan\s*(?:2|ikisi)",
    re.IGNORECASE,
)

_VISUAL_REVISION_PATTERNS = re.compile(
    r"en\s+büyük\s+bölümleri\s+öne\s+çıkar|büyük\s+bölümleri\s+öne\s+çıkar|büyükleri\s+vurgula|"
    r"bu\s+görsel\s+çok\s+kalabalık|daha\s+sade.*görsel|başka\s+bir\s+görsel\s+tasarla|daha\s+sade\s+tasarla|"
    r"aynı\s+bilgiyi\s+koruyan\s+başka|sadece\s+en\s+büyük",
    re.IGNORECASE,
)

_TRUE_FOLLOW_UP_PATTERNS = re.compile(
    r"aynı\s+(?:karşılaştırma|kıyaslama|birimler|bölümler|fakülteler|grafik)|"
    r"buna\s+ek\s+olarak|ayrıca|bir\s+de\s+.*oranını|oranını\s+da\s+görmek|oranı\s+açısından\s+göster|"
    r"bu\s+karşılaştırmada|aynı\s+kapsamda",
    re.IGNORECASE,
)

_TOTAL_STUDENTS_PATTERNS = re.compile(
    r"toplam\s+öğrenci|toplam\s+sayı|kaç\s+öğrenci\s+var|öğrenci\s+sayımız\s+kaç",
    re.IGNORECASE,
)

_STAFF_PERFORMANCE_PATTERNS = re.compile(
    r"(?:akademisyen|hoca|personel).*(?:performans|puan|yayın|başarılı)|"
    r"performans.*(?:akademisyen|hoca)|en\s+yüksek\s+performans",
    re.IGNORECASE,
)

_ACADEMIC_LOAD_PATTERNS = re.compile(
    r"akademik\s+personel.*yük|nerede\s+yük\s+yoğunluğu|yük\s+yoğunluğu|"
    r"öğrenci\s*/\s*akademisyen|öğrenci\s+başına\s+akademisyen|öğrenci\s+ve\s+akademisyen\s+oran",
    re.IGNORECASE,
)

_BENCHMARK_PATTERNS = re.compile(
    r"yök\s+atlas|yokatlas|medyan|benzer\s+program|atlas\s+açısından",
    re.IGNORECASE,
)

_HIERARCHICAL_STRUCTURE_PATTERNS = re.compile(
    r"öğrenci\s+yapı(?:sı|larını)|yapılarını\s+karşılaştır|yapısını\s+karşılaştır|"
    r"alt\s+birimlerden\s+kaynaklandığını|hangi\s+alt\s+birimlerden|fark(?:ın|ların)?\s+hangi\s+bölüm|"
    r"öğrenci\s+sayısı\s+farkı\s+hangi\s+bölümlerden|iç\s+yapı|bölüm\s+kırılımı|"
    r"öğrenci\s+farkının\s+nedenini\s+göster|farkın\s+nedeni",
    re.IGNORECASE,
)

_SIMPLE_RANKING_PATTERNS = re.compile(
    r"sırala|büyükten\s+küçüğe|küçükten\s+büyüğe|sıralama|en\s+çok\s+öğrenci|en\s+yüksek|öğrenci\s+sayısına\s+göre\s+sırala",
    re.IGNORECASE,
)

_EXECUTIVE_OVERVIEW_PATTERNS = re.compile(
    r"en\s+(?:önemli|kritik|dikkat\s+çekici)\s*3|öncelik|3\s+konu|3\s+bulgu|yönetim\s+açısından\s+en\s+önemli",
    re.IGNORECASE,
)


def _resolve_plan_year(message: str, ui_scope: Optional[Dict[str, Any]], previous_dataset: Optional[Dict[str, Any]]) -> str:
    """Explicit year in message > ui_scope > previous dataset > default 2025-2026."""
    m = re.search(r"\b(20\d\d\s*[-/]\s*20\d\d)\b", message)
    if m:
        return m.group(1).replace("/", "-").replace(" ", "")
    if ui_scope and ui_scope.get("academic_year"):
        return str(ui_scope["academic_year"])
    if previous_dataset and previous_dataset.get("academic_year"):
        return str(previous_dataset["academic_year"])
    return "2025-2026"


def plan_turn(
    db: Session,
    message: str,
    entities: Optional[List[Any]] = None,
    ui_scope: Optional[Dict[str, Any]] = None,
    previous_dataset: Optional[Dict[str, Any]] = None,
) -> TurnPlan:
    """Stage 1: Analyzes the current turn message and produces a structured, closed TurnPlan."""
    norm = message.strip()
    year = _resolve_plan_year(norm, ui_scope, previous_dataset)
    explicit_entities = entities if entities is not None else []
    has_previous = bool(previous_dataset and previous_dataset.get("available"))


    # 1. Explicit Context Override ("Bu grafiği boşver...", "Yeni soru...")
    if _CONTEXT_OVERRIDE_PATTERNS.search(norm):
        return _plan_new_analysis(
            db, norm, explicit_entities, year, ui_scope,
            objective="user_explicitly_reset_context"
        )

    # 2. Finding Reference Follow-Up ("İkinci bulguyu detaylandır", "diğer iki sıkıntı...")
    if has_previous and _FINDING_REFERENCE_PATTERNS.search(norm):
        ref_ids = []
        if re.search(r"ikinci|2\.", norm, re.I):
            ref_ids = [2]
        elif re.search(r"üçüncü|3\.", norm, re.I):
            ref_ids = [3]
        elif re.search(r"ilk|1\.", norm, re.I):
            ref_ids = [1]
        elif re.search(r"diğer|son|kalan", norm, re.I):
            ref_ids = [2, 3]

        return TurnPlan(
            relation=TurnRelation.FINDING_REFERENCE,
            objective="expand_or_visualize_previous_finding",
            explicit_entities=explicit_entities,
            inherited_entities=previous_dataset.get("entities") or [],
            academic_year=year,
            reference_finding_ids=ref_ids,
            needs_visualization=not bool(re.search(r"neden\s*önemli|açıkla", norm, re.I)),
            visual_goal="finding_specific_chart",
        )

    # 2b. Auto Insight Active Finding Follow-Up ("Neden?", "Açıkla", "Detaylandır")
    active_finding = ui_scope.get("active_finding") if ui_scope else None
    if (active_finding or has_previous) and re.search(r"^(?:neden|nasil|nasıl|acikla|açıkla|detaylandir|detaylandır|sebebi\s+ne)\??$", norm, re.I):
        return TurnPlan(
            relation=TurnRelation.FINDING_REFERENCE,
            objective="expand_or_visualize_previous_finding",
            explicit_entities=explicit_entities,
            inherited_entities=previous_dataset.get("entities") or [] if previous_dataset else [],
            academic_year=year,
            reference_finding_ids=[1],
            needs_visualization=False,
            notes=[f"Aktif ekran bulgusu: {active_finding}"] if active_finding else [],
        )

    # 2c. Deictic Screen-Scoped Question ("En kritik konu hangisi?", "Buradaki en büyük sorun ne?")
    if re.search(r"en\s+(?:kritik|önemli|büyük)\s+(?:konu|sorun|mesele)|buradaki\s+en", norm, re.I) and not explicit_entities:
        screen_domain = ui_scope.get("domain") if ui_scope else ""
        screen_id = str(ui_scope.get("screen_id") or "") if ui_scope else ""
        if screen_domain == "student" or screen_id.startswith("ogrenci"):
            return TurnPlan(
                relation=TurnRelation.NEW_ANALYSIS,
                objective="student_intake_critical_analysis",
                academic_year=year,
                requested_metrics=["student_count", "quota", "occupancy_percent"],
                hierarchy_needed=True,
                parent_level="faculty",
                child_level="department",
                needs_visualization=True,
                visual_goal="grouped_comparison",
                notes=["Öğrenci analizleri ekranı bağlamında kritik doluluk ve kapasite analizi."],
            )
        elif screen_domain == "academic" or screen_id.startswith("akademik"):
            return TurnPlan(
                relation=TurnRelation.NEW_ANALYSIS,
                objective="academic_staff_load_analysis",
                academic_year=year,
                requested_metrics=["students_per_academic"],
                additional_metrics_to_consider=["student_count", "academic_staff_count"],
                hierarchy_needed=True,
                parent_level="faculty",
                child_level="department",
                calculations=["students_per_academic"],
                needs_visualization=True,
                visual_goal="ranked_hbar",
                notes=["Akademik personel ekranı bağlamında akademik yük analizi."],
            )

    # 3. Visual Revision Follow-Up ("En büyük bölümleri öne çıkar", "Daha sade bir görsel...")
    if has_previous and _VISUAL_REVISION_PATTERNS.search(norm) and (
        previous_dataset.get("faculty_composition") or previous_dataset.get("hierarchical_composition") or previous_dataset.get("visual_plans")
    ):
        is_simplify = bool(re.search(r"çok\s+kalabalık|daha\s+sade|başka\s+bir\s+görsel", norm, re.I))
        return TurnPlan(
            relation=TurnRelation.VISUAL_REVISION,
            objective="simplify_or_focus_existing_visualization",
            explicit_entities=explicit_entities,
            inherited_entities=previous_dataset.get("entities") or [],
            academic_year=year,
            hierarchy_needed=True,
            needs_visualization=True,
            visual_goal="ranked_hbar" if is_simplify else "stacked_composition",
            notes=["Sadeleştirilmiş veya odaklanmış görsel plan uygulanıyor."],
        )

    # 4. True Contextual Follow-Up ("Aynı karşılaştırmada öğrenci/akademisyen oranını da gör...")
    if has_previous and _TRUE_FOLLOW_UP_PATTERNS.search(norm):
        prev_entities = previous_dataset.get("entities") or []
        derived_rules = derivation_registry.resolve_all_derived_metrics(norm)
        req_metrics = []
        rule_keys = [r.key for r in derived_rules] if derived_rules else []
        req_inputs = list({inp for r in derived_rules for inp in r.required_inputs}) if derived_rules else []

        if rule_keys:
            req_metrics.extend(rule_keys)
        elif _ACADEMIC_LOAD_PATTERNS.search(norm):
            req_metrics.append("students_per_academic")
        if _BENCHMARK_PATTERNS.search(norm):
            req_metrics.append("yokatlas_total_students")
        if _TOTAL_STUDENTS_PATTERNS.search(norm):
            req_metrics.append("student_count")

        has_fac = bool(re.search(r"fakülte", norm, re.I))
        has_dept = bool(re.search(r"bölüm", norm, re.I))
        prev_was_hierarchy = bool(previous_dataset.get("faculty_composition") or previous_dataset.get("hierarchical_composition"))

        return TurnPlan(
            relation=TurnRelation.FOLLOW_UP,
            objective="derivable_metric_analysis" if rule_keys else "extend_previous_comparison_with_new_metrics",
            explicit_entities=explicit_entities,
            inherited_entities=prev_entities,
            academic_year=year,
            requested_metrics=req_metrics or ["student_count", "academic_staff_count"],
            additional_metrics_to_consider=req_inputs or ["student_count", "academic_staff_count", "yokatlas_total_students"],
            requested_derived_rules=rule_keys,
            required_inputs=req_inputs,
            hierarchy_needed=(has_fac or has_dept or prev_was_hierarchy or not (explicit_entities or prev_entities)),
            parent_level="faculty" if (has_fac or prev_was_hierarchy) else None,
            child_level="department" if (has_dept or prev_was_hierarchy) else None,
            calculations=rule_keys or (["students_per_academic"] if "students_per_academic" in req_metrics else []),
            needs_visualization=True,
            visual_goal="grouped_comparison" if (len(req_metrics) > 1 or prev_was_hierarchy or (explicit_entities and len(explicit_entities) > 1)) else "ranked_hbar",
        )

    # 5. Self-Contained Headcount Query ("Toplam öğrenci sayımız kaç?")
    if _TOTAL_STUDENTS_PATTERNS.search(norm) and not explicit_entities and not _HIERARCHICAL_STRUCTURE_PATTERNS.search(norm):
        return TurnPlan(
            relation=TurnRelation.NEW_ANALYSIS,
            objective="university_total_students",
            academic_year=year,
            requested_metrics=["student_count"],
            needs_visualization=False,
            visual_goal="none",
        )

    # 6. Staff Performance Ranking Query ("En yüksek performanslı 10 akademisyen")
    if _STAFF_PERFORMANCE_PATTERNS.search(norm):
        return TurnPlan(
            relation=TurnRelation.NEW_ANALYSIS,
            objective="top_staff_performance",
            academic_year=year,
            requested_metrics=["academic_performance_score"],
            needs_visualization=True,
            visual_goal="ranked_hbar",
        )

    # 7. General Derivable Metric Analysis (e.g. academics_per_100_students, academics_per_student, students_per_academic, unused_capacity, capacity_excess, peer_difference_percent)
    derived_rules = derivation_registry.resolve_all_derived_metrics(norm)
    if derived_rules and not _EXECUTIVE_OVERVIEW_PATTERNS.search(norm) and not _HIERARCHICAL_STRUCTURE_PATTERNS.search(norm) and not re.search(r"kontenjanı?\s*artıralım\s*mı", norm, re.I):
        rule_keys = [r.key for r in derived_rules]
        req_inputs = list({inp for r in derived_rules for inp in r.required_inputs})
        has_fac = bool(re.search(r"fakülte", norm, re.I))
        has_dept = bool(re.search(r"bölüm", norm, re.I))
        vis_goal = "grouped_comparison" if len(derived_rules) > 1 or len(explicit_entities) > 1 else "ranked_hbar"

        return TurnPlan(
            relation=TurnRelation.NEW_ANALYSIS,
            objective="derivable_metric_analysis",
            explicit_entities=explicit_entities,
            academic_year=year,
            requested_metrics=rule_keys,
            additional_metrics_to_consider=req_inputs,
            requested_derived_rules=rule_keys,
            required_inputs=req_inputs,
            hierarchy_needed=(has_fac or has_dept or not explicit_entities),
            parent_level="faculty" if has_fac else None,
            child_level="department" if has_dept else None,
            calculations=rule_keys,
            needs_visualization=True,
            visual_goal=vis_goal,
            notes=[f"Türetilmiş metrikler: {', '.join(r.label for r in derived_rules)}."],
        )

    # 7b. Academic Staff Load Analysis ("Nerede yük yoğunluğu var?", "Öğrenci/akademisyen oranı")
    if _ACADEMIC_LOAD_PATTERNS.search(norm):
        return TurnPlan(
            relation=TurnRelation.NEW_ANALYSIS,
            objective="academic_staff_load_analysis",
            explicit_entities=explicit_entities,
            academic_year=year,
            requested_metrics=["students_per_academic"],
            additional_metrics_to_consider=["student_count", "academic_staff_count"],
            hierarchy_needed=not bool(explicit_entities),
            parent_level="faculty",
            child_level="department",
            calculations=["students_per_academic"],
            needs_visualization=True,
            visual_goal="ranked_hbar",
        )


    # 8. Open-Ended Strategic Executive Overview ("En önemli 3 konu nedir?")
    if _EXECUTIVE_OVERVIEW_PATTERNS.search(norm):
        return TurnPlan(
            relation=TurnRelation.NEW_ANALYSIS,
            objective="executive_overview_analysis",
            academic_year=year,
            requested_metrics=["student_count", "total_capacity", "academic_staff_count", "yokatlas_total_students"],
            additional_metrics_to_consider=["capacity_utilization", "students_per_academic", "peer_difference"],
            hierarchy_needed=True,
            parent_level="faculty",
            child_level="department",
            calculations=["capacity_utilization", "capacity_excess", "students_per_academic", "peer_diff_pct"],
            needs_visualization=True,
            visual_goal="bubble",
        )

    # 9. Hierarchical Composition Query ("Fakültelerin öğrenci yapılarını karşılaştır", "farkın nedeni")
    if _HIERARCHICAL_STRUCTURE_PATTERNS.search(norm):
        return TurnPlan(
            relation=TurnRelation.NEW_ANALYSIS,
            objective="hierarchical_composition_student_structure",
            explicit_entities=explicit_entities,
            academic_year=year,
            requested_metrics=["student_count"],
            hierarchy_needed=True,
            parent_level="faculty",
            child_level="department",
            needs_visualization=True,
            visual_goal="stacked_composition",
        )

    # 9b. Quota Decision Evaluation Query ("kontenjanı artıralım mı?")
    if re.search(r"kontenjanı?\s*artıralım\s*mı|kontenjan\s*artırılmalı\s*mı", norm, re.I):
        return TurnPlan(
            relation=TurnRelation.NEW_ANALYSIS,
            objective="quota_decision_reasoning",
            explicit_entities=explicit_entities,
            academic_year=year,
            requested_metrics=["student_count", "quota", "placed_students", "occupancy_percent", "academic_staff_count", "yokatlas_total_students", "total_capacity"],
            needs_visualization=True,
            visual_goal="grouped_comparison",
        )

    # 10. Benchmark Comparison Query (e.g. Endüstri ile Yazılımı YÖK Atlas açısından karşılaştır)
    if _BENCHMARK_PATTERNS.search(norm):

        return TurnPlan(
            relation=TurnRelation.NEW_ANALYSIS,
            objective="benchmark_peer_comparison",
            explicit_entities=explicit_entities,
            academic_year=year,
            requested_metrics=["yokatlas_total_students", "student_count"],
            calculations=["peer_diff_pct"],
            needs_visualization=True,
            visual_goal="benchmark_grouped",
        )


    # 11. Simple Ranking ("Fakülteleri öğrenci sayısına göre sırala")
    if _SIMPLE_RANKING_PATTERNS.search(norm) and not _HIERARCHICAL_STRUCTURE_PATTERNS.search(norm):
        return TurnPlan(
            relation=TurnRelation.NEW_ANALYSIS,
            objective="simple_ranking",
            explicit_entities=explicit_entities,
            academic_year=year,
            requested_metrics=["student_count"],
            hierarchy_needed=False,
            needs_visualization=True,
            visual_goal="ranked_bar",
        )

    # 12. Default: Self-Contained Clean Query / New Analysis
    return _plan_new_analysis(db, norm, explicit_entities, year, ui_scope, objective="standard_catalog_query")


def _plan_new_analysis(
    db: Session,
    message: str,
    explicit_entities: List[EntityMatch],
    academic_year: str,
    ui_scope: Optional[Dict[str, Any]],
    objective: str = "new_analysis",
) -> TurnPlan:
    """Build a default fresh TurnPlan without stale historical state."""
    req_metrics = []
    if _BENCHMARK_PATTERNS.search(message):
        req_metrics.append("yokatlas_total_students")
    if _ACADEMIC_LOAD_PATTERNS.search(message):
        req_metrics.append("students_per_academic")
    if _TOTAL_STUDENTS_PATTERNS.search(message) or not req_metrics:
        req_metrics.append("student_count")

    needs_vis = bool(re.search(r"grafi[kğ]|çiz|cizel|görsel|şema|kıyasla|karşılaştır", message, re.I)) or len(explicit_entities) >= 2

    return TurnPlan(
        relation=TurnRelation.NEW_ANALYSIS,
        objective=objective,
        explicit_entities=explicit_entities,
        academic_year=academic_year,
        requested_metrics=req_metrics,
        additional_metrics_to_consider=["student_count", "academic_staff_count"],
        hierarchy_needed=False,
        needs_visualization=needs_vis,
        visual_goal="grouped_comparison" if len(explicit_entities) >= 2 else ("ranked_hbar" if "students_per_academic" in req_metrics else "bar"),
    )
