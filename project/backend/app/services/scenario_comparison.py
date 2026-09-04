"""Senaryo sonuçlarını baseline ile karşılaştıran ortak katman.

Neden ayrı bir dosya: "önceki değer / yeni değer / mutlak değişim / yüzde
değişim" dörtlüsü her metrik için tekrar ediyordu. Her ekran bu farkı kendi
hesaplarsa (özellikle arayüzde) yuvarlama farkları oluşur ve iki yerde iki
farklı yüzde görünür. Karşılaştırma tek yerde üretilir, arayüz yalnızca çizer.

BURADA HESAP YAPILIR, ARAYÜZDE YAPILMAZ.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional

from app.core.decimal_types import quantize_money

ZERO = Decimal("0")
HUNDRED = Decimal("100")


@dataclass
class MetricComparison:
    """Tek bir göstergenin baseline ↔ senaryo karşılaştırması."""

    key: str
    label: str
    #: "usd_million" | "usd" | "percent" | "count" | "ratio"
    unit: str
    baseline_value: Decimal
    projected_value: Decimal
    absolute_change: Decimal
    #: Baseline sıfırsa yüzde değişim tanımsızdır; 0 yazmak yerine None döner.
    percent_change: Optional[Decimal]
    #: "up" | "down" | "flat"
    direction: str
    #: Değişimin kurum için olumlu olup olmadığı. Gider artışı olumsuzdur.
    is_favorable: Optional[bool]
    #: Göstergenin hangi başlık altında gruplanacağı.
    group: str
    #: Değerin ne anlama geldiğini anlatan kısa açıklama.
    description: str = ""


def compare(
    key: str,
    label: str,
    unit: str,
    baseline_value: Decimal,
    projected_value: Decimal,
    group: str,
    higher_is_better: Optional[bool] = True,
    description: str = "",
) -> MetricComparison:
    """İki değeri karşılaştırıp değişim bilgisini üretir.

    higher_is_better=None verilirse gösterge nötr kabul edilir ve iyi/kötü
    yorumu yapılmaz (örneğin öğrenci sayısı: artması da azalması da kuruma
    göre değişir).
    """
    baseline = Decimal(str(baseline_value))
    projected = Decimal(str(projected_value))
    absolute = projected - baseline

    # Baseline sıfırken yüzde değişim matematiksel olarak tanımsızdır.
    # 0 veya 100 yazmak yanlış bilgi olurdu.
    percent: Optional[Decimal] = None
    if baseline != ZERO:
        percent = quantize_money(absolute / baseline * HUNDRED)

    if absolute > ZERO:
        direction = "up"
    elif absolute < ZERO:
        direction = "down"
    else:
        direction = "flat"

    is_favorable: Optional[bool] = None
    if higher_is_better is not None and absolute != ZERO:
        is_favorable = (absolute > ZERO) == higher_is_better

    return MetricComparison(
        key=key,
        label=label,
        unit=unit,
        baseline_value=quantize_money(baseline),
        projected_value=quantize_money(projected),
        absolute_change=quantize_money(absolute),
        percent_change=percent,
        direction=direction,
        is_favorable=is_favorable,
        group=group,
        description=description,
    )


@dataclass
class ComparisonReport:
    """Bir senaryonun tüm karşılaştırmaları, gruplar hâlinde."""

    financial: List[MetricComparison] = field(default_factory=list)
    academic: List[MetricComparison] = field(default_factory=list)
    capacity: List[MetricComparison] = field(default_factory=list)

    def all(self) -> List[MetricComparison]:
        """Tüm karşılaştırmalar tek listede."""
        return self.financial + self.academic + self.capacity

    def most_significant(self, limit: int = 5) -> List[MetricComparison]:
        """Mutlak yüzde değişimi en büyük göstergeler.

        Yöneticinin "bu senaryoda en çok ne değişti" sorusuna cevap verir.
        """
        scored = [m for m in self.all() if m.percent_change is not None]
        scored.sort(key=lambda m: abs(m.percent_change), reverse=True)
        return scored[:limit]
