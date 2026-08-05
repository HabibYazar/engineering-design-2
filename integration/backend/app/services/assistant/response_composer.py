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


class ScopeConsistencyError(Exception):
    """Cevapta kapsamlar karışıyor veya birim/formül açıklanmamış."""

    def __init__(self, problems: List[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


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


def _number(value: Any) -> str:
    """Yüzde gövdesi: 15 -> "15", 2.50 -> "2,5"."""
    if value is None:
        return MISSING
    text = f"{Decimal(str(value)):.2f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


# Ondalık basamağı anlam taşıyan birimler.
_DECIMAL_UNITS = {"FTE", "oran", "koltuk-saat", "istasyon-saat"}


def _decimal_with_unit(value: Any, unit: str) -> str:
    """Ondalıklı değeri birimiyle yazar. Tam sayıysa ondalık gösterilmez."""
    if value is None:
        return MISSING
    number = Decimal(str(value))
    if number == number.to_integral_value():
        text = f"{number:,.0f}".replace(",", ".")
    else:
        text = f"{number:,.2f}".replace(",", "#").replace(".", ",").replace("#", ".")
    return f"{text} {unit}".strip()


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


def _plain(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return value


def _metric_from_scoped(metric: Any) -> Dict[str, Any]:
    """structured_result kaydı. Kapsam, birim ve formül HER metrikte bulunur."""
    return {
        "key": metric.key,
        "label": metric.label,
        "scope_type": metric.scope_type,
        "scope_name": metric.scope_name,
        "unit": metric.unit,
        "baseline": _plain(metric.baseline),
        "scenario": _plain(metric.scenario),
        "change": _plain(metric.change),
        "formula": metric.formula,
        "note": metric.note,
    }


def _metric(key: str, label: str, baseline: Any, scenario: Any,
            change: Any, unit: str, scope_type: str = "university",
            scope_name: str = "Üniversite geneli",
            formula: Optional[str] = None) -> Dict[str, Any]:
    """Kapsam etiketli metrik kaydı (kapsam listesi olmayan araçlar için)."""
    return {
        "key": key,
        "label": label,
        "scope_type": scope_type,
        "scope_name": scope_name,
        "unit": unit,
        "baseline": _plain(baseline),
        "scenario": _plain(scenario),
        "change": _plain(change),
        "formula": formula,
        "note": None,
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
# Kapsam uyumluluk kontrolü
# ---------------------------------------------------------------------------

SCOPE_LABELS = {
    "program": "Program kapsamındaki sonuçlar",
    "department": "Bölüm kapsamındaki sonuçlar",
    "faculty": "Fakülte kapsamındaki sonuçlar",
    "university": "Üniversite bütçesine ve kaynaklarına etkisi",
}

SCOPE_ORDER = ["program", "department", "faculty", "university"]

# Bir talep değeri, kapsamın öğrenci sayısından büyükse birim ve formül
# mutlaka açıklanmalıdır. Aksi halde "426 öğrenci için 1.420 kişi" gibi
# okunuyor.
_PLAIN_PERSON_UNITS = {"kişi", "öğrenci"}


def check_scope_consistency(metrics: List[Any]) -> None:
    """Kapsam, birim ve formül tutarlılığını denetler.

    Kontroller:
      1. Her göstergenin kapsamı ve birimi yazılı mı?
      2. Bir göstergenin taban ve senaryo değeri aynı kapsama mı ait?
         (Aynı ScopedMetric içinde olduğu için kapsam zaten tektir; burada
         kapsamın boş bırakılmadığı doğrulanır.)
      3. Talep değeri kapsamın öğrenci sayısından büyükse birim düz "kişi"
         olamaz; eş zamanlı/kişi-oturum gibi bir birim ve formül gerekir.

    Uyumsuzluk varsa ScopeConsistencyError fırlar ve cevap başarı sayılmaz.
    """
    problems: List[str] = []

    students_by_scope: Dict[str, Decimal] = {}
    for metric in metrics:
        if metric.key.endswith("student_count") and metric.scenario is not None:
            students_by_scope[metric.scope_type] = Decimal(str(metric.scenario))

    for metric in metrics:
        if not metric.scope_type or not metric.scope_name:
            problems.append(f"{metric.key}: kapsam etiketi yok")
            continue
        if metric.scope_type not in SCOPE_ORDER:
            problems.append(f"{metric.key}: bilinmeyen kapsam '{metric.scope_type}'")
        if not metric.unit:
            problems.append(f"{metric.key}: birim yazılmamış")
            continue

        # Talep göstergeleri: öğrenci sayısını aşıyorsa birim açıklanmalı.
        if "demand" not in metric.key or metric.scenario is None:
            continue
        reference = students_by_scope.get(metric.scope_type)
        if reference is None or Decimal(str(metric.scenario)) <= reference:
            continue
        if metric.unit in _PLAIN_PERSON_UNITS or not metric.formula:
            problems.append(
                f"{metric.key}: talep ({metric.scenario}) kapsamın öğrenci "
                f"sayısından ({reference}) büyük ama birim '{metric.unit}' ve "
                "formül açıklanmamış"
            )

    if problems:
        logger.error("Kapsam uyumsuzlugu: %s", problems)
        raise ScopeConsistencyError(problems)


def _render_scoped(metric: Any) -> str:
    """Tek bir kapsam etiketli göstergeyi satıra çevirir."""
    if metric.unit == "USD":
        formatter = _usd
    elif metric.unit == "%":
        formatter = _percent
    elif metric.unit in _DECIMAL_UNITS:
        # FTE ve oran gibi birimlerde ondalık ANLAM TAŞIR: 18,50 FTE'yi
        # "18 FTE" diye yuvarlamak yarım kadroluk farkı yok eder.
        formatter = lambda v: _decimal_with_unit(v, metric.unit)  # noqa: E731
    else:
        formatter = lambda v: _count(v, metric.unit)  # noqa: E731

    if metric.baseline is not None and metric.scenario is not None:
        value = f"{formatter(metric.baseline)} → {formatter(metric.scenario)}"
    elif metric.scenario is not None:
        value = formatter(metric.scenario)
    elif metric.change is not None:
        value = _signed_usd(metric.change) if metric.unit == "USD" else formatter(metric.change)
    elif metric.baseline is not None:
        value = formatter(metric.baseline)
    else:
        value = MISSING

    # Değeri olmayan, yalnızca durum bildiren gösterge (ör. "yetersiz").
    if value == MISSING and metric.note:
        return f"- {metric.label}: {metric.note}"

    line = f"- {metric.label}: {value}"
    if metric.change is not None and metric.baseline is not None and metric.scenario is not None:
        if metric.unit == "USD":
            delta = _signed_usd(metric.change)
        elif metric.unit in _DECIMAL_UNITS:
            sign = "+" if Decimal(str(metric.change)) > 0 else ""
            delta = f"{sign}{_decimal_with_unit(metric.change, metric.unit)}"
        else:
            delta = _signed_count(metric.change, metric.unit)
        line += f" ({delta})"
    if metric.note:
        line += f"\n  - {metric.note}"
    return line


def _render_scope_groups(metrics: List[Any]) -> List[str]:
    """Göstergeleri kapsamlarına göre başlıklandırarak yazar."""
    lines: List[str] = []
    for scope_type in SCOPE_ORDER:
        group = [m for m in metrics if m.scope_type == scope_type]
        if not group:
            continue
        scope_name = group[0].scope_name
        heading = SCOPE_LABELS[scope_type]
        lines.append("")
        lines.append(f"### {heading} — {scope_name}")
        lines.extend(_render_scoped(metric) for metric in group)
    return lines


# ---------------------------------------------------------------------------
# Öğrenci sayısı değişimi senaryosu
# ---------------------------------------------------------------------------


def _compose_enrollment(payload: Any) -> ComposedResponse:
    """Öğrenci senaryosunu KAPSAMLARA AYIRARAK yazar.

    Program göstergeleri ile üniversite göstergeleri ayrı başlıklar altında
    durur. Kurum geneli bir sayı asla program sayısı gibi sunulmaz.
    """
    scope = payload.scope
    scoped = list(payload.scoped_metrics)

    # Kapsam, birim ve formül tutarlılığı denetlenir; uyumsuzlukta cevap
    # başarı sayılmaz.
    check_scope_consistency(scoped)

    lines = [
        f"**{scope.academic_year} — {scope.program}**",
        "",
        f"Senaryo: program öğrenci sayısında %{_number(payload.student_change_percentage)} "
        f"değişim ({_signed_count(payload.program_student_change, 'öğrenci')}).",
    ]
    lines.extend(_render_scope_groups(scoped))

    risks = list(getattr(payload, "risks", []) or [])
    if risks:
        lines.append("")
        lines.append("### Tespit edilen riskler (üniversite geneli)")
        lines.extend(f"- {risk}" for risk in risks[:5])

    metrics = [_metric_from_scoped(metric) for metric in scoped]

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
    scoped = list(payload.scoped_metrics)
    check_scope_consistency(scoped)

    lines = [
        f"**{scope.academic_year} — {scope.label}**",
        "",
        f"Senaryo: akademik personel maaşlarında %{_number(payload.salary_change_percentage)} değişim.",
    ]
    lines.extend(_render_scope_groups(scoped))

    risks = list(getattr(payload, "risks", []) or [])
    if risks:
        lines.append("")
        lines.append("### Tespit edilen riskler (üniversite geneli)")
        lines.extend(f"- {risk}" for risk in risks[:5])

    metrics = [_metric_from_scoped(metric) for metric in scoped]

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

    program_scope = ("program", payload.program_name)
    metrics = [
        _metric("student_count", "Öğrenci sayısı", None, payload.student_count, None,
                "öğrenci", *program_scope),
        _metric("quota", "Kontenjan", None, payload.quota, None, "öğrenci", *program_scope),
        _metric("occupancy_rate", "Doluluk oranı", None, payload.occupancy_rate, None,
                "%", *program_scope, formula="kayıtlı öğrenci / kontenjan × 100"),
        _metric("graduation_rate", "Mezuniyet oranı", None, payload.graduation_rate, None,
                "%", *program_scope),
        _metric("student_staff_ratio", "Öğrenci / öğretim üyesi",
                None, payload.student_staff_ratio, None, "oran", "department",
                payload.scope.department or "Bölüm",
                formula="bölüm öğrenci sayısı / bölüm öğretim üyesi sayısı"),
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

    scope_pair = (
        ("department", payload.scope.department)
        if payload.scope.department
        else ("university", "Üniversite geneli")
    )
    metrics = [
        _metric("total_revenue_usd", "Toplam gelir", None, payload.total_revenue_usd,
                None, "USD", *scope_pair),
        _metric("total_expenditure_usd", "Toplam gider", None,
                payload.total_expenditure_usd, None, "USD", *scope_pair),
        _metric("net_balance_usd", "Net denge", None, payload.net_balance_usd,
                None, "USD", *scope_pair, formula="toplam gelir − toplam gider"),
        _metric("cost_per_student_usd", "Öğrenci başına maliyet",
                None, payload.cost_per_student_usd, None, "USD", *scope_pair,
                formula="toplam gider / öğrenci sayısı"),
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
