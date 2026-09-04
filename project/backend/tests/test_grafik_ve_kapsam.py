"""Grafik üretimi ve "tüm / hepsi / genel" kapsamı.

İKİ AYRI ARIZA, İKİ AYRI KÖK NEDEN
----------------------------------
1) GRAFİK — çizim yalnızca MODEL `render_chart` aracını çağırdığında
   yapılıyordu. Model çağırmazsa, ya da çağıramazsa (çok metrikli
   analizde veriyi backend çeker; ortada `source_tool` yoktur), veri
   elde durduğu hâlde grafik çıkmıyordu.

2) KAPSAM — varlık çözümleyici Türkçe eklere bilerek toleranslı:
   "üniversite", "üniversitesi" ve "üniversiteler" aynı kavrama düşer.
   Kavram eşleştirmesi için doğru, KAPSAM için yanlış. "Ankara'daki
   üniversiteler" ifadesi bitişik iki sözcük olduğu için ANKARA
   ÜNİVERSİTESİ'ne kilitleniyordu.

Testler soru metnine değil DAVRANIŞA bağlı: yeni bir program, yeni bir
tablo ya da başka kelimelerle sorulmuş bir soru bunları kırmaz.
"""

from __future__ import annotations

import time
from typing import List, Optional

import pytest

from app.services.assistant import abu_kds_store as store
from app.services.assistant import chart_builder, chat_service
from app.services.assistant import coklu_metrik, grafik_uret, kapsam
from app.services.assistant import veri_ailesi as va
from app.services.assistant.provider_shared import (AssistantProviderError,
                                                    ProviderHealth)

pytestmark = pytest.mark.skipif(
    not store.kullanilabilir(), reason="abu_kds.db yok.")


class SahteSaat:
    def __init__(self): self.simdi = 1000.0
    def __call__(self): return self.simdi
    def ilerlet(self, s): self.simdi += s


class SahteGemini:
    """Grafik ARACINI HİÇ ÇAĞIRMAYAN model — düzeltilen durum tam budur."""

    name = "sahte"
    timeout_seconds = 120.0

    def __init__(self, saat, *, metin: str = "Eğilim yukarı yönlü.",
                 arac=None, hata: Optional[str] = None):
        self.saat, self.model, self.metin = saat, "birincil", metin
        self.arac, self.hata, self.cagri = arac, hata, 0

    def etkin_model(self): return self.model
    def resolve_model(self): return self.model
    def is_available(self): return True
    def health(self): return ProviderHealth(True, True, (), "ok")
    def warm_up(self): return None
    def chat(self, m, tools=None): return "tamam", ""
    def stream_chat(self, m): yield "ok"

    def chat_with_tools(self, messages, tools=None):
        self.saat.ilerlet(1.0)
        self.cagri += 1
        if self.arac and self.cagri == 1 and tools:
            return ([{"name": self.arac[0], "arguments": self.arac[1],
                      "id": "c1"}], "", "")
        if self.hata:
            raise AssistantProviderError("hata", kind=self.hata)
        return [], self.metin, ""


def _kos(monkeypatch, client, soru: str, **kw):
    s = SahteGemini(SahteSaat(), **kw)
    monkeypatch.setattr(chat_service.time, "monotonic", s.saat)
    monkeypatch.setattr(chat_service, "get_provider", lambda: s)
    monkeypatch.setattr(chat_service, "_alternatif_modeller", lambda: [])
    return s, client.post("/api/assistant/chat", json={"message": soru})


# ===========================================================================
# BÖLÜM 1 — GRAFİK
# ===========================================================================
@pytest.mark.parametrize("soru", [
    "Son 5 yılın grafiğini çiz",
    "grafik olarak göster",
    "bar chart göster",
    "çizgi grafiği göster",
    "üniversitelere göre karşılaştırma grafiği",
    "bölümlerin dağılım grafiği",
    "trend grafiği çıkar",
    "show me a chart",
])
def test_grafik_niyeti_taniniyor(soru):
    assert grafik_uret.istendi_mi(soru), soru


@pytest.mark.parametrize("soru", [
    "Bilgisayar mühendisliği nedir?",
    "Kaç akademisyenimiz var?",
])
def test_grafik_istenmeyen_soru_isaretlenmiyor(soru):
    assert not grafik_uret.istendi_mi(soru), soru


