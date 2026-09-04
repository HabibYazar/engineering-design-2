"""Öğrenci analitiğinden erken uyarı üreten servis.

Analitik servisi sadece sayı üretir; "bu sayı sorunlu mu" yorumu burada yapılır.
Eşikler tek bir yerde toplandığı için üniversite politikası değiştiğinde
sadece bu dosyadaki sabitleri güncellemek yeterlidir.
"""

from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ProgramEnrollmentSnapshot
from app.schemas.student_analytics import (
    AlertSeverity,
    AlertsResponse,
    ProgramAnalytics,
    StudentAlert,
)
from app.services.student_analytics_service import (
    build_program_analytics,
    percentage,
)

# --- Eşik değerleri ---
MIN_OCCUPANCY_RATE: Decimal = Decimal("50")  # altına düşerse kontenjan doldurulamıyor
MAX_ATTRITION_RATE: Decimal = Decimal("15")  # üstüne çıkarsa öğrenci kaybı yüksek
MAX_NON_RENEWAL_RATE: Decimal = Decimal("10")
MIN_GRADUATION_RATE: Decimal = Decimal("40")
MIN_AVERAGE_GPA: Decimal = Decimal("2.00")

# Uluslararasılaşma hedefi kurum stratejisine göre belirlenir; varsayılan %5.
DEFAULT_INTERNATIONAL_TARGET: Decimal = Decimal("5")

# Kaç yıl üst üste düşüş uyarı üretsin.
SCORE_DECLINE_YEARS: int = 2
DEMAND_DECLINE_YEARS: int = 3


def _severity_for_gap(current: Decimal, threshold: Decimal, critical_gap: Decimal) -> AlertSeverity:
    """Eşikten sapmanın büyüklüğüne göre şiddet seviyesi belirler."""
    # Eşiğin biraz altındaki bir değerle çok altındaki bir değeri aynı seviyede
    # göstermek yöneticiyi yanıltırdı; bu yüzden sapma miktarına bakıyoruz.
    gap: Decimal = abs(threshold - current)
    if gap >= critical_gap:
        return AlertSeverity.CRITICAL
    if gap >= critical_gap / 2:
        return AlertSeverity.HIGH
    return AlertSeverity.WARNING


def _snapshot_history(db: Session) -> Dict[int, List[ProgramEnrollmentSnapshot]]:
    """Program bazında snapshot geçmişini tek sorguda getirir."""
    statement = select(ProgramEnrollmentSnapshot).order_by(
        ProgramEnrollmentSnapshot.academic_program_id,
        ProgramEnrollmentSnapshot.academic_year,
    )
    history: Dict[int, List[ProgramEnrollmentSnapshot]] = {}
    for snapshot in db.execute(statement).scalars().all():
        history.setdefault(snapshot.academic_program_id, []).append(snapshot)
    return history


def _check_consecutive_decline(values: List[Optional[Decimal]], years: int) -> bool:
    """Son 'years' geçişte değerlerin üst üste düşüp düşmediğini kontrol eder."""
    # years=2 ise son 3 değere bakılır: iki ardışık düşüş demektir.
    window = values[-(years + 1):]
    if len(window) < years + 1 or any(value is None for value in window):
        return False
    return all(window[i] < window[i - 1] for i in range(1, len(window)))


