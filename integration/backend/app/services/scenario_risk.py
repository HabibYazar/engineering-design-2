"""Senaryo sonuçlarındaki riskleri tespit eden servis.

Hesaplama motoru sadece sayıları üretir; "bu sayı iyi mi kötü mü" yorumu burada yapılır.
Bu ayrım sayesinde risk eşikleri değiştiğinde formüllere hiç dokunmak gerekmez.
"""

from decimal import Decimal
from typing import List, Tuple

from app.schemas.scenarios import RiskItem, RiskLevel
from app.services.scenario_engine import ScenarioComputation

# Öğrenci/öğretim üyesi oranı için üst sınır.
# YÖK ve akreditasyon değerlendirmelerinde yaygın kullanılan eşik referans alındı.
MAX_STUDENT_STAFF_RATIO: Decimal = Decimal("25")

ZERO: Decimal = Decimal("0")
HUNDRED: Decimal = Decimal("100")

# Risk seviyesi eşikleri: kaç adet uyarı hangi seviyeye karşılık geliyor.
MEDIUM_RISK_THRESHOLD: int = 1
HIGH_RISK_THRESHOLD: int = 3


def detect_risks(computation: ScenarioComputation) -> List[RiskItem]:
    """Hesaplanan senaryo sonucundaki tüm riskleri listeler."""
    risks: List[RiskItem] = []

    # --- 1) Bütçe açığı ---
    # Giderin geliri aşması, senaryonun sürdürülebilir olmadığının en temel göstergesi.
    if computation.projected_expenditure > computation.projected_revenue:
        deficit: Decimal = computation.projected_expenditure - computation.projected_revenue
        risks.append(
            RiskItem(
                code="budget_deficit",
                message=(
                    f"Bütçe açığı: Tahmini gider ({computation.projected_expenditure:,.2f}) "
                    f"tahmini geliri ({computation.projected_revenue:,.2f}) "
                    f"{deficit:,.2f} tutarında aşıyor."
                ),
                severity="warning",
            )
        )

    # --- 2) Öğrenci/öğretim üyesi oranı ---
    if computation.projected_student_staff_ratio > MAX_STUDENT_STAFF_RATIO:
        risks.append(
            RiskItem(
                code="high_student_staff_ratio",
                message=(
                    f"Öğrenci/öğretim üyesi oranı {computation.projected_student_staff_ratio} "
                    f"seviyesine çıkıyor ve kabul edilen üst sınır olan "
                    f"{MAX_STUDENT_STAFF_RATIO} değerini aşıyor. Eğitim kalitesi riske girer."
                ),
                severity="warning",
            )
        )

    # --- 3) Derslik kapasitesi ---
    # Karşılaştırma EŞ ZAMANLI talep üzerinden yapılır. Toplam öğrenci sayısını
    # kapasiteyle karşılaştırmak, tüm öğrencilerin aynı anda derslikte olduğunu
    # varsaymak demektir; bu varsayımla her kurum "kapasitesi yetersiz" çıkar ve
    # uyarı anlamını yitirir. Aynı düzeltme scenario_engine._capacity_status
    # içinde de yapıldı; iki yerde farklı ölçüt kullanmamak için burada da
    # motorun hesapladığı eş zamanlı talep kullanılıyor.
    if computation.simultaneous_classroom_demand > computation.projected_classroom_capacity:
        shortage: int = (
            computation.simultaneous_classroom_demand - computation.projected_classroom_capacity
        )
        risks.append(
            RiskItem(
                code="classroom_capacity_exceeded",
                message=(
                    f"Derslik kapasitesi yetersiz: aynı anda derslikte olması beklenen "
                    f"{computation.simultaneous_classroom_demand} öğrenciye karşılık "
                    f"{computation.projected_classroom_capacity} kapasite var. "
                    f"{shortage} kişilik açık oluşuyor."
                ),
                severity="warning",
            )
        )

    # --- 4) Laboratuvar kapasitesi ---
    if computation.simultaneous_laboratory_demand > computation.projected_laboratory_capacity:
        shortage = (
            computation.simultaneous_laboratory_demand - computation.projected_laboratory_capacity
        )
        risks.append(
            RiskItem(
                code="laboratory_capacity_exceeded",
                message=(
                    f"Laboratuvar kapasitesi yetersiz: aynı anda laboratuvarda olması beklenen "
                    f"{computation.simultaneous_laboratory_demand} öğrenciye karşılık "
                    f"{computation.projected_laboratory_capacity} kapasite var. "
                    f"{shortage} kişilik açık oluşuyor."
                ),
                severity="warning",
            )
        )

    # --- 5) Burs oranı geçersizliği ---
    # %100'ü aşan burs oranı, öğrenciden gelir yerine para ödendiği anlamına gelir;
    # bu matematiksel olarak geçersiz bir senaryodur.
    if computation.effective_scholarship_rate_percent > HUNDRED:
        risks.append(
            RiskItem(
                code="scholarship_rate_invalid",
                message=(
                    f"Toplam burs oranı %{computation.effective_scholarship_rate_percent} "
                    "seviyesine çıkıyor ve %100'ü aşıyor. Bu durumda öğrenim geliri negatife "
                    "döner, senaryo matematiksel olarak geçersizdir."
                ),
                severity="critical",
            )
        )
    elif computation.effective_scholarship_rate_percent < ZERO:
        risks.append(
            RiskItem(
                code="scholarship_rate_invalid",
                message=(
                    f"Toplam burs oranı %{computation.effective_scholarship_rate_percent} "
                    "olarak hesaplandı. Burs oranı negatif olamaz."
                ),
                severity="critical",
            )
        )

    # --- 6) Personel sayısının sıfıra düşmesi ---
    if computation.projected_staff_count <= 0:
        risks.append(
            RiskItem(
                code="staff_count_invalid",
                message=(
                    f"Tahmini akademik personel sayısı {computation.projected_staff_count} "
                    "olarak hesaplandı. Personel sayısı sıfır veya negatif olduğunda "
                    "öğrenci/öğretim üyesi oranı hesaplanamaz ve eğitim sürdürülemez."
                ),
                severity="critical",
            )
        )

    # --- 7) Öğrenci sayısının sıfıra düşmesi ---
    if computation.projected_student_count <= 0:
        risks.append(
            RiskItem(
                code="student_count_invalid",
                message=(
                    f"Tahmini öğrenci sayısı {computation.projected_student_count} olarak "
                    "hesaplandı. Öğrenci sayısı sıfır veya negatif olduğunda öğrenci başına "
                    "maliyet hesaplanamaz."
                ),
                severity="critical",
            )
        )

    return risks


def calculate_risk_level(risks: List[RiskItem]) -> RiskLevel:
    """Tespit edilen risklere bakarak genel risk seviyesini belirler."""
    # Kritik bir geçersizlik varsa risk sayısına bakmadan doğrudan critical döner;
    # çünkü bu durumda hesaplanan diğer sayılar da güvenilir değildir.
    if any(risk.severity == "critical" for risk in risks):
        return RiskLevel.CRITICAL

    risk_count: int = len(risks)
    if risk_count == 0:
        return RiskLevel.LOW
    if risk_count >= HIGH_RISK_THRESHOLD:
        return RiskLevel.HIGH
    return RiskLevel.MEDIUM


def evaluate(computation: ScenarioComputation) -> Tuple[List[RiskItem], RiskLevel]:
    """Riskleri tespit edip seviyeyi hesaplayan kısayol fonksiyonu."""
    risks: List[RiskItem] = detect_risks(computation)
    return risks, calculate_risk_level(risks)