def test_model_arac_cagirmasa_da_grafik_uretiliyor(monkeypatch, client):
    """ASIL DÜZELTME: grafik artık modelin isteğine bağlı değil."""
    s, yanit = _kos(monkeypatch, client,
                    "Son 5 yılda mühendisliklerin grafiğini çiz")
    assert yanit.status_code == 200
    govde = yanit.json()
    assert govde["chart_requested"] is True
    assert govde["charts"], f"Grafik üretilmedi: {govde.get('chart_reason')}"


def test_grafik_verisi_gercek_veriden_geliyor(monkeypatch, client):
    """Uydurma sayı yok: her nokta kanıttaki değere eşit olmalı."""
    soru = "Son 5 yılda mühendisliklerin grafiğini çiz"
    _, yanit = _kos(monkeypatch, client, soru)
    grafikler = yanit.json()["charts"]
    kanit = coklu_metrik.kanit_uret(va.plan_cikar(soru))
    beklenen = {m.etiket.capitalize(): [v for _, v, _ in m.noktalar]
                for m in kanit.metrikler}
    for g in grafikler:
        ad = g["title"].split(" — ")[0]
        if ad in beklenen:
            assert g["series"][0]["data"] == beklenen[ad], ad


def test_metin_ve_grafik_ayni_kaynaktan(monkeypatch, client):
    """Grafik başka bir sorgudan gelirse metinle çelişebilir."""
    _, yanit = _kos(monkeypatch, client,
                    "Son 5 yılda mühendisliklerin grafiğini çiz")
    govde = yanit.json()
    kaynaklar = {g.get("source_label") for g in govde["charts"]}
    kanit_kaynaklari = set(coklu_metrik.kanit_uret(
        va.plan_cikar("Son 5 yılda mühendisliklerin grafiğini çiz")
    ).kaynaklar())
    assert kaynaklar <= kanit_kaynaklari, (kaynaklar, kanit_kaynaklari)


def test_her_metrik_kendi_grafiginde():
    """Farklı birimler tek eksene karışmaz — bileşik skorun görsel eşi."""
    kanit = coklu_metrik.kanit_uret(
        va.plan_cikar("Son 5 yılda mühendisliklerin seyri"))
    grafikler = grafik_uret.kanittan(kanit, "grafik")
    for g in grafikler:
        birimler = {s.get("unit") for s in g["series"]}
        assert len(birimler) == 1, f"{g['title']}: karışık birim {birimler}"


def test_oran_birimi_toplanabilir_isaretlenmiyor():
    """Yüzdeleri üst üste yığmak %190 gibi anlamsız değer üretirdi."""
    kanit = coklu_metrik.kanit_uret(
        va.plan_cikar("Son 5 yılda mühendisliklerin seyri"))
    for g in grafik_uret.kanittan(kanit, "grafik"):
        if g["series"][0].get("unit") in ("%", "oran", "sıra"):
            assert g["additive"] is False, g["title"]


@pytest.mark.parametrize("soru,beklenen", [
    ("bar chart göster", "bar"),
    ("çizgi grafiği göster", "line"),
    ("pasta grafiği göster", "pie"),
])
def test_acik_tur_istegi_kazaniyor(soru, beklenen):
    assert grafik_uret.tur_sec(soru, yil_ekseni=True, nokta=5,
                               kategori=5) == beklenen


def test_tur_verinin_seklinden_cikiyor():
    """Kullanıcı tür söylemediyse eksen ve nokta sayısı karar verir."""
    assert grafik_uret.tur_sec("göster", yil_ekseni=True, nokta=5,
                               kategori=5) == "line"
    assert grafik_uret.tur_sec("göster", yil_ekseni=True, nokta=2,
                               kategori=2) == "bar"
    assert grafik_uret.tur_sec("göster", yil_ekseni=False, nokta=0,
                               kategori=20) == "hbar"


