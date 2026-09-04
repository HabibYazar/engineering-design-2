"""Metriklerin ANLAM türü ve buradan türeyen grafik seçimi.

NEDEN VAR
---------
Grafik türü ne modelin ne de programcının keyfine bırakılabilir. "Öğrenci
370'ten 426'ya çıkıyor" ile "derslik talebinin %38,96'sı karşılanıyor" aynı
grafikle anlatılamaz: biri iki nokta arasındaki hareket, öteki bir doluluk
oranı.

Bu dosya iki soruyu cevaplar:

1. Bir metrik NE ANLAMA geliyor?  → `classify()` → `semantic_type`
2. Bu anlam hangi grafikle anlatılır? → `ui_planner` bu türleri kullanır

Sınıflandırma anahtar adına ve BİRİME bakar; belirli bir programa, bölüme
veya senaryoya gömülü değildir. Yarın eklenecek bir metrik de aynı
kurallarla sınıflanır.

Bir metrik anlamını kendisi bildirebilir (`ScopedMetric.semantic_type`);
bildirmezse buradaki kurallar devreye girer.
"""

from typing import Optional

# Kullanıcı arayüzünün tanıdığı anlam türleri. Kapalı liste.
SEMANTIC_TYPES = (
    "count_change",       # sayım değişimi (öğrenci, kişi)
    "monetary_change",    # parasal değişim (USD)
    "capacity_coverage",  # talebin karşılanan/karşılanamayan oranı (%)
    "capacity_demand",    # fiziksel kapasite talebi (koltuk-saat, kişi)
    "staffing_gap",       # kadro/FTE açığı
    "target_comparison",  # mevcut kapasite ile hedefin karşılaştırılması
    "historical_trend",   # yıllara göre seyir
    "forecast",           # gelecek tahmini
    "risk_score",         # olasılık/etki
    "distribution",       # kaynak veya bütçe dağılımı
    "utilization",        # kullanım oranı (%100'ü aşabilir)
    "ranking",            # birimler arası sıralama/karşılaştırma
    "status",             # sayısal olmayan durum bilgisi
)

# Fiziksel kapasitenin zaman boyutu taşıyan birimleri.
_PHYSICAL_UNITS = {"koltuk-saat", "istasyon-saat", "eş zamanlı kişi"}


def classify(key: str, unit: str, label: str = "") -> str:
    """Bir metriğin anlam türünü belirler.

    Sıralama önemlidir: önce birim, sonra anahtar adındaki ipuçları. Birim
    en güvenilir işaret; "USD" taşıyan bir metrik her hâlükârda parasaldır.
    """
    key = (key or "").lower()
    unit = (unit or "").strip()

    if unit == "durum":
        return "status"

    if unit == "USD":
        return "monetary_change"

    if unit == "%":
        if "coverage" in key or "shortfall" in key:
            return "capacity_coverage"
        if "utilization" in key:
            return "utilization"
        if "risk" in key:
            return "risk_score"
        return "utilization"

    if unit == "FTE":
        if "gap" in key or "marginal" in key:
            return "staffing_gap"
        return "target_comparison"

    if unit in _PHYSICAL_UNITS:
        if key.endswith("_capacity") or "capacity" in key and "demand" not in key:
            return "target_comparison"
        return "capacity_demand"

    if unit == "kişi":
        if "gap" in key:
            return "staffing_gap"
        if "recommended" in key or "capacity" in key:
            return "target_comparison"
        return "count_change"

    if unit in {"öğrenci", "adet", "program", "bölüm"}:
        return "count_change"

    # Tanınmayan birim: en az zarar veren varsayım sayım değişimidir.
    return "count_change"


# ---------------------------------------------------------------------------
# Parasal kalemin bütçedeki YÖNÜ
# ---------------------------------------------------------------------------

#: Bütçe akış yönleri. Şelale grafiği bu alana bakar.
#: "unit_price" bir bütçe akışı DEĞİLDİR: ortalama maaş veya öğrenci başına
#: maliyet gibi birim fiyatlar toplanamaz, bütçeye eklenemez. Ayrı bir değer
#: olması gerekiyor; `None` bırakılsaydı sınıflandırıcı onları yeniden
#: "gider" sayardı.
FLOWS = ("inflow", "outflow", "balance", "unit_price")

_INFLOW_HINTS = ("revenue", "income", "gelir", "hibe", "grant", "bağış", "fon")
_OUTFLOW_HINTS = ("expense", "expenditure", "cost", "gider", "maliyet", "harcama",
                  "salary", "maaş", "personnel", "personel")
_BALANCE_HINTS = ("balance", "net", "bakiye", "denge")
#: Birim fiyatlar: bütçe kalemi değil, bölme sonucu.
_UNIT_PRICE_HINTS = ("average_", "_per_", "per_student", "ortalama", "başına")

#: "Toplam" olduğunu gösteren ipuçları. Toplam kalemler şelalede KATKI
#: sayılmaz; sayılsaydı aynı tutar hem alt kalem hem toplam olarak iki kez
#: hesaba girerdi.
_TOTAL_HINTS = ("total_", "_total", "toplam", "net_balance", "cost_per_")


def classify_flow(key: str, unit: str, label: str = "") -> Optional[str]:
    """Parasal bir kalemin gelir mi gider mi net sonuç mu olduğunu belirler.

    Yalnızca para birimli metrikler için anlamlıdır; diğerlerinde None döner.
    Sıralama önemli: "net bütçe" hem "net" hem "bütçe" içerir, önce bakiye
    kontrol edilir.
    """
    if (unit or "").strip() != "USD":
        return None
    haystack = f"{key} {label}".lower()
    if any(hint in haystack for hint in _UNIT_PRICE_HINTS):
        return "unit_price"
    if any(hint in haystack for hint in _BALANCE_HINTS):
        return "balance"
    if any(hint in haystack for hint in _OUTFLOW_HINTS):
        return "outflow"
    if any(hint in haystack for hint in _INFLOW_HINTS):
        return "inflow"
    return None


def looks_like_total(key: str) -> bool:
    """Anahtar bir toplam kalemi mi anlatıyor?"""
    lowered = (key or "").lower()
    return any(hint in lowered for hint in _TOTAL_HINTS)


def flow_of(metric) -> Optional[str]:
    """Metriğin bildirdiği yönü kullanır, yoksa sınıflandırır."""
    declared = (
        metric.get("flow") if isinstance(metric, dict) else getattr(metric, "flow", None)
    )
    if declared in FLOWS:
        return declared
    if isinstance(metric, dict):
        return classify_flow(metric.get("key", ""), metric.get("unit", ""),
                             metric.get("label", ""))
    return classify_flow(metric.key, metric.unit, metric.label)


def resolve(metric) -> str:
    """Metriğin bildirdiği türü kullanır, yoksa sınıflandırır.

    `metric` hem `ScopedMetric` nesnesi hem de sözlük olabilir.
    """
    declared: Optional[str] = None
    if isinstance(metric, dict):
        declared = metric.get("semantic_type")
        key, unit, label = metric.get("key", ""), metric.get("unit", ""), metric.get("label", "")
    else:
        declared = getattr(metric, "semantic_type", None)
        key, unit, label = metric.key, metric.unit, metric.label

    if declared and declared in SEMANTIC_TYPES:
        return declared
    return classify(key, unit, label)
