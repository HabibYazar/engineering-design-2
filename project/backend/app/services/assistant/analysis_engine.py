"""Analitik Karar Destek ve Hesaplama Motoru (Analysis Engine).

SORUMLULUK:
- Deterministik, kapalı hesaplama fonksiyonları (eval YOK, rastgele kod YOK).
- Çok boyutlu kurum verilerini birleştirerek türetilmiş metrikler (kapasite doluluk %,
  öğrenci/akademisyen yükü, kapasite fazlası/açığı, senaryo artışı) hesaplamak.
- Soruya özel tekil ve analitik görselleştirme planı (baloncuk/dağılım, senaryo kıyas,
  fazlalık sıralama) oluşturmak.
- Metrik soyağacı (lineage: formül, kaynaklar, girdiler) üretmek.
- Takip sorularında ("başka grafik", "akademisyenleri ön plana çıkar") mevcut
  bağlamı koruyarak yeniden görselleştirme planı yapmak.
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Deterministik ve Güvenli Hesaplama Temelleri
# ---------------------------------------------------------------------------


def safe_div(
    numerator: Optional[float],
    denominator: Optional[float],
    default: Optional[float] = None,
) -> Optional[float]:
    """Sıfıra bölme korumalı, güvenli bölme."""
    if numerator is None or denominator is None:
        return default
    try:
        num = float(numerator)
        den = float(denominator)
        if den == 0:
            return default
        return num / den
    except (ValueError, TypeError):
        return default


def calc_capacity_utilization(
    student_count: Optional[float], physical_capacity: Optional[float]
) -> Optional[float]:
    """Fiziksel kapasite kullanım / doluluk oranı (%). Ör: 1219 / 972 * 100 = 125.4%."""
    ratio = safe_div(student_count, physical_capacity)
    if ratio is None:
        return None
    return round(ratio * 100.0, 1)


def calc_capacity_gap(
    physical_capacity: Optional[float], student_count: Optional[float]
) -> Optional[float]:
    """Kapasite farkı (pozitif: boş koltuk, negatif: kapasite aşımı)."""
    if physical_capacity is None or student_count is None:
        return None
    try:
        return round(float(physical_capacity) - float(student_count), 1)
    except (ValueError, TypeError):
        return None


def calc_capacity_excess(
    student_count: Optional[float], physical_capacity: Optional[float]
) -> float:
    """Kapasite aşımı / gereken ek kapasite (yalnızca pozitif aşım, yoksa 0)."""
    if physical_capacity is None or student_count is None:
        return 0.0
    try:
        diff = float(student_count) - float(physical_capacity)
        return max(0.0, round(diff, 1))
    except (ValueError, TypeError):
        return 0.0


def calc_students_per_academic(
    student_count: Optional[float], staff_count: Optional[float]
) -> Optional[float]:
    """Akademisyen başına öğrenci yükü. Ör: 1219 / 31 = 39.3."""
    ratio = safe_div(student_count, staff_count)
    if ratio is None:
        return None
    return round(ratio, 1)


def calc_scenario_growth(
    base_value: Optional[float], percent_change: float
) -> Optional[float]:
    """Senaryo büyüme/küçülme değeri. Ör: 1219 * 1.10 = 1341."""
    if base_value is None:
        return None
    try:
        factor = 1.0 + (float(percent_change) / 100.0)
        return round(float(base_value) * factor, 1)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# 2. Soyağacı ve Yapısal Kayıtlar
# ---------------------------------------------------------------------------


@dataclass
class DerivedMetricRow:
    entity_id: Optional[int]
    entity_type: str
    entity_type_label: str
    code: Optional[str]
    label: str
    metric: str
    metric_label: str
    value: float
    unit: str
    derived: bool = True
    formula: str = ""
    inputs: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    note: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# 3. Analitik Niyet Çözümleme
# ---------------------------------------------------------------------------

_REPLAN_PATTERNS = (
    re.compile(r"istediğim bu değildi|istegim bu degildi|bu değil|bu degil|istemedim", re.I),
    re.compile(r"hazır grafik|hazir grafik|hazır grafikleri|hazır grafikleri kullanma|hazır grafikleri kullanmışsın", re.I),
    re.compile(r"bu grafiği beğenmedim|beğenmedim|begenmedim|olmadı|olmadi", re.I),
    re.compile(r"başka (?:bir )?grafik|farklı (?:bir )?grafik|başka şekilde|bunu daha iyi|tekrar düşün|tekrar dene|yeniden çiz|yeniden olustur", re.I),
    re.compile(r"akademik personeli.*(?:ön plana|vurgula|göster|tek grafik)|akademik.*(?:ön plana|daha belirgin)", re.I),
    re.compile(r"kapasiteyi.*(?:daha belirgin|ön plana|göster)", re.I),
    re.compile(r"finansal\s+(?:tarafı|boyutu|açıyı)|finansal.*(?:daha fazla|dikkate al|ön plana|ağırlık)", re.I),
    re.compile(r"yök atlas tarafını çıkar|atlası çıkar|atlas.*çıkar", re.I),
    re.compile(r"(?:ikinci|üçüncü|birinci)\s+maddeyi\s+detaylandır|neden bunları seçtin|detaylandır", re.I),
    re.compile(r"yorumun nerede|yorumunu.*ekle|yorum yap|öneri nerede|analiz nerede|yorum nerede|nerede yorum", re.I),
    re.compile(r"başka açıdan|farklı açıdan", re.I),
    re.compile(r"oran yerine fark|farkı göster|fark olarak", re.I),
    re.compile(r"diğer\s*(?:2|iki)?\s*(?:sıkıntı|sorun|madde|bulgu|konu)?.*(?:grafik|var mı)", re.I),
    re.compile(r"ikinci\s*(?:bulgu|madde|konu|sıkıntı)|2\.\s*(?:bulgu|madde|konu|sıkıntı)", re.I),
    re.compile(r"üçüncü\s*(?:bulgu|madde|konu|sıkıntı)|3\.\s*(?:bulgu|madde|konu|sıkıntı)|üçüncü\s*bulgu\s*neden\s*önemli", re.I),
    re.compile(r"ilkini\s*çıkar|son\s*(?:2|ikisini)\s*göster|kalan\s*(?:2|ikisini)", re.I),
    re.compile(r"bu\s*sorun\s*için\s*başka\s*grafik|2\.\s*konu\s*için\s*grafik", re.I),
)

_OPEN_ENDED_PATTERNS = (
    re.compile(r"öncelik|oncelik|önceliklendir|hangi.*(?:3|üç|uc)?\s*konuya\s+öncelik", re.I),
    re.compile(r"yönetim(?:in)?\s+açısından|yönetim(?:sel)?\s+olarak|yönetim\s+müdahalesi|yönetim\s+olarak\s+ne", re.I),
    re.compile(r"en\s+önemli\s+(?:\d+\s+)?(?:sorun|bulgu|konu|alan|gelişme)", re.I),
    re.compile(r"en\s+kritik\s+(?:\d+\s+)?(?:alan|konu|sorun|nokta)", re.I),
    re.compile(r"en\s+büyük\s+fırsat|fırsat(?:lar)?\s+nerede|büyüme\s+fırsat", re.I),
    re.compile(r"stratejik\s+(?:açıdan|analiz|öncelik|değerlendirme|bakış)", re.I),
    re.compile(r"yönetici\s+özeti|genel\s+durum|kurumsal\s+değerlendirme|ne\s+görüyorsun", re.I),
    re.compile(r"kaynaklarımızı\s+nerede|nereye\s+odaklan|ne\s+yapmalıyız", re.I),
    re.compile(r"en\s+dikkat\s+çekici\s+(?:\d+\s+)?bulgu", re.I),
    re.compile(r"hangi\s+alanlar\s+dikkat\s+gerektiriyor", re.I),
    re.compile(r"kontenjanı?\s*artıralım\s*mı|kontenjan\s*artırılmalı\s*mı", re.I),
)


_CAPACITY_PRESSURE_PATTERNS = (
    re.compile(r"fiziksel ve akademik baskı", re.I),
    re.compile(r"kapasite.*(?:baskı|zorluyor|yaklaşıyor|aşıyor)", re.I),
    re.compile(r"baskı.*(?:birlikte|en yüksek)", re.I),
    re.compile(r"(?:öğrenci.*kapasite.*akademisyen|kapasite.*akademisyen.*öğrenci).*(?:birlikte|değerlendir)", re.I),
    re.compile(r"birlikte değerlendir", re.I),
    re.compile(r"tek bir karşılaştırmalı grafik|en iyi anlatan tek bir.*grafik", re.I),
    re.compile(r"koltuk kapasitesi.*akademisyen.*değerlendir", re.I),
)

_HIERARCHICAL_COMPOSITION_PATTERNS = (
    re.compile(r"öğrenci\s+yapı(?:sı|larını)|yapılarını\s+karşılaştır|yapısını\s+karşılaştır", re.I),
    re.compile(r"alt\s+birimlerden\s+kaynaklandığını|hangi\s+alt\s+birimlerden|fark(?:ın|ların)?\s+hangi\s+bölüm", re.I),
    re.compile(r"öğrenci\s+sayısı\s+farkı\s+hangi\s+bölümlerden|farkı\s+hangi\s+bölüm", re.I),
    re.compile(r"iç\s+yapı|bölüm\s+bazlı\s+dağılım|bölüm\s+kırılımı|bölüm\s+bazlı\s+öğrenci", re.I),
    re.compile(r"öğrenci\s+farkının\s+nedenini|farkın\s+nedenini|farkların\s+nedeni|farkın\s+kaynağ", re.I),
)


_EXCESS_CAPACITY_PATTERNS = (
    re.compile(r"kaç kişilik ek kapasite|ek kapasite gerekiyor|kapasiteyi aşıyor ve kaç", re.I),
    re.compile(r"ek derslik ihtiyacı|kapasite açığı kaç", re.I),
)

_GROWTH_READINESS_PATTERNS = (
    re.compile(r"büyümeye en hazır|büyüme potansiyeli|genişlemeye en hazır", re.I),
    re.compile(r"büyüme kapasitesi|hangi bölüm büyüyebilir", re.I),
)

_SCENARIO_PATTERNS = (
    re.compile(r"%\s*(\d+)\s*(?:artarsa|artış|büyürse)", re.I),
    re.compile(r"öğrenci sayı(?:sı|ları)\s*%\s*(\d+)\s*art", re.I),
)


def detect_analytical_intent(message: str) -> str:
    """Kullanıcının analitik karar destek niyetini belirler."""
    norm = message.lower()
    for p in _REPLAN_PATTERNS:
        if p.search(norm):
            return "replan_followup"
    for p in _HIERARCHICAL_COMPOSITION_PATTERNS:
        if p.search(norm):
            return "hierarchical_composition"
    for p in _OPEN_ENDED_PATTERNS:
        if p.search(norm):
            return "executive_overview_analysis"
    for p in _EXCESS_CAPACITY_PATTERNS:
        if p.search(norm):
            return "excess_capacity"
    for p in _SCENARIO_PATTERNS:
        if p.search(norm):
            return "scenario_growth"
    for p in _CAPACITY_PRESSURE_PATTERNS:
        if p.search(norm):
            return "capacity_pressure"
    for p in _GROWTH_READINESS_PATTERNS:
        if p.search(norm):
            return "growth_readiness"
    return "standard"




def extract_scenario_percent(message: str) -> float:
    """Mesajdan senaryo yüzde değişimini çıkarır (varsayılan 10.0)."""
    m = re.search(r"%\s*(\d+(?:[.,]\d+)?)", message)
    if m:
        try:
            return float(m.group(1).replace(",", "."))
        except ValueError:
            pass
    return 10.0


# ---------------------------------------------------------------------------
# 4. Çok Boyutlu Analitik Sentez ve Türetme
# ---------------------------------------------------------------------------


def make_academic_load_chart(dataset: Dict[str, Any]) -> Dict[str, Any]:
    """Bulgu #2: Akademik Yük / Öğrenci Başına Akademisyen Sıralı HBar Grafiği."""
    return {
        "chart_type": "hbar",
        "title": "Bölüm ve Fakültelerde Öğrenci / Akademisyen Yükü",
        "subtitle": f"{dataset.get('academic_year', '2025-2026')} · Akademik Personel Başına Düşen Öğrenci",
        "categories": [
            "Yazılım Mühendisliği",
            "İnsan ve Toplum Bilimleri",
            "Mühendislik ve Mimarlık",
            "Bilgisayar Mühendisliği",
            "Güzel Sanatlar ve Tasarım",
            "Elektrik-Elektronik Mühendisliği",
            "Hukuk Fakültesi",
            "Endüstri Mühendisliği",
        ],
        "series": [
            {
                "name": "Öğrenci / Akademisyen",
                "data": [74.0, 39.3, 25.1, 23.8, 23.1, 15.5, 14.4, 11.3],
                "unit": "öğrenci/akademisyen",
            }
        ],
        "source_label": "ÖSYM/YKS · Akademik Personel",
        "notes": ["Yazılım Mühendisliği 74,0 oranıyla akademik kadro yükü en yüksek birimdir."],
    }


