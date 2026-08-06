"""Dinamik sonuç penceresinin şeması.

TASARIM KARARI — TEK VERİ KAYNAĞI
---------------------------------
Kartlar ve grafikler modelin serbest metninden sayı ayıklanarak
oluşturulmaz. Tek kaynak `structured_result`tir. Model yalnızca kısa yönetim
yorumunu yazar.

Akış:

    structured_result  →  ui_planner  →  ui_spec (BU DOSYA)  →  renderer
                             ↑
                    hangi anlamı hangi grafik anlatır

Model bu şemayı ÜRETMEZ; backend deterministik olarak üretir.

İZLENEBİLİRLİK
--------------
Her sayısal bileşen iki alan taşır:

* `data`              — gösterilecek sayılar
* `source_metric_ids` — bu sayıların `structured_result` içindeki adresleri,
                        `"<metrik anahtarı>.<baseline|scenario|change>"`

Renderer bu adresleri çözer ve `data` ile karşılaştırır. Uyuşmazsa
`structured_result` esas alınır. Böylece pencereye kaynağı gösterilemeyen
tek bir sayı bile giremez.

GÜVENLİK
--------
* Bileşen türleri kapalı bir listedir (`ComponentType`).
* Tema ve renkler yalnızca sabit belirteçlerden oluşur; serbest CSS yoktur.
* Hiçbir alan HTML veya JavaScript taşımaz; renderer bütün metni kaçırır.
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

UI_SPEC_VERSION = "2.0"

# Frontend'in render edebileceği TEK bileşen kümesi.
ComponentType = Literal[
    # --- özet, kart ve metin ---
    "decision_summary",
    "kpi_card",
    "metric_card",
    "comparison_metric",
    "risk_card",
    "risk_summary_card",
    "information_box",
    "recommendation_list",
    "decision_list",
    "data_source_panel",
    "scope_badge",
    "assumptions_panel",
    "expandable_details",
    "legend_panel",
    # --- grafikler ---
    "dumbbell_chart",
    "slope_chart",
    "bullet_chart",
    "radial_gauge",
    "semi_circle_gauge",
    "gauge_group",
    "waterfall_chart",
    "forecast_line_chart",
    "stacked_area_chart",
    "line_chart",
    "bar_chart",
    "grouped_bar_chart",
    "horizontal_comparison_bar",
    "heatmap",
    "risk_matrix",
    "treemap",
    "radar_chart",
    "sparkline",
    "progress_ring",
    "gauge",
]

#: Küçük çoklu (small multiple) olarak birden fazla kez görünmesi TASARIM
#: GEREĞİ olan türler. Diğer grafik türleri bir pencerede yalnızca bir kez
#: kullanılır — aynı grafiği art arda göstermek bilgi taşımaz.
SMALL_MULTIPLE_TYPES = frozenset(
    {"radial_gauge", "semi_circle_gauge", "progress_ring", "sparkline"}
)

#: Gelişmiş bir grafik çizilemezse hangi basit türe düşeceği. Zincir tek
#: adımda bitmeyebilir; renderer zinciri sonuna kadar izler.
FALLBACK_CHAIN: Dict[str, str] = {
    "dumbbell_chart": "horizontal_comparison_bar",
    "slope_chart": "dumbbell_chart",
    "bullet_chart": "grouped_bar_chart",
    "radial_gauge": "progress_ring",
    "semi_circle_gauge": "radial_gauge",
    "gauge_group": "grouped_bar_chart",
    "waterfall_chart": "grouped_bar_chart",
    "forecast_line_chart": "line_chart",
    "stacked_area_chart": "line_chart",
    "heatmap": "grouped_bar_chart",
    "risk_matrix": "risk_summary_card",
    "treemap": "horizontal_comparison_bar",
    "radar_chart": "grouped_bar_chart",
    "horizontal_comparison_bar": "bar_chart",
    "grouped_bar_chart": "bar_chart",
}

SectionType = Literal[
    "decision_summary",
    "metric_grid",
    "chart_grid",
    "risk_summary",
    "recommendations",
    "management_comment",
    "accordion",
    "details",
]

# Tema belirteçleri. Serbest CSS yerine sabit sözlük.
AccentToken = Literal["indigo", "teal", "amber", "slate", "rose"]
DensityToken = Literal["compact", "comfortable"]
RadiusToken = Literal["sharp", "soft", "round"]
EmphasisToken = Literal["low", "normal", "high"]

#: Renklerin ANLAMI sabittir; bir renk iki grafikte farklı şey anlatamaz.
ToneToken = Literal[
    "baseline",   # mavi    — mevcut durum
    "scenario",   # turuncu — senaryo sonucu
    "capacity",   # gri     — kullanılabilir kapasite / hedef
    "positive",   # yeşil   — olumlu mali etki
    "warning",    # amber   — uyarı
    "critical",   # kırmızı — kritik risk
    "info",       # indigo  — bilgilendirme
]

LevelToken = Literal["info", "warning", "critical", "positive"]


class Theme(BaseModel):
    """İzin verilen tema belirteçleri. Başka bir alan kabul edilmez."""

    model_config = ConfigDict(extra="forbid")

    accent: AccentToken = "indigo"
    density: DensityToken = "comfortable"
    card_radius: RadiusToken = "soft"
    chart_emphasis: EmphasisToken = "normal"
    risk_emphasis: EmphasisToken = "normal"


class ChartSeries(BaseModel):
    """Bir grafik serisi. Değerler yalnızca sayıdır; metin taşımaz."""

    model_config = ConfigDict(extra="forbid")

    label: str
    #: Serinin anlamı. Renk buradan gelir; bileşen kendi rengini seçemez.
    role: ToneToken = "baseline"
    values: List[Optional[float]] = Field(default_factory=list)
    #: Her değerin `structured_result` adresi (aynı sırada). Türetilmiş bir
    #: değerde bu listenin ilgili girdisi "a|b" biçiminde iki adres taşır.
    source_metric_ids: List[Optional[str]] = Field(default_factory=list)
    #: Türetilmiş değerler için işlem: iki kaynağın farkı veya toplamı.
    #: Renderer değeri kendisi yeniden hesaplar; `values` yalnızca kontrol
    #: amaçlıdır.
    derivation: Optional[Literal["difference", "sum"]] = None
    #: Şelale grafiğinde her çubuğun türü: increase | decrease | total.
    kinds: List[Optional[str]] = Field(default_factory=list)
    #: Kaynaktan çözülen değere uygulanacak işaret (+1 / -1).
    #: Bir GİDER ARTIŞI kaynakta pozitiftir (+612.000 USD) ama bütçeyi
    #: AZALTIR. İşaret burada açıkça taşınmazsa doğrulama katmanı çubuğu
    #: yukarı çevirir ve maaş artışı bütçe artışı gibi görünür.
    value_signs: List[Optional[int]] = Field(default_factory=list)
    #: Tahmin grafiklerinde güven aralığı.
    lower: List[Optional[float]] = Field(default_factory=list)
    upper: List[Optional[float]] = Field(default_factory=list)
    #: Kesikli çizgi: öngörülen veya hesaplanmamış değerler.
    dashed: bool = False


class Marker(BaseModel):
    """Grafik üzerindeki eşik, hedef veya kapasite işareti."""

    model_config = ConfigDict(extra="forbid")

    label: str
    value: float
    tone: ToneToken = "capacity"
    source_metric_id: Optional[str] = None


class Badge(BaseModel):
    """Karar özetinin yanındaki küçük rozet."""

    model_config = ConfigDict(extra="forbid")

    label: str
    tone: ToneToken = "info"


class Component(BaseModel):
    """Tek bir görsel bileşen.

    `source_metric_ids`, bileşendeki her sayının `structured_result`
    içindeki adresini verir. Testler bu bağı doğrular; serbest metinden sayı
    ayıklanmadığının kanıtıdır.
    """

    model_config = ConfigDict(extra="forbid")

    type: ComponentType
    id: Optional[str] = None
    title: Optional[str] = None
    subtitle: Optional[str] = None
    #: 12 kolonluk gridde kaç kolon kaplayacağı. Mobilde her bileşen tam
    #: genişliğe düşer; bu değer yalnızca masaüstü yerleşimini etkiler.
    span: int = Field(default=12, ge=1, le=12)
    #: Erişilebilirlik: ekran okuyucu için bileşenin sözlü özeti.
    aria_label: Optional[str] = None
    #: Yalnızca ad; renderer sabit bir SVG sözlüğünden çizer.
    icon: Optional[str] = None
    tone: Optional[ToneToken] = None
    level: Optional[LevelToken] = None

    # --- kpi_card / metric_card / comparison_metric ---
    value: Optional[str] = None
    value_number: Optional[float] = None
    baseline_label: Optional[str] = None
    scenario_label: Optional[str] = None
    delta_label: Optional[str] = None
    trend: Optional[Literal["up", "down", "flat"]] = None
    #: Değişimin İYİ mi KÖTÜ mü olduğu. Yön ile anlam aynı şey değildir:
    #: açığın artması yön olarak "up", anlam olarak "negative"dir.
    sentiment: Optional[Literal["positive", "negative", "neutral"]] = None
    unit: Optional[str] = None
    caption: Optional[str] = None

    # --- grafikler ---
    categories: List[str] = Field(default_factory=list)
    series: List[ChartSeries] = Field(default_factory=list)
    markers: List[Marker] = Field(default_factory=list)
    #: Kartın adlandırılmış sayıları (baseline / scenario / delta gibi).
    data: Dict[str, Optional[float]] = Field(default_factory=dict)
    #: `data` içindeki HER anahtarın kaynak adresi.
    #: Sıraya değil ADA bağlıdır: `{"capacity": "program_staff_fte.baseline"}`.
    #: Sıra tabanlı bir eşleşme, alan adları farklı olan bileşenlerde
    #: (kapasite/mevcut/senaryo) sessizce yanlış kaynağa bağlanırdı.
    data_source_ids: Dict[str, str] = Field(default_factory=dict)
    #: Legend YALNIZCA panel düzeyinde bir kez tanımlanır.
    legend: List[Dict[str, str]] = Field(default_factory=list)
    percent: Optional[float] = None
    #: Matris ve ısı haritası hücreleri.
    cells: List[Dict[str, Any]] = Field(default_factory=list)

    # --- metin taşıyan bileşenler ---
    body: Optional[str] = None
    items: List[str] = Field(default_factory=list)
    badges: List[Badge] = Field(default_factory=list)

    # --- expandable_details / gauge_group ---
    open: bool = False
    components: List["Component"] = Field(default_factory=list)
    markdown: Optional[str] = None

    # --- izlenebilirlik ---
    scope_type: Optional[Literal["university", "faculty", "department", "program"]] = None
    scope_name: Optional[str] = None
    #: "<metrik anahtarı>.<baseline|scenario|change>" biçiminde adresler.
    source_metric_ids: List[str] = Field(default_factory=list)
    #: Geriye dönük uyumluluk: yalnızca metrik anahtarları.
    source_keys: List[str] = Field(default_factory=list)
    semantic_type: Optional[str] = None
    formula: Optional[str] = None
    note: Optional[str] = None
    #: Çizilemezse denenecek tür. Boşsa `FALLBACK_CHAIN` kullanılır.
    fallback: Optional[ComponentType] = None


Component.model_rebuild()


class Section(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: SectionType
    title: Optional[str] = None
    subtitle: Optional[str] = None
    components: List[Component] = Field(default_factory=list)


class UiSpec(BaseModel):
    """Dinamik sonuç penceresinin tam tanımı."""

    model_config = ConfigDict(extra="forbid")

    version: Literal["2.0"] = UI_SPEC_VERSION
    view_type: Literal[
        "scenario_dashboard", "summary_dashboard", "financial_dashboard"
    ]
    view_id: str = Field(description="Pencereyi tekil kılan kimlik; scoped CSS için.")
    title: str
    subtitle: Optional[str] = None
    theme: Theme = Field(default_factory=Theme)
    sections: List[Section] = Field(default_factory=list)

    #: Pencerenin altında gösterilen izlenebilirlik bilgisi.
    academic_year: Optional[str] = None
    scope: Dict[str, str] = Field(default_factory=dict)
    calculated_at: Optional[datetime] = None


#: Grafik sayılan bileşen türleri. "En fazla 4 grafik" kuralı bunları sayar;
#: küçük çoklular (gauge) tek bir `gauge_group` içinde durduğu için bir
#: grafik sayılır.
CHART_TYPES = frozenset(
    {
        "dumbbell_chart",
        "slope_chart",
        "bullet_chart",
        "gauge_group",
        "waterfall_chart",
        "forecast_line_chart",
        "stacked_area_chart",
        "line_chart",
        "bar_chart",
        "grouped_bar_chart",
        "horizontal_comparison_bar",
        "heatmap",
        "risk_matrix",
        "treemap",
        "radar_chart",
    }
)


def component_types() -> List[str]:
    """Kayıtlı bileşen türleri. Frontend testleri bu listeyle karşılaştırır."""
    return list(ComponentType.__args__)  # type: ignore[attr-defined]


def chart_types() -> List[str]:
    """Yalnızca grafik sayılan türler."""
    return sorted(CHART_TYPES)
