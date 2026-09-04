"""Metrik belirtilmemiş analitik sorular — soru sormak yerine ölçmek.

DEĞİŞEN DAVRANIŞ
----------------
Eskiden `metric=UNKNOWN` bir DURDURUCUYDU: kaynak seçilmiyor, kullanıcıya
"Hangi ölçüyü karşılaştırmamı istersiniz?" diye bir netleştirme sorusu
dönüyordu. Artık aynı durumda o kapsam/zaman için anlamlı olan TÜM
ölçüler bulunur, gerçekten verisi olanlar ayrı ayrı hesaplanır ve tek
cevapta sunulur.

Bu testler SORU METNİNİ değil DAVRANIŞI korur: yeni bir program, yeni
bir tablo ya da başka kelimelerle sorulmuş bir soru bunları kırmaz.

    A) trend + UNKNOWN        → netleştirme yok, çok metrik
    B) ranking + UNKNOWN      → metrik başına AYRI sıralama
    C) comparison + UNKNOWN   → anlamlı ölçüler karşılaştırılıyor
    D) metrik açık            → tek metrik davranışı AYNEN korunuyor
    E) kısmi veri             → olan cevaplanır, tümü başarısız olmaz
    F) hiç veri yok           → ancak burada data_not_found
    G) Gemini kotası          → deterministik grounded cevap, soru yok
"""

from __future__ import annotations

import time
from typing import List, Optional

import pytest

from app.services.assistant import abu_kds_store as store
from app.services.assistant import chat_service, coklu_metrik, query_policy
from app.services.assistant import veri_ailesi as va
from app.services.assistant.provider_shared import (AssistantProviderError,
                                                    ProviderHealth)

pytestmark = pytest.mark.skipif(
    not store.kullanilabilir(),
    reason="abu_kds.db yok; çok metrikli analiz kurulamaz.")

#: Metrik belirtilmemiş sorular. Niyetleri farklı olmalı ki tek bir
#: kalıbın tesadüfen çalışması testi geçirmesin.
TREND = "Son 3 yılda mühendislik programlarının seyri nasıl?"
RANKING = "Son 2 yılda hangi mühendislikler yükseldi, hangileri düştü?"
COMPARISON = ("Son 3 yılda vakıf üniversiteleri ile devlet "
              "üniversiteleri arasında ne fark var?")
BELIRSIZ = (TREND, RANKING, COMPARISON)

#: Metriği AÇIK sorular — davranış değişmemeli.
ACIK = ("Son iki yılda hangi mühendisliklerin doluluğu arttı?",
        "Bilgisayar mühendisliğinin taban puanı nedir?")

#: Veritabanında karşılığı olmayan ama açık soru.
VERI_YOK = "Yükseköğretimde kalite güvencesi ne anlama gelir?"

#: Eski netleştirme cümlesinin imzası. Bir daha görünmemeli.
NETLESTIRME = "Hangi ölçüyü"


class SahteSaat:
    def __init__(self): self.simdi = 1000.0
    def __call__(self): return self.simdi
    def ilerlet(self, s): self.simdi += s


class SahteGemini:
    name = "sahte"
    timeout_seconds = 120.0

    def __init__(self, saat, *, metin: str = "Model yorumu.",
                 hata: Optional[str] = None, model: str = "birincil"):
        self.saat, self.model, self.metin, self.hata = saat, model, metin, hata
        self.cagri = 0
        self.gordugu: List[str] = []

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
        self.gordugu = [str(m.get("content") or "") for m in messages]
        if self.hata:
            raise AssistantProviderError("hata", kind=self.hata)
        return [], self.metin, ""


def _kos(monkeypatch, client, soru: str, saglayici=None, **kw):
    s = saglayici or SahteGemini(SahteSaat(), **kw)
    monkeypatch.setattr(chat_service.time, "monotonic", s.saat)
    monkeypatch.setattr(chat_service, "get_provider", lambda: s)
    monkeypatch.setattr(chat_service, "_alternatif_modeller", lambda: [])
    return s, client.post("/api/assistant/chat", json={"message": soru})


