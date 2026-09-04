"""Sunum için genişletilen süre bütçesi ve kullanıcıya gösterilen dil.

ÖLÇÜLEN OLAY
------------
    Gemini zaman asimi (25.0 sn)
    [AI TURN 35bfcef2] ROUND 3 TIMEOUT duration=25.4 remaining_deadline=11.1

Karmaşık bir soruda (on üniversite × iki bölüm × çok yıllı taban puan)
modelin SON yorum turu 25 saniyede bitmiyordu; veri elde olmasına rağmen
cevap yarıda kalıyor ve kullanıcı "Modelin yorum turu zaman aşımına
uğradı" cümlesini görüyordu. Sunumda bu, sistemin çöktüğü izlenimi
veriyor.

Çözüm tur SAYISINI artırmak DEĞİL (üç tur ve iki veri çağrısı aynı
kaldı); var olan turlara yetecek süreyi vermek. Bu testler hem yeni
bütçeyi hem de ekranda teknik ayrıntı görünmemesini kilitler.

GERÇEK GEMINI İSTEĞİ YAPILMAZ.
"""

from __future__ import annotations

import pytest

from app.services.assistant import chat_service
from app.services.assistant.provider_shared import (
    AssistantProviderError, ProviderHealth)


class SahteSaat:
    def __init__(self): self.simdi = 1000.0
    def __call__(self): return self.simdi
    def ilerlet(self, s): self.simdi += s


class SahteSaglayici:
    """Planlanan süre kadar 'çalışır'; sınırı aşarsa gerçek httpx gibi kesilir."""
    name = model = "sahte"
    timeout_seconds = 120.0

    def __init__(self, saat, plan):
        self.saat, self.plan, self.istek = saat, list(plan), 0
        self.sinirlar = []
        self.son_mesajlar = None

    def etkin_model(self): return "sahte"
    def resolve_model(self): return "sahte"
    def is_available(self): return True
    def health(self): return ProviderHealth(True, True, (), "ok")
    def warm_up(self): return None
    def chat(self, m, tools=None): return "tamam", ""
    def stream_chat(self, m): yield "ok"

    def chat_with_tools(self, messages, tools=None):
        self.istek += 1
        self.sinirlar.append(self.timeout_seconds)
        self.son_mesajlar = list(messages)
        if not self.plan:
            return [], "Son cevap.", ""
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
        return [], yuk, ""


SORGU = ("query_canonical_data", {
    "source": "yok_atlas_benchmark_metrics",
    "filters": {"metric": "base_score"}, "limit": 50})


@pytest.fixture
def kos(monkeypatch, db_session):
    saat = SahteSaat()
    monkeypatch.setattr(chat_service.time, "monotonic", saat)

    def _kos(plan, soru="Bilgisayar ve Elektrik taban puanları 2025-2026"):
        s = SahteSaglayici(saat, plan)
        monkeypatch.setattr(chat_service, "get_provider", lambda: s)
        basladi = saat.simdi
        sonuc = chat_service.answer(soru, db=db_session)
        return s, sonuc, saat.simdi - basladi
    return _kos


# ------------------------------------------------------------------ 1
def test_30_saniyelik_son_tur_artik_basarili():
    """Eski 25 sn sınırında düşerdi; bugünkü sınırda rahatça geçmeli.

    SABİT DEĞER YAZILMAZ. Bu test bir kez 25→40, sonra 40→120 değişince
    kırıldı; oysa koruduğu şey hiç değişmedi — "30 saniyelik bir yanıt
    kesilmemeli". Ölçüt artık sabitin KENDİSİNDEN okunur.
    """
    tavan = chat_service.GEMINI_ROUND_TIMEOUT_SECONDS
    # Turun başında hiç süre harcanmamışken sınır tavana kadar çıkabilir.
    assert chat_service._tur_timeout(0.0) == tavan
    # 30 saniyelik bir yanıt bu sınırın altında kalır.
    assert 30.0 < chat_service._tur_timeout(0.0)


def test_uc_tur_30_saniyelik_yanitla_tamamlanir(kos):
    s, sonuc, gecen = kos([(3.0, ("tool", SORGU)),
                           (3.0, ("tool", SORGU)),
                           (30.0, ("text", "Final yorum."))])
    assert s.istek == 3
    assert sonuc["answer"]
    assert "zaman aşımı" not in sonuc["answer"].lower()


# ------------------------------------------------------------------ 2
def test_60_saniyelik_tur_global_butceye_sigar(kos):
    """Toplam ~60 sn süren bir tur global bütçeye sığmalı."""
    assert chat_service.MAX_USER_TURN_SECONDS >= 60.0
    s, sonuc, gecen = kos([(20.0, ("tool", SORGU)),
                           (20.0, ("tool", SORGU)),
                           (18.0, ("text", "Final yorum."))])
    assert s.istek == 3
    assert gecen <= chat_service.MAX_USER_TURN_SECONDS
    assert sonuc["answer"] and "zaman aşımı" not in sonuc["answer"].lower()