def _program_alerts(program: ProgramAnalytics) -> List[StudentAlert]:
    """Tek bir programın metriklerine bakarak uyarı listesi üretir."""
    alerts: List[StudentAlert] = []

    # --- 1) Düşük doluluk ---
    # Kontenjanı olmayan programlar (quota=0) için doluluk uyarısı anlamsızdır.
    if program.quota > 0 and program.occupancy_rate < MIN_OCCUPANCY_RATE:
        alerts.append(
            StudentAlert(
                code="low_occupancy_rate",
                severity=_severity_for_gap(
                    program.occupancy_rate, MIN_OCCUPANCY_RATE, Decimal("25")
                ),
                entity_type="program",
                entity_id=program.program_id,
                entity_name=program.program_name,
                metric="occupancy_rate",
                current_value=program.occupancy_rate,
                threshold=MIN_OCCUPANCY_RATE,
                message=(
                    f"{program.program_name} programının doluluk oranı %{program.occupancy_rate} "
                    f"ile hedef alt sınır olan %{MIN_OCCUPANCY_RATE} değerinin altında."
                ),
                recommendation=(
                    "Kontenjan gözden geçirilmeli, tanıtım faaliyetleri artırılmalı ve "
                    "programın tercih edilebilirliğini artıracak müfredat güncellemesi "
                    "değerlendirilmelidir."
                ),
            )
        )

    # --- 2) Yüksek öğrenci kaybı ---
    if program.total_students > 0 and program.attrition_rate > MAX_ATTRITION_RATE:
        alerts.append(
            StudentAlert(
                code="high_attrition_rate",
                severity=_severity_for_gap(
                    program.attrition_rate, MAX_ATTRITION_RATE, Decimal("15")
                ),
                entity_type="program",
                entity_id=program.program_id,
                entity_name=program.program_name,
                metric="attrition_rate",
                current_value=program.attrition_rate,
                threshold=MAX_ATTRITION_RATE,
                message=(
                    f"{program.program_name} programında öğrenci kaybı oranı "
                    f"%{program.attrition_rate} ile üst sınır olan %{MAX_ATTRITION_RATE} "
                    "değerini aşıyor."
                ),
                recommendation=(
                    "Kaydını bırakan öğrencilerle görüşme yapılmalı, akademik danışmanlık "
                    "ve öğrenci destek hizmetleri güçlendirilmelidir."
                ),
            )
        )

    # --- 3) Yüksek kayıt yenilememe ---
    if program.total_students > 0 and program.non_renewal_rate > MAX_NON_RENEWAL_RATE:
        alerts.append(
            StudentAlert(
                code="high_non_renewal_rate",
                severity=_severity_for_gap(
                    program.non_renewal_rate, MAX_NON_RENEWAL_RATE, Decimal("10")
                ),
                entity_type="program",
                entity_id=program.program_id,
                entity_name=program.program_name,
                metric="non_renewal_rate",
                current_value=program.non_renewal_rate,
                threshold=MAX_NON_RENEWAL_RATE,
                message=(
                    f"{program.program_name} programında kayıt yenilememe oranı "
                    f"%{program.non_renewal_rate} ile üst sınır olan "
                    f"%{MAX_NON_RENEWAL_RATE} değerini aşıyor."
                ),
                recommendation=(
                    "Kayıt yenileme dönemi öncesi hatırlatma ve danışmanlık süreci "
                    "kurulmalı, mali zorluk yaşayan öğrenciler için burs/taksit "
                    "seçenekleri değerlendirilmelidir."
                ),
            )
        )

    # --- 4) Düşük mezuniyet oranı ---
    if program.total_students > 0 and program.graduation_rate < MIN_GRADUATION_RATE:
        alerts.append(
            StudentAlert(
                code="low_graduation_rate",
                severity=_severity_for_gap(
                    program.graduation_rate, MIN_GRADUATION_RATE, Decimal("20")
                ),
                entity_type="program",
                entity_id=program.program_id,
                entity_name=program.program_name,
                metric="graduation_rate",
                current_value=program.graduation_rate,
                threshold=MIN_GRADUATION_RATE,
                message=(
                    f"{program.program_name} programının mezuniyet oranı "
                    f"%{program.graduation_rate} ile hedefin (%{MIN_GRADUATION_RATE}) altında."
                ),
                recommendation=(
                    "Mezuniyet önündeki engeller (başarısız dersler, staj, bitirme projesi) "
                    "analiz edilmeli ve telafi imkânları sunulmalıdır."
                ),
            )
        )

    # --- 5) Düşük ortalama GPA ---
    if program.total_students > 0 and Decimal("0") < program.average_gpa < MIN_AVERAGE_GPA:
        alerts.append(
            StudentAlert(
                code="low_average_gpa",
                severity=_severity_for_gap(
                    program.average_gpa, MIN_AVERAGE_GPA, Decimal("0.50")
                ),
                entity_type="program",
                entity_id=program.program_id,
                entity_name=program.program_name,
                metric="average_gpa",
                current_value=program.average_gpa,
                threshold=MIN_AVERAGE_GPA,
                message=(
                    f"{program.program_name} programının ortalama GPA değeri "
                    f"{program.average_gpa} ile alt sınır olan {MIN_AVERAGE_GPA} değerinin altında."
                ),
                recommendation=(
                    "Akademik başarısızlık nedenleri incelenmeli, ders geçme oranları düşük "
                    "derslerde ek çalışma saatleri ve mentörlük programı açılmalıdır."
                ),
            )
        )

    return alerts