def _kanit_gordu(saglayici) -> bool:
    return any("ÇOK METRİKLİ" in g for g in saglayici.gordugu)


# --------------------------------------------------------------- ORTAK
@pytest.mark.parametrize("soru", BELIRSIZ)
def test_test_verisi_gercekten_belirsiz(soru):
    """Bu paketin ölçtüğü şeyi ölçmeye devam ettiğinin denetimi.

    Soru cümlelerinden biri zamanla metrik içerir hale gelirse (yeni bir
    kavram terimi eklenir), aşağıdaki testler hiçbir şey ölçmeden
    geçmeye başlardı. Önce sorunun UNKNOWN olduğu doğrulanır.
    """
    assert va.plan_cikar(soru).metrik_bilinmiyor, va.plan_cikar(soru).ozet()


@pytest.mark.parametrize("soru", BELIRSIZ)
def test_netlestirme_sorusu_artik_donmuyor(monkeypatch, client, soru):
    """ASIL DEĞİŞİKLİK. Kullanıcı ölçü seçmeye zorlanmaz."""
    s, yanit = _kos(monkeypatch, client, soru)
    assert yanit.status_code == 200, yanit.text
    metin = yanit.json()["answer"]
    assert NETLESTIRME not in metin, f"Netleştirme sorusu döndü: {metin[:200]}"
    assert s.cagri >= 1, "Belirsiz metrikte model hiç çağrılmadı"


@pytest.mark.parametrize("soru", BELIRSIZ)
def test_belirsiz_metrikte_kurumsal_veri_uretiliyor(monkeypatch, client, soru):
    """Cevap artık gerçekten veriye dayanıyor: kaynak ve araç izi var."""
    _, yanit = _kos(monkeypatch, client, soru)
    govde = yanit.json()
    assert govde["used_tools"], "Hiçbir veri okunmadı"
    assert govde["data_sources"], "Kaynak bildirilmedi"
    assert govde["data_source"] == query_policy.SOURCE_INSTITUTIONAL


# --------------------------------------------------------------- A
def test_A_trend_birden_fazla_metrik_analiz_ediliyor(monkeypatch, client):
    """Tek ölçü seçilmez; birden çok ölçü AYRI AYRI hesaplanır."""
    s, yanit = _kos(monkeypatch, client, TREND)
    assert yanit.status_code == 200
    assert _kanit_gordu(s), "Çok metrikli kanıt modele gitmedi"
    plan = va.plan_cikar(TREND)
    kanit = coklu_metrik.kanit_uret(plan)
    assert len({m.metrik for m in kanit.metrikler}) >= 2, kanit.metrikler


def test_A2_her_metrik_kendi_birimiyle_raporlanir():
    """Farklı ölçüler tek bir bileşik skora indirgenmez."""
    kanit = coklu_metrik.kanit_uret(va.plan_cikar(TREND))
    birimler = {m.birim for m in kanit.metrikler}
    assert len(birimler) >= 2, f"Tek boyuta indirgenmiş: {birimler}"
    for m in kanit.metrikler:
        assert m.birim, f"{m.metrik} birimsiz raporlandı"
        assert m.kaynak, f"{m.metrik} kaynaksız"


# --------------------------------------------------------------- B
def test_B_ranking_metrik_basina_ayri_siralama():
    """Sıralama metrik başına ayrıdır — ortalama bir "yükseliş" yoktur."""
    kanit = coklu_metrik.kanit_uret(va.plan_cikar(RANKING))
    siralamali = [m for m in kanit.metrikler if m.siralama]
    assert len(siralamali) >= 2, "Tek metrikte sıralama üretildi"
    for m in siralamali:
        adlar = [a for a, *_ in m.siralama]
        assert len(adlar) == len(set(adlar)), f"{m.metrik} tekrarlı varlık"


def test_B2_siralama_ayni_metrigin_iki_ucundan_gelir():
    """Fark, uydurulmuş bir endeks değil; aynı ölçünün iki yılı."""
    kanit = coklu_metrik.kanit_uret(va.plan_cikar(RANKING))
    for m in kanit.metrikler:
        for _, ilk, son, fark in m.siralama:
            assert abs((son - ilk) - fark) < 0.011, (
                f"{m.metrik}: fark {fark} ≠ {son} - {ilk}")