# ------------------------------------------------------------------ 3
def test_kalan_sure_azsa_tavan_verilmez(kos):
    """Global deadline yaklaşınca tur sınırı kalan süreye iner.

    Senaryo, sabitlerden TÜRETİLİR: ilk iki tur global bütçenin çoğunu
    yer, böylece üçüncü tura tavandan azı kalır. Sabit saniye yazmak,
    bütçe her değiştiğinde bu testi anlamsızca kırıyordu.
    """
    tavan = chat_service.GEMINI_ROUND_TIMEOUT_SECONDS
    kure = chat_service.MAX_USER_TURN_SECONDS
    # İlk iki tur global bütçenin ~%80'ini tüketsin.
    uzun = min(tavan - 2.0, kure * 0.40)
    s, _, _ = kos([(uzun, ("tool", SORGU)),
                   (uzun, ("tool", SORGU)),
                   (tavan, ("text", "gelmeyecek"))])
    assert s.sinirlar[0] == tavan
    # Üçüncü tura gelindiğinde tavan değil, kalan süre verilmiş olmalı.
    if len(s.sinirlar) >= 3:
        assert s.sinirlar[2] < tavan


def test_effective_timeout_formulu():
    """Formül sabitlerden okunur, elle yazılmış saniyelerden değil."""
    m = chat_service._TUR_SONU_MARJI
    tavan = chat_service.GEMINI_ROUND_TIMEOUT_SECONDS
    kure = chat_service.MAX_USER_TURN_SECONDS
    # Bol süre varken tavan geçerli
    assert chat_service._tur_timeout(0.0) == tavan
    # Kalan azaldığında kalan − marj
    gecen = kure - tavan / 2.0
    assert chat_service._tur_timeout(gecen) == pytest.approx(kure - gecen - m)
    # Hiç kalmadığında alt sınır 1 sn
    assert chat_service._tur_timeout(kure - 0.5) == 1.0


# ------------------------------------------------------------------ 4
def test_son_tur_yeni_arac_cagirmayi_yasakliyor():
    """Notun KORUDUĞU DAVRANIŞ kontrol edilir, sloganı değil.

    Not bilinçli olarak kısaltıldı: uzun görev listesi modeli "önce
    planlayayım" moduna sokuyor, ölçülen sonuç cevabın hiç yazılmaya
    başlanmaması oluyordu. Bu yüzden test artık "SON TUR" gibi bir
    başlık aramaz; iki emrin durduğunu doğrular.
    """
    g = chat_service._SON_TUR_GOREVI.lower()
    assert "yeni araç çağırma" in g
    assert "final cevabı yaz" in g or "cevabı hemen tamamla" in g


def test_ikinci_turda_erken_final_notu_var():
    n = chat_service._ERKEN_FINAL_NOTU
    assert "YETİYORSA" in n.upper()
    assert "yeni araç çağırma" in n.lower()


def test_son_tur_notu_modele_gercekten_gonderiliyor(kos):
    s, _, _ = kos([(2.0, ("tool", SORGU)), (2.0, ("tool", SORGU)),
                   (2.0, ("text", "Final."))])
    sistem = " ".join(m["content"] for m in (s.son_mesajlar or [])
                      if m.get("role") == "system")
    # Notun kendisi gönderilmiş olmalı (metni sabit değil, içeriği ölçülür).
    assert "yeni araç çağırma" in sistem.lower()


# ------------------------------------------------------------------ 5
def test_fallback_teknik_hatada_hala_calisiyor(kos):
    """Gerçek bir sağlayıcı hatasında fallback devrede kalmalı."""
    s, sonuc, _ = kos([(2.0, ("tool", SORGU)), (100.0, ("text", "gelmeyecek"))])
    assert sonuc["answer"], "fallback boş cevap döndürdü"


# ------------------------------------------------------------------ 6
def test_kullaniciya_teknik_ifade_gosterilmiyor(kos):
    """Ekranda 'timeout', 'zaman aşımı', 'Gemini' geçmemeli."""
    s, sonuc, _ = kos([(2.0, ("tool", SORGU)), (100.0, ("text", "x")),
                       (100.0, ("text", "y"))])
    metin = (sonuc["answer"] or "").lower()
    for yasak in ("zaman aşımı", "zaman asimi", "timeout", "gemini",
                  "yorum turu", "istek sınırı"):
        assert yasak not in metin, f"kullanıcıya teknik ifade sızdı: {yasak}"


# ------------------------------------------------------------------ 7
def test_grafik_uyarisi_sunum_dilinde():
    from app.routers.assistant import grafik_yok_sebebi as sebep
    # Veri yoksa dürüst mesaj korunur
    assert sebep(veri_geldi=False, zaman_asimi=False) == \
        "Bu veri mevcut kaynaklarda bulunmuyor."
    # Veri varsa teknik sebep YAZILMAZ
    for za in (True, False):
        m = sebep(veri_geldi=True, zaman_asimi=za)
        assert m == "Bu sonuç için grafik üretilemedi."
        for yasak in ("tamamlanamadı", "aşama", "şema", "timeout"):
            assert yasak not in m.lower()


# ------------------------------------------------------------------ sınırlar
def test_tur_ve_arac_limitleri_degismedi():
    assert chat_service.MAX_LLM_ROUNDS_PER_USER_MESSAGE == 3
    assert chat_service.MAX_DATA_TOOL_CALLS == 2
    assert chat_service.DATA_TOOL_TIMEOUT_SECONDS == 10.0
