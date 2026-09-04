"""İki ayrı durum: "veri yok" ile "soru belirsiz" aynı şey değil.

AYRIM — GÜNCEL HÂLİ
-------------------
    data_not_found   — Soru açık ama hiçbir anlamlı ölçüde kullanılabilir
                       veri yok. Model kendi bilgisiyle cevap verebilir.
                       Bu davranış KORUNUR.

    metric=UNKNOWN   — Sorunun ölçüsü belirtilmemiş: "Son iki yılda hangi
                       mühendislikler yükseldi?" Yükselen NE?

İKİNCİSİNİN DAVRANIŞI DEĞİŞTİ. Eskiden kullanıcıya "Hangi ölçüyü
karşılaştırmamı istersiniz?" diye bir netleştirme sorusu dönüyordu.
Gerekçe şuydu: rastgele bir ölçü seçip analiz etmek, kendinden emin
görünen yanlış bir cevap üretir.

Ama sorun ölçüyü bilmemek değil, TEK ölçü seçme zorunluluğuydu. Artık o
kapsam ve zaman için anlamlı olan ölçülerin hepsi ayrı ayrı hesaplanıp
tek cevapta sunuluyor (bkz. `test_coklu_metrik.py`). Seçim yapılmadığı
için yanlış ölçü seçme riski de ortadan kalkıyor.

BU DOSYA, DEĞİŞİMDE KORUNMASI GEREKENİ ölçer:
  · metrik açıkken akış aynen çalışıyor mu,
  · açık ama verisiz soruda model-only davranışı duruyor mu,
  · belirsiz metrikte plan hâlâ TEK bir kaynağa yapışmıyor mu,
  · netleştirme mekanizması gerçekten kaldırıldı mı.
"""

from __future__ import annotations

from typing import List

import pytest

from app.services.assistant import chat_service, query_policy, veri_ailesi
from app.services.assistant.provider_shared import ProviderHealth

#: Metrik belirtilmemiş sorular — hepsi netleştirme istemeli.
BELIRSIZ = [
    "Son iki yılda hangi mühendislikler yükseldi?",
    "Hangi bölümler geriledi?",
    "Son üç yılda hangi programlar öne çıktı?",
]

#: Metrik açık — normal akış çalışmalı.
ACIK = [
    "Son iki yılda hangi mühendisliklerin doluluğu arttı?",
    "Bilgisayar mühendisliğinin taban puanı nedir?",
]

#: Veritabanında karşılığı olmayan, ama AÇIK sorular. Model kendi
#: bilgisiyle cevap vermeli — netleştirme sorusu ÇIKMAMALI.
VERI_YOK = [
    "Yükseköğretimde kalite güvencesi ne anlama gelir?",
    "Bologna süreci nedir?",
]


class SahteSaat:
    def __init__(self): self.simdi = 1000.0
    def __call__(self): return self.simdi
    def ilerlet(self, s): self.simdi += s


class SahteGemini:
    name = model = "sahte"
    timeout_seconds = 120.0

    def __init__(self, saat, metin="Model cevabı."):
        self.saat, self.metin, self.cagri = saat, metin, 0

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
        return [], self.metin, ""


def _kos(monkeypatch, client, soru: str, metin="Model cevabı."):
    s = SahteGemini(SahteSaat(), metin)
    monkeypatch.setattr(chat_service.time, "monotonic", s.saat)
    monkeypatch.setattr(chat_service, "get_provider", lambda: s)
    return s, client.post("/api/assistant/chat", json={"message": soru})


# ---------------------------------------------------------------- 1
@pytest.mark.parametrize("soru", BELIRSIZ)
def test_belirsiz_metrikte_netlestirme_sorusu_donmuyor(
        monkeypatch, client, soru):
    """DEĞİŞEN DAVRANIŞ. Kullanıcı ölçü seçmeye zorlanmaz."""
    saglayici, yanit = _kos(monkeypatch, client, soru,
                            metin="Ölçülere göre şu tablo çıkıyor.")
    assert yanit.status_code == 200, yanit.text
    metin = yanit.json()["answer"]
    assert "Hangi ölçüyü" not in metin, (
        f"Netleştirme sorusu hâlâ dönüyor: {metin[:200]}")