# --------------------------------------------------------------- C
def test_C_comparison_anlamli_metrikler_secilir():
    """Kurum karşılaştırmasında kurum ölçüleri gelir, derslik gelmez."""
    plan = va.plan_cikar(COMPARISON)
    metrikler = coklu_metrik.uygun_metrikler(plan)
    assert len(metrikler) >= 2, metrikler
    for alakasiz in ("room_capacity", "classroom", "room_schedule"):
        assert alakasiz not in metrikler, (
            f"Kurum sorusuna altyapı ölçüsü karıştı: {metrikler}")


def test_C2_olculemeyen_kavramlar_analize_girmez():
    """Stratejik hedef ya da künye bir eğilim üretemez."""
    for soru in BELIRSIZ:
        metrikler = coklu_metrik.uygun_metrikler(va.plan_cikar(soru))
        for anahtar in metrikler:
            kav = next(k for k in va.KAVRAMLAR if k.anahtar == anahtar)
            assert kav.birim, f"Birimsiz kavram seçildi: {anahtar}"


def test_C3_metrikler_veritabaninda_gercekten_var():
    """Katalogda olup DB'de olmayan bir ölçü analize sokulmaz."""
    mevcut = {a for p in va.profiller().values() for a in p.kavramlar}
    for soru in BELIRSIZ:
        for anahtar in coklu_metrik.uygun_metrikler(va.plan_cikar(soru)):
            assert anahtar in mevcut, f"DB'de olmayan metrik: {anahtar}"


# --------------------------------------------------------------- D
@pytest.mark.parametrize("soru", ACIK)
def test_D_metrik_acikken_davranis_degismiyor(monkeypatch, client, soru):
    """Ölçü belliyse çok metrikli yol HİÇ çalışmaz."""
    plan = va.plan_cikar(soru)
    assert not plan.metrik_bilinmiyor
    s, yanit = _kos(monkeypatch, client, soru, metin="Verilere göre cevap.")
    assert yanit.status_code == 200
    assert not _kanit_gordu(s), "Metrik açıkken çok metrikli kanıt üretildi"
    assert coklu_metrik.ARAC_ADI not in yanit.json()["used_tools"]


# --------------------------------------------------------------- E
def test_E_verisi_olmayan_metrik_cevabi_bozmaz():
    """Bir ölçü eksik diye tüm soru başarısız sayılmaz."""
    kanit = coklu_metrik.kanit_uret(va.plan_cikar(RANKING))
    assert kanit.var, "Kısmi veri tüm cevabı düşürdü"
    if kanit.atlanan:
        # Atlanan ölçü SESSİZCE kaybolmaz; sebebiyle birlikte yazılır.
        govde = coklu_metrik.metin(kanit)
        for ad, _ in kanit.atlanan:
            assert ad in govde, f"{ad} atlandı ama söylenmedi"


def test_E2_veri_yoksa_sifir_uretilmez():
    """NULL sıfır değildir: ölçülmemiş yıl noktaya dönüşmez."""
    for soru in BELIRSIZ:
        for m in coklu_metrik.kanit_uret(va.plan_cikar(soru)).metrikler:
            assert m.noktalar, f"{m.metrik} boş noktayla raporlandı"
            assert all(n > 0 for _, _, n in m.noktalar), (
                f"{m.metrik} kayıtsız yıl üretti")


def test_E3_dengesiz_kapsamda_degisim_uydurulmaz():
    """Yıllar farklı büyüklükte kümelerden geliyorsa fark yazılmaz.

    ÖLÇÜLEN ARIZA: bir yıl 188, diğeri 12 kayıttan hesaplanıyor ve
    aradaki %83'lük düşüş eğilim gibi sunuluyordu. Düşen şey veri
    değil, örneklemdi.
    """
    for soru in BELIRSIZ:
        for m in coklu_metrik.kanit_uret(va.plan_cikar(soru)).metrikler:
            sayilar = [n for _, _, n in m.noktalar]
            if min(sayilar) / max(sayilar) < 0.5:
                assert m.delta is None, (
                    f"{m.metrik}: dengesiz kapsamda değişim hesaplandı")