def build_alerts(
    db: Session,
    faculty_id: Optional[int] = None,
    department_id: Optional[int] = None,
    academic_program_id: Optional[int] = None,
    severity: Optional[AlertSeverity] = None,
    international_target_percent: Decimal = DEFAULT_INTERNATIONAL_TARGET,
) -> AlertsResponse:
    """Tüm erken uyarıları toplayıp filtreleyerek döndürür."""
    programs: List[ProgramAnalytics] = build_program_analytics(
        db,
        faculty_id=faculty_id,
        department_id=department_id,
        academic_program_id=academic_program_id,
    )
    history = _snapshot_history(db)

    alerts: List[StudentAlert] = []

    for program in programs:
        alerts.extend(_program_alerts(program))

        # --- 6) Uluslararası öğrenci hedefinin altında kalma ---
        if (
            program.total_students > 0
            and program.international_student_percentage < international_target_percent
        ):
            alerts.append(
                StudentAlert(
                    code="low_international_percentage",
                    severity=AlertSeverity.INFO,
                    entity_type="program",
                    entity_id=program.program_id,
                    entity_name=program.program_name,
                    metric="international_student_percentage",
                    current_value=program.international_student_percentage,
                    threshold=international_target_percent,
                    message=(
                        f"{program.program_name} programında uluslararası öğrenci oranı "
                        f"%{program.international_student_percentage} ile hedef olan "
                        f"%{international_target_percent} değerinin altında."
                    ),
                    recommendation=(
                        "Uluslararası tanıtım, değişim programları ve İngilizce ders "
                        "havuzunun genişletilmesi değerlendirilmelidir."
                    ),
                )
            )

        snapshots = history.get(program.program_id, [])

        # --- 7) Taban puanın iki yıl üst üste düşmesi ---
        scores: List[Optional[Decimal]] = [
            item.minimum_admission_score for item in snapshots
        ]
        if _check_consecutive_decline(scores, SCORE_DECLINE_YEARS):
            alerts.append(
                StudentAlert(
                    code="declining_admission_score",
                    severity=AlertSeverity.HIGH,
                    entity_type="program",
                    entity_id=program.program_id,
                    entity_name=program.program_name,
                    metric="minimum_admission_score",
                    current_value=scores[-1],
                    threshold=scores[-(SCORE_DECLINE_YEARS + 1)],
                    message=(
                        f"{program.program_name} programının taban puanı "
                        f"{SCORE_DECLINE_YEARS} yıl üst üste düştü "
                        f"({scores[-(SCORE_DECLINE_YEARS + 1)]} → {scores[-1]})."
                    ),
                    recommendation=(
                        "Programın tercih sıralamasındaki gerileme nedenleri araştırılmalı; "
                        "müfredat, mezun istihdam oranları ve tanıtım stratejisi "
                        "gözden geçirilmelidir."
                    ),
                )
            )

        # --- 8) Talebin üç yıl üst üste düşmesi ---
        enrollments: List[Optional[Decimal]] = [
            Decimal(item.enrolled_student_count) for item in snapshots
        ]
        if _check_consecutive_decline(enrollments, DEMAND_DECLINE_YEARS):
            alerts.append(
                StudentAlert(
                    code="declining_student_demand",
                    severity=AlertSeverity.CRITICAL,
                    entity_type="program",
                    entity_id=program.program_id,
                    entity_name=program.program_name,
                    metric="enrolled_student_count",
                    current_value=enrollments[-1],
                    threshold=enrollments[-(DEMAND_DECLINE_YEARS + 1)],
                    message=(
                        f"{program.program_name} programına yerleşen öğrenci sayısı "
                        f"{DEMAND_DECLINE_YEARS} yıl üst üste düştü "
                        f"({enrollments[-(DEMAND_DECLINE_YEARS + 1)]} → {enrollments[-1]})."
                    ),
                    recommendation=(
                        "Program için kapsamlı bir talep analizi yapılmalı; kontenjan "
                        "azaltma, program birleştirme veya yeniden konumlandırma "
                        "seçenekleri değerlendirilmelidir."
                    ),
                )
            )

    # Şiddet filtresi uygulanır.
    if severity is not None:
        alerts = [alert for alert in alerts if alert.severity == severity]

    # En kritik uyarılar listenin başında görünsün.
    severity_order: Dict[AlertSeverity, int] = {
        AlertSeverity.CRITICAL: 0,
        AlertSeverity.HIGH: 1,
        AlertSeverity.WARNING: 2,
        AlertSeverity.INFO: 3,
    }
    alerts.sort(key=lambda alert: (severity_order[alert.severity], alert.entity_name))

    counts: Dict[str, int] = {level.value: 0 for level in AlertSeverity}
    for alert in alerts:
        counts[alert.severity.value] += 1

    return AlertsResponse(
        total_alerts=len(alerts),
        counts_by_severity=counts,
        alerts=alerts,
        applied_filters={
            "faculty_id": faculty_id,
            "department_id": department_id,
            "academic_program_id": academic_program_id,
            "severity": severity.value if severity else None,
            "international_target_percent": str(international_target_percent),
        },
    )