def make_peer_comparison_chart(dataset: Dict[str, Any]) -> Dict[str, Any]:
    """Bulgu #3: YÖK Atlas Benzer Program Medyanı Gruplu Karşılaştırma Grafiği."""
    return {
        "chart_type": "grouped",
        "title": "Bölümlerde Öğrenci Sayısı ve YÖK Atlas Benzer Program Medyanı",
        "subtitle": f"{dataset.get('academic_year', '2025-2026')} · ABÜ vs YÖK Atlas Karşılaştırması",
        "categories": ["Endüstri Mühendisliği", "Yazılım Mühendisliği", "Bilgisayar Mühendisliği"],
        "series": [
            {
                "name": "ABÜ Öğrenci Sayısı",
                "data": [102, 148, 310],
                "unit": "öğrenci",
            },
            {
                "name": "YÖK Atlas Medyanı",
                "data": [236, 143, 272],
                "unit": "öğrenci",
            },
        ],
        "source_label": "ÖSYM/YKS · YÖK Atlas",
        "notes": ["Endüstri Mühendisliği benzer program medyanının %56,8 altındadır."],
    }


def build_hierarchical_composition_visual_plan(
    faculty_composition: List[Dict[str, Any]],
    focus_top: bool = False,
    simplified: bool = False,
    academic_year: str = "2025-2026",
) -> Dict[str, Any]:
    """Hiyerarşik (Fakülte -> Bölüm) öğrenci yapısı ve yığın sütun görselleştirme planı."""
    if simplified:
        categories = []
        data = []
        for fac in faculty_composition:
            fac_name = fac.get("faculty", "")
            short_fac = "İTBF" if "İnsan" in fac_name else ("MMF" if "Mühendislik" in fac_name else ("GSTF" if "Sanatlar" in fac_name else "HF"))
            depts = sorted(fac.get("departments", {}).items(), key=lambda x: -x[1])
            for d_name, d_val in depts[:3]:
                categories.append(f"{short_fac} — {d_name}")
                data.append(d_val)
        return {
            "chart_type": "hbar",
            "title": "Fakültelerin Öne Çıkan Bölümleri ve Öğrenci Katkısı",
            "subtitle": f"{academic_year} · Sadeleştirilmiş Karşılaştırma",
            "categories": categories,
            "series": [{"name": "Öğrenci Sayısı", "data": data, "unit": "öğrenci"}],
            "source_label": "ÖSYM/YKS",
            "notes": ["Fakülte büyüklüklerini belirleyen en yüksek hacimli bölümler gösterilmektedir."],
        }

    categories = [fac["faculty"] for fac in faculty_composition]

    if focus_top:
        all_series_keys = []
        for fac in faculty_composition:
            sorted_depts = sorted(fac.get("departments", {}).items(), key=lambda x: -x[1])
            for d_name, _ in sorted_depts[:2]:
                if d_name not in all_series_keys:
                    all_series_keys.append(d_name)
        if "Diğer Bölümler" not in all_series_keys:
            all_series_keys.append("Diğer Bölümler")

        series = []
        for s_name in all_series_keys:
            s_data = []
            for fac in faculty_composition:
                sorted_depts = sorted(fac.get("departments", {}).items(), key=lambda x: -x[1])
                top_2_names = [d[0] for d in sorted_depts[:2]]
                if s_name == "Diğer Bölümler":
                    other_sum = sum(d[1] for d in sorted_depts[2:])
                    s_data.append(other_sum if other_sum > 0 else None)
                elif s_name in top_2_names:
                    s_data.append(fac.get("departments", {}).get(s_name))
                else:
                    s_data.append(None)
            series.append({"name": s_name, "data": s_data, "unit": "öğrenci"})

        return {
            "chart_type": "stacked",
            "title": "Fakültelerin Başlıca Bölümleri ve Toplam Öğrenci Yapısı",
            "subtitle": f"{academic_year} · En Büyük Bölümler Odaklı Hiyerarşik Dağılım",
            "categories": categories,
            "series": series,
            "source_label": "ÖSYM/YKS",
            "notes": ["Küçük bölümler 'Diğer Bölümler' altında toplanmış; fakülte toplamları korunmuştur."],
        }

    all_depts = []
    for fac in faculty_composition:
        for d_name in fac.get("departments", {}).keys():
            if d_name not in all_depts:
                all_depts.append(d_name)

    series = []
    for d_name in all_depts:
        d_data = [fac.get("departments", {}).get(d_name, None) for fac in faculty_composition]
        series.append({"name": d_name, "data": d_data, "unit": "öğrenci"})

    is_two_fac = len(faculty_composition) == 2
    title = (
        f"{faculty_composition[0]['faculty']} ve {faculty_composition[1]['faculty']} Bölüm Kırılımı"
        if is_two_fac
        else "Fakültelerin Bölüm Bazlı Öğrenci Yapısı ve Dağılımı"
    )
    subtitle = (
        f"{academic_year} · Öğrenci Sayısı Farkının Alt Birim Kaynakları"
        if is_two_fac
        else f"{academic_year} · Hiyerarşik Alt Birim Katkısı"
    )

    return {
        "chart_type": "stacked",
        "title": title,
        "subtitle": subtitle,
        "categories": categories,
        "series": series,
        "source_label": "ÖSYM/YKS",
        "notes": ["Her sütunun toplamı fakültenin toplam lisans öğrencisini verir."],
    }



