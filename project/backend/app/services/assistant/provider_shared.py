"""Sağlayıcıdan bağımsız ortak parçalar.

NEDEN AYRI BİR DOSYA
--------------------
Bu tanımlar (hata sınıfı, sağlık kaydı, düşünme metni ayıklayıcısı, araç
çağrısı ayrıştırıcısı) yerel sağlayıcı modülünde doğmuştu ve oradan
`chat_service` ile router'lara yayılmıştı. Sağlayıcı buluta taşınırken bu
durum iki kötü seçenek bırakıyordu: ya yeni modül eski modülden
import edecekti (emekli edilen bileşene bağımlılık), ya da tanımlar
kopyalanacaktı (iki ayrı doğruluk kaynağı).

Üçüncüsü seçildi: ortak parçalar buraya taşındı ve her sağlayıcı
buradan içe aktarır — tek doğruluk kaynağı.

HATA METİNLERİ SAĞLAYICIYA ÖZGÜDÜR
----------------------------------
Burada yalnızca GENEL metinler durur. "Servisi başlatın" gibi bir
öneri, bulut kullanan bir kurulumda kullanıcıyı yanlış yere yönlendirir;
o yüzden sağlayıcıya özgü metinler kendi modülünde tanımlanır.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Dict, List, Tuple

# <think>…</think> ve <thinking>…</thinking> bloklarını yakalar.
THINK_BLOCK = re.compile(r"<think(?:ing)?>.*?</think(?:ing)?>", re.DOTALL | re.IGNORECASE)
# Kapanmamış açılış etiketi: model yarıda kesilmişse geri kalan her şey
# düşünmedir.
UNCLOSED_THINK = re.compile(r"<think(?:ing)?>.*\Z", re.DOTALL | re.IGNORECASE)


class AssistantProviderError(RuntimeError):
    """Sağlayıcı katmanının kullanıcıya gösterilebilir hatası.

    `user_message` doğrudan arayüze yazılabilir; `kind` arayüzün hangi
    durumu göstereceğine karar vermesini sağlar.
    """

    def __init__(self, user_message: str, kind: str = "error") -> None:
        super().__init__(user_message)
        self.user_message = user_message
        self.kind = kind


@dataclass(frozen=True)
class ProviderHealth:
    """Sağlayıcının o anki durumu."""

    service_available: bool
    model_available: bool
    installed_models: Tuple[str, ...]
    message: str

    @property
    def ready(self) -> bool:
        return self.service_available and self.model_available


def split_thinking(text: str) -> Tuple[str, str]:
    """Metni (görünen cevap, düşünme metni) olarak ayırır.

    Düşünme metni yalnızca günlük ve hata ayıklama içindir; API cevabına
    ve arayüze KONULMAZ.
    """
    if not text:
        return "", ""

    thinking_parts = THINK_BLOCK.findall(text)
    visible = THINK_BLOCK.sub("", text)

    unclosed = UNCLOSED_THINK.search(visible)
    if unclosed:
        thinking_parts.append(unclosed.group(0))
        visible = UNCLOSED_THINK.sub("", visible)

    return visible.strip(), "\n".join(thinking_parts).strip()


def parse_tool_calls(raw) -> List[Dict]:
    """Araç çağrılarını sağlayıcıdan bağımsız biçime sadeleştirir.

    Kabul edilen giriş:
        [{"function": {"name": "...", "arguments": {...} | "json metni"}}]

    Bazı sağlayıcılar `arguments` alanını sözlük, OpenAI uyumlu uçlar JSON METNİ
    olarak döndürür; ikisi de kabul edilir.

    Ayrıştırılamayan bir çağrı SESSİZCE ATILMAZ — boş argüman sözlüğüyle
    geçirilir ki doğrulama katmanı hatayı modele bildirsin ve model
    düzeltme şansı bulsun. Sessizce atmak, modelin aracı çağırdığını
    sanıp cevapsız kalmasına yol açardı.
    """
    if not isinstance(raw, list):
        return []

    calls: List[Dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        function = item.get("function") or {}
        name = function.get("name")
        if not name:
            continue
        arguments = function.get("arguments")
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except ValueError:
                arguments = {}
        if not isinstance(arguments, dict):
            arguments = {}
        cagri: Dict = {"name": str(name), "arguments": arguments}
        # ÇAĞRI KİMLİĞİ KORUNUR.
        # --------------------------------------------------------------
        # OpenAI uyumlu sağlayıcılar, bir araç sonucunu geri gönderirken
        # hangi çağrıya ait olduğunu `tool_call_id` ile ister. Kimlik
        # burada atılırsa döngü ikinci turda 400 alır ve kullanıcı
        # yalnızca "geçerli yanıt alınamadı" görür.
        if item.get("id"):
            cagri["id"] = str(item["id"])
        calls.append(cagri)
    return calls
