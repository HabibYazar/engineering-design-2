"""Yerel Ollama sağlayıcısı.

Model kullanıcının kendi makinesinde çalışır. Bu dosya YALNIZCA
`settings.OLLAMA_BASE_URL` adresine istek gönderir; hiçbir bulut servisine
(OpenAI, Gemini, Claude vb.) çağrı yapılmaz ve hiçbir API anahtarı kullanılmaz.

SORUMLULUK SINIRI
-----------------
Bu sınıf modelle konuşur. Ne soracağına, hangi sistem yönergesini
kullanacağına ve konuşmanın nasıl saklanacağına karar VERMEZ — o iş
`chat_service` katmanına aittir. Router da doğrudan buraya değil, servise
konuşur. Böylece sağlayıcı değişirse (ör. başka bir yerel çalıştırıcı)
yalnızca bu dosya değişir.

DÜŞÜNME METNİ
-------------
Qwen ailesi modeller cevaptan önce bir muhakeme bloğu üretebilir. Ollama bunu
iki farklı biçimde döndürebilir: ayrı bir `thinking` alanı olarak veya cevap
metninin içinde `<think>...</think>` etiketleriyle. İkisi de kullanıcıya
gösterilmez; `split_thinking()` her ikisini de ayıklar.
"""

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Dict, Iterator, List, Optional, Tuple

import httpx

from app.core.config import settings
from app.services.assistant.base import AssistantProvider
from app.services.assistant.schemas import ContextItem

logger = logging.getLogger(__name__)

# Kullanıcıya gösterilecek hata metinleri. Teknik ayrıntı (yığın izi, adres)
# kullanıcıya değil günlüğe yazılır.
ERROR_SERVICE_UNREACHABLE = (
    "Yerel yapay zekâ servisine ulaşılamıyor. Ollama'nın çalıştığından emin olun."
)
ERROR_MODEL_MISSING_TEMPLATE = (
    "{model} modeli bulunamadı. ollama pull {model} komutuyla modeli kurun."
)
ERROR_TIMEOUT = (
    "Yerel model yanıt vermedi (zaman aşımı). Model ilk çalıştırmada belleğe "
    "yüklenirken uzun sürebilir; lütfen tekrar deneyin."
)
ERROR_INVALID_RESPONSE = (
    "Yerel modelden geçerli bir yanıt alınamadı. Ollama günlüklerini kontrol edin."
)

# <think>…</think> ve <thinking>…</thinking> bloklarını yakalar.
THINK_BLOCK = re.compile(r"<think(?:ing)?>.*?</think(?:ing)?>", re.DOTALL | re.IGNORECASE)
# Kapanmamış açılış etiketi: model yarıda kesilmişse geri kalan her şey düşünmedir.
UNCLOSED_THINK = re.compile(r"<think(?:ing)?>.*\Z", re.DOTALL | re.IGNORECASE)


def _effective_timeout() -> int:
    """Geçerli zaman aşımı süresi.

    Canlı testler ASSISTANT_LIVE_TIMEOUT_SECONDS ortam değişkeniyle bu değeri
    yükseltebilir; uygulamanın varsayılanı config'te kalır. Bir kullanıcıyı
    beş dakika bekletmek kabul edilemez, ama canlı testin modeli diskten
    yüklemesi için o kadar süre gerekebiliyor.
    """
    raw = os.getenv("ASSISTANT_LIVE_TIMEOUT_SECONDS", "").strip()
    if raw:
        try:
            value = int(raw)
            if value > 0:
                return value
        except ValueError:
            logger.warning("ASSISTANT_LIVE_TIMEOUT_SECONDS sayi degil: %r", raw)
    return settings.OLLAMA_TIMEOUT_SECONDS


def _local_client(timeout: float) -> httpx.Client:
    """Yerel Ollama için HTTP istemcisi üretir.

    `trust_env=False` bilinçlidir: makinede HTTP_PROXY / ALL_PROXY tanımlıysa
    httpx varsayılan olarak onu kullanır ve 127.0.0.1'e giden istek bile
    proxy'ye yönlenir. Bu hem bağlantıyı kırar hem de "model yereldir, veri
    dışarı çıkmaz" güvencesini bozardı.
    """
    return httpx.Client(timeout=timeout, trust_env=False)


