"""Deterministik cevap oluşturucu.

NEDEN VAR
---------
Canlı testte araç doğru çağrıldı, dönem doğruydu, senaryo motoru doğru sonucu
üretti (370 → 426 öğrenci). Ama model final cevapta bu iki sayıyı YAZMADI;
yalnızca mali etkileri anlattı. Bu bir araç çağırma hatası değil, bir CEVAP
OLUŞTURMA hatasıdır.

Sistem yönergesine "bu sayıları yaz" eklemek çözüm değildir: yönerge bir
ricadır. Kritik metriklerin cevapta bulunması backend tarafından garanti
edilir.

NASIL ÇALIŞIR
-------------
Final cevap iki parçadan oluşur:

    [Backend'in yazdığı zorunlu gerçekler]  ← BU DOSYA
    [Modelin yazdığı yönetim değerlendirmesi]

Model yalnızca ikinci parçayı üretir. Birinci parça araç çıktısından
biçimlendirilir; model onu ne değiştirebilir ne de atlayabilir.

SINIR — BU DOSYA HESAP YAPMAZ
-----------------------------
Buradaki her sayı araç çıktısından OLDUĞU GİBİ alınır. Değişim, yüzde ve
fark değerleri araç katmanında hesaplanır. Bu ayrım bilinçlidir: iki farklı
yerde yapılan aynı hesap er ya da geç birbirinden ayrılır.

Araç çıktısında bulunmayan alan UYDURULMAZ; "Veri bulunamadı" yazılır.
"""

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MISSING = "Veri bulunamadı"

# Her senaryo türü için cevapta MUTLAKA bulunması gereken alanlar.
# Biri eksikse cevap "başarılı" sayılmaz; kontrollü hata döner.
REQUIRED_FIELDS: Dict[str, List[str]] = {
    "run_enrollment_change_scenario": [
        "scope.academic_year",
        "scope.program",
        "baseline.program_student_count",
        "scenario.program_student_count",
        "student_change_percentage",
    ],
    "run_staff_salary_scenario": [
        "scope.academic_year",
        "salary_change_percentage",
        "previous_annual_staff_cost_usd",
        "new_annual_staff_cost_usd",
    ],
    "get_program_summary": ["scope.academic_year", "program_name"],
    "get_financial_summary": ["scope.academic_year"],
}


class MissingMetricError(Exception):
    """Araç çıktısında zorunlu bir alan yok."""

    def __init__(self, tool_name: str, missing: List[str]) -> None:
        super().__init__(f"{tool_name}: eksik alanlar {missing}")
        self.tool_name = tool_name
        self.missing = missing