# --------------------------------------------------------------- F
def test_F_hicbir_metrikte_veri_yoksa_model_only(monkeypatch, client):
    """`data_not_found` yalnız burada geçerli; model kendi cevabını verir."""
    s, yanit = _kos(monkeypatch, client, VERI_YOK,
                    metin="Kalite güvencesi, süreçlerin ölçütlere göre "
                          "değerlendirilmesidir.")
    assert yanit.status_code == 200
    metin = yanit.json()["answer"]
    assert "Kalite güvencesi" in metin, f"Model metni kayboldu: {metin[:200]}"
    assert NETLESTIRME not in metin
    assert not _kanit_gordu(s)


def test_F2_kanit_yoksa_var_bayragi_dusuk():
    """Boş kanıt "veri var" demez — sessiz yanlış cevap üretilmez."""
    bos = coklu_metrik.Kanit()
    assert not bos.var
    assert coklu_metrik.metin(bos) == ""


# --------------------------------------------------------------- G
def test_G_kotada_coklu_metrik_deterministik_cevaba_donusur(
        monkeypatch, client):
    """Sağlayıcı arızası kanıtı silmez ve netleştirme sorusu doğurmaz."""
    s = SahteGemini(SahteSaat(), hata="rate_limit")
    _, yanit = _kos(monkeypatch, client, RANKING, saglayici=s)
    assert yanit.status_code == 200
    metin = yanit.json()["answer"]
    assert NETLESTIRME not in metin
    assert "güvenilir bir yanıt üretilemedi" not in metin
    assert yanit.json()["used_tools"], "Kota kanıtı sildi"
    # Hesaplanmış sayılar kullanıcıya ulaşmalı.
    assert any(m.etiket in metin
               for m in coklu_metrik.kanit_uret(
                   va.plan_cikar(RANKING)).metrikler), metin[:300]


def test_G2_zaman_asiminda_da_kanit_korunur(monkeypatch, client):
    s = SahteGemini(SahteSaat(), hata="timeout")
    _, yanit = _kos(monkeypatch, client, RANKING, saglayici=s)
    assert yanit.status_code == 200
    assert NETLESTIRME not in yanit.json()["answer"]
    assert yanit.json()["answer"].strip()


# --------------------------------------------------------------- PERF
def test_kor_tarama_yok():
    """60 tablo taranmaz; sorgu sayısı seçilen metrik sayısıyla sınırlı."""
    kanit = coklu_metrik.kanit_uret(va.plan_cikar(RANKING))
    assert kanit.sorgu_sayisi <= coklu_metrik.EN_FAZLA_METRIK, (
        f"{kanit.sorgu_sayisi} sorgu yapıldı")
    # Aynı kaynaktan gelen ölçüler tek okumayı paylaşır.
    assert len(kanit.kaynaklar()) <= kanit.sorgu_sayisi


def test_metadata_her_soruda_yeniden_kurulmuyor():
    va.profiller()
    once = va.profiller.cache_info().misses
    for soru in BELIRSIZ:
        coklu_metrik.uygun_metrikler(va.plan_cikar(soru))
    assert va.profiller.cache_info().misses == once, "Metadata yeniden kuruldu"


def test_coklu_metrik_hizli():
    """SQL dahil; Gemini hariç. Cömert tavan — aşarsa kör tarama vardır."""
    va.profiller()
    coklu_metrik.kanit_uret(va.plan_cikar(RANKING))    # ısınma
    basladi = time.perf_counter()
    for soru in BELIRSIZ:
        coklu_metrik.kanit_uret(va.plan_cikar(soru))
    ortalama = (time.perf_counter() - basladi) / len(BELIRSIZ)
    assert ortalama < 1.0, f"Sorgu başına {ortalama * 1000:.0f} ms"


def test_netlestirme_yardimcisi_kaldirildi():
    """Metrik netleştirmesi koddan çıktı; kazara geri gelmemeli."""
    assert not hasattr(chat_service, "_netlestirme_sorusu")
