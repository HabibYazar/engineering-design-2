"""Akıllı asistan katmanının veri sözleşmeleri.

ÖNEMLİ: Bu katman hiçbir dil modeline (LLM) bağlı DEĞİLDİR ve cevap üretmez.
Yaptığı tek iş, bir soruya cevap verilebilmesi için hangi kurumsal verilerin
gerekli olduğunu belirleyip bu veriyi veritabanından toplamaktır. Model
bağlandığında aynı bağlam modele gönderilecek; şu anda kullanıcıya ham veri ve
"cevap üretilmedi" bilgisi gösterilir.
"""

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class AssistantStatus(BaseModel):
    """Asistanın yapılandırma durumu.

    Değerler .env dosyasından okunur. Anahtarın kendisi hiçbir zaman
    döndürülmez; yalnızca tanımlı olup olmadığı bildirilir.
    """

    enabled: bool = Field(
        description="ASSISTANT_ENABLED ortam değişkeni.", examples=[False]
    )
    provider: Optional[str] = Field(
        default=None,
        description="LLM_PROVIDER ortam değişkeni. Boşsa sağlayıcı seçilmemiştir.",
        examples=[None],
    )
    model: Optional[str] = Field(
        default=None, description="LLM_MODEL ortam değişkeni.", examples=[None]
    )
    base_url: Optional[str] = Field(
        default=None, description="LLM_BASE_URL ortam değişkeni.", examples=[None]
    )
    api_key_configured: bool = Field(
        description="LLM_API_KEY tanımlı mı? Anahtarın kendisi asla döndürülmez.",
        examples=[False],
    )
    message: str = Field(
        examples=[
            "Asistan devre dışı. Hiçbir dil modeli bağlı değil; sistem cevap üretmez."
        ]
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
