"""Grounding öncelikli, zorunlu değil — model metni artık silinmiyor.

ÖLÇÜLEN ARIZA
-------------
Canlı logda şu ikili görülüyordu:

    "Kurumsal soru backend bağlamı/araç sonucu olmadan cevaplandı;
     model metni reddedildi."
    "[AI TURN ...] MODEL METNİ YOK (empty_or_invalid_response);
     fallback=kontrollu_mesaj"

İkinci satır modelin sustuğunu ima ediyordu. Oysa model KONUŞMUŞTU —
metni birinci satırda backend tarafından silinmişti. Kullanıcı, Gemini'nin
yazdığı geçerli bir cevabı hiç görmeden "güvenilir yanıt üretilemedi"
mesajıyla karşılaşıyordu.

YENİ SÖZLEŞME
-------------
    grounded cevap  >  yalnızca-model cevabı  >  hata

Retrieval başarısızlığı bir cevabı yok etme sebebi değildir. RAG hâlâ
birinci tercihtir; yalnızca "veri bulunamadı" durumu artık sessizliğe
değil modelin kendi cevabına düşer.

Model GERÇEKTEN sustuğunda ise iki ek deneme yapılır (araçsız
finalizasyon, sonra sadeleştirilmiş istem); ancak ondan sonra
deterministik geri düşüşe inilir.
"""

from __future__ import annotations

from typing import List

import pytest

from app.services.assistant import chat_service, query_policy
from app.services.assistant.provider_shared import (
    AssistantProviderError, ProviderHealth)

#: Kullanıcının retrieval hatası yüzünden ASLA görmemesi gereken cümle.
TEKNIK_MESAJ = "güvenilir bir yanıt üretilemedi"

#: Grounding olmadan cevaplanacak soru — veritabanında karşılığı yok.
GROUNDINGSIZ = "Yükseköğretimde kalite güvencesi ne anlama gelir?"

#: Grounding olan soru.
GROUNDED = "Öğrenci kayıtlarının genel durumu nedir"

SORGU = ("query_canonical_data", {"source": "students", "limit": 20})


class SahteSaat:
    def __init__(self): self.simdi = 1000.0
    def __call__(self): return self.simdi
    def ilerlet(self, s): self.simdi += s


class SahteGemini:
    """Plana göre davranır: araç çağırır, metin yazar ya da susar.

    `susma_sayisi`: kaç çağrı boyunca boş dönecek. Retry zincirini
    sınamak için: 1 → ilk finalizasyon denemesinde konuşur.
    """

    name = model = "sahte"
    timeout_seconds = 120.0

    def __init__(self, saat, *, arac: bool = False, susma_sayisi: int = 0,
                 metin: str = "Model kendi bilgisiyle cevap veriyor."):
        self.saat, self.arac = saat, arac
        self.susma_sayisi, self.metin = susma_sayisi, metin
        self.cagri = 0
        self.araci_kapali_turlar: List[int] = []

    def etkin_model(self): return "sahte"
    def resolve_model(self): return "sahte"
    def is_available(self): return True
    def health(self): return ProviderHealth(True, True, (), "ok")
    def warm_up(self): return None
    def chat(self, m, tools=None): return "tamam", ""
    def stream_chat(self, m): yield "ok"

    def chat_with_tools(self, messages, tools=None):
        self.saat.ilerlet(1.0)
        self.cagri += 1
        if tools is None:
            self.araci_kapali_turlar.append(self.cagri)
        if self.arac and self.cagri == 1 and tools:
            return ([{"name": SORGU[0], "arguments": SORGU[1], "id": "c1"}],
                    "", "")
        if self.cagri <= self.susma_sayisi:
            return [], "", ""
        return [], self.metin, ""


def _kos(monkeypatch, client, soru: str, saglayici: SahteGemini):
    monkeypatch.setattr(chat_service.time, "monotonic", saglayici.saat)
    monkeypatch.setattr(chat_service, "get_provider", lambda: saglayici)
    return client.post("/api/assistant/chat", json={"message": soru})


