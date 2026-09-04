"""Tespit edilen risklere göre Türkçe yönetim önerileri üreten servis.

Yönetici sayfayı açtığında sadece "risk var" demek yeterli değil; ne yapması
gerektiğini de görmeli. Öneri metinleri risk kodlarına bağlandığı için yeni bir
risk eklendiğinde sadece buraya bir satır eklemek yeterli olur.
"""

from decimal import Decimal
from typing import Dict, List

from app.schemas.scenarios import RiskItem, RiskLevel
from app.services.scenario_engine import ScenarioComputation

# Risk kodu -> öneri metni eşlemesi.
RECOMMENDATION_BY_RISK: Dict[str, str] = {
    "budget_deficit": (
        "Bütçe açığını kapatmak için öğrenim ücreti artışı, burs oranının kademeli azaltılması "
        "veya enerji ve teknoloji giderlerinde tasarruf seçenekleri değerlendirilmelidir."
    ),
    "high_student_staff_ratio": (
        "Öğrenci/öğretim üyesi oranını düşürmek için yeni akademik personel alımı planlanmalı "
        "ya da öğrenci kontenjanı artışı sınırlandırılmalıdır."
    ),
    "classroom_capacity_exceeded": (
        "Derslik açığı için yeni derslik yatırımı, ikili öğretim düzeni veya hibrit/uzaktan "
        "eğitim seçenekleri değerlendirilmelidir."
    ),
    "laboratory_capacity_exceeded": (
        "Laboratuvar açığı için laboratuvar yatırımı, grup sayısının artırılması veya "
        "laboratuvar kullanım saatlerinin genişletilmesi planlanmalıdır."
    ),
    "scholarship_rate_invalid": (
        "Burs oranı 0-100 aralığına çekilmelidir. Mevcut haliyle senaryo geçerli bir "
        "gelir tablosu üretemez."
    ),
    "staff_count_invalid": (
        "Akademik personel sayısı pozitif olacak şekilde personel değişimi yeniden "
        "düzenlenmelidir."
    ),
    "student_count_invalid": (
        "Öğrenci sayısı pozitif kalacak şekilde öğrenci değişim oranı yeniden "
        "düzenlenmelidir."
    ),
}

# Risk seviyesine göre açılış cümlesi.
HEADLINE_BY_LEVEL: Dict[RiskLevel, str] = {
    RiskLevel.LOW: "Senaryo sürdürülebilir görünüyor; kritik bir risk tespit edilmedi.",
    RiskLevel.MEDIUM: "Senaryo uygulanabilir ancak izlenmesi gereken riskler var.",
    RiskLevel.HIGH: "Senaryo yüksek riskli; uygulamadan önce önlem alınması gerekiyor.",
    RiskLevel.CRITICAL: (
        "Senaryo matematiksel olarak geçersiz değerler üretiyor; "
        "girdi parametreleri düzeltilmeden karar alınmamalıdır."
    ),
}

ZERO: Decimal = Decimal("0")


def build_recommendation(
    computation: ScenarioComputation,
    risks: List[RiskItem],
    risk_level: RiskLevel,
) -> str:
    """Risklere ve sayısal sonuçlara göre Türkçe öneri metni üretir."""
    parts: List[str] = [HEADLINE_BY_LEVEL[risk_level]]

    # Riske özel öneriler numaralandırılarak eklenir.
    if risks:
        for index, risk in enumerate(risks, start=1):
            advice: str = RECOMMENDATION_BY_RISK.get(
                risk.code, "Bu risk için ilgili birimle değerlendirme yapılmalıdır."
            )
            parts.append(f"{index}. {advice}")

    # Risk olmasa bile bütçe fazlası veya maliyet artışı gibi bilgilendirici notlar eklenir.
    parts.append(_financial_note(computation))
    parts.append(_cost_note(computation))

    # Metni tek parça halinde döndürüyoruz; arayüz isterse satır sonlarından bölebilir.
    return "\n".join(part for part in parts if part)


def _financial_note(computation: ScenarioComputation) -> str:
    """Bütçe dengesindeki değişimi açıklayan kısa not üretir."""
    difference: Decimal = computation.projected_balance - computation.baseline_balance

    if computation.projected_balance >= ZERO and difference >= ZERO:
        return (
            f"Bütçe dengesi {computation.baseline_balance:,.2f} seviyesinden "
            f"{computation.projected_balance:,.2f} seviyesine iyileşiyor."
        )
    if computation.projected_balance >= ZERO:
        return (
            f"Bütçe hâlâ fazla veriyor ancak denge {computation.baseline_balance:,.2f} "
            f"seviyesinden {computation.projected_balance:,.2f} seviyesine geriliyor."
        )
    return (
        f"Bütçe dengesi {computation.projected_balance:,.2f} ile açık veriyor; "
        "gelir artırıcı veya gider azaltıcı bir önlem gerekiyor."
    )


def _cost_note(computation: ScenarioComputation) -> str:
    """Öğrenci başına maliyetteki değişimi açıklayan kısa not üretir."""
    baseline_cost: Decimal = computation.baseline_cost_per_student
    projected_cost: Decimal = computation.projected_cost_per_student

    # Baseline maliyeti sıfırsa yüzdesel karşılaştırma yapılamaz.
    if baseline_cost == ZERO:
        return ""

    change_percent: Decimal = ((projected_cost - baseline_cost) / baseline_cost) * Decimal("100")
    change_percent = change_percent.quantize(Decimal("0.01"))

    if change_percent > ZERO:
        return (
            f"Öğrenci başına maliyet {baseline_cost:,.2f} seviyesinden "
            f"{projected_cost:,.2f} seviyesine, yani %{change_percent} oranında artıyor."
        )
    if change_percent < ZERO:
        return (
            f"Öğrenci başına maliyet {baseline_cost:,.2f} seviyesinden "
            f"{projected_cost:,.2f} seviyesine, yani %{abs(change_percent)} oranında azalıyor."
        )
    return f"Öğrenci başına maliyet {projected_cost:,.2f} seviyesinde sabit kalıyor."
