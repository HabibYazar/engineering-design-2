"""Asistanın kurumsal veriye eriştiği tek katman.

Neden ayrı bir dosya: asistan doğrudan modellere veya SQL'e dokunmamalı.
Erişim buradan geçtiğinde, ileride "asistan hangi verileri görebilir"
sorusuna tek bir yerde cevap verilebilir (rol bazlı kısıtlama, hassas alanların
dışarıda bırakılması gibi).

Bu katman salt okunurdur; hiçbir veri yazmaz veya değiştirmez.
"""

from typing import Callable, Dict, List, Optional

from sqlalchemy.orm import Session

from app.services.assistant.schemas import ContextItem
from app.services.scope import Scope

# Güncel akademik yıl. Ortak veri setiyle uyumlu olacak şekilde sabit;
# ileride yapılandırmadan okunabilir.
CURRENT_ACADEMIC_YEAR = "2025-2026"


def _item(module: str, key: str, label: str, value) -> ContextItem:
    """Tek bir bağlam satırı üretir. None değerler açıkça işaretlenir."""
    return ContextItem(
        source_module=module,
        key=key,
        label=label,
        # "veri yok" ile "sıfır" ayrımı burada da korunuyor; modele boş değer
        # yerine durumu anlatan bir metin gider.
        value="veri yok" if value is None else str(value),
    )


# ----------------------------------------------------------------------------
# Veri toplayıcılar — her biri kendi modülünün servisini çağırır
# ----------------------------------------------------------------------------


def student_overview(db: Session, scope: Optional[Scope] = None,
                     academic_year: Optional[str] = None) -> List[ContextItem]:
    """Modül 2 — öğrenci özeti."""
    from app.services import decision_analytics_service as service

    module = "Modül 2 — Öğrenci Analitiği"
    try:
        data = service.student_body_overview(db, scope, academic_year)
    except Exception:
        return [_item(module, "durum", "Öğrenci özeti", None)]

    labels = {
        "student_count": "Toplam öğrenci",
        "latest_quota": "Seçili dönem kontenjanı",
        "latest_placed_students": "Seçili dönem yerleşen öğrenci",
        "latest_occupancy_percent": "Seçili dönem doluluk oranı (%)",
        "academic_staff_count": "Akademik personel",
        "students_per_academic_staff": "Öğrenci / akademisyen",
    }
    return [
        _item(module, key, label, data.get(key))
        for key, label in labels.items()
    ]


def program_demand(db: Session, scope: Optional[Scope] = None,
                   academic_year: Optional[str] = None) -> List[ContextItem]:
    """Modül 2 — program bazlı doluluk (talep göstergesi)."""
    from app.services import peer_comparison_service as service

    module = "Modül 2 — Öğrenci Analitiği"
    try:
        if scope is not None and scope.level == "program":
            one = service.unit_self(db, scope, academic_year)
            rows = [one] if one else []
        else:
            rows = service.child_breakdown(
                db, scope, academic_year).get("rows", [])
    except Exception:
        return [_item(module, "durum", "Program doluluk verisi", None)]

    items: List[ContextItem] = []
    normalized = [dict(r) for r in rows]
    # Doluluk oranı düşük olanlar önce; asistanın ilgilendiği sorular
    # genellikle riskli programlarla ilgili.
    normalized.sort(key=lambda r: float(r.get("occupancy_percent") or 0))
    for row in normalized[:8]:
        items.append(
            _item(
                module,
                f"doluluk_{row.get('code') or row.get('unit_id')}",
                f"{row.get('name')} doluluk oranı",
                row.get("occupancy_percent"),
            )
        )
    return items


def sustainability_scores(db: Session, scope: Optional[Scope] = None,
                          academic_year: Optional[str] = None) -> List[ContextItem]:
    """Modül 7 — program sürdürülebilirlik skorları."""
    from app.services import sustainability_service as service

    module = "Modül 7 — Program Sürdürülebilirliği"
    try:
        rows = service.evaluate_all(
            db, academic_year or CURRENT_ACADEMIC_YEAR)
    except Exception:
        return [_item(module, "durum", "Sürdürülebilirlik skoru", None)]

    items = []
    for row in list(rows):
        data = row if isinstance(row, dict) else dict(row)
        if (scope is not None and scope.program_ids is not None
                and data.get("program_code") not in scope.program_codes):
            continue
        items.append(
            _item(
                module,
                f"surdurulebilirlik_{data.get('program_code')}",
                f"{data.get('program_name')} sürdürülebilirlik skoru",
                f"{data.get('sustainability_score')} ({data.get('category')})",
            )
        )
        if len(items) >= 8:
            break
    return items or [_item(module, "durum", "Sürdürülebilirlik skoru", None)]


