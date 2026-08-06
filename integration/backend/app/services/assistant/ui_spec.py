"""Dinamik sonuç penceresinin şeması.

TASARIM KARARI — TEK VERİ KAYNAĞI
---------------------------------
Kartlar ve grafikler modelin serbest metninden sayı ayıklanarak
oluşturulmaz. Tek kaynak `structured_result`tir. Model yalnızca kısa yönetim
yorumunu yazar.

Akış:

    structured_result  →  ui_spec (BU DOSYA)  →  frontend renderer

Model bu şemayı ÜRETMEZ; backend deterministik olarak üretir. İleride model
yalnızca "hangi doğrulanmış metrik öne çıksın", "hangi grafik türü", "bölüm
sırası" ve "tema tokenı" seçebilecek — yeni sayı üretemeyecek.

GÜVENLİK
--------
* Bileşen türleri kapalı bir listedir (`ComponentType`). Bilinmeyen tür
  şemadan geçmez, dolayısıyla arayüze hiç ulaşmaz.
* Tema yalnızca beş belirteçten oluşur; serbest CSS yoktur.
* Hiçbir alan HTML veya JavaScript taşımaz; renderer bütün metni kaçırır.
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

UI_SPEC_VERSION = "1.0"

# Frontend'in render edebileceği TEK bileşen kümesi.
ComponentType = Literal[
    "metric_card",
    "comparison_metric",
    "bar_chart",
    "line_chart",
    "gauge",
    "risk_card",
    "information_box",
    "recommendation_list",
    "data_source_panel",
    "scope_badge",
    "assumptions_panel",
    "expandable_details",
]

SectionType = Literal[
    "metric_grid",
    "chart_grid",
    "risk_summary",
    "management_comment",
    "details",
]

# Tema belirteçleri. Serbest CSS yerine sabit sözlük; renderer bunları
# kapsamlı (scoped) CSS değişkenlerine çevirir.
AccentToken = Literal["indigo", "teal", "amber", "slate", "rose"]
DensityToken = Literal["compact", "comfortable"]
RadiusToken = Literal["sharp", "soft", "round"]
EmphasisToken = Literal["low", "normal", "high"]


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
    #: Serinin anlamı: mevcut durum / senaryo / kullanılabilir kapasite.
    role: Literal["baseline", "scenario", "capacity"] = "baseline"
    values: List[Optional[float]]


class Component(BaseModel):
    """Tek bir görsel bileşen.

    `source_keys`, bu bileşendeki her sayının `structured_result` içindeki
    hangi metrikten geldiğini söyler. Testler bu bağı doğrular; serbest
    metinden sayı ayıklanmadığının kanıtıdır.
    """

    model_config = ConfigDict(extra="forbid")

    type: ComponentType
    title: Optional[str] = None
    subtitle: Optional[str] = None

    # --- metric_card / comparison_metric ---
    value: Optional[str] = None
    baseline_label: Optional[str] = None
    scenario_label: Optional[str] = None
    delta_label: Optional[str] = None
    trend: Optional[Literal["up", "down", "flat"]] = None

    # --- grafikler ---
    categories: List[str] = Field(default_factory=list)
    series: List[ChartSeries] = Field(default_factory=list)
    unit: Optional[str] = None
    #: Legend yalnızca burada tanımlanır; renderer ikinci bir legend çizmez.
    legend: List[Dict[str, str]] = Field(default_factory=list)

    # --- gauge ---
    percent: Optional[float] = None

    # --- risk_card / information_box ---
    level: Optional[Literal["info", "warning", "critical"]] = None
    body: Optional[str] = None
    items: List[str] = Field(default_factory=list)

    # --- expandable_details ---
    open: bool = False
    components: List["Component"] = Field(default_factory=list)
    markdown: Optional[str] = None

    # --- izlenebilirlik ---
    scope_type: Optional[Literal["university", "faculty", "department", "program"]] = None
    scope_name: Optional[str] = None
    source_keys: List[str] = Field(default_factory=list)
    formula: Optional[str] = None
    note: Optional[str] = None


Component.model_rebuild()


class Section(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: SectionType
    title: Optional[str] = None
    components: List[Component] = Field(default_factory=list)


class UiSpec(BaseModel):
    """Dinamik sonuç penceresinin tam tanımı."""

    model_config = ConfigDict(extra="forbid")

    version: Literal["1.0"] = UI_SPEC_VERSION
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


def component_types() -> List[str]:
    """Kayıtlı bileşen türleri. Frontend testleri bu listeyle karşılaştırır."""
    return list(ComponentType.__args__)  # type: ignore[attr-defined]
