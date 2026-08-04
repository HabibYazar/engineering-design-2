"""Modül 7 — Akademik Program Sürdürülebilirlik Analizi.

PDF Bölüm 7, her akademik programın YALNIZCA finansal performansa göre değil,
çok boyutlu bir çerçeveyle değerlendirilmesini ister. Bu servis o çerçeveyi kurar:
11 kriteri 0-100 aralığında puanlar, yapılandırılabilir ağırlıklarla birleştirir ve
programı PDF'te sayılan beş kategoriden birine yerleştirir.

EKSİK VERİ YAKLAŞIMI
--------------------
11 kriterin yalnızca 3'ü (talep, doluluk, mezuniyet oranı) Modül 3 verisinden
hesaplanabilir. Kalan 8 kriter Modül 4 (akademik kadro/araştırma), Modül 5 (finans
ve fiziksel kaynak) ve Modül 8 (stratejik plan) modüllerinden gelir. Bu servis
eksik kriterleri UYDURMAZ; ağırlıkları mevcut kriterler üzerinde yeniden
normalize eder ve sonuca bir "veri tamlığı" yüzdesi ekler. Böylece modül tek
başına da çalışır, diğer modüller bağlandığında da puan kendiliğinden zenginleşir.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.services import education_analytics_service as analytics

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "sustainability_weights.json"

# Modül 3 verisinden doğrudan hesaplanabilen kriterler.
COMPUTED_CRITERIA = {"student_demand", "occupancy_rate", "graduation_rate"}

CATEGORY_GROWTH = "Büyüme potansiyeli olan program"
CATEGORY_STRENGTHEN = "Güçlendirilmesi gereken program"
CATEGORY_RESTRUCTURE = "Yeniden yapılandırılması gereken program"
CATEGORY_MERGE = "Birleştirme/konsolidasyon için uygun program"
CATEGORY_STRATEGIC = "Stratejik kurumsal destek gerektiren program"

# ABU PDF'inin yeni (basitleştirilmiş) sürümü 11 kriterli ağırlıklı puanlama yerine
# Mali Analiz bölümünün sonunda 4 kategorili bir sınıflandırma tanımlıyor. Mevcut
# 11 kriterli sistem daha kapsamlı olduğu için korunuyor; bu eşleme yalnızca aynı
# sonucu PDF'in yeni terimleriyle de sunmak için eklenen ek bir görünümdür.
SIMPLE_STRENGTHEN = "Güçlendirilmesi gereken program"
SIMPLE_EXPAND = "Büyütülebilecek program"
SIMPLE_REORGANIZE = "Yeniden yapılandırılması gereken program"
SIMPLE_MERGE = "Birleştirilmesi değerlendirilebilecek program"

_SIMPLE_CATEGORY_MAP = {
    CATEGORY_GROWTH: (SIMPLE_EXPAND, "Talep ve doluluk güçlü; büyütme adayı."),
    CATEGORY_STRENGTHEN: (SIMPLE_STRENGTHEN, "Puan orta seviyede; hedefli iyileştirme yeterli."),
    CATEGORY_RESTRUCTURE: (SIMPLE_REORGANIZE, "Talep ve doluluk zayıf; yeniden yapılandırma gerekiyor."),
    CATEGORY_MERGE: (SIMPLE_MERGE, "Kontenjan ve öğrenci gövdesi küçük; birleştirme adayı."),
    CATEGORY_STRATEGIC: (
        SIMPLE_STRENGTHEN,
        "Yeni PDF'in 4 kategorisinde 'stratejik destek' ayrımı yok; en yakın karşılığı "
        "olan 'güçlendirilmesi gereken' kategorisine eşlendi.",
    ),
}


def _classify_simple(category: str) -> tuple:
    """5 kategorili sonucu ABU PDF'inin yeni 4 kategorili terimlerine eşler."""
    return _SIMPLE_CATEGORY_MAP[category]


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    """Değeri verilen aralığa sıkıştırır."""
    return round(max(low, min(high, value)), 2)


