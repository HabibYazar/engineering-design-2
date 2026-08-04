"""Stratejik öneri üretme servisi.

Hesaplama motoru sayı üretir; bu servis "bu sayıyla ne yapmalı" sorusunu
cevaplar. Öneriler sabit cümleler değildir: mevcut değer, hedef ve aradaki fark
kullanılarak her gösterge için dinamik olarak yazılır.

expected_score_gain, hedefe ulaşılırsa çerçevenin performans skorunda beklenen
artışı puan cinsinden verir. Böylece yönetici "hangi iyileştirme en çok kazandırır"
sorusunu veriye dayanarak yanıtlayabilir.
"""

from decimal import Decimal
from typing import Dict, List, Optional

from app.schemas.ranking_evaluations import (
    AssessmentDetailResponse,
    DataStatus,
    DimensionAssessmentResponse,
    IndicatorAssessmentDetail,
    IndicatorDirection,
    RecommendationItem,
    RecommendationUrgency,
)
from app.services.ranking_readiness_service import HUNDRED, ZERO, quantize

# Bu skorun altındaki göstergeler için iyileştirme önerisi üretilir.
IMPROVEMENT_SCORE_THRESHOLD: Decimal = Decimal("70.00")

# Aciliyet eşikleri (gösterge performans skoruna göre).
URGENCY_THRESHOLDS: List[tuple] = [
    (Decimal("25.00"), RecommendationUrgency.CRITICAL),
    (Decimal("50.00"), RecommendationUrgency.HIGH),
    (Decimal("70.00"), RecommendationUrgency.MEDIUM),
]

# Bir raporda döndürülecek en fazla öneri sayısı.
MAX_RECOMMENDATIONS: int = 15

# Gösterge koduna göre konuya özel eylem metinleri.
# Anahtar, gösterge kodunun içinde ARANIR; böylece the-/qs-/yok- önekli
# farklı kodlar aynı konu başlığına düşer.
ACTION_BY_TOPIC: Dict[str, str] = {
    "international-student": (
        "Uluslararası tanıtım faaliyetleri, değişim programları (Erasmus+, Mevlana) ve "
        "İngilizce ders havuzunun genişletilmesi planlanmalıdır."
    ),
    "international-staff": (
        "Yurt dışından öğretim üyesi alımı için kadro planlaması yapılmalı ve "
        "uluslararası ilan süreçleri hızlandırılmalıdır."
    ),
    "international-faculty": (
        "Yurt dışından öğretim üyesi alımı için kadro planlaması yapılmalı ve "
        "uluslararası ilan süreçleri hızlandırılmalıdır."
    ),
    "citation": (
        "Atıf etkisini yükseltmek için yüksek etkili dergilere yönelim teşvik edilmeli, "
        "uluslararası ortak yayın sayısı artırılmalıdır."
    ),
    "publication": (
        "Akademik personel başına yayın sayısını artırmak için yayın teşvik sistemi "
        "güçlendirilmeli ve araştırma izni süreçleri kolaylaştırılmalıdır."
    ),
    "research-income": (
        "Araştırma gelirini artırmak için TÜBİTAK, AB ve kalkınma ajansı proje "
        "başvuruları için proje destek ofisi kapasitesi güçlendirilmelidir."
    ),
    "industry-income": (
        "Sanayi gelirini artırmak için teknoloji transfer ofisi aktifleştirilmeli ve "
        "sanayi iş birliği protokolleri genişletilmelidir."
    ),
    "patent": (
        "Patent sayısını artırmak için fikri mülkiyet danışmanlığı sağlanmalı ve "
        "patent başvuru maliyetleri kurumca karşılanmalıdır."
    ),
    "doctor": (
        "Doktora mezunu sayısını artırmak için doktora burs kontenjanları genişletilmeli "
        "ve tez tamamlama süreleri izlenmelidir."
    ),
    "staff-ratio": (
        "Öğrenci başına düşen öğretim üyesi sayısını iyileştirmek için kadro talebi "
        "planlanmalı veya kontenjan artışı sınırlandırılmalıdır."
    ),
    "student-staff": (
        "Öğrenci başına düşen öğretim üyesi sayısını iyileştirmek için kadro talebi "
        "planlanmalı veya kontenjan artışı sınırlandırılmalıdır."
    ),
    "reputation": (
        "İtibar göstergesini yükseltmek için akademik görünürlük, konferans katılımı ve "
        "medya iletişimi faaliyetleri planlanmalıdır."
    ),
    "employment": (
        "Mezun istihdam oranını artırmak için kariyer merkezi güçlendirilmeli ve "
        "sektörle staj/işe yerleştirme protokolleri genişletilmelidir."
    ),
    "employer": (
        "İşveren itibarını artırmak için mezun-işveren buluşmaları ve sektör danışma "
        "kurulları oluşturulmalıdır."
    ),
    "sustainability": (
        "Sürdürülebilirlik skorunu yükseltmek için enerji verimliliği, atık yönetimi ve "
        "kurumsal sürdürülebilirlik raporlaması süreçleri kurulmalıdır."
    ),
    "community": (
        "Topluma hizmet göstergesini iyileştirmek için sosyal sorumluluk projeleri "
        "belgelenmeli ve gönüllülük saatleri kayıt altına alınmalıdır."
    ),
    "graduation": (
        "Mezuniyet göstergesini iyileştirmek için akademik danışmanlık güçlendirilmeli ve "
        "mezuniyet önündeki engeller (başarısız ders, staj, tez) analiz edilmelidir."
    ),
    "occupancy": (
        "Program doluluk oranını artırmak için kontenjan planlaması gözden geçirilmeli ve "
        "tanıtım faaliyetleri yoğunlaştırılmalıdır."
    ),
    "collaboration": (
        "Uluslararası iş birliği oranını artırmak için ortak proje ve ortak yayın "
        "anlaşmaları hedeflenmelidir."
    ),
}

