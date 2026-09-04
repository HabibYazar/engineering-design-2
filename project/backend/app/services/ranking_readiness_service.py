"""Veri hazırlık (readiness) katsayıları ve eksik veri analizi.

Bu dosya, "elimizdeki veri bir değerlendirme yapmaya ne kadar hazır?" sorusunu
cevaplar. Performans skorundan bilinçli olarak ayrılmıştır: bir kurum eldeki
az sayıda veriyle yüksek performans gösteriyor olabilir, ama veri hazırlığı
düşükse o skor güvenilir değildir.
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, List, Optional

from app.schemas.ranking_evaluations import DataStatus, EvaluationRiskLevel

TWO_PLACES: Decimal = Decimal("0.01")
ZERO: Decimal = Decimal("0.00")
HUNDRED: Decimal = Decimal("100.00")

# Veri durumunun hazırlık skoruna katkı katsayıları.
# Tek yerde tanımlanır ki kurum politikası değiştiğinde sadece burası güncellensin.
#   available : veri tam ve doğrulanmış     -> tam puan
#   estimated : tahmin edilmiş ama kullanılabilir -> yüksek kısmi puan
#   partial   : verinin bir kısmı var       -> yarım puan
#   missing   : veri hiç yok                -> puan yok
#   invalid   : veri var ama geçersiz       -> puan yok
DATA_STATUS_READINESS_FACTOR: Dict[str, Decimal] = {
    DataStatus.AVAILABLE.value: Decimal("1.00"),
    DataStatus.ESTIMATED.value: Decimal("0.75"),
    DataStatus.PARTIAL.value: Decimal("0.50"),
    DataStatus.MISSING.value: Decimal("0.00"),
    DataStatus.INVALID.value: Decimal("0.00"),
}

# Performans skorunda kullanılabilir sayılan durumlar.
# missing ve invalid verilerden skor üretilmez.
USABLE_STATUSES: frozenset = frozenset(
    {DataStatus.AVAILABLE.value, DataStatus.PARTIAL.value, DataStatus.ESTIMATED.value}
)

# Risk seviyesi eşikleri (compliance skoru üzerinden).
RISK_THRESHOLDS: List[tuple] = [
    (Decimal("75.00"), EvaluationRiskLevel.LOW),
    (Decimal("50.00"), EvaluationRiskLevel.MEDIUM),
    (Decimal("25.00"), EvaluationRiskLevel.HIGH),
]

# Hazırlık bu değerlerin altındayken risk yapay olarak düşük görünmesin diye
# alt sınır (taban) uygulanır.
READINESS_FLOOR_HIGH: Decimal = Decimal("50.00")
READINESS_FLOOR_CRITICAL: Decimal = Decimal("25.00")


def quantize(value: Decimal) -> Decimal:
    """Skorları iki ondalık basamağa yuvarlar."""
    return Decimal(str(value)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def clamp_score(value: Decimal) -> Decimal:
    """Skoru 0-100 aralığına kırpar."""
    # Normalizasyon formülleri uç değerlerde aralığın dışına taşabildiği için
    # sonucu her zaman güvenli aralığa çekiyoruz.
    if value < ZERO:
        return ZERO
    if value > HUNDRED:
        return HUNDRED
    return quantize(value)


def readiness_factor(data_status: Optional[str]) -> Decimal:
    """Veri durumuna karşılık gelen hazırlık katsayısını döndürür."""
    # Hiç kayıt yoksa (None) veri eksik sayılır.
    if data_status is None:
        return DATA_STATUS_READINESS_FACTOR[DataStatus.MISSING.value]
    return DATA_STATUS_READINESS_FACTOR.get(data_status, ZERO)


def is_usable(data_status: Optional[str]) -> bool:
    """Verinin performans hesabında kullanılabilir olup olmadığını söyler."""
    return data_status in USABLE_STATUSES


def calculate_risk_level(
    compliance_score: Decimal,
    readiness_score: Decimal,
) -> EvaluationRiskLevel:
    """Uyum ve hazırlık skorlarına göre risk seviyesini belirler.

    Önce compliance skoruna göre eşik uygulanır. Ardından hazırlık çok düşükse
    risk seviyesi yukarı çekilir: az veriyle üretilmiş yüksek bir skor yüzünden
    riskin yapay olarak "low" görünmesini engellemek için.
    """
    level: EvaluationRiskLevel = EvaluationRiskLevel.CRITICAL
    for threshold, candidate in RISK_THRESHOLDS:
        if compliance_score >= threshold:
            level = candidate
            break

    # Hazırlık tabanı: veri yetersizse risk düşük gösterilemez.
    if readiness_score < READINESS_FLOOR_CRITICAL:
        return EvaluationRiskLevel.CRITICAL

    order: List[EvaluationRiskLevel] = [
        EvaluationRiskLevel.LOW,
        EvaluationRiskLevel.MEDIUM,
        EvaluationRiskLevel.HIGH,
        EvaluationRiskLevel.CRITICAL,
    ]
    if readiness_score < READINESS_FLOOR_HIGH:
        # En az "high" seviyesine yükselt.
        if order.index(level) < order.index(EvaluationRiskLevel.HIGH):
            return EvaluationRiskLevel.HIGH

    return level


def compliance_score(performance_score: Decimal, readiness_score: Decimal) -> Decimal:
    """Uyum skorunu hesaplar.

    Formül: performance × readiness / 100

    Mantığı şu: bir skorun ne kadar "güvenilir" olduğu, onu üreten verinin ne
    kadar tam olduğuna bağlıdır. Performansı 80 olan ama verisinin yalnızca
    yarısı hazır bir çerçevenin gerçek uyum düzeyi 40'tır.
    """
    return quantize(performance_score * readiness_score / HUNDRED)


def weighted_average(pairs: List[tuple]) -> Decimal:
    """(değer, ağırlık) çiftlerinden ağırlıklı ortalama hesaplar.

    Ağırlık toplamı sıfırsa 0 döner; sıfıra bölme oluşmaz.
    """
    total_weight: Decimal = sum((Decimal(str(weight)) for _, weight in pairs), ZERO)
    if total_weight == ZERO:
        return ZERO

    total_value: Decimal = sum(
        (Decimal(str(value)) * Decimal(str(weight)) for value, weight in pairs), ZERO
    )
    return quantize(total_value / total_weight)