class AssistantProviderError(RuntimeError):
    """Sağlayıcı katmanının kullanıcıya gösterilebilir hatası.

    `user_message` doğrudan arayüze yazılabilir; `kind` arayüzün hangi durumu
    göstereceğine karar vermesini sağlar.
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

    # Yarıda kesilmiş bir düşünme bloğu kalmışsa onu da at.
    unclosed = UNCLOSED_THINK.search(visible)
    if unclosed:
        thinking_parts.append(unclosed.group(0))
        visible = UNCLOSED_THINK.sub("", visible)

    return visible.strip(), "\n".join(thinking_parts).strip()


def _model_matches(installed: str, wanted: str) -> bool:
    """Kurulu model adı istenen modelle eşleşiyor mu?

    Ollama etiketsiz çekilen modelleri `ad:latest` olarak listeler. Kullanıcı
    `qwen3.5:9b` yazdıysa tam eşleşme aranır; `qwen3.5` yazdıysa etiketi
    yok sayarız.
    """
    if installed == wanted:
        return True
    if ":" not in wanted and installed.split(":")[0] == wanted:
        return True
    return False


class OllamaProvider(AssistantProvider):
    """Yerel Ollama sunucusuyla konuşan sağlayıcı."""

    name = "ollama"

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        think: Optional[bool] = None,
        keep_alive: Optional[str] = None,
        context_length: Optional[int] = None,
    ) -> None:
        # Ayarlar tek merkezden gelir; testlerde açıkça geçilebilsin diye
        # parametre olarak da kabul edilir.
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model = model or settings.OLLAMA_MODEL
        # Canlı testler ASSISTANT_LIVE_TIMEOUT_SECONDS ile bu değeri
        # yükseltebilir; uygulamanın kendi sınırı config'te kalır.
        self.timeout_seconds = timeout_seconds or _effective_timeout()
        self.think = settings.OLLAMA_THINK if think is None else think
        self.keep_alive = keep_alive or settings.OLLAMA_KEEP_ALIVE
        self.context_length = context_length or settings.OLLAMA_CONTEXT_LENGTH

    # ------------------------------------------------------------------
    # Durum sorgulama
    # ------------------------------------------------------------------

    def list_models(self) -> List[str]:
        """Ollama'da kurulu model adlarını döndürür.

        Servise ulaşılamazsa AssistantProviderError fırlatır; sessizce boş
        liste döndürmek "model yok" ile "servis kapalı" durumunu birbirine
        karıştırırdı.
        """
        try:
            # Durum sorgusu kısa tutulur: kullanıcı ekran açılışında 120 saniye
            # bekletilemez.
            with _local_client(5.0) as client:
                response = client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                payload = response.json()
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
            logger.warning("Ollama servisine ulasilamadi: %s", exc.__class__.__name__)
            raise AssistantProviderError(ERROR_SERVICE_UNREACHABLE, kind="service_down") from exc
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Ollama model listesi okunamadi: %s", exc.__class__.__name__)
            raise AssistantProviderError(ERROR_INVALID_RESPONSE, kind="invalid_response") from exc

        models = payload.get("models") or []
        return [m.get("name", "") for m in models if isinstance(m, dict) and m.get("name")]

    def health(self) -> ProviderHealth:
        """Servis ayakta mı, istenen model kurulu mu?

        Bu metot HATA FIRLATMAZ. Ekran açılışında çağrıldığı için Ollama kapalı
        olsa bile uygulama çalışmaya devam etmelidir.
        """
        try:
            installed = self.list_models()
        except AssistantProviderError as exc:
            return ProviderHealth(
                service_available=False,
                model_available=False,
                installed_models=(),
                message=exc.user_message,
            )
        except Exception:  # noqa: BLE001
            # Beklenmeyen bir hata (ör. eksik bir HTTP eklentisi, bozuk proxy
            # yapılandırması) durum ekranını çökertmemeli. Ayrıntı günlüğe
            # yazılır, kullanıcıya sakin bir mesaj gösterilir.
            logger.exception("Ollama durum sorgusu beklenmedik sekilde basarisiz oldu")
            return ProviderHealth(
                service_available=False,
                model_available=False,
                installed_models=(),
                message=ERROR_SERVICE_UNREACHABLE,
            )

        model_available = any(_model_matches(name, self.model) for name in installed)
        if model_available:
            message = f"Yapay zekâ hazır — {self.model}"
        else:
            message = ERROR_MODEL_MISSING_TEMPLATE.format(model=self.model)

        return ProviderHealth(
            service_available=True,
            model_available=model_available,
            installed_models=tuple(installed),
            message=message,
        )

    def is_available(self) -> bool:
        """AssistantProvider sözleşmesi: sağlayıcı gerçekten kullanılabilir mi?"""
        return self.health().ready

    # ------------------------------------------------------------------
    # Sohbet
    # ------------------------------------------------------------------

    def _payload(
        self,
        messages: List[Dict[str, str]],
        stream: bool,
        tools: Optional[List[Dict]] = None,
    ) -> Dict:
        payload: Dict = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            # think=False: muhakeme üretimi kapalı. Hesabı araçlar yapıyor,
            # muhakeme metni kullanıcıya zaten gösterilmiyor ve ilk cevabı
            # dakikalarca geciktiriyordu.
            "think": self.think,
            # Model bellekte kalsın; her istekte yeniden yüklenmesi canlı
            # testlerde 120 saniyelik zaman aşımının başlıca sebebiydi.
            "keep_alive": self.keep_alive,
            "options": {
                "temperature": settings.OLLAMA_TEMPERATURE,
                "num_ctx": self.context_length,
            },
        }
        # Araç listesi yalnızca doluysa gönderilir; boş liste bazı model
        # sürümlerinde "araç kullanmalısın" sinyali gibi yorumlanabiliyor.
        if tools:
            payload["tools"] = tools
        return payload

    def warm_up(self) -> bool:
        """Modeli belleğe yükler. Başarısız olursa sessizce False döner.

        İlk gerçek soru sorulduğunda model diskten yükleniyor ve 9B'lik bir
        model için bu tek başına dakikalar sürebiliyor. Kısa bir ısınma
        isteği bu maliyeti kullanıcının sorusundan önce ödetir.
        """
        try:
            with _local_client(self.timeout_seconds) as client:
                response = client.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": "Merhaba"}],
                        "stream": False,
                        "think": False,
                        "keep_alive": self.keep_alive,
                        "options": {"temperature": 0, "num_predict": 1},
                    },
                )
                return response.status_code == 200
        except Exception:  # noqa: BLE001 - ısınma başarısızlığı testi durdurmamalı
            logger.warning("Model isitma istegi basarisiz oldu")
            return False

    def _raise_for_status(self, response: httpx.Response) -> None:
        """HTTP hatalarını kullanıcıya anlaşılır hataya çevirir."""
        if response.status_code == 404:
            # Ollama kurulu olmayan model için 404 döner.
            raise AssistantProviderError(
                ERROR_MODEL_MISSING_TEMPLATE.format(model=self.model), kind="model_missing"
            )
        if response.status_code >= 400:
            logger.warning("Ollama %s dondu", response.status_code)
            raise AssistantProviderError(ERROR_INVALID_RESPONSE, kind="invalid_response")

    def chat(
        self, messages: List[Dict[str, str]], tools: Optional[List[Dict]] = None
    ) -> Tuple[str, str]:
        """Tek seferde cevap alır. (görünen cevap, düşünme metni) döndürür."""
        _, visible, thinking = self.chat_with_tools(messages, tools)
        return visible, thinking

    def chat_with_tools(
        self, messages: List[Dict[str, str]], tools: Optional[List[Dict]] = None
    ) -> Tuple[List[Dict], str, str]:
        """Araç çağrısı da döndürebilen sohbet.

        Dönen üçlü: (araç çağrıları, görünen cevap, düşünme metni).
        Model araç çağırdığında görünen cevap boş olabilir; bu bir hata
        değildir, bu yüzden `chat()`ten farklı olarak boş metin kabul edilir.
        """
        try:
            with _local_client(self.timeout_seconds) as client:
                response = client.post(
                    f"{self.base_url}/api/chat",
                    json=self._payload(messages, stream=False, tools=tools),
                )
                self._raise_for_status(response)
                payload = response.json()
        except AssistantProviderError:
            raise
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            logger.warning("Ollama baglanti hatasi: %s", exc.__class__.__name__)
            raise AssistantProviderError(ERROR_SERVICE_UNREACHABLE, kind="service_down") from exc
        except (httpx.ReadTimeout, httpx.TimeoutException) as exc:
            logger.warning("Ollama zaman asimi (%s sn)", self.timeout_seconds)
            raise AssistantProviderError(ERROR_TIMEOUT, kind="timeout") from exc
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Ollama cevabi okunamadi: %s", exc.__class__.__name__)
            raise AssistantProviderError(ERROR_INVALID_RESPONSE, kind="invalid_response") from exc

        return self._extract_with_tools(payload)

    def _extract_with_tools(self, payload: Dict) -> Tuple[List[Dict], str, str]:
        """Ollama cevabından araç çağrılarını, görünen metni ve muhakemeyi ayırır."""
        if not isinstance(payload, dict):
            raise AssistantProviderError(ERROR_INVALID_RESPONSE, kind="invalid_response")

        message = payload.get("message")
        if not isinstance(message, dict):
            raise AssistantProviderError(ERROR_INVALID_RESPONSE, kind="invalid_response")

        content = message.get("content") or ""
        # Ollama'nın yeni sürümleri muhakemeyi ayrı alanda döndürebiliyor.
        thinking_field = message.get("thinking") or ""

        visible, inline_thinking = split_thinking(content)
        thinking = "\n".join(part for part in (thinking_field, inline_thinking) if part)

        tool_calls = _parse_tool_calls(message.get("tool_calls"))

        if not visible and not tool_calls:
            # Ne cevap ne araç çağrısı: kullanıcıya boş balon göstermek yerine
            # kontrollü hata döndürülür.
            raise AssistantProviderError(ERROR_INVALID_RESPONSE, kind="invalid_response")

        return tool_calls, visible, thinking

    def _extract(self, payload: Dict) -> Tuple[str, str]:
        """Geriye uyum: yalnızca metin döndürür."""
        _, visible, thinking = self._extract_with_tools(payload)
        if not visible:
            raise AssistantProviderError(ERROR_INVALID_RESPONSE, kind="invalid_response")
        return visible, thinking

    def stream_chat(self, messages: List[Dict[str, str]]) -> Iterator[str]:
        """Cevabı parça parça üretir; düşünme metni parçaları atlanır.

        Akış sırasında `<think>` bloğu gelirse blok bitene kadar hiçbir şey
        yayınlanmaz. Böylece kullanıcı ekranında muhakeme metni görünmez.
        """
        buffer = ""
        inside_think = False

        try:
            with _local_client(self.timeout_seconds) as client:
                with client.stream(
                    "POST", f"{self.base_url}/api/chat", json=self._payload(messages, stream=True)
                ) as response:
                    self._raise_for_status(response)
                    for line in response.iter_lines():
                        if not line:
                            continue
                        try:
                            chunk = json.loads(line)
                        except ValueError:
                            continue
                        message = chunk.get("message") or {}
                        piece = message.get("content") or ""
                        if not piece:
                            continue

                        buffer += piece
                        emit, buffer, inside_think = _drain(buffer, inside_think)
                        if emit:
                            yield emit
        except AssistantProviderError:
            raise
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise AssistantProviderError(ERROR_SERVICE_UNREACHABLE, kind="service_down") from exc
        except (httpx.ReadTimeout, httpx.TimeoutException) as exc:
            raise AssistantProviderError(ERROR_TIMEOUT, kind="timeout") from exc
        except httpx.HTTPError as exc:
            raise AssistantProviderError(ERROR_INVALID_RESPONSE, kind="invalid_response") from exc

    # ------------------------------------------------------------------
    # Eski sözleşme (bağlam tabanlı üretim)
    # ------------------------------------------------------------------

    def generate(self, question: str, context: List[ContextItem]) -> str:
        """AssistantProvider arayüzünün eski imzası.

        Bağlam aktarımı bir sonraki aşamada (araç entegrasyonu) devreye
        girecek; şu an yalnızca soru gönderilir.
        """
        visible, _ = self.chat([{"role": "user", "content": question}])
        return visible


def _parse_tool_calls(raw) -> List[Dict]:
    """Ollama'nın döndürdüğü araç çağrılarını sadeleştirir.

    Beklenen biçim:
        [{"function": {"name": "...", "arguments": {...}}}]

    Bazı model sürümleri `arguments` alanını JSON METNİ olarak döndürüyor;
    ikisi de kabul edilir. Ayrıştırılamayan bir çağrı sessizce atılmaz —
    boş sözlükle geçirilir ki doğrulama katmanı hatayı modele bildirsin.
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
        calls.append({"name": str(name), "arguments": arguments})
    return calls


