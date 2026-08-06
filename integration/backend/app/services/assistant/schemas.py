"""Akıllı asistan katmanının veri sözleşmeleri.

Asistan YEREL bir dil modeliyle (Ollama) çalışır. Hiçbir bulut servisine istek
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

    Değerler yapılandırmadan ve yerel Ollama servisinden okunur. Bu uç nokta
    Ollama kapalıyken de cevap verir; hata fırlatmaz.
    """

    provider: str = Field(description="Etkin sağlayıcı.", examples=["ollama"])
    model: str = Field(description="Kullanılacak model.", examples=["qwen3.5:9b"])
    enabled: bool = Field(
        description="Asistan yapılandırmada etkin mi?", examples=[True]
    )
    service_available: bool = Field(
        description="Yerel Ollama servisine ulaşılabiliyor mu?", examples=[True]
    )
    model_available: bool = Field(
        description="İstenen model Ollama'da kurulu mu?", examples=[True]
    )
    ready: bool = Field(
        description="Servis ayakta VE model kurulu mu?", examples=[True]
    )
    message: str = Field(examples=["Yapay zekâ hazır — qwen3.5:9b"])
    installed_models: List[str] = Field(
        default_factory=list,
        description="Ollama'da kurulu model adları. Servis kapalıysa boştur.",
        examples=[["qwen3.5:9b"]],
    )
    tool_count: int = Field(
        default=0,
        description="Modelin çağırabileceği kurumsal veri aracı sayısı.",
        examples=[6],
    )


class ChatRequest(BaseModel):
    """Kullanıcının asistana gönderdiği mesaj."""

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

    model_config = ConfigDict(extra="forbid")


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
    provider: str = Field(examples=["ollama"])
    model: str = Field(examples=["qwen3.5:9b"])
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
    calculated_at: datetime = Field(
        description="Cevabın üretildiği an.",
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
