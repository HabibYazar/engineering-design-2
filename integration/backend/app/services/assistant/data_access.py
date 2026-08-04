"""Asistanın kurumsal veriye eriştiği tek katman.

Neden ayrı bir dosya: asistan doğrudan modellere veya SQL'e dokunmamalı.
Erişim buradan geçtiğinde, ileride "asistan hangi verileri görebilir"
sorusuna tek bir yerde cevap verilebilir (rol bazlı kısıtlama, hassas alanların
dışarıda bırakılması gibi).

Bu katman salt okunurdur; hiçbir veri yazmaz veya değiştirmez.
"""

from typing import Callable, Dict, List

from sqlalchemy.orm import Session

from app.services.assistant.schemas import ContextItem

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


def student_overview(db: Session) -> List[ContextItem]:
    """Modül 2 — öğrenci özeti."""
    from app.services import student_analytics_service as service

    module = "Modül 2 — Öğrenci Analitiği"
    try:
        data = service.build_overview(db)
    except Exception:
        return [_item(module, "durum", "Öğrenci özeti", None)]

    payload = data.model_dump() if hasattr(data, "model_dump") else dict(data)
    labels = {
        "total_students": "Toplam öğrenci",
        "active_students": "Aktif öğrenci",
        "newly_enrolled_students": "Yeni kayıtlı öğrenci",
        "graduated_students": "Mezun öğrenci",
        "dropped_out_students": "Ayrılan öğrenci",
        "average_gpa": "Ortalama not ortalaması",
    }
    return [
        _item(module, key, label, payload.get(key))
        for key, label in labels.items()
        if key in payload
    ]


def program_demand(db: Session) -> List[ContextItem]:
    """Modül 2 — program bazlı doluluk (talep göstergesi)."""
    from app.services import student_analytics_service as service

    module = "Modül 2 — Öğrenci Analitiği"
    try:
        rows = service.build_program_analytics(db)
    except Exception:
        return [_item(module, "durum", "Program doluluk verisi", None)]

    items: List[ContextItem] = []
    normalized = [
        r.model_dump() if hasattr(r, "model_dump") else dict(r) for r in rows
    ]
    # Doluluk oranı düşük olanlar önce; asistanın ilgilendiği sorular
    # genellikle riskli programlarla ilgili.
    normalized.sort(key=lambda r: float(r.get("occupancy_rate") or 0))
    for row in normalized[:8]:
        items.append(
            _item(
                module,
                f"doluluk_{row.get('program_code')}",
                f"{row.get('program_name')} doluluk oranı",
                row.get("occupancy_rate"),
            )
        )
    return items


def sustainability_scores(db: Session) -> List[ContextItem]:
    """Modül 7 — program sürdürülebilirlik skorları."""
    from app.services import sustainability_service as service

    module = "Modül 7 — Program Sürdürülebilirliği"
    try:
        rows = service.evaluate_all(db, CURRENT_ACADEMIC_YEAR)
    except Exception:
        return [_item(module, "durum", "Sürdürülebilirlik skoru", None)]

    items = []
    for row in list(rows)[:8]:
        data = row if isinstance(row, dict) else dict(row)
        items.append(
            _item(
                module,
                f"surdurulebilirlik_{data.get('program_code')}",
                f"{data.get('program_name')} sürdürülebilirlik skoru",
                f"{data.get('sustainability_score')} ({data.get('category')})",
            )
        )
    return items


def financial_summary(db: Session) -> List[ContextItem]:
    """Modül 6 — mali özet."""
    from app.services import finance_service as service

    module = "Modül 6 — Finansal Analiz"
    try:
        data = service.financial_summary(db, CURRENT_ACADEMIC_YEAR)
    except Exception:
        return [_item(module, "durum", "Mali özet", None)]

    labels = {
        "total_revenue": "Toplam gelir (milyon TL)",
        "total_expenditure": "Toplam gider (milyon TL)",
        "balance": "Gelir-gider dengesi (milyon TL)",
        "revenue_per_student_thousand_try": "Öğrenci başına gelir (bin TL)",
        "cost_per_student_thousand_try": "Öğrenci başına maliyet (bin TL)",
        "personnel_expense_share_percent": "Personel giderinin payı (%)",
        "scholarship_impact_percent": "Burs yükünün gelire oranı (%)",
    }
    return [
        _item(module, key, label, data.get(key)) for key, label in labels.items()
    ]


def kpi_scorecard(db: Session) -> List[ContextItem]:
    """Modül 8 — KPI karnesi."""
    from app.services import kpi_service as service

    module = "Modül 8 — Performans Yönetimi"
    try:
        card = service.scorecard(db, CURRENT_ACADEMIC_YEAR)
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


def staff_performance(db: Session) -> List[ContextItem]:
    """Modül 4 — akademik personel özeti."""
    from app.services import academic_staff_service as service

    module = "Modül 4 — Akademik Personel"
    try:
        data = service.staff_overview(db, None)
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


def capacity_overview(db: Session) -> List[ContextItem]:
    """Modül 5 — fiziksel kapasite özeti."""
    from app.services import physical_resources_service as service

    module = "Modül 5 — Fiziksel Kaynaklar"
    try:
        data = service.capacity_overview(db)
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


def early_warnings(db: Session) -> List[ContextItem]:
    """Modül 11 — açık erken uyarılar."""
    from app.services import early_warning_rule_engine as engine

    module = "Modül 11 — Erken Uyarı"
    try:
        alerts = engine.evaluate(db, CURRENT_ACADEMIC_YEAR)
    except Exception:
        return [_item(module, "durum", "Erken uyarılar", None)]

    normalized = [a if isinstance(a, dict) else dict(a) for a in alerts]
    items = [_item(module, "uyari_sayisi", "Açık uyarı sayısı", len(normalized))]
    for alert in normalized[:6]:
        items.append(
            _item(
                module,
                f"uyari_{alert.get('rule_key')}_{alert.get('scope_code')}",
                f"[{alert.get('severity')}] {alert.get('rule_name')}",
                alert.get("message") or alert.get("scope_name"),
            )
        )
    return items


def ranking_readiness(db: Session) -> List[ContextItem]:
    """Modül 10 — sıralama değerlendirme hazırlığı."""
    from app.models import FrameworkAssessment
    from sqlalchemy import select

    module = "Modül 10 — THE/QS/YÖK Değerlendirme"
    try:
        rows = list(db.execute(select(FrameworkAssessment)).scalars())
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


# Konu adı -> hangi toplayıcıların çalışacağı.
# Bir soru bir konuya eşleştiğinde yalnızca ilgili veriler toplanır; her soruda
# tüm veritabanını taramak hem yavaş hem de modele gereksiz gürültü gönderir.
TOPIC_COLLECTORS: Dict[str, List[Callable[[Session], List[ContextItem]]]] = {
    "öğrenci talebi": [student_overview, program_demand, sustainability_scores],
    "mali durum": [financial_summary, kpi_scorecard],
    "akademik performans": [staff_performance, ranking_readiness],
    "fiziksel kapasite": [capacity_overview, student_overview],
    "risk ve uyarı": [early_warnings, sustainability_scores],
    "performans göstergeleri": [kpi_scorecard, ranking_readiness],
    "genel": [student_overview, financial_summary, kpi_scorecard, early_warnings],
}