# Akış filtresi: <think> bloğu içindeyken hiçbir şey yayınlanmaz.
_OPEN_TAG = re.compile(r"<think(?:ing)?>", re.IGNORECASE)
_CLOSE_TAG = re.compile(r"</think(?:ing)?>", re.IGNORECASE)
# Etiket parça parça gelebilir ("<thi" + "nk>"). Sondaki yarım etiket adayı
# yayınlanmadan bekletilir.
_PARTIAL_TAG = re.compile(r"<[a-z/]{0,8}$", re.IGNORECASE)


def _drain(buffer: str, inside_think: bool) -> Tuple[str, str, bool]:
    """Tampondan yayınlanabilecek metni ayırır.

    Döndürdüğü üçlü: (yayınlanacak metin, tamponda kalan, hâlâ düşünme içinde mi).
    """
    output = ""

    while buffer:
        if inside_think:
            match = _CLOSE_TAG.search(buffer)
            if not match:
                # Blok bitmedi: her şeyi at, hiçbir şey yayınlama.
                return output, "", True
            buffer = buffer[match.end() :]
            inside_think = False
            continue

        match = _OPEN_TAG.search(buffer)
        if match:
            output += buffer[: match.start()]
            buffer = buffer[match.end() :]
            inside_think = True
            continue

        # Açılış etiketi yok. Sonda yarım kalmış bir etiket olabilir; onu bekletiriz.
        partial = _PARTIAL_TAG.search(buffer)
        if partial:
            output += buffer[: partial.start()]
            return output, buffer[partial.start() :], False

        output += buffer
        return output, "", False

    return output, "", inside_think