def load_config() -> Dict:
    """Ağırlık ve eşik yapılandırmasını dosyadan okur."""
    with CONFIG_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def _score_student_demand(metrics: Dict, trend: Optional[Dict]) -> Optional[float]:
    """Öğrenci talebi kriterini puanlar.

    İki bileşenden oluşur:
      - Taban puanın Türkiye ortalamasına göre konumu (%70)
      - Doluluk oranının yıllar içindeki değişimi (%30)
    """
    gap = metrics.get("national_score_gap")
    change = trend.get("occupancy_change_points") if trend else None

    # Ortalamanın 1 puan üstü ≈ 0.6 puan avantaj; ölçek 0-100'e sıkıştırılır.
    score_position = _clamp(50 + gap * 0.6) if gap is not None else None
    # Doluluğun 1 yüzde puan artışı ≈ 1.67 puan avantaj.
    trend_position = _clamp(50 + change * 1.67) if change is not None else None

    if score_position is not None and trend_position is not None:
        return _clamp(0.7 * score_position + 0.3 * trend_position)
    if score_position is not None:
        return score_position
    return trend_position


def _computed_scores(metrics: Dict, trend: Optional[Dict]) -> Dict[str, Optional[float]]:
    """Modül 3 verisinden hesaplanabilen kriter puanlarını üretir."""
    return {
        "student_demand": _score_student_demand(metrics, trend),
        # Doluluk oranı zaten 0-100 ölçeğinde bir yüzdedir; %100 üstü tavanlanır.
        "occupancy_rate": _clamp(metrics["occupancy_rate"]),
        # Mezuniyet oranı da doğrudan yüzdedir.
        "graduation_rate": _clamp(metrics["graduation_rate"]),
    }


def _classify(
    score: float, metrics: Dict, external: Dict[str, float], thresholds: Dict
) -> tuple:
    """Programı PDF Bölüm 7'deki kategorilerden birine yerleştirir.

    Kategori sırf puana bakılarak değil, programın büyüklüğü ve stratejik
    katkısı da dikkate alınarak belirlenir.
    """
    if score >= thresholds["growth_potential_min_score"]:
        return (
            CATEGORY_GROWTH,
            f"Sürdürülebilirlik puanı {score} ile büyüme eşiğinin "
            f"({thresholds['growth_potential_min_score']}) üzerinde; talep ve doluluk güçlü.",
        )

    if score >= thresholds["strengthening_min_score"]:
        return (
            CATEGORY_STRENGTHEN,
            f"Puan {score}; program ayakta ancak talep veya mezuniyet göstergeleri "
            "hedefin altında, hedefli iyileştirme gerekiyor.",
        )

    strategic = external.get("strategic_contribution")
    if strategic is not None and strategic >= thresholds["strategic_support_min_contribution"]:
        return (
            CATEGORY_STRATEGIC,
            f"Puan {score} düşük olmakla birlikte stratejik katkı puanı {strategic}; "
            "program kapatılmak yerine kurumsal destekle sürdürülmeli.",
        )

    occupancy_ratio = (
        metrics["enrolled_student_count"] / metrics["quota"] if metrics["quota"] else 0
    )
    is_small = (
        occupancy_ratio < thresholds["merger_max_occupancy_ratio"]
        and metrics["total_students"] < thresholds["merger_max_student_body"]
    )
    if is_small:
        return (
            CATEGORY_MERGE,
            f"Puan {score}; kontenjanın yalnızca %{round(occupancy_ratio * 100, 1)}'i dolu ve "
            f"toplam öğrenci sayısı {metrics['total_students']} — yakın programlarla "
            "birleştirme değerlendirilmeli.",
        )

    return (
        CATEGORY_RESTRUCTURE,
        f"Puan {score}; öğrenci gövdesi büyük ancak talep ve doluluk göstergeleri "
        "zayıf, programın yeniden yapılandırılması gerekiyor.",
    )