# ---------------------------------------------------------------- 1
def test_grounding_yokken_model_metni_gosterilir(monkeypatch, client):
    """ASIL DEĞİŞİKLİK. Araç sonucu yok ama model konuştu → metin görünür."""
    s = SahteGemini(SahteSaat(), arac=False,
                    metin="Kalite güvencesi, yükseköğretimde süreçlerin "
                          "belirli ölçütlere göre değerlendirilmesidir.")
    yanit = _kos(monkeypatch, client, GROUNDINGSIZ, s)
    assert yanit.status_code == 200, yanit.text
    metin = yanit.json()["answer"]
    assert "Kalite güvencesi" in metin, (
        f"Model metni silinmiş. Dönen: {metin[:200]}")
    assert TEKNIK_MESAJ not in metin


# ---------------------------------------------------------------- 2
def test_kurumsal_soruda_da_model_metni_silinmez(monkeypatch, client):
    """Kurumsal soru + grounding yok → metin yine korunur.

    Eski davranışta bu durum `NO_TOOL_RESULT_MESSAGE` ile eziliyordu.

    SORU SEÇİMİ ÖNEMLİ: "Toplam öğrenci sayımız kaç?" bu testi ölçmez —
    backend o soruya kendi bağlamını üretiyor, yani grounding VAR ve
    metin zaten korunuyor. Burada gerçekten karşılığı olmayan, ama
    kurumsal görünen bir soru gerekir.
    """
    s = SahteGemini(SahteSaat(), arac=False,
                    metin="Elimde bu döneme ait kesin bir kayıt yok, "
                          "ancak genel eğilim şudur.")
    yanit = _kos(
        monkeypatch, client,
        "2035-2036 döneminde kaç akademisyenimiz olacak?", s)
    assert yanit.status_code == 200
    metin = yanit.json()["answer"]
    assert "genel eğilim" in metin, f"Metin silindi: {metin[:200]}"


# ---------------------------------------------------------------- 3
def test_grounded_cevap_hala_oncelikli(monkeypatch, client):
    """RAG bozulmadı: araç çalıştığında kurumsal kaynak işaretlenir."""
    s = SahteGemini(SahteSaat(), arac=True,
                    metin="Verilere göre öğrenci kayıtları şu durumda.")
    yanit = _kos(monkeypatch, client, GROUNDED, s)
    assert yanit.status_code == 200
    govde = yanit.json()
    assert "Verilere göre" in govde["answer"]
    assert govde["data_source"] == query_policy.SOURCE_INSTITUTIONAL
    assert govde["used_tools"], "Araç sonucu kayboldu"


# ---------------------------------------------------------------- 4
def test_model_susarsa_finalizasyon_denenir(monkeypatch, client):
    """İlk tur boş → araçsız finalizasyon turu → metin gelir."""
    s = SahteGemini(SahteSaat(), arac=True, susma_sayisi=2,
                    metin="Finalizasyon turunda üretilen cevap.")
    yanit = _kos(monkeypatch, client, GROUNDED, s)
    assert yanit.status_code == 200
    metin = yanit.json()["answer"]
    assert "Finalizasyon turunda" in metin, (
        f"Retry yapılmadı ya da metni kullanılmadı: {metin[:200]}")
    # En az bir tur ARAÇSIZ gitmiş olmalı: yeniden araç çağırıp aynı
    # döngüye girmesin diye finalizasyon turunda şema gönderilmez.
    assert s.araci_kapali_turlar, "Finalizasyon turu araçsız gönderilmedi"


# ---------------------------------------------------------------- 5
def test_retry_sinirli(monkeypatch, client):
    """Sonsuz denenmez: toplam iki ek çağrı."""
    s = SahteGemini(SahteSaat(), arac=False, susma_sayisi=99)
    yanit = _kos(monkeypatch, client, GROUNDINGSIZ, s)
    assert yanit.status_code == 200
    # 3 tur döngü + en fazla 2 ek deneme.
    tavan = (chat_service.MAX_LLM_ROUNDS_PER_USER_MESSAGE
             + chat_service.EK_DENEME_SAYISI)
    assert s.cagri <= tavan, f"{s.cagri} çağrı yapıldı, tavan {tavan}"