@pytest.mark.parametrize("soru", BELIRSIZ)
def test_belirsiz_metrikte_model_cagriliyor(monkeypatch, client, soru):
    """Model artık atlanmıyor: yorumlayacak yapılandırılmış kanıt var."""
    saglayici, yanit = _kos(monkeypatch, client, soru)
    assert yanit.status_code == 200
    assert saglayici.cagri >= 1, "Belirsiz metrikte model hiç çağrılmadı"


# ---------------------------------------------------------------- 2
def test_netlestirme_mekanizmasi_kaldirildi():
    """Kaldırılan davranış kazara geri gelmemeli."""
    assert not hasattr(chat_service, "_netlestirme_sorusu")


def test_metrik_katalogu_etiketleri_duruyor():
    """Etiketler netleştirme için değil, artık RAPORLAMA için gerekli.

    Çok metrikli cevapta her ölçü Türkçe adıyla yazılıyor; katalogdaki
    `etiket` alanı boşalırsa kullanıcı "occupancy" görürdü.
    """
    olculebilir = [k for k in veri_ailesi.KAVRAMLAR if k.birim]
    assert len(olculebilir) >= 8
    assert all(k.etiket for k in olculebilir), (
        [k.anahtar for k in olculebilir if not k.etiket])


# ---------------------------------------------------------------- 3
@pytest.mark.parametrize("soru", ACIK)
def test_metrik_acikken_normal_akis(monkeypatch, client, soru):
    """Metrik belliyse netleştirme YAPILMAZ; RAG normal çalışır."""
    saglayici, yanit = _kos(monkeypatch, client, soru,
                            metin="Verilere göre cevap.")
    assert yanit.status_code == 200
    assert saglayici.cagri >= 1, "Açık soruda model çağrılmadı"
    assert "Hangi ölçüyü" not in yanit.json()["answer"]


# ---------------------------------------------------------------- 4
@pytest.mark.parametrize("soru", VERI_YOK)
def test_veri_yoksa_model_only_davranisi_korunuyor(monkeypatch, client, soru):
    """DİĞER DURUM: soru açık, veri yok → model kendi cevabını verir.

    Bu testin koruduğu şey, önceki turda kazanılan davranıştır:
    retrieval başarısızlığı bir cevabı yok etme sebebi değildir.
    Netleştirme ayrımı onu bozmamalı.
    """
    saglayici, yanit = _kos(
        monkeypatch, client, soru,
        metin="Kalite güvencesi, süreçlerin ölçütlere göre "
              "değerlendirilmesidir.")
    assert yanit.status_code == 200
    metin = yanit.json()["answer"]
    assert saglayici.cagri >= 1, "Model çağrılmadı"
    assert "Kalite güvencesi" in metin or "değerlendirilmesidir" in metin, (
        f"Model metni kayboldu: {metin[:200]}")
    assert "Hangi ölçüyü" not in metin, (
        "Açık ama veri bulunmayan soruda netleştirme sorusu çıktı")


# ---------------------------------------------------------------- 5
def test_belirsiz_planla_tek_kaynaga_yapisilmiyor():
    """Belirsiz plan TEK bir kaynak seçmez.

    Kaynak seçimi artık metrik BAŞINA yapılıyor (`coklu_metrik`).
    Belirsiz planın kendisiyle kaynak seçilmesi, o eski "rastgele bir
    ölçü seç" davranışının geri gelmesi demek olurdu.
    """
    for soru in BELIRSIZ:
        plan = veri_ailesi.plan_cikar(soru)
        assert plan.metrik_bilinmiyor, plan.ozet()
        assert not veri_ailesi.aday_kaynaklar(plan), (
            f"Belirsiz soruda kaynak seçildi: {soru!r}")
