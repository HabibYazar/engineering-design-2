"""Araç kayıt defteri.

Modelin çağırabileceği her şey burada tanımlıdır. Kayıt defterinde olmayan
bir ad çalıştırılmaz — modelin ürettiği metin asla bir fonksiyon seçimine
dönüşemez.

GÜVENLİK SINIRLARI
------------------
1. Model SQL yazamaz. Araç girdileri Pydantic modelleridir; serbest metin
   alanları yalnızca birim ADIDIR ve `entity_resolver` üzerinden gerçek
   kayıtlarla eşleştirilir, sorguya gömülmez.
2. Model endpoint URL'si üretemez. Araçlar servis fonksiyonlarını doğrudan
   çağırır; HTTP katmanı devrede değildir.
3. Model hesap yapmaz. Bütün sayılar mevcut servis ve senaryo motorundan
   gelir; model yalnızca gelen sonucu cümleye döker.
4. Her aracın çıktısı bir Pydantic modeliyle doğrulanır. Doğrulamadan geçmeyen
   sonuç modele GÖNDERİLMEZ.
5. Her aracın kendi süre sınırı vardır; ayrıca döngünün toplam süre sınırı
   `chat_service` tarafında uygulanır.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Type

from pydantic import BaseModel
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class ToolExecutionError(Exception):
    """Araç çalıştırılamadı. Mesaj modele ve kullanıcıya gösterilebilir."""

    def __init__(self, message: str, kind: str = "error") -> None:
        super().__init__(message)
        self.message = message
        self.kind = kind


@dataclass(frozen=True)
class ToolDefinition:
    """Bir aracın tam tanımı."""

    name: str
    description: str
    input_model: Type[BaseModel]
    output_model: Type[BaseModel]
    handler: Callable[[Session, BaseModel], BaseModel]
    #: Bu aracın tek başına aşamayacağı süre (saniye).
    timeout_seconds: float
    #: Aracı çalıştırmak için gereken yetki. Oturum yetkisi yoksa çalışmaz.
    required_permission: Optional[str]
    #: Kullanıcıya gösterilecek Türkçe veri kaynağı adı. Teknik araç adı değil.
    data_source: str

    def json_schema(self) -> Dict[str, Any]:
        """Ollama'nın beklediği araç tanımı."""
        schema = self.input_model.model_json_schema()
        # Ollama/OpenAI araç şemasında $defs ve title alanları gereksiz yer
        # kaplıyor; modelin bağlam penceresi boşa harcanmasın.
        schema.pop("title", None)
        for prop in schema.get("properties", {}).values():
            prop.pop("title", None)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": schema,
            },
        }


class ToolRegistry:
    """Araçların tek kayıt noktası."""

    def __init__(self) -> None:
        self._tools: Dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> ToolDefinition:
        if tool.name in self._tools:
            raise ValueError(f"Araç zaten kayıtlı: {tool.name}")
        self._tools[tool.name] = tool
        return tool

    def get(self, name: str) -> ToolDefinition:
        """Adı doğrular. Kayıtlı değilse çalıştırmaz."""
        tool = self._tools.get(name)
        if tool is None:
            raise ToolExecutionError(
                f"'{name}' adında bir araç yok. Kullanılabilir araçlar: "
                f"{', '.join(sorted(self._tools))}.",
                kind="unknown_tool",
            )
        return tool

    def has(self, name: str) -> bool:
        return name in self._tools

    def names(self) -> List[str]:
        return sorted(self._tools)

    def all(self) -> List[ToolDefinition]:
        return [self._tools[name] for name in sorted(self._tools)]

    def schemas(self, permissions: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Modele gönderilecek araç tanımları.

        Yetkisi olmayan araç modele hiç TANITILMAZ; model çağıramayacağı bir
        aracı deneyip hata almaz.
        """
        return [
            tool.json_schema()
            for tool in self.all()
            if _is_allowed(tool, permissions)
        ]

    def data_sources(self, tool_names: List[str]) -> List[str]:
        """Kullanılan araçların Türkçe veri kaynağı adları (tekrarsız, sıralı)."""
        seen: List[str] = []
        for name in tool_names:
            tool = self._tools.get(name)
            if tool and tool.data_source not in seen:
                seen.append(tool.data_source)
        return seen


def _is_allowed(tool: ToolDefinition, permissions: Optional[List[str]]) -> bool:
    """Yetki kontrolü.

    permissions=None → kontrol devre dışı (sunucu içi çağrı).
    Aracın gereksinimi None ise herkese açıktır.
    """
    if tool.required_permission is None:
        return True
    if permissions is None:
        return True
    return tool.required_permission in permissions


# Uygulama genelinde tek kayıt defteri.
registry = ToolRegistry()