# ---------------------------------------------------------------- 6
def test_zaman_asiminda_da_bir_hizli_deneme_yapilir(monkeypatch, client):
    """Zaman aşımı da bir cevap şansı hak eder — ama TEK ve HIZLI.

    Önceki sürümde zaman aşımından sonra hiç denenmiyordu; kullanıcı
    beklediği hâlde cevapsız kalıyordu. Şimdi tam olarak bir ek deneme
    yapılır: araçsız, sadeleştirilmiş bağlamla ve kısa bir tavanla.
    """
    saat = SahteSaat()

    class IlkTuruYavas(SahteGemini):
        """İlk çağrı zaman aşımı, ikinci çağrı cevap verir."""

        def chat_with_tools(self, messages, tools=None):
            self.cagri += 1
            if self.cagri == 1:
                self.saat.ilerlet(self.timeout_seconds)
                raise AssistantProviderError("zaman asimi", kind="timeout")
            self.saat.ilerlet(1.0)
            if tools is None:
                self.araci_kapali_turlar.append(self.cagri)
            return [], "Zaman aşımı sonrası üretilen cevap.", ""

    s = IlkTuruYavas(saat)
    yanit = _kos(monkeypatch, client, GROUNDED, s)
    assert yanit.status_code == 200
    assert s.cagri == 2, f"Beklenen 2 çağrı, yapılan {s.cagri}"
    assert "Zaman aşımı sonrası" in yanit.json()["answer"], (
        f"Hızlı denemenin metni kullanılmadı: {yanit.json()['answer'][:200]}")
    # Ağır zincir baştan çalışmaz: ikinci çağrı ARAÇSIZ gider.
    assert s.araci_kapali_turlar == [2], (
        f"İkinci çağrı araçsız gönderilmedi: {s.araci_kapali_turlar}")


def test_zaman_asiminda_tek_deneme_yapilir(monkeypatch, client):
    """Sürekli zaman aşımında bile ek deneme sayısı BİRDE kalır."""
    saat = SahteSaat()

    class HepYavas(SahteGemini):
        def chat_with_tools(self, messages, tools=None):
            self.cagri += 1
            self.saat.ilerlet(min(self.timeout_seconds, 20.0))
            raise AssistantProviderError("zaman asimi", kind="timeout")

    s = HepYavas(saat)
    yanit = _kos(monkeypatch, client, GROUNDED, s)
    assert yanit.status_code == 200
    assert s.cagri == 2, (
        f"Zaman aşımında {s.cagri} çağrı yapıldı; tam olarak 2 olmalı "
        "(ilk tur + bir hızlı deneme)")
    assert yanit.json()["answer"].strip(), "Boş cevap döndü"


def test_kotada_ayni_model_tekrar_denenmez(monkeypatch, client):
    """Kotada AYNI modeli tekrar denemek anlamsızdır.

    Alternatif bulut modeli tanımlıysa o AYRI bir denemedir (bkz.
    test_provider_kota.py); burada tanımsız bırakılır.
    """
    monkeypatch.setattr(chat_service, "_alternatif_modeller", lambda: [])
    saat = SahteSaat()

    class Kotali(SahteGemini):
        def chat_with_tools(self, messages, tools=None):
            self.cagri += 1
            self.saat.ilerlet(1.0)
            raise AssistantProviderError("kota", kind="rate_limit")

    s = Kotali(saat)
    yanit = _kos(monkeypatch, client, GROUNDED, s)
    assert yanit.status_code == 200
    assert s.cagri == 1, f"Kotada {s.cagri} çağrı yapıldı"


# ---------------------------------------------------------------- 7
def test_teknik_mesaj_yalnizca_son_care(monkeypatch, client):
    """Retrieval hatası tek başına teknik mesajı tetiklemez.

    Teknik mesaj yalnızca hiçbir yerden metin gelmediğinde çıkar; bu
    testte model konuştuğu için çıkmamalı.
    """
    for soru in (GROUNDINGSIZ, "Toplam öğrenci sayımız kaç?",
                 "Kampüsteki kedi sayısı kaç?"):
        s = SahteGemini(SahteSaat(), arac=False, metin="Normal bir cevap.")
        yanit = _kos(monkeypatch, client, soru, s)
        assert yanit.status_code == 200
        assert TEKNIK_MESAJ not in yanit.json()["answer"], (
            f"{soru!r} sorusunda teknik mesaj gösterildi")


# ---------------------------------------------------------------- 8
def test_hic_metin_yoksa_kontrollu_mesaj_kalir(monkeypatch, client):
    """Son çare korunur: model hiç konuşmazsa kullanıcı boş ekran görmez."""
    s = SahteGemini(SahteSaat(), arac=False, susma_sayisi=99)
    yanit = _kos(monkeypatch, client, GROUNDINGSIZ, s)
    assert yanit.status_code == 200
    assert yanit.json()["answer"].strip(), "Boş cevap döndü"
