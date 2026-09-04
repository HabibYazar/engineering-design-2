"""Sağlayıcı susunca istek 502 ile ölmez.

ÖLÇÜLEN ARIZA
-------------
`/api/assistant/chat` şu gövdeyle 502 dönüyordu:

    "Modelden geçerli bir yanıt alınamadı. Sunucu günlüklerini kontrol edin."

Sebep, `chat_service.answer()` içindeki geri düşüş kapısının
`rate_limited or timed_out` koşuluna bağlı olmasıydı. Model zaman aşımına
uğramadan, kotayı doldurmadan, yalnızca BOŞ bir metin döndürdüğünde kapı
kapalı kalıyor, `visible` boş kalıyor ve `AssistantProviderError(
kind="invalid_response")` fırlıyordu; router bu türü 502'ye eşliyordu.

Bunun ağırlığı şurada: veri araçları çalışmıştı. Veritabanından satırlar
okunmuştu. Kullanıcı, kendi verisi elde dururken "Bad Gateway" görüyordu.
Sağlayıcının susması bir AĞ GEÇİDİ ARIZASI DEĞİLDİR.

Buradaki testler tek bir kuralı korur:

    ARAÇLAR ÇALIŞTIYSA CEVAP VERİLİR. HİÇBİR SEBEPLE 502 DÖNÜLMEZ.

ve sebepleri tek tek dolaşır: boş metin, yalnızca araç çağrısı içeren
yanıt, bozuk/ayrıştırılamayan gövde, sağlayıcı istisnası, zaman aşımı,
kota. Elde hiçbir şey yokken bile kontrollü bir 200 beklenir.

GERÇEK GEMINI İSTEĞİ YAPILMAZ; sağlayıcı baştan sona sahtedir.
"""

from __future__ import annotations

import pytest

from app.services.assistant import chat_service, query_policy
from app.services.assistant.provider_shared import (
    AssistantProviderError, ProviderHealth)


# Test veritabanında GERÇEKTEN satır döndüren bir kaynak seçilir.
# Boş dönen bir kaynakla çalışmak, "araç başarılı ama model sustu"
# durumunu hiç kurmazdı; test yeşil görünüp asıl arızayı kaçırırdı.
SORGU = ("query_canonical_data", {"source": "students", "limit": 20})

SORU = "Öğrenci kayıtlarının genel durumu nedir"

# Kullanıcıya asla görünmemesi gereken teknik cümle.
YASAK = "Modelden geçerli bir yanıt alınamadı"


class SahteSaat:
    def __init__(self): self.simdi = 1000.0
    def __call__(self): return self.simdi
    def ilerlet(self, s): self.simdi += s


class SahteSaglayici:
    """Planı sırayla uygular. Her adım bir "sağlayıcı davranışı"dır.

    Davranışlar gerçek arıza biçimlerini taklit eder:
      ("tool", ...)   → araç çağrısı döndür
      ("text", ...)   → normal metin döndür
      ("bos", None)   → BOŞ metin döndür (zaman aşımı yok, kota yok)
      ("hata", kind)  → AssistantProviderError fırlat
    """

    name = model = "sahte"
    timeout_seconds = 120.0

    def __init__(self, saat, plan):
        self.saat, self.plan, self.istek = saat, list(plan), 0

    def etkin_model(self): return "sahte"
    def resolve_model(self): return "sahte"
    def is_available(self): return True
    def health(self): return ProviderHealth(True, True, (), "ok")
    def warm_up(self): return None
    def chat(self, m, tools=None): return "tamam", ""
    def stream_chat(self, m): yield "ok"

    def chat_with_tools(self, messages, tools=None):
        self.istek += 1
        if not self.plan:
            # Plan bittiyse model susmaya devam ediyor demektir.
            return [], "", ""
        sure, davranis = self.plan.pop(0)
        if sure > self.timeout_seconds:
            self.saat.ilerlet(self.timeout_seconds)
            raise AssistantProviderError("zaman asimi", kind="timeout")
        self.saat.ilerlet(sure)
        tur, yuk = davranis
        if tur == "tool":
            if tools is None:
                return [], "Eldeki verilerle cevap.", ""
            return [{"name": yuk[0], "arguments": yuk[1], "id": "c1"}], "", ""
        if tur == "bos":
            return [], "", ""
        if tur == "hata":
            raise AssistantProviderError("bozuk gövde", kind=yuk)
        return [], yuk, ""


@pytest.fixture
def kos(monkeypatch, db_session):
    saat = SahteSaat()
    monkeypatch.setattr(chat_service.time, "monotonic", saat)

    def _kos(plan, soru=SORU):
        s = SahteSaglayici(saat, plan)
        monkeypatch.setattr(chat_service, "get_provider", lambda: s)
        return s, chat_service.answer(soru, db=db_session)
    return _kos


