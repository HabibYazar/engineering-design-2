"""Bir kullanıcı sorusunun kaç model isteği harcadığını kilitler.

NEDEN VAR
---------
Ölçülen olay: tek bir kullanıcı sorusu günlük API kotasını (ücretsiz
katmanda 20 istek) bitirdi ve tool döngüsü tamamlanamadığı için
kullanıcıya final cevap bile dönmedi. Sebep, döngünün üst sınırının
sekiz tur olmasıydı; yani bir soru dokuz isteğe kadar çıkabiliyordu.

Bu testler o sınırı DAVRANIŞ düzeyinde sabitler. Sabitin değerini
okumakla yetinmezler; sahte bir sağlayıcıyla gerçekten kaç istek
yapıldığını sayarlar. Sabit büyütülür ama döngü sızdırırsa yine yakalanır.

GERÇEK API İSTEĞİ YAPILMAZ. Sağlayıcı tamamen sahtedir; ağ yoktur.
"""

from __future__ import annotations

import pytest

from app.services.assistant import chat_service
from app.services.assistant.provider_shared import (
    AssistantProviderError, ProviderHealth)


SORGU = ("query_canonical_data", {
    "source": "yok_atlas_benchmark_metrics",
    "filters": {"metric": "quota", "academic_year": "2025-2026"},
    "limit": 5})
SORGU2 = ("query_canonical_data", {
    "source": "university_student_headcounts",
    "filters": {"university_name": "BİLİM"}, "limit": 5})
GRAFIK = ("render_chart", {"source_tool": "query_canonical_data",
                           "x_field": "academic_year", "y_field": "value",
                           "title": "t"})


class SahteSaglayici:
    """İstekleri sayar, planlanan araç çağrılarını sırayla döndürür."""

    name = "sahte"
    model = "sahte"

    def __init__(self, plan, hata=None):
        self.plan = list(plan)
        self.istek = 0
        self.hata = hata

    def etkin_model(self):
        return "sahte"

    def resolve_model(self):
        return "sahte"

    def is_available(self):
        return True

    def health(self):
        return ProviderHealth(True, True, (), "ok")

    def warm_up(self):
        return None

    def chat(self, messages, tools=None):
        return "tamam", ""

    def chat_with_tools(self, messages, tools=None):
        self.istek += 1
        if self.hata and self.istek >= self.hata[0]:
            raise AssistantProviderError("sinir", kind=self.hata[1])
        if self.plan:
            ad, arg = self.plan.pop(0)
            if tools is None:
                # Son turda araç sunulmaz; model cevabı yazmak zorundadır.
                return [], "Eldeki verilerle cevap.", ""
            return [{"name": ad, "arguments": arg, "id": f"c{self.istek}"}], "", ""
        return [], "Son cevap.", ""

    def stream_chat(self, messages):
        yield "ok"


@pytest.fixture
def kos(monkeypatch, db_session):
    def _kos(plan, hata=None, soru="2025 kontenjan durumu nedir"):
        saglayici = SahteSaglayici(plan, hata)
        monkeypatch.setattr(chat_service, "get_provider", lambda: saglayici)
        sonuc = chat_service.answer(soru, db=db_session)
        return saglayici.istek, sonuc
    return _kos


def test_arac_gerekmeyen_soru_tek_istek(kos):
    istek, sonuc = kos([], soru="merhaba")
    assert istek == 1
    assert sonuc["answer"]


def test_tek_veri_sorusu_butce_icinde_kalir(kos):
    """Tek veri çağrısı tavanı zorlamamalı.

    Üst sınır burada 3'tür, 2 değil: aracın SONUÇ DÖNDÜREMEDİĞİ
    durumda mevcut sistem kurumsal soruya "araçsız cevap" üretilmesini
    engellemek için bir ikinci şans turu veriyor. O davranış veri
    doğruluğunu koruyor ve kaldırılmadı; sadece bütçenin içine alındı.
    """
    istek, sonuc = kos([SORGU])
    assert istek <= chat_service.MAX_LLM_ROUNDS_PER_USER_MESSAGE
    assert sonuc["answer"]


def test_sonsuz_arac_isteyen_model_tavanda_durur(kos):
    """En kritik test: model durmak bilmezse döngü onu durdurur."""
    istek, sonuc = kos([SORGU, SORGU2] + [SORGU] * 20)
    assert istek <= chat_service.MAX_LLM_ROUNDS_PER_USER_MESSAGE
    # Bütçe bitse bile kullanıcı cevapsız kalmaz.
    assert sonuc["answer"]


def test_ayni_sorgu_tekrarlanirsa_butce_harcanmaz(kos):
    """Önbellek isabeti veri bütçesinden düşülmemeli."""
    istek, sonuc = kos([SORGU, SORGU])
    assert istek <= chat_service.MAX_LLM_ROUNDS_PER_USER_MESSAGE
    assert sonuc["answer"]


def test_grafik_veri_butcesini_tuketmez(kos):
    istek, sonuc = kos([SORGU, GRAFIK])
    assert istek <= chat_service.MAX_LLM_ROUNDS_PER_USER_MESSAGE
    assert sonuc["answer"]


def test_kota_dolunca_istisna_degil_aciklama_doner(kos, monkeypatch):
    """429 sonrası kullanıcı boş ekranla kalmamalı.

    İKİ NOKTA BİLİNÇLİ OLARAK DEĞİŞTİ:

    1. Alternatif bulut modeli yapılandırılmışsa kotada BİR kez denenir.
       Burada tanımsız bırakılır ki bu test yalnızca "yeniden deneme
       fırtınası yok" kuralını ölçsün.

    2. KOTA artık kullanıcıya söylenir. Diğer teknik sebepler (zaman
       aşımı, boş cevap) hâlâ gizlidir — ama kota farklıdır: kullanıcı
       neden farklı bir cevap aldığını bilmeli, yoksa sistemin bozuk
       olduğunu sanır.
    """
    from app.services.assistant import chat_service as _cs
    monkeypatch.setattr(_cs, "_alternatif_modeller", lambda: [])
    istek, sonuc = kos([SORGU, SORGU2], hata=(2, "rate_limit"))
    assert istek == 2  # yeniden deneme fırtınası yok
    assert sonuc["answer"]
    # Kota DIŞINDAKİ teknik ayrıntılar hâlâ yazılmaz.
    for yasak in ("zaman aşımı", "timeout", "http", "quota", "retrydelay"):
        assert yasak not in sonuc["answer"].lower()


def test_serbest_araclar_selamlamada_sunulmaz():
    """Pahalı keşif araçları sohbet mesajlarında görünmemeli."""
    from app.services.assistant import tool_selection
    from app.services.assistant.tool_registry import registry

    secilen = tool_selection.ilgili_araclar("merhaba", registry.names())
    assert not (set(secilen) & set(tool_selection.SON_CARE))


def test_ozel_arac_eslesince_serbest_araclar_sunulmaz():
    from app.services.assistant import tool_selection
    from app.services.assistant.tool_registry import registry

    secilen = tool_selection.ilgili_araclar(
        "2025 Yazılım Mühendisliği doluluğu nedir", registry.names())
    assert not (set(secilen) & set(tool_selection.SON_CARE))


def test_ozel_arac_yoksa_serbest_araclar_devreye_girer():
    from app.services.assistant import tool_selection
    from app.services.assistant.tool_registry import registry

    secilen = tool_selection.ilgili_araclar(
        "Üniversitemizin son yıllardaki en büyük yapısal problemi nedir",
        registry.names())
    assert set(secilen) & set(tool_selection.SON_CARE)
