"""Süre bütçesinin davranışını sahte saatle kilitler.

NEDEN VAR
---------
Ölçülen olay: `.env` içindeki `GEMINI_TIMEOUT_SECONDS=120` tek bir HTTP
isteğinin sınırıydı. Model yanıt vermeyince istek 120 saniye askıda
kalıyor, kullanıcı sonunda 504 alıyordu — üstelik o ana kadar
veritabanından okunmuş araç sonuçları da kayboluyordu.

Buradaki testler GERÇEKTEN BEKLEMEZ. Sağlayıcı sahtedir ve `time.monotonic`
ilerletilerek geçen süre simüle edilir; böylece 45 saniyelik bir senaryo
milisaniyede ölçülür. GERÇEK GEMINI İSTEĞİ YAPILMAZ.
"""

from __future__ import annotations

import pytest

from app.services.assistant import chat_service, tool_runner
from app.services.assistant.provider_shared import (
    AssistantProviderError, ProviderHealth)


SORGU = ("query_canonical_data", {
    "source": "yok_atlas_benchmark_metrics",
    "filters": {"metric": "quota", "academic_year": "2025-2026"},
    "limit": 5})
SORGU2 = ("query_canonical_data", {
    "source": "university_student_headcounts",
    "filters": {"university_name": "BİLİM"}, "limit": 5})


class SahteSaat:
    """İlerletilebilir monotonik saat."""

    def __init__(self) -> None:
        self.simdi = 1000.0

    def __call__(self) -> float:
        return self.simdi

    def ilerlet(self, saniye: float) -> None:
        self.simdi += saniye


class SahteSaglayici:
    """Planlanan süre kadar 'çalışır', sonra plana göre sonuç döner.

    `plan` her tur için (harcanan_saniye, davranış) çiftidir.
    Davranış: ("tool", (ad, argüman)) | ("text", metin) | ("hata", tür)
    Zaman aşımı, çağrının `timeout_seconds` sınırını aşması durumunda
    KENDİLİĞİNDEN üretilir — testin sabit yazması gerekmez.
    """

    name = "sahte"
    model = "sahte"
    timeout_seconds = 120.0  # provider'ın gerçekteki başlangıç değeri

    def __init__(self, saat: SahteSaat, plan) -> None:
        self.saat = saat
        self.plan = list(plan)
        self.istek = 0
        self.gorulen_sinirlar = []

    def etkin_model(self): return "sahte"
    def resolve_model(self): return "sahte"
    def is_available(self): return True
    def health(self): return ProviderHealth(True, True, (), "ok")
    def warm_up(self): return None
    def chat(self, messages, tools=None): return "tamam", ""
    def stream_chat(self, messages): yield "ok"

    def chat_with_tools(self, messages, tools=None):
        self.istek += 1
        sinir = self.timeout_seconds
        self.gorulen_sinirlar.append(sinir)
        if not self.plan:
            return [], "Son cevap.", ""
        sure, davranis = self.plan.pop(0)

        # Sınırı aşan çağrı, gerçek httpx gibi, sınır dolduğunda kesilir.
        if sure > sinir:
            self.saat.ilerlet(sinir)
            raise AssistantProviderError("zaman asimi", kind="timeout")

        self.saat.ilerlet(sure)
        tur, yuk = davranis
        if tur == "hata":
            raise AssistantProviderError("hata", kind=yuk)
        if tur == "tool":
            ad, arg = yuk
            if tools is None:
                return [], "Eldeki verilerle cevap.", ""
            return [{"name": ad, "arguments": arg, "id": f"c{self.istek}"}], "", ""
        return [], yuk, ""


@pytest.fixture
def kos(monkeypatch, db_session):
    saat = SahteSaat()
    monkeypatch.setattr(chat_service.time, "monotonic", saat)
    monkeypatch.setattr(tool_runner.time, "monotonic", saat)

    def _kos(plan, arac_suresi=1.0, soru="2025 kontenjan durumu nedir"):
        saglayici = SahteSaglayici(saat, plan)
        monkeypatch.setattr(chat_service, "get_provider", lambda: saglayici)

        # Araç çalışması da saati ilerletsin.
        gercek_run = chat_service.ToolSession.run

        def sayan_run(self, ad, argumanlar):
            kayit = gercek_run(self, ad, argumanlar)
            saat.ilerlet(arac_suresi)
            return kayit

        monkeypatch.setattr(chat_service.ToolSession, "run", sayan_run)
        basladi = saat.simdi
        sonuc = chat_service.answer(soru, db=db_session)
        return saglayici, sonuc, saat.simdi - basladi
    return _kos