# Konu eşleşmesi bulunamadığında kullanılacak genel eylem.
DEFAULT_ACTION: str = (
    "İlgili birimle iyileştirme planı oluşturulmalı ve gösterge dönemsel olarak izlenmelidir."
)


def _match_action(indicator_code: str) -> str:
    """Gösterge koduna göre konuya özel eylem metnini bulur."""
    lowered: str = indicator_code.lower()
    for topic, action in ACTION_BY_TOPIC.items():
        if topic in lowered:
            return action
    return DEFAULT_ACTION


def _urgency_for_score(score: Optional[Decimal]) -> RecommendationUrgency:
    """Gösterge skoruna göre aciliyet seviyesi belirler."""
    # Skor hiç hesaplanamadıysa (veri yok) bu yüksek önceliklidir:
    # ölçemediğimiz şeyi yönetemeyiz.
    if score is None:
        return RecommendationUrgency.HIGH

    for threshold, urgency in URGENCY_THRESHOLDS:
        if score < threshold:
            return urgency
    return RecommendationUrgency.LOW


def _expected_gain(
    detail: IndicatorAssessmentDetail,
    dimension: DimensionAssessmentResponse,
    total_dimension_weight: Decimal,
    dimension_indicator_weight: Decimal,
) -> Decimal:
    """Gösterge hedefe ulaşırsa çerçeve skorunda beklenen artışı hesaplar.

    Formül:
        eksik puan × göstergenin boyut içindeki payı × boyutun çerçeve içindeki payı
    """
    current_score: Decimal = detail.performance_score or ZERO
    missing_points: Decimal = HUNDRED - current_score
    if missing_points <= ZERO:
        return ZERO

    indicator_share: Decimal = (
        detail.weight / dimension_indicator_weight
        if dimension_indicator_weight > ZERO
        else ZERO
    )
    dimension_share: Decimal = (
        dimension.dimension_weight / total_dimension_weight
        if total_dimension_weight > ZERO
        else ZERO
    )
    return quantize(missing_points * indicator_share * dimension_share)


def _format_value(value: Optional[Decimal], unit: Optional[str]) -> str:
    """Değeri birimiyle birlikte okunabilir metne çevirir."""
    if value is None:
        return "veri yok"
    if unit:
        return f"{value} {unit}"
    return str(value)