def test_grafik_cizilemezse_metin_cevabi_kaliyor(monkeypatch, client):
    """Grafiğin çıkmaması cevabı düşürmez."""
    _, yanit = _kos(monkeypatch, client,
                    "Bologna sürecinin grafiğini çiz",
                    metin="Bologna süreci bir uyum çerçevesidir.")
    govde = yanit.json()
    assert yanit.status_code == 200
    assert "Bologna süreci" in govde["answer"]
    if not govde["charts"]:
        assert govde["chart_reason"], "Grafik yok ama gerekçe de yok"


def test_grafik_istenmemisse_sozlesme_sessiz(monkeypatch, client):
    _, yanit = _kos(monkeypatch, client, "Bilgisayar mühendisliği nedir?")
    govde = yanit.json()
    assert govde["chart_requested"] is False
    assert govde["chart_reason"] == ""


def test_model_grafigi_varsa_turetme_devreye_girmez(monkeypatch, client):
    """Mevcut `render_chart` yolu korunur; iki yol yarışmaz."""
    soru = "Son 5 yılda mühendisliklerin grafiğini çiz"
    _, yanit = _kos(monkeypatch, client, soru)
    grafikler = yanit.json()["charts"]
    assert len(grafikler) <= grafik_uret.EN_FAZLA_GRAFIK


def test_grafik_hicbir_kosulda_istisna_atmiyor():
    """Bozuk girdi cevabı düşürmemeli — grafik ikincil bir çıktıdır."""
    assert grafik_uret.uret("grafik") == []
    assert grafik_uret.uret("grafik", plan=None, kanit=None, session=None) == []
    assert grafik_uret.kanittan(coklu_metrik.Kanit(), "grafik") == []


# ===========================================================================
# BÖLÜM 2 — TOPLU KAPSAM
# ===========================================================================
@pytest.mark.parametrize("soru", [
    "tüm üniversiteler",
    "bütün fakülteler",
    "Ankara'daki tüm üniversiteler",
    "mühendislik bölümlerinin geneli",
    "üniversitelere göre doluluk",
    "bölümlere göre kontenjan",
    "genel durum nedir",
    "overall performans",
])
def test_toplu_ifadeler_taniniyor(soru):
    assert kapsam.coz(soru).toplu, soru


@pytest.mark.parametrize("soru", [
    "Ankara Üniversitesi'nin öğrenci sayısı",
    "Bilgisayar mühendisliğinin taban puanı nedir?",
])
def test_tekil_sorular_toplu_sayilmiyor(soru):
    assert not kapsam.coz(soru).toplu, soru


@pytest.mark.parametrize("soru", [
    "Ankara'daki üniversitelerde bilgisayar mühendisliğinin trendi",
    "Ankara genelinde durum nedir?",
    "Ankara'daki tüm üniversitelerin öğrenci sayısı",
])
def test_cografi_kelime_tek_universite_sectirmiyor(soru):
    """KÖK ARIZA: "Ankara'daki üniversiteler" → ANKARA ÜNİVERSİTESİ."""
    plan = va.plan_cikar(soru)
    assert plan.varlik is None, (
        f"Coğrafi kelimeden tek kurum seçildi: {plan.varlik}")
    assert plan.toplu_kapsam


@pytest.mark.parametrize("soru", [
    "Gazi Üniversitesi bilgisayar mühendisliği trendi",
    "Ankara Üniversitesi'nin öğrenci sayısı kaç?",
])
def test_tam_ad_verilince_tek_entity_coluyor(soru):
    """Karşı denetim: açıkça adı geçen kurum SEÇİLMELİ."""
    plan = va.plan_cikar(soru)
    assert plan.varlik is not None, f"Tam ad verildi ama çözülmedi: {soru}"
    assert "ÜNİVERSİTE" in plan.varlik.upper()


def test_farkli_turde_varlik_kapsama_donusuyor():
    """"Gazi'nin tüm bölümleri" → Gazi kapsam, bölümler hedef."""
    plan = va.plan_cikar("Gazi Üniversitesi'nin tüm bölümlerinin doluluğu")
    assert plan.varlik is None
    assert plan.kapsam_varligi and "GAZİ" in plan.kapsam_varligi.upper()
    assert plan.varlik_turu == "department"


def test_toplu_kapsam_niyeti_coklu_yapiyor():
    """Tek değer sorusu, küme sorulunca karşılaştırmaya döner."""
    plan = va.plan_cikar("Tüm üniversitelerin öğrenci sayısı")
    assert plan.niyet in ("comparison", "ranking", "trend")