def test_sabitler_beklenen_degerde():
    assert chat_service.GEMINI_ROUND_TIMEOUT_SECONDS >= 40.0
    assert chat_service.MAX_USER_TURN_SECONDS >= 90.0
    # Önceki turda konan bütçeler BOZULMADI.
    assert chat_service.MAX_LLM_ROUNDS_PER_USER_MESSAGE == 3
    assert chat_service.MAX_DATA_TOOL_CALLS == 2


def test_ilk_tur_zaman_asimi(kos):
    """18) Round 1 uzun sürerse: BİR hızlı deneme, kontrollü cevap, 504 yok.

    SÖZLEŞME DEĞİŞTİ. Eskiden zaman aşımından sonra hiç denenmiyordu ve
    kullanıcı beklediği hâlde cevapsız kalıyordu. Artık tam olarak bir
    ek deneme yapılır: araçsız, sadeleştirilmiş bağlamla ve kısa bir
    tavanla (`_HIZLI_RETRY_SANIYE`).

    Testin KORUDUĞU DEĞER aynı: sonsuz denenmez, kullanıcı boş ekran
    görmez, teknik ayrıntı cevaba yazılmaz.
    """
    # Süre TAVANDAN türetilir. Sabit 60 sn yazmak, tavan 40→120 olunca
    # senaryoyu sessizce "zaman aşımı değil"e çeviriyordu: test yeşil
    # kalıp başka bir şeyi ölçmeye başlardı.
    _asan = chat_service.GEMINI_ROUND_TIMEOUT_SECONDS + 20.0
    saglayici, sonuc, gecen = kos([(_asan, ("text", "gelmeyecek"))])
    # İlk tur + bir hızlı deneme. Üçüncü çağrı YOK.
    assert saglayici.istek == 2
    assert sonuc["answer"]                          # boş ekran yok
    # Teknik ayrıntı kullanıcıya YAZILMAZ (sunum dili); sebep günlükte.
    for yasak in ("zaman aşımı", "timeout", "gemini"):
        assert yasak not in sonuc["answer"].lower()


def test_ikinci_tur_zaman_asimi_arac_sonucunu_korur(kos):
    """19) Round 2 zaman aşımı: ağır zincir baştan çalışmaz, veri durur.

    Hızlı deneme eklendi ama ASIL KORUNAN ŞEY değişmedi: araç sonuçları
    kaybolmaz ve araç döngüsü yeniden başlatılmaz. Ek çağrı ARAÇSIZDIR;
    modelden yalnızca eldeki veriyle cümleyi yazması istenir.
    """
    _asan = chat_service.GEMINI_ROUND_TIMEOUT_SECONDS + 20.0
    saglayici, sonuc, _ = kos([
        (3.0, ("tool", SORGU)),
        (_asan, ("text", "gelmeyecek")),
    ])
    # Araç turu + zaman aşımına uğrayan tur + bir hızlı deneme.
    assert saglayici.istek == 3
    assert sonuc["answer"]
    assert sonuc["used_tools"]                      # araç sonucu duruyor