def financial_summary(db: Session, scope: Optional[Scope] = None,
                      academic_year: Optional[str] = None) -> List[ContextItem]:
    """Modül 6 — mali özet."""
    from app.services import finance_service as service

    module = "Modül 6 — Finansal Analiz"
    if scope is not None and not scope.is_university:
        return [_item(module, "durum", "Mali özet (bu kapsam)", None)]
    try:
        data = service.financial_summary(
            db, academic_year or CURRENT_ACADEMIC_YEAR)
    except Exception:
        return [_item(module, "durum", "Mali özet", None)]

    labels = {
        "total_revenue": "Toplam gelir (milyon USD)",
        "total_expenditure": "Toplam gider (milyon USD)",
        "balance": "Gelir-gider dengesi (milyon USD)",
        "revenue_per_student_thousand_usd": "Öğrenci başına gelir (bin USD)",
        "cost_per_student_thousand_usd": "Öğrenci başına maliyet (bin USD)",
        "personnel_expense_share_percent": "Personel giderinin payı (%)",
        "scholarship_impact_percent": "Burs yükünün gelire oranı (%)",
    }
    return [
        _item(module, key, label, data.get(key)) for key, label in labels.items()
    ]


def kpi_scorecard(db: Session, scope: Optional[Scope] = None,
                  academic_year: Optional[str] = None) -> List[ContextItem]:
    """Modül 8 — KPI karnesi."""
    from app.services import kpi_service as service

    module = "Modül 8 — Performans Yönetimi"
    if scope is not None and not scope.is_university:
        return [_item(module, "durum", "KPI karnesi (bu kapsam)", None)]
    try:
        card = service.scorecard(db, academic_year or CURRENT_ACADEMIC_YEAR)
    except Exception:
        return [_item(module, "durum", "KPI karnesi", None)]

    items = [
        _item(module, "toplam_kpi", "İzlenen gösterge sayısı", card["total_kpis"]),
        _item(module, "genel_basari", "Genel başarı oranı (%)", card["overall_achievement_percent"]),
        _item(module, "riskli_kpi", "Riskli gösterge sayısı", card["at_risk_count"]),
    ]
    for dim in card["by_dimension"][:4]:
        items.append(
            _item(
                module,
                f"boyut_{dim['dimension']}",
                f"{dim['dimension']} ortalama başarı (%)",
                dim["average_achievement_percent"],
            )
        )
    return items


def staff_performance(db: Session, scope: Optional[Scope] = None,
                      academic_year: Optional[str] = None) -> List[ContextItem]:
    """Modül 4 — akademik personel özeti."""
    from app.services import decision_analytics_service as service

    module = "Modül 4 — Akademik Personel"
    try:
        staff = service.staffing_overview(db, scope, academic_year)
        pubs = service.publication_productivity(db, scope, academic_year)
        data = {
            "total_staff": staff.get("academic_staff_count"),
            "total_publication": sum(
                r.get("total_publications") or 0 for r in pubs) if pubs else None,
            "average_teaching_load_hours": staff.get(
                "average_teaching_load_hours"),
        }
    except Exception:
        return [_item(module, "durum", "Personel özeti", None)]

    labels = {
        "total_staff": "Toplam akademik personel",
        "total_publication": "Toplam yayın sayısı",
        "total_citation": "Toplam atıf sayısı",
        "average_score": "Ortalama performans puanı",
        "average_teaching_load_hours": "Ortalama ders yükü (saat)",
    }
    return [_item(module, k, v, data.get(k)) for k, v in labels.items()]


def capacity_overview(db: Session, scope: Optional[Scope] = None,
                      academic_year: Optional[str] = None) -> List[ContextItem]:
    """Modül 5 — fiziksel kapasite özeti."""
    from app.services import physical_resources_service as service

    module = "Modül 5 — Fiziksel Kaynaklar"
    try:
        data = service.capacity_overview(db, scope)
    except Exception:
        return [_item(module, "durum", "Kapasite özeti", None)]

    labels = {
        "total_facilities": "Toplam mekân sayısı",
        "total_capacity": "Toplam kapasite",
        "overall_occupancy_percent": "Genel doluluk oranı (%)",
        "overcrowded_count": "Aşırı dolu mekân sayısı",
        "underutilized_count": "Atıl kapasiteli mekân sayısı",
    }
    return [_item(module, k, v, data.get(k)) for k, v in labels.items()]