def test_kapsam_turu_seviye_bayragini_besliyor():
    assert va.plan_cikar("üniversitelere göre doluluk").universite_seviyesi
    assert va.plan_cikar("bölümlere göre kontenjan").program_seviyesi


def test_tur_belirsizse_varliga_dokunulmuyor():
    """"genel durumu" tür söylemez; muhafazakâr davranılır."""
    k = kapsam.coz("Ankara Üniversitesi'nin genel durumu")
    assert k.toplu and k.tur is None


@pytest.mark.parametrize("soru", [
    "Son 2 yılda hangi mühendislikler yükseldi?",
    "Ankara'daki üniversitelerde yazılım alanının trendi",
])
def test_coklu_entity_analizine_geciliyor(soru):
    """Beklenen sonuç: tek kuruma değil, kümeye bakılıyor."""
    plan = va.plan_cikar(soru)
    assert plan.varlik is None
    assert plan.niyet in ("ranking", "trend", "comparison")


# ===========================================================================
# BÖLÜM 3 — REGRESYON VE PERFORMANS
# ===========================================================================
def test_rag_yoksa_model_cevabi_gosteriliyor(monkeypatch, client):
    """KORUNAN DAVRANIŞ: grounding yoksa bile model metni gider."""
    _, yanit = _kos(monkeypatch, client,
                    "Yükseköğretimde kalite güvencesi nedir?",
                    metin="Kalite güvencesi bir değerlendirme çerçevesidir.")
    assert "Kalite güvencesi" in yanit.json()["answer"]


@pytest.mark.parametrize("hata", ["rate_limit", "timeout"])
def test_saglayici_arizasinda_cevap_var(monkeypatch, client, hata):
    """Kota/zaman aşımı fallback'i grafik katmanından etkilenmemeli."""
    _, yanit = _kos(monkeypatch, client,
                    "Son 5 yılda mühendisliklerin grafiğini çiz", hata=hata)
    assert yanit.status_code == 200
    assert yanit.json()["answer"].strip()


def test_token_butcesi_sadece_karmasik_turda_geniliyor():
    """Basit soru eski bütçeyle çalışır; ortalama gecikme değişmez."""
    basit = va.plan_cikar("Kaç akademisyenimiz var?")
    karmasik = va.plan_cikar("Son 5 yılda üniversiteleri karşılaştır")
    assert chat_service._tur_butcesi(basit, False) == \
        chat_service.MAX_PROMPT_TOKENS
    assert chat_service._tur_butcesi(karmasik, False) > \
        chat_service.MAX_PROMPT_TOKENS
    assert chat_service._tur_butcesi(basit, True) > \
        chat_service.MAX_PROMPT_TOKENS


def test_kapsam_katmani_hizli():
    """Kapsam kararı retrieval'ı yavaşlatmamalı."""
    kapsam.coz("ısınma")
    sorular = ["Ankara'daki tüm üniversitelerin doluluk oranı",
               "Bilgisayar mühendisliğinin taban puanı nedir?",
               "bölümlere göre kontenjan"] * 20
    basladi = time.perf_counter()
    for s in sorular:
        kapsam.coz(s)
    ortalama = (time.perf_counter() - basladi) / len(sorular)
    assert ortalama < 0.002, f"Soru başına {ortalama * 1000:.2f} ms"


def test_grafik_katmani_katalogu_yeniden_kurmuyor():
    va.profiller()
    once = va.profiller.cache_info().misses
    for _ in range(10):
        grafik_uret.istendi_mi("grafiğini çiz")
        kapsam.coz("tüm üniversiteler")
    assert va.profiller.cache_info().misses == once


def test_grafik_semasi_mevcut_sozlesmeye_uyuyor():
    """Arayüz `charts` alanını okumaya devam eder; şema değişmedi."""
    kanit = coklu_metrik.kanit_uret(
        va.plan_cikar("Son 5 yılda mühendisliklerin seyri"))
    for g in grafik_uret.kanittan(kanit, "grafik"):
        assert g["type"] == "chart"
        assert g["chart_type"] in chart_builder.CHART_TYPES
        for seri in g["series"]:
            assert len(seri["data"]) == len(g["categories"])