def evaluate_program(
    metrics: Dict,
    trend: Optional[Dict],
    external: Dict[str, float],
    weights: Dict[str, float],
    criterion_sources: Dict[str, str],
    thresholds: Dict,
) -> Dict:
    """Tek bir program için sürdürülebilirlik puanını ve kategorisini üretir."""
    computed = _computed_scores(metrics, trend)

    criteria: List[Dict] = []
    available_weight = 0.0
    weighted_total = 0.0
    missing: List[str] = []

    for name, weight in weights.items():
        if name in COMPUTED_CRITERIA:
            score = computed.get(name)
        else:
            score = external.get(name)

        if score is None:
            missing.append(name)
            criteria.append(
                {
                    "name": name,
                    "source": criterion_sources.get(name, "bilinmiyor"),
                    "weight": weight,
                    "effective_weight": 0.0,
                    "score": None,
                    "available": False,
                }
            )
            continue

        score = _clamp(float(score))
        available_weight += weight
        weighted_total += score * weight
        criteria.append(
            {
                "name": name,
                "source": criterion_sources.get(name, "bilinmiyor"),
                "weight": weight,
                "effective_weight": 0.0,  # Aşağıda yeniden normalize edilir.
                "score": score,
                "available": True,
            }
        )

    total_weight = sum(weights.values())

    if available_weight == 0:
        sustainability_score = 0.0
    else:
        # Ağırlıklar yalnızca verisi bulunan kriterler üzerinde yeniden normalize edilir.
        sustainability_score = round(weighted_total / available_weight, 2)
        for criterion in criteria:
            if criterion["available"]:
                criterion["effective_weight"] = round(
                    criterion["weight"] / available_weight * 100, 2
                )

    category, reason = _classify(sustainability_score, metrics, external, thresholds)
    simplified_category, simplified_reason = _classify_simple(category)

    return {
        "program_code": metrics["program_code"],
        "program_name": metrics["program_name"],
        "academic_year": metrics["academic_year"],
        "sustainability_score": sustainability_score,
        "data_completeness_percent": round(available_weight / total_weight * 100, 2),
        "category": category,
        "category_reason": reason,
        "simplified_category": simplified_category,
        "simplified_category_reason": simplified_reason,
        "criteria": criteria,
        "missing_criteria": missing,
        "supporting_metrics": {
            "quota": metrics["quota"],
            "enrolled_student_count": metrics["enrolled_student_count"],
            "occupancy_rate": metrics["occupancy_rate"],
            "graduation_rate": metrics["graduation_rate"],
            "attrition_rate": metrics["attrition_rate"],
            "total_students": metrics["total_students"],
            "minimum_admission_score": metrics["minimum_admission_score"],
            "national_score_gap": metrics["national_score_gap"],
        },
    }


def evaluate_all(
    db: Session,
    academic_year: str,
    external_inputs: Optional[Dict[str, Dict[str, float]]] = None,
    weight_overrides: Optional[Dict[str, float]] = None,
) -> List[Dict]:
    """Tüm programları değerlendirip puana göre artan sırada döndürür.

    external_inputs: {"CENG-BSC": {"research_performance": 72, ...}, ...}
    weight_overrides: yapılandırma dosyasındaki ağırlıkları geçici olarak değiştirir.
    """
    config = load_config()
    weights = dict(config["weights"])
    if weight_overrides:
        weights.update(weight_overrides)

    criterion_sources = config["criterion_sources"]
    thresholds = config["classification_thresholds"]
    external_inputs = external_inputs or {}

    trends = {t["program_code"]: t for t in analytics.get_demand_trends(db)}

    results = []
    for metrics in analytics.get_program_metrics(db, academic_year):
        code = metrics["program_code"]
        results.append(
            evaluate_program(
                metrics=metrics,
                trend=trends.get(code),
                external=external_inputs.get(code, {}),
                weights=weights,
                criterion_sources=criterion_sources,
                thresholds=thresholds,
            )
        )

    return sorted(results, key=lambda r: r["sustainability_score"])


def summarize_categories(results: List[Dict]) -> List[Dict]:
    """Kategori dağılımını özetler (yönetici paneli için)."""
    buckets: Dict[str, List[str]] = {}
    for result in results:
        buckets.setdefault(result["category"], []).append(result["program_code"])

    return [
        {"category": category, "program_count": len(codes), "program_codes": sorted(codes)}
        for category, codes in sorted(buckets.items())
    ]