@dataclass
class ComposedResponse:
    """Backend'in ürettiği zorunlu bölüm ve makine okunur sonuç."""

    facts_markdown: str
    structured_result: Dict[str, Any]
    metrics: List[Dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Biçimlendirme yardımcıları — hiçbiri hesap yapmaz
# ---------------------------------------------------------------------------


def _get(payload: Any, path: str) -> Any:
    """Noktalı yolla iç içe alan okur. Yoksa None."""
    current = payload
    for part in path.split("."):
        if current is None:
            return None
        current = getattr(current, part, None)
    return current


def _usd(value: Any) -> str:
    """Tutarı okunabilir USD metnine çevirir.

    BİRİM ASLA DEĞİŞMEZ: değer neyse USD olarak yazılır, milyona çevrilmez.
    Küçük tutarlarda ondalık korunur — 30,60 USD'yi "31 USD" diye yuvarlamak
    öğrenci başına maliyet gibi göstergelerde anlamı bozar.
    """
    if value is None:
        return MISSING
    number = Decimal(str(value))
    if abs(number) < 1000 and number != number.to_integral_value():
        formatted = f"{number:,.2f}".replace(",", "#").replace(".", ",").replace("#", ".")
    else:
        formatted = f"{number:,.0f}".replace(",", ".")
    return f"{formatted} USD"


def _count(value: Any, unit: str = "") -> str:
    if value is None:
        return MISSING
    text = f"{int(value):,}".replace(",", ".")
    return f"{text} {unit}".strip()


def _percent(value: Any) -> str:
    if value is None:
        return MISSING
    number = Decimal(str(value))
    text = f"{number:.2f}".rstrip("0").rstrip(".").replace(".", ",")
    return f"%{text}"


def _signed_usd(value: Any) -> str:
    if value is None:
        return MISSING
    number = Decimal(str(value))
    sign = "+" if number > 0 else ""
    return f"{sign}{_usd(number)}"


def _signed_count(value: Any, unit: str = "") -> str:
    if value is None:
        return MISSING
    number = int(value)
    sign = "+" if number > 0 else ""
    return f"{sign}{_count(number, unit)}"


def _arrow(before: Any, after: Any, formatter) -> str:
    """"X → Y" biçimi. Taraflardan biri yoksa açıkça belirtilir."""
    if before is None and after is None:
        return MISSING
    return f"{formatter(before)} → {formatter(after)}"


def _metric(key: str, label: str, baseline: Any, scenario: Any,
            change: Any, unit: str) -> Dict[str, Any]:
    """structured_result için tek bir metrik kaydı."""

    def _plain(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return float(value)
        return value

    return {
        "key": key,
        "label": label,
        "baseline": _plain(baseline),
        "scenario": _plain(scenario),
        "change": _plain(change),
        "unit": unit,
    }


def _validate(tool_name: str, payload: Any) -> None:
    """Zorunlu alanların varlığını denetler."""
    missing = [
        path for path in REQUIRED_FIELDS.get(tool_name, []) if _get(payload, path) is None
    ]
    if missing:
        logger.error("Zorunlu senaryo alanlari eksik: %s -> %s", tool_name, missing)
        raise MissingMetricError(tool_name, missing)


# ---------------------------------------------------------------------------
# Öğrenci sayısı değişimi senaryosu
# ---------------------------------------------------------------------------


def _compose_enrollment(payload: Any) -> ComposedResponse:
    scope = payload.scope
    base = payload.baseline
    scen = payload.scenario

    metrics = [
        _metric("program_student_count", "Öğrenci sayısı",
                base.program_student_count, scen.program_student_count,
                payload.program_student_change, "öğrenci"),
        _metric("university_student_count", "Üniversite geneli öğrenci",
                base.university_student_count, scen.university_student_count,
                None, "öğrenci"),
        _metric("total_revenue_usd", "Yıllık gelir",
                base.total_revenue_usd, scen.total_revenue_usd,
                payload.revenue_change_usd, "USD"),
        _metric("net_balance_usd", "Net bütçe",
                base.net_balance_usd, scen.net_balance_usd,
                payload.net_balance_change_usd, "USD"),
        _metric("academic_staff_count", "Akademik personel",
                base.academic_staff_count, scen.academic_staff_count, None, "kişi"),
        _metric("recommended_staff_count", "Önerilen personel",
                None, scen.recommended_staff_count, scen.staff_gap, "kişi"),
        _metric("laboratory_capacity", "Laboratuvar kapasitesi",
                base.laboratory_capacity, scen.laboratory_capacity, None, "kişi"),
        _metric("laboratory_demand", "Laboratuvar talebi",
                base.laboratory_demand, scen.laboratory_demand, scen.laboratory_gap, "kişi"),
    ]

    lines = [
        f"**{scope.academic_year} — {scope.program}**",
        "",
        "### Hesaplanan sonuçlar",
        f"- Öğrenci sayısı: {_arrow(base.program_student_count, scen.program_student_count, lambda v: _count(v))}",
        f"- Değişim: {_signed_count(payload.program_student_change, 'öğrenci')} "
        f"({_percent(payload.student_change_percentage)})",
        f"- Yıllık gelir: {_arrow(base.total_revenue_usd, scen.total_revenue_usd, _usd)}",
        f"- Gelir etkisi: {_signed_usd(payload.revenue_change_usd)}",
        f"- Net bütçe: {_arrow(base.net_balance_usd, scen.net_balance_usd, _usd)}",
        f"- Bütçe etkisi: {_signed_usd(payload.net_balance_change_usd)}",
        f"- Akademik personel: {_count(base.academic_staff_count, 'kişi')}",
        f"- Önerilen personel: {_count(scen.recommended_staff_count, 'kişi')}",
        f"- Ek personel ihtiyacı: {_signed_count(scen.staff_gap, 'kişi')}",
        f"- Laboratuvar kapasitesi: {_count(scen.laboratory_capacity, 'kişi')}",
        f"- Senaryo laboratuvar talebi: {_count(scen.laboratory_demand, 'kişi')}",
        f"- Laboratuvar kapasite farkı: {_signed_count(scen.laboratory_gap, 'kişi')}",
        f"- Derslik kapasitesi: {_count(scen.classroom_capacity, 'kişi')}",
        f"- Senaryo derslik talebi: {_count(scen.classroom_demand, 'kişi')}",
        f"- Derslik kapasite farkı: {_signed_count(scen.classroom_gap, 'kişi')}",
        f"- Kapasite durumu: {scen.capacity_status or MISSING}",
    ]

    risks = list(getattr(payload, "risks", []) or [])
    if risks:
        lines.append("")
        lines.append("### Tespit edilen riskler")
        lines.extend(f"- {risk}" for risk in risks[:5])

    return ComposedResponse(
        facts_markdown="\n".join(lines),
        structured_result={
            "type": "enrollment_change_scenario",
            "academic_year": scope.academic_year,
            "scope": {
                "faculty": scope.faculty,
                "department": scope.department,
                "program": scope.program,
            },
            "metrics": metrics,
            "risks": risks,
            "recommendations": list(getattr(payload, "recommendations", []) or []),
            "notes": list(getattr(payload, "notes", []) or []),
            "method_note": getattr(payload, "method_note", None),
        },
        metrics=metrics,
    )


# ---------------------------------------------------------------------------
# Maaş değişimi senaryosu
# ---------------------------------------------------------------------------


def _compose_salary(payload: Any) -> ComposedResponse:
    scope = payload.scope

    metrics = [
        _metric("annual_staff_cost_usd", "Yıllık personel gideri",
                payload.previous_annual_staff_cost_usd,
                payload.new_annual_staff_cost_usd,
                payload.cost_change_usd, "USD"),
        _metric("total_expenditure_change_usd", "Toplam gider etkisi",
                None, None, payload.total_expenditure_change_usd, "USD"),
        _metric("net_balance_change_usd", "Net bütçe etkisi",
                None, None, payload.net_balance_change_usd, "USD"),
        _metric("cost_per_student_change_usd", "Öğrenci başına maliyet etkisi",
                None, None, payload.cost_per_student_change_usd, "USD"),
    ]

    lines = [
        f"**{scope.academic_year} — {scope.label}**",
        "",
        "### Hesaplanan sonuçlar",
        f"- Maaş değişimi: {_percent(payload.salary_change_percentage)}",
        f"- Yıllık personel gideri: "
        f"{_arrow(payload.previous_annual_staff_cost_usd, payload.new_annual_staff_cost_usd, _usd)}",
        f"- Gider değişimi: {_signed_usd(payload.cost_change_usd)}",
        f"- Toplam gider etkisi: {_signed_usd(payload.total_expenditure_change_usd)}",
        f"- Net bütçe etkisi: {_signed_usd(payload.net_balance_change_usd)}",
        f"- Öğrenci başına maliyet etkisi: {_signed_usd(payload.cost_per_student_change_usd)}",
    ]

    risks = list(getattr(payload, "risks", []) or [])
    if risks:
        lines.append("")
        lines.append("### Tespit edilen riskler")
        lines.extend(f"- {risk}" for risk in risks[:5])

    return ComposedResponse(
        facts_markdown="\n".join(lines),
        structured_result={
            "type": "staff_salary_scenario",
            "academic_year": scope.academic_year,
            "scope": {
                "faculty": scope.faculty,
                "department": scope.department,
                "program": scope.program,
            },
            "metrics": metrics,
            "risks": risks,
            "recommendations": list(getattr(payload, "recommendations", []) or []),
            "notes": list(getattr(payload, "notes", []) or []),
            "method_note": getattr(payload, "method_note", None),
        },
        metrics=metrics,
    )


# ---------------------------------------------------------------------------
# Mevcut durum özetleri
# ---------------------------------------------------------------------------


def _compose_program_summary(payload: Any) -> ComposedResponse:
    scope = payload.scope

    metrics = [
        _metric("student_count", "Öğrenci sayısı", None, payload.student_count, None, "öğrenci"),
        _metric("quota", "Kontenjan", None, payload.quota, None, "öğrenci"),
        _metric("occupancy_rate", "Doluluk oranı", None, payload.occupancy_rate, None, "%"),
        _metric("graduation_rate", "Mezuniyet oranı", None, payload.graduation_rate, None, "%"),
        _metric("student_staff_ratio", "Öğrenci / öğretim üyesi",
                None, payload.student_staff_ratio, None, "oran"),
    ]

    lines = [
        f"**{scope.academic_year} — {payload.program_name}**",
        "",
        "### Hesaplanan sonuçlar",
        f"- Öğrenci sayısı: {_count(payload.student_count, 'öğrenci')}",
        f"- Kontenjan: {_count(payload.quota, 'öğrenci')}",
        f"- Doluluk oranı: {_percent(payload.occupancy_rate)}",
        f"- Mezuniyet oranı: {_percent(payload.graduation_rate)}",
        f"- Öğrenci / öğretim üyesi oranı: "
        f"{_percent(payload.student_staff_ratio).lstrip('%') if payload.student_staff_ratio is not None else MISSING}",
    ]

    return ComposedResponse(
        facts_markdown="\n".join(lines),
        structured_result={
            "type": "program_summary",
            "academic_year": scope.academic_year,
            "scope": {
                "faculty": scope.faculty,
                "department": scope.department,
                "program": scope.program,
            },
            "metrics": metrics,
            "risks": [],
            "recommendations": [],
            "notes": list(getattr(payload, "notes", []) or []),
        },
        metrics=metrics,
    )


def _compose_financial_summary(payload: Any) -> ComposedResponse:
    scope = payload.scope

    metrics = [
        _metric("total_revenue_usd", "Toplam gelir", None, payload.total_revenue_usd, None, "USD"),
        _metric("total_expenditure_usd", "Toplam gider", None, payload.total_expenditure_usd, None, "USD"),
        _metric("net_balance_usd", "Net denge", None, payload.net_balance_usd, None, "USD"),
        _metric("cost_per_student_usd", "Öğrenci başına maliyet",
                None, payload.cost_per_student_usd, None, "USD"),
    ]

    lines = [
        f"**{scope.academic_year} — {scope.label}**",
        "",
        "### Hesaplanan sonuçlar",
        f"- Toplam gelir: {_usd(payload.total_revenue_usd)}",
        f"- Toplam gider: {_usd(payload.total_expenditure_usd)}",
        f"- Net denge: {_signed_usd(payload.net_balance_usd)}",
        f"- Öğrenci başına maliyet: {_usd(payload.cost_per_student_usd)}",
    ]

    return ComposedResponse(
        facts_markdown="\n".join(lines),
        structured_result={
            "type": "financial_summary",
            "academic_year": scope.academic_year,
            "scope": {
                "faculty": scope.faculty,
                "department": scope.department,
                "program": scope.program,
            },
            "metrics": metrics,
            "risks": [],
            "recommendations": [],
            "notes": list(getattr(payload, "notes", []) or []),
        },
        metrics=metrics,
    )


_COMPOSERS = {
    "run_enrollment_change_scenario": _compose_enrollment,
    "run_staff_salary_scenario": _compose_salary,
    "get_program_summary": _compose_program_summary,
    "get_financial_summary": _compose_financial_summary,
}


def supports(tool_name: str) -> bool:
    """Bu araç için deterministik bir gerçekler bölümü üretilebilir mi?"""
    return tool_name in _COMPOSERS


def compose(tool_name: str, payload: Any) -> ComposedResponse:
    """Araç çıktısından zorunlu gerçekler bölümünü üretir.

    Zorunlu bir alan eksikse MissingMetricError fırlatır; çağıran bunu
    kontrollü bir hataya çevirir. Eksik veriyle "başarılı" cevap dönmek,
    kullanıcıya yarım bir senaryo sunmak demektir.
    """
    composer = _COMPOSERS.get(tool_name)
    if composer is None:  # pragma: no cover - çağıran supports() ile kontrol eder
        raise KeyError(f"Bu araç için cevap oluşturucu yok: {tool_name}")

    _validate(tool_name, payload)
    return composer(payload)


# Modelin zorunlu gerçekleri yeniden yazmasını engelleyen yönerge.
COMPOSER_INSTRUCTION = (
    "Aşağıdaki 'Hesaplanan sonuçlar' bölümü backend tarafından hazırlanmıştır "
    "ve kullanıcıya AYNEN gösterilecektir. Bu değerleri değiştirme, yeniden "
    "hesaplama, yuvarlama veya farklı birimle (milyon USD / USD) tekrar yazma. "
    "Sayıları tekrar listeleme; yalnızca etkilerini yorumla.\n\n"
    "Senden istenen: '### Yönetim değerlendirmesi' başlığı altında en fazla "
    "dört madde yaz — en önemli mali etki, en önemli personel riski, en "
    "önemli kapasite riski ve önerilen karar. Kısa ve yönetici odaklı ol."
)

INTERPRETATION_HEADING = "### Yönetim değerlendirmesi"
