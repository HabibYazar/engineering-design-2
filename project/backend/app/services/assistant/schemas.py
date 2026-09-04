"""Akıllı asistan katmanının veri sözleşmeleri.

Asistan Gemini API'si üzerinden çalışır. Gemini dışında hiçbir bulut servisine istek
gönderilmez ve hiçbir API anahtarı kullanılmaz.

Bu aşamada model kurumsal veriye ERİŞEMEZ: araç çağrısı, veritabanı sorgusu ve
senaryo motoru bağlantısı yoktur. Bağlam hazırlama katmanı (`context_builder`)
ayrı durur ve bir sonraki aşamada modele bağlanacaktır.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class AssistantStatus(BaseModel):
    """Asistanın çalışma durumu.

    Değerler yapılandırmadan ve Gemini servisinden okunur. Bu uç nokta
    Gemini erişilemezken de cevap verir; hata fırlatmaz.
    """

    provider: str = Field(description="Etkin sağlayıcı.", examples=["gemini"])
    model: str = Field(description="Kullanılacak model.", examples=["gemini-2.5-flash"])
    enabled: bool = Field(
        description="Asistan yapılandırmada etkin mi?", examples=[True]
    )
    service_available: bool = Field(
        description="Gemini servisine ulaşılabiliyor mu?", examples=[True]
    )
    model_available: bool = Field(
        description="İstenen model Gemini hesabında kullanılabiliyor mu?", examples=[True]
    )
    ready: bool = Field(
        description="Servis ayakta VE model kurulu mu?", examples=[True]
    )
    message: str = Field(examples=["Yapay zekâ hazır — gemini-2.5-flash"])
    installed_models: List[str] = Field(
        default_factory=list,
        description="Gemini hesabındaki model adları. Servise ulaşılamıyorsa boştur.",
        examples=[["gemini-2.5-flash"]],
    )
    tool_count: int = Field(
        default=0,
        description="Modelin çağırabileceği kurumsal veri aracı sayısı.",
        examples=[6],
    )


class ScopeSelection(BaseModel):
    """Arayüzde o an SEÇİLİ olan birim — kimlikle, adla değil.

    Asistan bağlamının kapsam dışına çıkmaması için gönderilir. Kullanıcı
    "Yazılım Mühendisliği" sayfasındayken sorduğu soru, hiçbir birim adı
    içermese bile o programın verisiyle cevaplanmalıdır.

    Ad/kod DEĞİL kimlik taşınır; ad eşleştirmesi yazım ve büyük-küçük harf
    farklarında sessizce yanlış birimi seçebilirdi.
    """

    faculty_id: Optional[int] = Field(default=None, ge=1)
    department_id: Optional[int] = Field(default=None, ge=1)
    academic_program_id: Optional[int] = Field(default=None, ge=1)

    model_config = ConfigDict(extra="forbid")


class ChatRequest(BaseModel):
    """Kullanıcının asistana gönderdiği mesaj."""

    # BİLİNMEYEN ALAN SESSİZCE YOK SAYILMAZ.
    # ------------------------------------------------------------------
    # Varsayılan davranışta pydantic fazladan alanları atıyordu: arayüz
    # `temperature` gönderiyor, backend görmezden geliyor ve kimse fark
    # etmiyordu. Bu proje daha önce tam olarak bu sınıf hatadan zarar
    # gördü (alan adı uyuşmazlığı aylarca gizli kaldı).
    #
    # `forbid` ile istek 422 döner ve uyuşmazlık ilk denemede görünür.
    model_config = ConfigDict(extra="forbid")

    # Uzunluk sınırı hem burada hem serviste var: şema HTTP seviyesinde 422
    # üretir, servis ise doğrudan çağrıldığında da korur.
    message: str = Field(
        min_length=1,
        max_length=4000,
        description="Kullanıcı mesajı. Boş olamaz.",
        examples=["Merhaba"],
    )
    conversation_id: Optional[str] = Field(
        default=None,
        description="Var olan bir konuşmayı sürdürmek için. Boşsa yeni konuşma açılır.",
        examples=[None],
    )
    stream: bool = Field(
        default=False,
        description="Bu alan uyumluluk içindir; akış için /chat/stream kullanılır.",
        examples=[False],
    )
    # ÖNCEKİ GRAFİKLER — "bunu line yap" için ikinci kaynak.
    # ------------------------------------------------------------------
    # Sunucu, konuşma başına son grafikleri süreç belleğinde tutuyor. Bu
    # tek başına KIRILGAN: süreç yeniden başlarsa, birden çok işçi
    # varsa ya da kullanıcı sekme değiştirirse hafıza kaybolur ve
    # dönüştürme yapılacak grafik bulunamaz.
    #
    # Arayüz o grafikleri ZATEN elinde tutuyor (son asistan mesajının
    # `charts` alanı). Onu isteğe eklemek yeni bir state sistemi
    # kurmadan takip mesajını güvenceye alır. Alan İSTEĞE BAĞLIDIR:
    # göndermeyen istemciler eskisi gibi çalışır.
    previous_charts: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description=("Son asistan cevabındaki grafikler. Yalnızca grafik "
                     "türü değiştirme takip mesajlarında kullanılır."),
        examples=[None],
    )
    # ÖNCEKİ CEVAPTA GRAFİK OLMAYABİLİR AMA VERİ VARDIR.
    # Kullanıcı tablo içeren bir cevap alıp "line yap" dediğinde
    # dönüştürülecek şey o tablodur. Yapılandırılmış sonuç birinci,
    # görünür metin son çare kaynaktır; ikisi de İSTEĞE BAĞLIDIR.
    previous_data: Optional[Any] = Field(
        default=None,
        description=("Son asistan cevabının yapılandırılmış sonucu. "
                     "Grafik yoksa buradan grafik üretilebilir."),
        examples=[None],
    )
    previous_answer: Optional[str] = Field(
        default=None,
        max_length=20000,
        description=("Son asistan cevabının görünür metni. Yalnızca "
                     "içindeki tablo grafiğe çevrilecekse kullanılır."),
        examples=[None],
    )
    scope: Optional[ScopeSelection] = Field(
        default=None,
        description=(
            "Arayüzde seçili birim. Verilirse araçlar bu kapsamı VARSAYILAN "
            "olarak kullanır; soruda başka bir birim adı geçerse o kazanır."
        ),
    )
    academic_year: Optional[str] = Field(
        default=None,
        pattern=r"^\d{4}-\d{4}$",
        description=(
            "Arayüzde seçili akademik yıl. Kullanıcı mesajında açıkça başka "
            "bir yıl yazmadıkça araçların varsayılan dönemidir."
        ),
        examples=["2025-2026"],
    )

    screen_context: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Arayüz ekran bağlamı (screen_id, domain, visible_metric_keys, vb.).",
    )
    mode: Optional[str] = Field(
        default=None,
        description="İstek kipi (örn. 'screen_auto_insight').",
    )

    # `model_config` BURADA TEKRAR TANIMLANMAZ.
    # ------------------------------------------------------------------
    # Sınıfın başında `extra="forbid"` var. Buraya ikinci bir atama
    # koymak Python'da normal bir yeniden atamadır: sonuncusu kazanır ve
    # yasak sessizce "yok say"a döner. Kural sınıfın en üstündedir.


class ScreenContext(BaseModel):
    screen_id: Optional[str] = None
    screen_title: Optional[str] = None
    domain: Optional[str] = None
    faculty_id: Optional[int] = None
    department_id: Optional[int] = None
    academic_program_id: Optional[int] = None
    academic_year: Optional[str] = None
    visible_metric_keys: Optional[List[str]] = Field(default_factory=list)
    active_finding: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class ScreenInsightFinding(BaseModel):
    id: int
    title: str
    finding: str
    evidence: str
    recommendation: Optional[str] = None
    metric_key: Optional[str] = None
    source_label: Optional[str] = None
    is_synthetic: bool = False


class ScreenInsightRequest(BaseModel):
    screen_context: ScreenContext
    conversation_id: Optional[str] = None
    academic_year: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class ScreenInsightResponse(BaseModel):
    screen_id: str
    screen_title: str
    academic_year: str
    summary_text: str
    observations: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    findings: List[ScreenInsightFinding] = Field(default_factory=list)
    data_sources: List[str] = Field(default_factory=list)
    provenance_notes: List[str] = Field(default_factory=list)
    conversation_id: str
    calculated_at: datetime
    charts: List[Dict[str, Any]] = Field(default_factory=list)
    has_synthetic_data: bool = False


class UsedTool(BaseModel):
    """Modelin çağırdığı bir araç ve sonucu."""

    name: str = Field(
        description="Teknik araç adı. Arayüzde KULLANICIYA GÖSTERİLMEZ.",
        examples=["run_enrollment_change_scenario"],
    )
    success: bool = Field(examples=[True])


class ChatResponse(BaseModel):
    """Modelin ürettiği cevap ve dayandığı veri.

    Modelin düşünme (reasoning) metni bu cevaba KONULMAZ; sağlayıcı katmanında
    ayıklanır ve yalnızca sunucu günlüğüne uzunluğu yazılır.
    """

    conversation_id: str = Field(examples=["7f1c2e6a-9a4b-4d1f-9c2a-1f3b5d7e9c11"])
    answer: str = Field(examples=["2025-2026 verilerine göre…"])
    provider: str = Field(examples=["gemini"])
    model: str = Field(examples=["gemini-2.5-flash"])
    used_tools: List[UsedTool] = Field(
        default_factory=list,
        description="Çağrılan araçlar. Arayüz teknik adları göstermez.",
    )
    data_sources: List[str] = Field(
        default_factory=list,
        description="Kullanıcıya gösterilecek Türkçe veri kaynağı adları.",
        examples=[["Öğrenci kayıtları", "Mali dönem kayıtları"]],
    )
    academic_year: Optional[str] = Field(
        default=None,
        description="Araç sonuçlarının ait olduğu akademik yıl.",
        examples=["2025-2026"],
    )
    scope: Dict[str, str] = Field(
        default_factory=dict,
        description="Araç sonuçlarından derlenen kapsam (fakülte/bölüm/program).",
        examples=[{"program": "Bilgisayar Mühendisliği Lisans Programı"}],
    )
    # GRAFİK NİYETİ — EKLENEN ALANLAR, DEĞİŞEN ALAN YOK.
    # Arayüz grafikleri `charts` alanından okumaya devam eder; bu iki
    # alan yalnızca "kullanıcı grafik istedi mi, istediyse neden
    # çıkmadı" sorusunu cevaplar. Varsayılanları olduğu için eski
    # istemciler ve grafik üretmeyen dönüş yolları etkilenmez.
    chart_requested: bool = Field(
        default=False,
        description="Kullanıcı görselleştirme istedi mi.",
    )
    chart_reason: str = Field(
        default="",
        description=("Grafik istendi ama üretilemediyse kısa gerekçe. "
                     "Teknik ayrıntı içermez."),
    )
    calculated_at: datetime = Field(
        description="Cevabın üretildiği an.",
    )
    charts: List[Dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Backend tarafından ÜRETİLEN grafikler. Sayılar mevcut "
            "servislerden okunur; dil modeli grafik verisi üretmez, "
            "yürütülebilir kod döndüremez."
        ),
    )
    structured_result: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "Senaryo/özet sonucunun makine okunur hâli. Arayüz şimdilik "
            "yalnızca `answer` metnini gösterir; bu alan sonraki dinamik "
            "grafik aşaması için korunur."
        ),
        examples=[
            {
                "type": "enrollment_change_scenario",
                "academic_year": "2025-2026",
                "scope": {"program": "Bilgisayar Mühendisliği Lisans Programı"},
                "metrics": [
                    {
                        "key": "program_student_count",
                        "label": "Öğrenci sayısı",
                        "baseline": 370,
                        "scenario": 426,
                        "change": 56,
                        "unit": "öğrenci",
                    }
                ],
                "risks": [],
                "recommendations": [],
            }
        ],
    )
    ui_spec: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "Dinamik sonuç penceresinin tanımı. Kartlar ve grafikler "
            "structured_result'tan üretilir; modelin serbest metninden sayı "
            "ayıklanmaz. Bileşen türleri kapalı bir listedir."
        ),
    )
    data_source: str = Field(
        description=(
            "Cevabın dayanağı. 'institutional_data' araç sonuçlarına, "
            "'general_model_knowledge' modelin kendi genel bilgisine dayanır."
        ),
        examples=["institutional_data"],
    )


class ContextItem(BaseModel):
    """Bağlama eklenen tek bir kurumsal gösterge."""

    source_module: str = Field(
        description="Verinin hangi modülden geldiği.",
        examples=["Modül 2 — Öğrenci Analitiği"],
    )
    key: str = Field(examples=["total_students"])
    label: str = Field(examples=["Toplam öğrenci sayısı"])
    value: str = Field(
        description="Değer metin olarak taşınır; modele gönderilecek biçim budur.",
        examples=["4000"],
    )


class ContextResponse(BaseModel):
    """Bir soru için hazırlanan bağlam."""

    question: str = Field(examples=["Hangi programların doluluk oranı düşüyor?"])
    matched_topic: Optional[str] = Field(
        default=None,
        description="Sorunun eşleştiği konu. Eşleşme yoksa genel bağlam toplanır.",
        examples=["öğrenci talebi"],
    )
    context_items: List[ContextItem]
    academic_year: Optional[str] = None
    scope: Dict[str, str] = Field(default_factory=dict)
    notice: str = Field(
        description="Cevabın neden üretilmediğini açıklayan uyarı.",
        examples=[
            "Bu bir dil modeli cevabı değildir. Sisteme bağlı bir LLM yoktur; "
            "yalnızca soruya ilişkin kurumsal veriler toplanmıştır."
        ],
    )


class SampleQuestion(BaseModel):
    """Arayüzde gösterilen örnek soru."""

    question: str = Field(examples=["Hangi programların doluluk oranı düşüyor?"])
    topic: str = Field(examples=["öğrenci talebi"])
    covered_modules: List[str] = Field(
        examples=[["Modül 2 — Öğrenci Analitiği", "Modül 7 — Program Sürdürülebilirliği"]]
    )


class ArchitectureComponent(BaseModel):
    """Asistan katmanının bir bileşeni."""

    file: str = Field(examples=["app/services/assistant/context_builder.py"])
    responsibility: str = Field(examples=["Soruyu konuya eşler ve bağlamı derler."])
    status: str = Field(description="hazır / eksik", examples=["hazır"])


class ArchitectureResponse(BaseModel):
    """Asistan mimarisi ve model bağlandığında yapılacaklar."""

    summary: str
    components: List[ArchitectureComponent]
    next_steps: List[str]


class ContextRequest(BaseModel):
    """Bağlam hazırlama isteği."""

    question: str = Field(
        min_length=3,
        max_length=500,
        examples=["Hangi programların doluluk oranı düşüyor?"],
    )
    scope: Optional[ScopeSelection] = None
    academic_year: Optional[str] = Field(
        default=None, pattern=r"^\d{4}-\d{4}$")