def early_warnings(db: Session, scope: Optional[Scope] = None,
                   academic_year: Optional[str] = None) -> List[ContextItem]:
    """Modül 11 — açık erken uyarılar."""
    from app.services import decision_analytics_service as engine

    module = "Modül 11 — Erken Uyarı"
    try:
        alerts = engine.operational_warnings(db, scope, academic_year)
    except Exception:
        return [_item(module, "durum", "Erken uyarılar", None)]

    normalized = [a if isinstance(a, dict) else dict(a) for a in alerts]
    items = [_item(module, "uyari_sayisi", "Açık uyarı sayısı", len(normalized))]
    for alert in normalized[:6]:
        items.append(
            _item(
                module,
                f"uyari_{alert.get('code')}",
                f"[{alert.get('severity')}] {alert.get('title')}",
                alert.get("explanation"),
            )
        )
    return items


def ranking_readiness(db: Session, scope: Optional[Scope] = None,
                      academic_year: Optional[str] = None) -> List[ContextItem]:
    """Modül 10 — sıralama değerlendirme hazırlığı."""
    from app.models import FrameworkAssessment
    from sqlalchemy import select

    module = "Modül 10 — THE/QS/YÖK Değerlendirme"
    if scope is not None and not scope.is_university:
        return [_item(module, "durum", "Sıralama hazırlığı (bu kapsam)", None)]
    try:
        sorgu = select(FrameworkAssessment)
        if academic_year:
            sorgu = sorgu.where(
                FrameworkAssessment.academic_year == academic_year)
        rows = list(db.execute(sorgu).scalars())
    except Exception:
        return [_item(module, "durum", "Değerlendirme verisi", None)]

    if not rows:
        return [_item(module, "durum", "Değerlendirme verisi", None)]

    items = []
    for row in rows[:6]:
        items.append(
            _item(
                module,
                f"degerlendirme_{row.id}",
                f"Değerlendirme #{row.id} performans puanı",
                getattr(row, "performance_score", None),
            )
        )
    return items


def _uploaded_metrics(
    db: Session,
    scope: Optional[Scope],
    academic_year: Optional[str],
    screen_key: Optional[str],
) -> List[ContextItem]:
    """Tam kapsam/dönemdeki kullanıcı dosyası verisini açık kaynakla taşır."""
    from app.services.data_source_service import uploaded_context_rows

    module = "Kullanıcı Veri Kaynakları"
    try:
        rows = uploaded_context_rows(
            db,
            scope or Scope(),
            academic_year or CURRENT_ACADEMIC_YEAR,
            screen_key,
        )
    except Exception:
        return []
    return [
        _item(
            module,
            row["metric_key"],
            f'{row["label"]} [Kullanıcı veri kaynağı: {row["filename"]}]',
            f'{row["value"]} {row.get("unit") or ""} · kaynak: Kullanıcı veri kaynağı: {row["filename"]}'.strip(),
        )
        for row in rows
    ]


def uploaded_academic_metrics(db: Session, scope: Optional[Scope] = None,
                              academic_year: Optional[str] = None) -> List[ContextItem]:
    return _uploaded_metrics(db, scope, academic_year, "academic")


def uploaded_financial_metrics(db: Session, scope: Optional[Scope] = None,
                               academic_year: Optional[str] = None) -> List[ContextItem]:
    return _uploaded_metrics(db, scope, academic_year, "finance")


def uploaded_physical_metrics(db: Session, scope: Optional[Scope] = None,
                              academic_year: Optional[str] = None) -> List[ContextItem]:
    return _uploaded_metrics(db, scope, academic_year, "infrastructure")


def uploaded_all_metrics(db: Session, scope: Optional[Scope] = None,
                         academic_year: Optional[str] = None) -> List[ContextItem]:
    return _uploaded_metrics(db, scope, academic_year, None)


# Konu adı -> hangi toplayıcıların çalışacağı.
# Bir soru bir konuya eşleştiğinde yalnızca ilgili veriler toplanır; her soruda
# tüm veritabanını taramak hem yavaş hem de modele gereksiz gürültü gönderir.
TOPIC_COLLECTORS: Dict[
    str, List[Callable[[Session, Optional[Scope], Optional[str]],
                       List[ContextItem]]]
] = {
    "öğrenci talebi": [student_overview, program_demand, sustainability_scores],
    "mali durum": [financial_summary, uploaded_financial_metrics, kpi_scorecard],
    "akademik performans": [staff_performance, uploaded_academic_metrics, ranking_readiness],
    "fiziksel kapasite": [capacity_overview, uploaded_physical_metrics, student_overview],
    "risk ve uyarı": [early_warnings, sustainability_scores],
    "performans göstergeleri": [kpi_scorecard, ranking_readiness],
    "genel": [student_overview, financial_summary, uploaded_all_metrics, kpi_scorecard, early_warnings],
}