def build_recommendations(
    assessment: AssessmentDetailResponse,
    limit: int = MAX_RECOMMENDATIONS,
) -> List[RecommendationItem]:
    """Değerlendirme sonucundan dinamik Türkçe öneriler üretir."""
    recommendations: List[RecommendationItem] = []

    total_dimension_weight: Decimal = sum(
        (dimension.dimension_weight for dimension in assessment.dimensions), ZERO
    )

    for dimension in assessment.dimensions:
        dimension_indicator_weight: Decimal = sum(
            (detail.weight for detail in dimension.indicators), ZERO
        )

        for detail in dimension.indicators:
            gain: Decimal = _expected_gain(
                detail, dimension, total_dimension_weight, dimension_indicator_weight
            )

            # --- 1) Veri eksikliği önerileri ---
            if detail.data_status in (DataStatus.MISSING, DataStatus.INVALID):
                status_text: str = (
                    "hiç girilmemiş"
                    if detail.data_status == DataStatus.MISSING
                    else "geçersiz"
                )
                source_text: str = detail.data_source or "ilgili birim"
                recommendations.append(
                    RecommendationItem(
                        framework=assessment.framework,
                        dimension=dimension.dimension_name,
                        indicator=detail.indicator_name,
                        indicator_code=detail.indicator_code,
                        current_value=None,
                        target_value=detail.target_value,
                        gap=None,
                        urgency=RecommendationUrgency.HIGH,
                        expected_score_gain=gain,
                        recommendation=(
                            f"'{detail.indicator_name}' göstergesinin verisi {status_text}. "
                            f"Bu gösterge {assessment.framework} çerçevesinin "
                            f"'{dimension.dimension_name}' boyutunu etkiliyor ve veri "
                            f"tamamlandığında performans skoruna yaklaşık {gain} puan "
                            "katkı sağlayabilir."
                        ),
                        required_data_or_action=(
                            f"{source_text} biriminden {assessment.academic_year} dönemine ait "
                            "veri talep edilmeli ve düzenli veri toplama süreci kurulmalıdır."
                        ),
                    )
                )
                continue

            # --- 2) Kısmi/tahmini veri için doğrulama önerileri ---
            if detail.data_status in (DataStatus.PARTIAL, DataStatus.ESTIMATED):
                quality_text: str = (
                    "kısmi" if detail.data_status == DataStatus.PARTIAL else "tahmini"
                )
                recommendations.append(
                    RecommendationItem(
                        framework=assessment.framework,
                        dimension=dimension.dimension_name,
                        indicator=detail.indicator_name,
                        indicator_code=detail.indicator_code,
                        current_value=detail.effective_value,
                        target_value=detail.target_value,
                        gap=(
                            quantize(detail.target_value - detail.effective_value)
                            if detail.target_value is not None
                            and detail.effective_value is not None
                            else None
                        ),
                        urgency=RecommendationUrgency.MEDIUM,
                        expected_score_gain=gain,
                        recommendation=(
                            f"'{detail.indicator_name}' göstergesi {quality_text} veriyle "
                            f"({_format_value(detail.effective_value, detail.unit)}) "
                            "hesaplandı. Verinin doğrulanması hazırlık skorunu yükseltecek "
                            "ve sonucun güvenilirliğini artıracaktır."
                        ),
                        required_data_or_action=(
                            f"{detail.data_source or 'İlgili birim'} ile veri doğrulama süreci "
                            "kurulmalı ve kaynak referansı kayıt altına alınmalıdır."
                        ),
                    )
                )
                continue

            # --- 3) Performans iyileştirme önerileri ---
            score: Optional[Decimal] = detail.performance_score
            if score is None or score >= IMPROVEMENT_SCORE_THRESHOLD:
                continue

            current_value = detail.effective_value
            target_value = detail.target_value
            gap: Optional[Decimal] = None
            if current_value is not None and target_value is not None:
                gap = quantize(abs(target_value - current_value))

            direction_text: str = (
                "yükseltilmesi"
                if detail.direction == IndicatorDirection.HIGHER_IS_BETTER
                else (
                    "düşürülmesi"
                    if detail.direction == IndicatorDirection.LOWER_IS_BETTER
                    else "hedef değere yaklaştırılması"
                )
            )

            gap_sentence: str = ""
            if gap is not None:
                gap_sentence = (
                    f" Hedef {_format_value(target_value, detail.unit)}; "
                    f"aradaki fark {gap}."
                )

            recommendations.append(
                RecommendationItem(
                    framework=assessment.framework,
                    dimension=dimension.dimension_name,
                    indicator=detail.indicator_name,
                    indicator_code=detail.indicator_code,
                    current_value=current_value,
                    target_value=target_value,
                    gap=gap,
                    urgency=_urgency_for_score(score),
                    expected_score_gain=gain,
                    recommendation=(
                        f"'{detail.indicator_name}' göstergesi "
                        f"{_format_value(current_value, detail.unit)} seviyesinde ve "
                        f"{score}/100 performans skoru üretiyor.{gap_sentence} "
                        f"Göstergenin {direction_text} durumunda "
                        f"{assessment.framework} performans skoruna yaklaşık {gain} puan "
                        "katkı beklenmektedir."
                    ),
                    required_data_or_action=_match_action(detail.indicator_code),
                )
            )

    # Önce aciliyet, sonra beklenen kazanç: en çok fark yaratacak öneri üstte.
    urgency_order: Dict[RecommendationUrgency, int] = {
        RecommendationUrgency.CRITICAL: 0,
        RecommendationUrgency.HIGH: 1,
        RecommendationUrgency.MEDIUM: 2,
        RecommendationUrgency.LOW: 3,
    }
    recommendations.sort(
        key=lambda item: (urgency_order[item.urgency], -item.expected_score_gain)
    )
    return recommendations[:limit]