def _cevap_saglikli(sonuc):
    """Yanıt sözleşmesi: arayüzün okuduğu alanlar None olmamalı."""
    assert isinstance(sonuc.get("answer"), str) and sonuc["answer"].strip()
    assert YASAK not in sonuc["answer"]
    assert sonuc.get("data_sources") is not None
    assert sonuc.get("used_tools") is not None
    assert sonuc.get("data_source")


# ---------------------------------------------------------------- 1
def test_arac_calisti_model_bos_dondu_istisna_yok(kos):
    """ASIL ARIZA. Araç başarılı, model boş metin: 502 değil, cevap."""
    _, sonuc = kos([(2.0, ("tool", SORGU)), (3.0, ("bos", None))])
    _cevap_saglikli(sonuc)
    assert sonuc["data_source"] == query_policy.SOURCE_INSTITUTIONAL


# ---------------------------------------------------------------- 2
def test_bos_cevapta_veri_ozeti_gosterilir(kos):
    """Boş cevabın yerine ham satır değil, deterministik özet konur."""
    _, sonuc = kos([(2.0, ("tool", SORGU)), (3.0, ("bos", None))])
    metin = sonuc["answer"]
    assert "doğrudan sistem kayıtlarından" in metin
    # Özet istatistiktir; ham alan dökümü değil.
    assert "kayıt" in metin


# ---------------------------------------------------------------- 3
def test_model_sadece_arac_cagirip_susarsa_cevap_verilir(kos):
    """Yalnızca araç çağrısı içeren, metni olmayan yanıt da kapıdan geçer."""
    _, sonuc = kos([(2.0, ("tool", SORGU)), (2.0, ("tool", SORGU)),
                    (2.0, ("bos", None))])
    _cevap_saglikli(sonuc)


# ---------------------------------------------------------------- 4
def test_bozuk_govde_502_uretmez(kos):
    """`invalid_response` sağlayıcıdan gelse bile yukarı fırlatılmaz."""
    _, sonuc = kos([(2.0, ("tool", SORGU)),
                    (2.0, ("hata", "invalid_response"))])
    _cevap_saglikli(sonuc)


# ---------------------------------------------------------------- 5
def test_veri_yokken_bozuk_govde_de_502_uretmez(kos):
    """Elde araç sonucu YOKKEN bile 502 değil, kontrollü cevap döner."""
    _, sonuc = kos([(2.0, ("hata", "invalid_response"))])
    _cevap_saglikli(sonuc)
    assert "daha dar bir kapsamla" in sonuc["answer"]


# ---------------------------------------------------------------- 6
def test_zaman_asiminda_da_ayni_kapi_calisir(kos):
    """Eski davranış korunuyor: zaman aşımı da aynı kapıdan geçer."""
    _, sonuc = kos([(2.0, ("tool", SORGU)), (999.0, ("text", "gelmeyecek"))])
    _cevap_saglikli(sonuc)
    assert sonuc["data_source"] == query_policy.SOURCE_INSTITUTIONAL


# ---------------------------------------------------------------- 7
def test_kotada_da_ayni_kapi_calisir(kos):
    _, sonuc = kos([(2.0, ("tool", SORGU)), (2.0, ("hata", "rate_limit"))])
    _cevap_saglikli(sonuc)


# ---------------------------------------------------------------- 8
def test_normal_cevap_bozulmadi(kos):
    """Düzeltme, çalışan yolu değiştirmemeli."""
    _, sonuc = kos([(2.0, ("tool", SORGU)), (3.0, ("text", "Normal yorum."))])
    assert "Normal yorum." in sonuc["answer"]
    assert "doğrudan sistem kayıtlarından" not in sonuc["answer"]


# ---------------------------------------------------------------- 9
def test_uctan_uca_http_200(monkeypatch, client):
    """Router seviyesinde: model sussa da istemci 200 alır."""
    saat = SahteSaat()
    monkeypatch.setattr(chat_service.time, "monotonic", saat)
    saglayici = SahteSaglayici(saat, [(2.0, ("tool", SORGU)),
                                      (3.0, ("bos", None))])
    monkeypatch.setattr(chat_service, "get_provider", lambda: saglayici)

    yanit = client.post("/api/assistant/chat", json={"message": SORU})

    assert yanit.status_code == 200, yanit.text
    govde = yanit.json()
    assert govde["answer"].strip()
    assert YASAK not in govde["answer"]
    # Arayüzün okuduğu alanlar yok/None olmamalı.
    assert govde.get("data_sources") is not None
    assert govde.get("charts") is not None


def test_gercek_gemini_istegi_yapilmadi(kos):
    """Bu dosyadaki hiçbir test ağa çıkmaz; sağlayıcı sahtedir."""
    s, _ = kos([(2.0, ("tool", SORGU)), (2.0, ("bos", None))])
    assert isinstance(s, SahteSaglayici)
    assert s.istek > 0