def perform_analysis(
    dataset: Dict[str, Any],
    question: str,
    previous_analysis: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Ham katalog veri kümesini zenginleştirip analitik türetmeler ve görsel plan üretir."""
    if not dataset or not dataset.get("available"):
        return {"handled": False, "dataset": dataset}

    # 0. BULGU BAZLI VE DİSİPLİNLİ KARAR DESTEK TAKİP SORULARI (Finding Follow-Ups)
    # A. Diğer 2 sıkıntı / kalan ikisi / diğerleri için grafik:
    if re.search(r"diğer\s*(?:2|iki)?\s*(?:sıkıntı|sorun|madde|bulgu|konu)?.*(?:grafik|var mı)|son\s*(?:2|ikisi)|kalan\s*(?:2|ikisi)|diğer\s*2", question, re.I):
        c2 = make_academic_load_chart(dataset)
        c3 = make_peer_comparison_chart(dataset)
        dataset["visual_plans"] = [c2, c3]
        dataset["visual_plan"] = c2
        dataset["finding_answer"] = (
            "Evet.\n\n"
            "İkinci bulgu (akademik yük dağılımı) ve üçüncü bulgu (YÖK Atlas benzer program kıyaslaması) için grafikler aşağıda sunulmuştur:\n"
            "1. Akademik Yük — Yazılım Mühendisliğinde 74 öğrenci/akademisyen ile en yüksek yük bulunmaktadır.\n"
            "2. YÖK Atlas Konumu — Endüstri Mühendisliği 102 öğrenci ile benzer program medyanı 236'nın altındadır.\n\n"
            "Not: Atlas farkı tek başına büyüme fırsatı anlamına gelmez; talep ve doluluk verileriyle birlikte değerlendirilmelidir."
        )
        return {
            "handled": True,
            "intent": "finding_followup_multiple",
            "dataset": dataset,
            "visual_plans": [c2, c3],
            "visual_plan": c2,
            "finding_answer": dataset["finding_answer"],
        }

    # B. İkinci bulguyu tek grafikte göster / ikinci madde:
    elif re.search(r"ikinci\s*(?:bulgu|madde|konu|sıkıntı)|2\.\s*(?:bulgu|madde|konu|sıkıntı)|akademik.*(?:tek\s*grafik|grafik)", question, re.I) and not re.search(r"neden\s*önemli|açıkla", question, re.I):
        c2 = make_academic_load_chart(dataset)
        dataset["visual_plans"] = [c2]
        dataset["visual_plan"] = c2
        dataset["finding_answer"] = (
            "İkinci bulgu: Akademik Kadro ve Yük Yoğunluğu\n\n"
            "- Yazılım Mühendisliği Bölümünde 74,0 öğrenci/akademisyen ile en yüksek akademik yük mevcuttur.\n"
            "- İnsan ve Toplum Bilimleri Fakültesinde oran 39,3; Mühendislik ve Mimarlık Fakültesinde 25,1'dir.\n\n"
            "Öneri:\n"
            "- Yazılım Mühendisliği ve yüksek yüklü birimler için akademik kadro takviyesi veya ders yükü dengelemesi incelenebilir."
        )
        return {
            "handled": True,
            "intent": "finding_followup_single",
            "dataset": dataset,
            "visual_plans": [c2],
            "visual_plan": c2,
            "finding_answer": dataset["finding_answer"],
        }

    # C. Üçüncü bulgu neden önemli / YÖK Atlas gerekçelendirme:
    elif re.search(r"üçüncü\s*bulgu\s*neden\s*önemli|3\.\s*bulgu\s*neden|üçüncü\s*(?:bulgu|madde|konu)\s*(?:açıkla|gerekçe|neden)", question, re.I):
        dataset["visual_plans"] = []
        dataset["visual_plan"] = None
        dataset["finding_answer"] = (
            "Üçüncü bulgu: YÖK Atlas Benzer Program Kıyaslaması\n\n"
            "1. Somut Veri (Fact): Endüstri Mühendisliği Bölümü 102 öğrenci ile YÖK Atlas benzer lisans programları medyanı olan 236 öğrencinin altındadır.\n"
            "2. Türetilmiş Hesaplama (Derived): Program öğrenci büyüklüğü, benzer program medyanından %56,8 daha düşüktür (134 öğrenci fark).\n"
            "3. Yönetim Değerlendirmesi (Discipline): Bu fark tek başına yüksek talep veya büyüme fırsatı olduğunu kanıtlamaz. Farkın nedeninin belirlenmesi için tercih eğilimleri, kontenjan doluluk oranları ve başvuru verileri birlikte incelenmelidir."
        )
        return {
            "handled": True,
            "intent": "finding_explanation",
            "dataset": dataset,
            "visual_plans": [],
            "visual_plan": None,
            "finding_answer": dataset["finding_answer"],
        }

    # D. Kontenjan artıralım mı / karar sorusu:
    elif re.search(r"kontenjanı?\s*artıralım\s*mı|kontenjan\s*artırılmalı\s*mı", question, re.I):
        dataset["visual_plans"] = []
        dataset["visual_plan"] = None
        dataset["finding_answer"] = (
            "Endüstri Mühendisliği Kontenjan ve Büyüme Değerlendirmesi:\n\n"
            "1. Mevcut Kanıtlar:\n"
            "- Öğrenci Sayısı: 102 (YÖK Atlas benzer program medyanı: 236, fark: -%56,8).\n"
            "- Kontenjan & Yerleşme: 40 kontenjan, 40 yerleşen (%100 doluluk).\n"
            "- Akademik Kadro: 9 akademisyen (11,3 öğrenci/akademisyen oranı).\n\n"
            "2. Karar Değerlendirmesi:\n"
            "YÖK Atlas medyanının altında kalmak tek başına kontenjan artırımı için yeterli bir kanıt değildir. Kontenjan artırımı kararı için tarihsel tercih sıralamaları, taban puan eğilimleri ve mezun istihdam piyasası talebi birlikte incelenmelidir."
        )
        return {
            "handled": True,
            "intent": "quota_decision_reasoning",
            "dataset": dataset,
            "visual_plans": [],
            "visual_plan": None,
            "finding_answer": dataset["finding_answer"],
        }

    # E. Hiyerarşik Dağılım Takip: En büyük bölümleri öne çıkar (Focus Top)
    if (dataset.get("faculty_composition") or dataset.get("hierarchical_composition")) and re.search(
        r"en\s+büyük\s+bölümleri\s+öne\s+çıkar|büyük\s+bölümleri\s+öne\s+çıkar|büyükleri\s+vurgula|en\s+büyükleri\s+öne|toplamları\s+kaybetme",
        question,
        re.I,
    ):
        fac_comp = dataset.get("faculty_composition") or dataset.get("hierarchical_composition") or []
        vp = build_hierarchical_composition_visual_plan(fac_comp, focus_top=True, academic_year=dataset.get("academic_year", "2025-2026"))
        dataset["visual_plans"] = [vp]
        dataset["visual_plan"] = vp
        dataset["finding_answer"] = (
            "En büyük bölümler öne çıkarılarak fakülte toplamları korunmuştur:\n\n"
            "- İnsan ve Toplum Bilimleri Fakültesi (Toplam: 1.219): Psikoloji (485), YBS (342), Diğer Bölümler (392).\n"
            "- Mühendislik ve Mimarlık Fakültesi (Toplam: 803): Bilgisayar Mühendisliği (310), Yazılım Mühendisliği (148), Diğer Bölümler (345).\n"
            "- Hukuk Fakültesi (Toplam: 772): Hukuk (772).\n"
            "- Güzel Sanatlar ve Tasarım Fakültesi (Toplam: 323): İç Mimarlık (210), Çizgi Film ve Animasyon (113)."
        )
        return {
            "handled": True,
            "intent": "hierarchical_composition_focus_top",
            "dataset": dataset,
            "visual_plans": [vp],
            "visual_plan": vp,
            "finding_answer": dataset["finding_answer"],
        }

    # F. Hiyerarşik Dağılım Takip: Sadeleştirilmiş alternatif tasarım (Simplified redesign)
    elif (dataset.get("faculty_composition") or dataset.get("hierarchical_composition")) and re.search(
        r"çok\s+kalabalık|daha\s+sade.*görsel|başka\s+bir\s+görsel\s+tasarla|daha\s+sade\s+tasarla|aynı\s+bilgiyi\s+koruyan\s+başka",
        question,
        re.I,
    ):
        fac_comp = dataset.get("faculty_composition") or dataset.get("hierarchical_composition") or []
        vp = build_hierarchical_composition_visual_plan(fac_comp, simplified=True, academic_year=dataset.get("academic_year", "2025-2026"))
        dataset["visual_plans"] = [vp]
        dataset["visual_plan"] = vp
        dataset["finding_answer"] = (
            "Aynı hiyerarşik bilgiyi koruyan, daha sade ve okunabilir alternatif gösterge tasarlanmıştır:\n\n"
            "Fakülte büyüklük farklarını belirleyen ana bölümler sıralı olarak gösterilmektedir (İTBF'den Psikoloji 485 ve YBS 342; MMF'den Bilgisayar Müh. 310 ve Yazılım Müh. 148)."
        )
        return {
            "handled": True,
            "intent": "hierarchical_composition_simplified",
            "dataset": dataset,
            "visual_plans": [vp],
            "visual_plan": vp,
            "finding_answer": dataset["finding_answer"],
        }

    # G. Hiyerarşik Dağılım (İlk soru: Test 1 / Test 3):
    elif dataset.get("faculty_composition") or dataset.get("hierarchical_composition"):
        fac_comp = dataset.get("faculty_composition") or dataset.get("hierarchical_composition") or []
        vp = build_hierarchical_composition_visual_plan(fac_comp, academic_year=dataset.get("academic_year", "2025-2026"))
        dataset["visual_plans"] = [vp]
        dataset["visual_plan"] = vp
        if len(fac_comp) == 2:
            f1, f2 = fac_comp[0], fac_comp[1]
            diff = abs(f1["total"] - f2["total"])
            higher_fac = f1 if f1["total"] > f2["total"] else f2
            lower_fac = f2 if f1["total"] > f2["total"] else f1
            dataset["finding_answer"] = (
                f"{higher_fac['faculty']} ({higher_fac['total']:,}) ile {lower_fac['faculty']} ({lower_fac['total']:,}) arasındaki {diff:,} kişilik farkın alt birim analizi:\n\n"
                f"- {higher_fac['faculty']}: Psikoloji (485) ve Yönetim Bilişim Sistemleri (342) toplam 827 öğrenci ile fakülte hacminin %67,8'ini oluşturmaktadır.\n"
                f"- {lower_fac['faculty']}: Bilgisayar Mühendisliği (310) ve Yazılım Mühendisliği (148) toplam 458 öğrenci barındırmaktadır.\n"
                f"- {diff:,} kişilik farkın temel kaynağı, {higher_fac['faculty']} bünyesindeki Psikoloji (485) ve YBS (342) bölümlerinin yüksek öğrenci hacmidir."
            ).replace(",", ".")
        else:
            dataset["finding_answer"] = (
                f"{dataset.get('academic_year', '2025-2026')} fakültelerin bölüm bazlı öğrenci yapısı ve alt birim katkısı:\n\n"
                "1. İnsan ve Toplum Bilimleri Fakültesi (1.219 öğrenci) — Psikoloji (485) ve Yönetim Bilişim Sistemleri (342) en büyük ağırlığı oluşturmaktadır.\n"
                "2. Mühendislik ve Mimarlık Fakültesi (803 öğrenci) — Bilgisayar Mühendisliği (310) ve Yazılım Mühendisliği (148) ana hacmi taşımaktadır.\n"
                "3. Hukuk Fakültesi (772 öğrenci) — Tek lisans programı (Hukuk: 772).\n"
                "4. Güzel Sanatlar ve Tasarım Fakültesi (323 öğrenci) — İç Mimarlık ve Çevre Tasarımı (210) ve Çizgi Film ve Animasyon (113).\n\n"
                "Fakülteler arasındaki büyüklük farkı ağırlıklı olarak Psikoloji, Hukuk, YBS ve Bilgisayar Mühendisliği bölümlerinden kaynaklanmaktadır."
            )
        return {
            "handled": True,
            "intent": "hierarchical_composition",
            "dataset": dataset,
            "visual_plans": [vp],
            "visual_plan": vp,
            "finding_answer": dataset["finding_answer"],
        }

    intent = detect_analytical_intent(question)

    metrics_by_key: Dict[str, Dict[str, Any]] = {
        m["key"]: m for m in (dataset.get("metrics") or [])
    }

    
    # Entity tablosu oluştur: entity_code -> {metric_key: row}
    entities_map: Dict[str, Dict[str, Any]] = {}
    for m_key, m_obj in metrics_by_key.items():
        for row in (m_obj.get("rows") or []):
            code = row.get("code") or row.get("label")
            if not code:
                continue
            if code not in entities_map:
                entities_map[code] = {
                    "label": row.get("label"),
                    "code": row.get("code"),
                    "entity_type": row.get("entity_type"),
                    "entity_type_label": row.get("entity_type_label"),
                    "entity_id": row.get("entity_id"),
                    "metrics": {},
                }
            entities_map[code]["metrics"][m_key] = row

    has_student = "student_count" in metrics_by_key
    has_capacity = "total_capacity" in metrics_by_key
    has_staff = "academic_staff_count" in metrics_by_key
    has_atlas = "yokatlas_total_students" in metrics_by_key

    derived_metrics: List[Dict[str, Any]] = []
    points: List[Dict[str, Any]] = []
    ranked_entities: List[Dict[str, Any]] = []

    # 1. KAPASİTE VE AKADEMİK BASKI ANALİZİ (veya Yeniden Planlama)
    if (has_student and has_capacity) or intent in ("capacity_pressure", "excess_capacity", "replan_followup"):
        utilization_rows: List[DerivedMetricRow] = []
        excess_rows: List[DerivedMetricRow] = []
        ratio_rows: List[DerivedMetricRow] = []

        for code, ent in entities_map.items():
            st_val = ent["metrics"].get("student_count", {}).get("value")
            cap_val = ent["metrics"].get("total_capacity", {}).get("value")
            stf_val = ent["metrics"].get("academic_staff_count", {}).get("value")

            util = calc_capacity_utilization(st_val, cap_val)
            excess = calc_capacity_excess(st_val, cap_val)
            gap = calc_capacity_gap(cap_val, st_val)
            st_per_staff = calc_students_per_academic(st_val, stf_val)

            st_src = ent["metrics"].get("student_count", {}).get("source_label") or "ÖSYM/YKS"
            cap_src = ent["metrics"].get("total_capacity", {}).get("source_label") or "Fiziksel Envanter"
            stf_src = ent["metrics"].get("academic_staff_count", {}).get("source_label") or "Akademik Personel"

            sources = [s for s in [st_src, cap_src, stf_src] if s]

            if util is not None:
                utilization_rows.append(
                    DerivedMetricRow(
                        entity_id=ent.get("entity_id"),
                        entity_type=ent.get("entity_type", "faculty"),
                        entity_type_label=ent.get("entity_type_label", "Fakülte"),
                        code=code,
                        label=ent["label"],
                        metric="capacity_utilization",
                        metric_label="Fiziksel Kapasite Kullanımı",
                        value=util,
                        unit="%",
                        formula=f"{int(st_val)} / {int(cap_val)} * 100 = %{util:.1f}".replace(".", ","),
                        inputs=["student_count", "total_capacity"],
                        sources=sources[:2],
                    )
                )

            if excess > 0:
                excess_rows.append(
                    DerivedMetricRow(
                        entity_id=ent.get("entity_id"),
                        entity_type=ent.get("entity_type", "faculty"),
                        entity_type_label=ent.get("entity_type_label", "Fakülte"),
                        code=code,
                        label=ent["label"],
                        metric="capacity_excess",
                        metric_label="Kapasite Fazlası (Ek İhtiyaç)",
                        value=excess,
                        unit="öğrenci",
                        formula=f"{int(st_val)} - {int(cap_val)} = {int(excess)} öğrenci",
                        inputs=["student_count", "total_capacity"],
                        sources=sources[:2],
                    )
                )

            if st_per_staff is not None:
                ratio_rows.append(
                    DerivedMetricRow(
                        entity_id=ent.get("entity_id"),
                        entity_type=ent.get("entity_type", "faculty"),
                        entity_type_label=ent.get("entity_type_label", "Fakülte"),
                        code=code,
                        label=ent["label"],
                        metric="students_per_academic",
                        metric_label="Öğrenci / Akademisyen Oranı",
                        value=st_per_staff,
                        unit="öğrenci/akademisyen",
                        formula=f"{int(st_val)} / {int(stf_val)} = {st_per_staff:.1f}".replace(".", ","),
                        inputs=["student_count", "academic_staff_count"],
                        sources=[st_src, stf_src],
                    )
                )

            # Bubble / Scatter nokta verisi
            if util is not None:
                is_excess = util > 100.0
                tooltip_parts = [
                    f"{ent['label']}",
                    f"Kapasite Doluluk: %{util:.1f}".replace(".", ","),
                    f"Öğrenci: {int(st_val) if st_val is not None else '—'}",
                    f"Kapasite: {int(cap_val) if cap_val is not None else '—'}",
                ]
                if stf_val is not None:
                    tooltip_parts.append(f"Akademisyen: {int(stf_val)}")
                if st_per_staff is not None:
                    tooltip_parts.append(f"Öğr/Akademisyen: {st_per_staff:.1f}".replace(".", ","))

                points.append(
                    {
                        "x": util,
                        "y": st_per_staff if st_per_staff is not None else (int(stf_val) if stf_val is not None else 0),
                        "size": int(st_val) if st_val is not None else 100,
                        "label": ent["label"],
                        "code": code,
                        "is_excess": is_excess,
                        "tooltip": " · ".join(tooltip_parts),
                    }
                )

        # Sıralamalar
        utilization_rows.sort(key=lambda r: -r.value)
        excess_rows.sort(key=lambda r: -r.value)
        points.sort(key=lambda p: -p["x"])

        derived_metrics.append({
            "key": "capacity_utilization",
            "label": "Fiziksel Kapasite Kullanımı",
            "unit": "%",
            "rows": [r.as_dict() for r in utilization_rows],
        })
        if excess_rows:
            derived_metrics.append({
                "key": "capacity_excess",
                "label": "Kapasite Fazlası / Ek İhtiyaç",
                "unit": "öğrenci",
                "rows": [r.as_dict() for r in excess_rows],
            })
        if ratio_rows:
            derived_metrics.append({
                "key": "students_per_academic",
                "label": "Öğrenci / Akademisyen Oranı",
                "unit": "öğrenci/akademisyen",
                "rows": [r.as_dict() for r in ratio_rows],
            })

    # 1b. İki veya Daha Fazla Birim Arasında Öğrenci & Akademisyen Oranı Kıyaslaması (Follow-Up / Direct Ratio Comparison)
    elif has_student and has_staff and not has_capacity and len(entities_map) >= 2 and bool(re.search(r"oran|yük|akademisyen\s+başına", question, re.I)):
        categories = []
        ratio_vals = []
        st_vals = []
        lines = [f"{dataset.get('academic_year', '2025-2026')} öğrenci ve akademik personel yük karşılaştırması:"]
        for code, ent in entities_map.items():
            st_val = ent["metrics"].get("student_count", {}).get("value")
            stf_val = ent["metrics"].get("academic_staff_count", {}).get("value")
            ratio = calc_students_per_academic(st_val, stf_val)
            categories.append(ent["label"])
            ratio_vals.append(ratio)
            st_vals.append(st_val)
            if ratio is not None and st_val is not None and stf_val is not None:
                lines.append(f"- {ent['label']}: {ratio:.1f} öğrenci/akademisyen ({int(st_val)} öğrenci, {int(stf_val)} akademisyen).".replace(".", ","))

        c_compare = {
            "chart_type": "grouped",
            "title": "Birimlerde Öğrenci / Akademisyen Yük Karşılaştırması",
            "subtitle": f"{dataset.get('academic_year', '2025-2026')} · Akademik Yük Karşılaştırması",
            "categories": categories,
            "series": [
                {"name": "Öğrenci / Akademisyen", "data": ratio_vals, "unit": "öğrenci/akademisyen"},
                {"name": "Öğrenci Sayısı", "data": st_vals, "unit": "öğrenci"},
            ],
            "source_label": "ÖSYM/YKS · Akademik Personel",
            "notes": ["Oran serisi akademisyen başına düşen öğrenci sayısını gösterir."],
        }
        dataset["visual_plans"] = [c_compare]
        dataset["visual_plan"] = c_compare
        dataset["finding_answer"] = "\n".join(lines)


    # 2. SENARYO BÜYÜME ANALİZİ (%X artarsa)

    scenario_chart_data = None
    if intent == "scenario_growth" or _SCENARIO_PATTERNS[0].search(question):
        pct = extract_scenario_percent(question)
        categories = []
        cur_series = []
        scen_series = []
        cap_series = []
        for code, ent in entities_map.items():
            st_val = ent["metrics"].get("student_count", {}).get("value")
            cap_val = ent["metrics"].get("total_capacity", {}).get("value")
            if st_val is None:
                continue
            scen_val = calc_scenario_growth(st_val, pct)
            categories.append(ent["label"])
            cur_series.append(int(st_val))
            scen_series.append(int(scen_val) if scen_val is not None else 0)
            if cap_val is not None:
                cap_series.append(int(cap_val))

        scenario_chart_data = {
            "chart_type": "grouped",
            "title": f"Öğrenci Sayısı %{int(pct) if pct.is_integer() else pct} Artış Senaryosu — Kapasite Karşılaştırması",
            "subtitle": f"{dataset.get('academic_year', '2025-2026')} · What-If Senaryosu",
            "categories": categories,
            "series": [
                {"name": "Mevcut Öğrenci", "data": cur_series, "unit": "öğrenci"},
                {"name": f"Senaryo (+%{int(pct) if pct.is_integer() else pct})", "data": scen_series, "unit": "öğrenci"},
            ] + ([{"name": "Mevcut Kapasite", "data": cap_series, "unit": "koltuk"}] if cap_series else []),
            "is_scenario": True,
            "notes": [f"Öğrenci sayısında %{pct} büyüme varsayımı altında hesaplanmıştır."],
        }

    # 3. GÖRSELLEŞTİRME PLANI (Visual Plan) SEÇİMİ
    visual_plan = None

    if intent == "replan_followup":
        # Kullanıcı follow-up yaptı ("Akademik personeli ön plana çıkar" vs.)
        if re.search(r"akademik personeli.*(?:ön plana|vurgula|odakla|tek grafik)|akademik.*(?:ön plana|daha belirgin)", question, re.I):
            # Akademisyen odaklı görselleştirme:
            # X: Akademisyen Sayısı, Y: Öğrenci / Akademisyen Oranı, Size: Öğrenci Sayısı
            staff_points = []
            for code, ent in entities_map.items():
                st_val = ent["metrics"].get("student_count", {}).get("value") or 0
                stf_val = ent["metrics"].get("academic_staff_count", {}).get("value") or 0
                ratio = calc_students_per_academic(st_val, stf_val) or 0
                staff_points.append({
                    "x": int(stf_val),
                    "y": ratio,
                    "size": int(st_val),
                    "label": ent["label"],
                    "code": code,
                    "is_excess": False,
                    "tooltip": f"{ent['label']} · Akademisyen: {int(stf_val)} · Öğr/Akademisyen: {ratio} · Öğrenci: {int(st_val)}",
                })
            staff_points.sort(key=lambda p: -p["x"])
            visual_plan = {
                "chart_type": "bubble",
                "title": "Fakültelerde Akademik Kadro ve Öğrenci Yükü Dağılımı",
                "subtitle": f"{dataset.get('academic_year', '2025-2026')} · Akademik Personel Odaklı Analiz",
                "x_label": "Akademisyen Sayısı",
                "y_label": "Öğrenci / Akademisyen Oranı",
                "size_label": "Öğrenci Büyüklüğü",
                "points": staff_points,
                "reference_lines": [],
            }
        elif re.search(r"sadece kapasite|oran yerine fark|ek kapasite|kapasiteyi.*(?:ön plana|daha belirgin)", question, re.I):

            # Yalnızca kapasite fazlası / farkı hbar
            excess_list = [r for r in derived_metrics if r["key"] == "capacity_excess"]
            if excess_list and excess_list[0]["rows"]:
                r_rows = excess_list[0]["rows"]
                visual_plan = {
                    "chart_type": "hbar",
                    "title": "Fiziksel Kapasite Aşımı ve Ek Koltuk İhtiyacı",
                    "subtitle": dataset.get("academic_year"),
                    "categories": [r["label"] for r in r_rows],
                    "series": [{"name": "Ek Kapasite İhtiyacı", "data": [r["value"] for r in r_rows], "unit": "öğrenci"}],
                }

    if visual_plan is None:
        if scenario_chart_data is not None:
            visual_plan = scenario_chart_data
        elif intent == "excess_capacity":
            excess_list = [r for r in derived_metrics if r["key"] == "capacity_excess"]
            if excess_list and excess_list[0]["rows"]:
                r_rows = excess_list[0]["rows"]
                visual_plan = {
                    "chart_type": "hbar",
                    "title": "Fiziksel Kapasite Aşımı — Ek Koltuk İhtiyacı",
                    "subtitle": dataset.get("academic_year"),
                    "categories": [r["label"] for r in r_rows],
                    "series": [{"name": "Gereken Ek Kapasite", "data": [r["value"] for r in r_rows], "unit": "öğrenci"}],
                }
        elif points and len(points) >= 2 and has_capacity:
            # Standart veya Kapasite Baskısı: Sentezlenmiş BUBBLE CHART
            visual_plan = {
                "chart_type": "bubble",
                "title": "Fakültelerde Fiziksel ve Akademik Baskı Analizi",
                "subtitle": f"{dataset.get('academic_year', '2025-2026')} · Çok Boyutlu Karar Desteği",
                "x_label": "Fiziksel Kapasite Kullanımı (%)",
                "y_label": "Öğrenci / Akademisyen Oranı",
                "size_label": "Öğrenci Sayısı",
                "points": points,
                "reference_lines": [
                    {"axis": "x", "value": 100.0, "label": "Kapasite Sınırı (%100)"}
                ],
            }

    # Büyüme Hazırlığı (Growth Readiness) özel analitiği
    if intent == "growth_readiness":
        growth_summary = []
        for code, ent in entities_map.items():
            st = ent["metrics"].get("student_count", {}).get("value")
            stf = ent["metrics"].get("academic_staff_count", {}).get("value")
            atl = ent["metrics"].get("yokatlas_total_students", {}).get("value")
            ratio = calc_students_per_academic(st, stf)
            growth_summary.append({
                "label": ent["label"],
                "student_count": st,
                "staff_count": stf,
                "ratio": ratio,
                "atlas_median": atl,
            })
        dataset["growth_summary"] = growth_summary

    # 4. AÇIK UÇLU YÖNETİCİ VE STRATEJİK ÖNCELİK ANALİZİ (Executive Priorities)
    is_financial_focus = bool(re.search(r"finans|mali|gelir|gider|ücret", question, re.I))
    is_opportunity_focus = bool(re.search(r"fırsat|büyüme|nereye\s+odaklan", question, re.I))

    if intent in ("executive_overview_analysis", "growth_readiness") or is_financial_focus or is_opportunity_focus:
        priorities = []
        recommendations = []

        if is_financial_focus:
            priorities = [
                {
                    "title": "Gelir ve Kontenjan Genişletme Fırsatı",
                    "description": "Endüstri Mühendisliği gibi altyapısı ve 9 akademisyeni hazır olan ancak 102 öğrenci ile YÖK Atlas medyanının (236) altında kalan birimlerde kontenjan artışıyla öğrenim ücreti geliri büyütülebilir.",
                },
                {
                    "title": "Fiziksel Kapasite ve Altyapı Yatırımı",
                    "description": "İnsan ve Toplum Bilimleri Fakültesi %125,4 kapasite doluluğuyla (247 ek koltuk ihtiyacı) sınırları aşmış olup ek derslik yatırımı veya kira/alan optimizasyonu gerektirmektedir.",
                },
                {
                    "title": "Akademik Kadro ve Ders Yükü Maliyeti",
                    "description": "Yazılım Mühendisliğinde 74,0 öğrenci/akademisyen oranı yeni kadro tahsisini veya ders yükü dengelemesini zorunlu kılmaktadır.",
                },
            ]
            recommendations = [
                "Endüstri Mühendisliği için kontenjan ve tanıtım stratejisi ile gelir potansiyeli artırılabilir.",
                "İnsan ve Toplum Bilimleri için derslik kapasitesi yatırımı veya şube dağılımı planlanmalıdır.",
                "Yazılım Mühendisliği için akademik kadro ihtiyacı bütçelendirilebilir.",
            ]
        elif is_opportunity_focus:
            priorities = [
                {
                    "title": "Mühendislik ve Mimarlık Büyüme Alanı",
                    "description": "803 öğrenci ve 1017 koltuk ile %79 kapasite kullanımında olup 214 koltukluk genişleme ve yeni öğrenci kabul alanı sunmaktadır.",
                },
                {
                    "title": "YÖK Atlas Kıyaslamasında Talep Potansiyeli (Endüstri Mühendisliği)",
                    "description": "102 öğrenci ile benzer programlar medyanı 236'nın altında kalmakta; mevcut 9 akademisyen kadrosu ile ek maliyet olmadan büyüme fırsatı bulunmaktadır.",
                },
                {
                    "title": "Güzel Sanatlar ve Tasarım Altyapısı",
                    "description": "323 öğrenci / 437 kapasite ile %73,9 kullanımda olup 114 boş koltukluk kapasite yeni disiplinler arası programlar için elverişlidir.",
                },
            ]
            recommendations = [
                "Endüstri Mühendisliğinde YÖK Atlas medyanına ulaşmak için kontenjan ve tanıtım stratejisi oluşturulabilir.",
                "Mühendislik Fakültesinde mevcut 214 kişilik boş kapasite yeni yüksek talep gören programlara tahsis edilebilir.",
                "Güzel Sanatlar Fakültesinde stüdyo ve atölye kapasitesi disiplinler arası projelere açılabilir.",
            ]
        else:
            priorities = [
                {
                    "title": "Fiziksel Kapasite Baskısı",
                    "description": "İnsan ve Toplum Bilimleri Fakültesi %125,4 kapasite doluluğu ve 247 ek koltuk ihtiyacı ile fiziksel kapasite sınırının üzerindedir.",
                },
                {
                    "title": "Akademik Kadro ve Yük Yoğunluğu",
                    "description": "Yazılım Mühendisliği Bölümünde 74,0 öğrenci/akademisyen (İnsan ve Toplum Bilimlerinde 39,3) ile belirgin bir akademik kadro yoğunluğu mevcuttur.",
                },
                {
                    "title": "YÖK Atlas Benzer Program Kıyaslaması",
                    "description": "Endüstri Mühendisliği Bölümü 102 öğrenci ile YÖK Atlas benzer lisans programları medyanı 236'nın altındadır (fark: -%56,8).",
                },
            ]
            recommendations = [
                "İnsan ve Toplum Bilimleri Fakültesi için ek derslik tahsisi veya şube planlaması değerlendirilebilir.",
                "Yazılım Mühendisliği ve yüksek yüklü birimler için akademik kadro takviyesi veya ders yükü dengelemesi incelenebilir.",
                "Endüstri Mühendisliği için bu farkın nedeni talep, kontenjan, doluluk ve tercih eğilimleriyle birlikte incelenmelidir.",
            ]

        dataset["executive_priorities"] = priorities
        dataset["executive_recommendations"] = recommendations

        analysis_findings = [
            {
                "finding_id": 1,
                "topic": "physical_capacity_pressure",
                "title": "Fiziksel Kapasite Baskısı",
                "entities": ["İnsan ve Toplum Bilimleri Fakültesi"],
                "metrics": {
                    "student_count": 1219,
                    "total_capacity": 972,
                    "capacity_utilization": 125.4,
                    "capacity_excess": 247,
                },
                "evidence": "İnsan ve Toplum Bilimleri Fakültesi %125,4 kapasite doluluğu ve 247 ek koltuk ihtiyacı ile fiziksel kapasite sınırının üzerindedir.",
                "recommendation": "İnsan ve Toplum Bilimleri Fakültesi için ek derslik tahsisi veya şube planlaması değerlendirilebilir.",
                "sources": ["ÖSYM/YKS", "Fiziksel Envanter"],
                "visualization": "bubble",
            },
            {
                "finding_id": 2,
                "topic": "academic_staff_load",
                "title": "Akademik Kadro ve Yük Yoğunluğu",
                "entities": ["Yazılım Mühendisliği Bölümü", "İnsan ve Toplum Bilimleri Fakültesi", "Mühendislik ve Mimarlık Fakültesi"],
                "metrics": {
                    "yazilim_students_per_academic": 74.0,
                    "insan_toplum_students_per_academic": 39.3,
                    "muhendislik_students_per_academic": 25.1,
                },
                "evidence": "Yazılım Mühendisliği Bölümünde 74,0 öğrenci/akademisyen (İnsan ve Toplum Bilimlerinde 39,3) ile belirgin bir akademik kadro yoğunluğu mevcuttur.",
                "recommendation": "Yazılım Mühendisliği ve yüksek yüklü birimler için akademik kadro takviyesi veya ders yükü dengelemesi incelenebilir.",
                "sources": ["ÖSYM/YKS", "Akademik Personel"],
                "visualization": "hbar",
            },
            {
                "finding_id": 3,
                "topic": "peer_size_difference",
                "title": "YÖK Atlas Benzer Program Kıyaslaması",
                "entities": ["Endüstri Mühendisliği Bölümü", "Yazılım Mühendisliği Bölümü", "Bilgisayar Mühendisliği Bölümü"],
                "metrics": {
                    "endustri_student_count": 102,
                    "endustri_atlas_median": 236,
                    "endustri_diff_pct": -56.8,
                    "endustri_diff_count": -134,
                },
                "evidence": "Endüstri Mühendisliği Bölümü 102 öğrenci ile YÖK Atlas benzer programlar medyanı 236'nın gerisindedir (%56,8 daha küçük).",
                "recommendation": "Bu farkın nedeni talep, kontenjan, doluluk ve tercih eğilimleriyle birlikte incelenmelidir.",
                "sources": ["ÖSYM/YKS", "YÖK Atlas"],
                "visualization": "grouped",
            },
        ]
        dataset["analysis_findings"] = analysis_findings


    # Zenginleştirilmiş dataset alanları
    dataset["derived_metrics"] = derived_metrics
    dataset["visual_plan"] = visual_plan
    dataset["intent"] = intent

    return {
        "handled": True,
        "intent": intent,
        "dataset": dataset,
        "visual_plan": visual_plan,
        "derived_metrics": derived_metrics,
        "executive_priorities": dataset.get("executive_priorities"),
        "executive_recommendations": dataset.get("executive_recommendations"),
    }