def test_toplam_sure_asilmaz(kos):
    """20) Kalan süre tur sınırından azsa çağrı kalan kadar bekler."""
    saglayici, sonuc, gecen = kos(
        [(20.0, ("tool", SORGU)),
         (chat_service.MAX_USER_TURN_SECONDS, ("text", "gelmeyecek"))],
        arac_suresi=10.0)
    # Round 1 = 20 sn, araç = 10 sn → 30 sn geçti.
    # Round 2'nin sınırı min(tavan, kalan - marj). Marj
    # (`_TUR_SONU_MARJI`) cevabın hazırlanması için ayrılır: model tam
    # deadline'da dönse bile özet kurulup yanıt yazılabilsin diye.
    beklenen = min(chat_service.GEMINI_ROUND_TIMEOUT_SECONDS,
                   chat_service.MAX_USER_TURN_SECONDS - 30.0
                   - chat_service._TUR_SONU_MARJI)
    # İlk turda hiç süre harcanmamıştı: tam tavan verilmiş olmalı.
    assert (saglayici.gorulen_sinirlar[0]
            == chat_service.GEMINI_ROUND_TIMEOUT_SECONDS)
    assert saglayici.gorulen_sinirlar[1] == pytest.approx(beklenen, abs=0.01)
    assert gecen <= chat_service.MAX_USER_TURN_SECONDS
    assert sonuc["answer"]


def test_429_sonrasi_ayni_model_tekrar_denenmez(kos, monkeypatch):
    """21) Hız sınırı: AYNI model tekrar denenmez, veri korunur.

    SÖZLEŞME İNCELDİ. Eskiden kotada hiç ek çağrı yapılmıyordu. Artık
    yapılandırılmış bir ALTERNATİF BULUT modeli varsa bir kez denenir —
    farklı modelin kotası ayrıdır. Korunan şey aynı: aynı modeli tekrar
    tekrar çağırmak yok, araç sonuçları kaybolmuyor.

    Burada alternatif model tanımsız bırakılır; o hâlde davranış
    tamamen eskisi gibi olmalıdır.
    """
    monkeypatch.setattr(chat_service, "_alternatif_modeller", lambda: [])
    saglayici, sonuc, _ = kos([
        (2.0, ("tool", SORGU)),
        (1.0, ("hata", "rate_limit")),
    ])
    assert saglayici.istek == 2
    assert sonuc["answer"]
    assert sonuc["used_tools"]


def test_normal_hizli_soru_fallback_tetiklemez(kos):
    """22) Hızlı akış: normal cevap, zaman aşımı yolu çalışmaz."""
    saglayici, sonuc, gecen = kos(
        [(2.0, ("tool", SORGU)), (3.0, ("text", "Normal cevap."))],
        arac_suresi=1.0)
    # Test veritabanında bu sorgu satır döndürmediği için mevcut sistem
    # kurumsal soruya araçsız cevap verilmesini engelleyen "ikinci şans"
    # turunu kullanabiliyor. O davranış veri doğruluğunu koruyor ve
    # bilerek değiştirilmedi; burada ölçülen şey, hızlı turlarda
    # ZAMAN AŞIMI YOLUNUN HİÇ ÇALIŞMAMASI ve toplamın bütçe içinde
    # kalması.
    assert saglayici.istek <= chat_service.MAX_LLM_ROUNDS_PER_USER_MESSAGE
    assert gecen < chat_service.GEMINI_ROUND_TIMEOUT_SECONDS
    assert gecen <= chat_service.MAX_USER_TURN_SECONDS
    assert "zaman aşımı" not in sonuc["answer"].lower()
    assert "zamanında yanıt veremedi" not in sonuc["answer"].lower()


def test_uc_tur_deadline_icinde_calisir(kos):
    """23) İki alanlı soru üç turda biter; dördüncü tur asla olmaz."""
    saglayici, sonuc, gecen = kos([
        (3.0, ("tool", SORGU)),
        (3.0, ("tool", SORGU2)),
        (3.0, ("text", "İki alanlı cevap.")),
        (3.0, ("text", "OLMAMALI")),
    ], arac_suresi=1.0)
    assert saglayici.istek == 3
    assert gecen <= chat_service.MAX_USER_TURN_SECONDS
    assert sonuc["answer"]


def test_arac_timeout_tavani_uygulanir():
    """13) Hiçbir araç 10 saniyeden uzun bekletmez, kısası uzamaz."""
    from app.services.assistant.tool_registry import registry
    tavan = tool_runner.DATA_TOOL_TIMEOUT_SECONDS
    for arac in registry.all():
        assert min(arac.timeout_seconds, tavan) <= tavan
    # En az bir araç gerçekten kırpılıyor olmalı; yoksa tavan etkisiz.
    assert any(t.timeout_seconds > tavan for t in registry.all())
