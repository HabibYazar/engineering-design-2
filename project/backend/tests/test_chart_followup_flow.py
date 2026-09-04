"""Saf grafik dönüşümü modele ve veritabanına HİÇ gitmez.

CANLI UI'DA ÖLÇÜLEN ARIZA
-------------------------
Kullanıcı bir grafik aldıktan sonra "line yap" dediğinde Gemini YENİ
BİR ANALİZ METNİ üretiyordu. Tür de değişiyordu ama bu bir yan etkiydi:
istek normal bir soru gibi işlenmiş, RAG planı çıkarılmış, model
çağrılmıştı.

KÖK NEDEN
---------
Dönüştürme kancası `chat_service.answer()` çağrıldıktan SONRA
çalışıyordu. Grafiği düzeltiyor ama boşuna yapılan model turunu ve
üretilen yeni metni engellemiyordu. "line yap" bir soru değil, bir
görüntüleme komutudur: içinde ne metrik, ne varlık, ne yıl var. Karar
servis çağrılmadan ÖNCE verilmeliydi.

BU PAKETİN ÖLÇTÜĞÜ ŞEY
----------------------
Önceki testler dönüştürücüye grafiği DOĞRUDAN veriyordu; bu yüzden
gerçek akıştaki kopukluğu göremediler. Buradaki testler yalnızca
`/api/assistant/chat` üzerinden konuşur ve sağlayıcı çağrı sayacını
denetler:

    İSTEK 1  normal grafik sorusu        → charts=[...]
    İSTEK 2  aynı konuşma, "line yap"    → provider çağrısı = 0
    İSTEK 3  aynı konuşma, "pie yap"     → provider çağrısı = 0
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from app.services.assistant import chart_builder, chat_service
from app.services.assistant import grafik_donustur as gd
from app.services.assistant.provider_shared import ProviderHealth

#: Zincirde denenen dönüşümler — canlı UI senaryosunun aynısı.
ZINCIR = (("line yap", "line"), ("pie yap", "pie"),
          ("donut yap", "donut"), ("hbar yap", "hbar"),
          ("bar yap", "bar"))


class SahteSaat:
    def __init__(self): self.simdi = 1000.0
    def __call__(self): return self.simdi
    def ilerlet(self, s): self.simdi += s


class SayanGemini:
    """Çağrıldığında SAYAN sağlayıcı.

    Bu testlerin bütün mesele ettiği şey `cagri` alanıdır: saf bir tür
    değişiminde bu sayaç ARTMAMALIDIR.
    """

    name = "sahte"
    timeout_seconds = 120.0

    def __init__(self, saat, metin: str = "Eğilim yukarı yönlü."):
        self.saat, self.model, self.metin = saat, "birincil", metin
        self.cagri = 0

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
        return [], self.metin, ""


@pytest.fixture()
def saglayici(monkeypatch):
    """Tüm konuşma boyunca AYNI sağlayıcı — sayaç birikerek ölçülür."""
    s = SayanGemini(SahteSaat())
    monkeypatch.setattr(chat_service.time, "monotonic", s.saat)
    monkeypatch.setattr(chat_service, "get_provider", lambda: s)
    monkeypatch.setattr(chat_service, "_alternatif_modeller", lambda: [])
    return s


def _gonder(client, mesaj: str, konusma: Optional[str] = None,
            onceki: Optional[List[Dict[str, Any]]] = None):
    """Gerçek istek. Sahte session YOK."""
    govde: Dict[str, Any] = {"message": mesaj}
    if konusma:
        govde["conversation_id"] = konusma
    if onceki is not None:
        govde["previous_charts"] = onceki
    yanit = client.post("/api/assistant/chat", json=govde)
    assert yanit.status_code == 200, yanit.text
    return yanit.json()


def _grafikli_tur(client, saglayici):
    """İlk tur: gerçek bir grafik üretilir. Üretilemezse test atlanır."""
    ilk = _gonder(client, "Son 5 yılda mühendisliklerin grafiğini çiz")
    if not ilk["charts"]:
        pytest.skip("İlk turda grafik üretilmedi; zincir ölçülemez.")
    return ilk


# ===========================================================================
# 1) SAF DÖNÜŞÜM MODELE GİTMEZ
# ===========================================================================
@pytest.mark.parametrize("mesaj,beklenen", ZINCIR)
def test_saf_donusumde_gemini_cagrilmiyor(client, saglayici, mesaj,
                                          beklenen):
    """EN ÖNEMLİ KRİTER: provider çağrısı ARTMAMALI."""
    ilk = _grafikli_tur(client, saglayici)
    konusma = ilk["conversation_id"]
    once = saglayici.cagri

    sonra = _gonder(client, mesaj, konusma)

    assert saglayici.cagri == once, (
        f"'{mesaj}' için {saglayici.cagri - once} model turu açıldı")
    assert sonra["charts"], f"'{mesaj}' sonrası grafik kayboldu"
    turler = {g["chart_type"] for g in sonra["charts"]}
    assert turler <= {beklenen, "bar"}, turler


def test_zincir_boyunca_tek_model_turu(client, saglayici):
    """Beş dönüşüm üst üste: yalnızca İLK tur modele gider."""
    ilk = _grafikli_tur(client, saglayici)
    konusma = ilk["conversation_id"]
    ilk_tur_cagrisi = saglayici.cagri
    assert ilk_tur_cagrisi >= 1, "İlk tur zaten modele gitmeliydi"

    for mesaj, beklenen in ZINCIR:
        cevap = _gonder(client, mesaj, konusma)
        assert cevap["charts"], mesaj
    assert saglayici.cagri == ilk_tur_cagrisi, (
        f"Zincirde {saglayici.cagri - ilk_tur_cagrisi} fazladan model turu")


def test_saf_donusumde_db_sorgusu_yok(client, saglayici, monkeypatch):
    """RAG ve araç katmanı hiç çalışmamalı."""
    ilk = _grafikli_tur(client, saglayici)
    konusma = ilk["conversation_id"]

    cagrildi = {"kanit": 0, "plan": 0}
    from app.services.assistant import coklu_metrik, veri_ailesi

    _kanit = coklu_metrik.kanit_uret
    _plan = veri_ailesi.plan_cikar

    def sayan_kanit(*a, **k):
        cagrildi["kanit"] += 1
        return _kanit(*a, **k)

    def sayan_plan(*a, **k):
        cagrildi["plan"] += 1
        return _plan(*a, **k)

    monkeypatch.setattr(coklu_metrik, "kanit_uret", sayan_kanit)
    monkeypatch.setattr(veri_ailesi, "plan_cikar", sayan_plan)

    _gonder(client, "line yap", konusma)
    assert cagrildi == {"kanit": 0, "plan": 0}, (
        f"Saf dönüşümde retrieval çalıştı: {cagrildi}")


# ===========================================================================
# 2) VERİ AYNI KALIR
# ===========================================================================
def test_zincir_boyunca_veri_degismiyor(client, saglayici):
    """bar → line → pie → donut → hbar: etiketler ve değerler aynı."""
    ilk = _grafikli_tur(client, saglayici)
    konusma = ilk["conversation_id"]
    ref = ilk["charts"][0]

    for mesaj, _ in ZINCIR:
        cevap = _gonder(client, mesaj, konusma)
        g = cevap["charts"][0]
        assert g["categories"] == ref["categories"], f"{mesaj}: etiket değişti"
        assert g["series"][0]["data"] == ref["series"][0]["data"], (
            f"{mesaj}: değerler değişti")


def test_grafik_sayisi_korunuyor(client, saglayici):
    """Çok metrikli cevapta üç grafik varsa üçü de dönüşmeli."""
    ilk = _grafikli_tur(client, saglayici)
    konusma = ilk["conversation_id"]
    cevap = _gonder(client, "bunları line yap", konusma)
    assert len(cevap["charts"]) == len(ilk["charts"])


# ===========================================================================
# 3) METİN DE DETERMİNİSTİK
# ===========================================================================
@pytest.mark.parametrize("mesaj,parca", [
    ("line yap", "çizgi"), ("pie yap", "pasta"),
    ("donut yap", "halka"), ("hbar yap", "yatay sütun"),
])
def test_cevap_metni_backendden_geliyor(client, saglayici, mesaj, parca):
    ilk = _grafikli_tur(client, saglayici)
    cevap = _gonder(client, mesaj, ilk["conversation_id"])
    assert parca in cevap["answer"], cevap["answer"]
    assert "Eğilim yukarı yönlü" not in cevap["answer"], (
        "Model metni sızdı — sağlayıcı çağrılmış olmalı")


def test_donusumde_yeni_analiz_uretilmiyor(client, saglayici):
    """Cevap kısa ve tek konuludur; yeni bir analiz değildir."""
    ilk = _grafikli_tur(client, saglayici)
    cevap = _gonder(client, "line yap", ilk["conversation_id"])
    assert len(cevap["answer"]) < 200, cevap["answer"]
    assert not cevap["used_tools"]
    assert not cevap["data_sources"]


# ===========================================================================
# 4) ÖNCEKİ GRAFİK KAYNAĞI
# ===========================================================================
def test_istemcinin_gonderdigi_grafik_kullaniliyor(client, saglayici):
    """Sunucu belleği boş olsa bile istemcinin payload'ı yeterli.

    Süreç yeniden başladığında ya da başka bir işçiye düşüldüğünde
    bellek kaybolur; arayüz o grafikleri zaten elinde tutar.
    """
    onceki = [chart_builder._chart(
        "bar", "Başarı sırası", ["2023", "2024", "2025"],
        [{"name": "Başarı sırası", "data": [99614, 92419, 104416],
          "unit": "sıra"}])]
    gd.unut("temiz-konusma")
    once = saglayici.cagri

    cevap = _gonder(client, "line yap", "temiz-konusma", onceki=onceki)

    assert saglayici.cagri == once, "İstemci grafiği varken model çağrıldı"
    assert cevap["charts"][0]["chart_type"] == "line"
    assert cevap["charts"][0]["series"][0]["data"] == [99614, 92419, 104416]


def test_sunucu_bellegi_de_calisiyor(client, saglayici):
    """`previous_charts` göndermeyen eski istemci de desteklenir."""
    ilk = _grafikli_tur(client, saglayici)
    konusma = ilk["conversation_id"]
    once = saglayici.cagri
    cevap = _gonder(client, "donut yap", konusma)      # payload YOK
    assert saglayici.cagri == once
    assert cevap["charts"]


def test_onceki_grafik_yoksa_analiz_uretilmiyor(client, saglayici):
    """Grafik bulunamazsa da yeni bir konu araştırılmaz."""
    gd.unut("bos-konusma")
    once = saglayici.cagri
    cevap = _gonder(client, "line yap", "bos-konusma")
    assert saglayici.cagri == once, "Grafik yokken model çağrıldı"
    assert not cevap["charts"]
    assert "bulunamadı" in cevap["answer"].lower()
    assert cevap["chart_reason"]


# ===========================================================================
# 5) YENİ SORU DÖNÜŞÜM SAYILMAZ
# ===========================================================================
@pytest.mark.parametrize("mesaj", [
    "2025 doluluk oranını line chart göster",
    "son 5 yılın taban puanını çiz",
    "kaç akademisyenimiz var",
])
def test_yeni_soru_normal_akista_kaliyor(client, saglayici, mesaj):
    """Yeni retrieval gerektiren soru dönüştürmeye kaçırılmaz."""
    once = saglayici.cagri
    _gonder(client, mesaj)
    assert saglayici.cagri > once, (
        f"'{mesaj}' dönüşüm sanıldı; model hiç çağrılmadı")


def test_grafik_kodu_korumasi_bozulmadi(client, monkeypatch):
    """Önceki turda eklenen sızıntı koruması yerinde kalmalı."""
    s = SayanGemini(SahteSaat(),
                    'Kadro büyümüştür.\n```render_chart\n'
                    '{"source_tool":"x","x_field":"year"}\n```\nSonuç iyi.')
    monkeypatch.setattr(chat_service.time, "monotonic", s.saat)
    monkeypatch.setattr(chat_service, "get_provider", lambda: s)
    monkeypatch.setattr(chat_service, "_alternatif_modeller", lambda: [])
    cevap = _gonder(client, "Kadro durumu nedir?")
    assert "render_chart" not in cevap["answer"]
    assert "x_field" not in cevap["answer"]
    assert "Kadro büyümüştür" in cevap["answer"]


# ===========================================================================
# 6) ARAYÜZ ÖNCEKİ GRAFİĞİ TAŞIYOR
# ===========================================================================
def test_arayuz_onceki_grafikleri_gonderiyor():
    """Frontend DOM'dan ayrıştırmıyor; yapısal state gönderiyor."""
    import pathlib
    p = (pathlib.Path(__file__).resolve().parents[2]
         / "frontend" / "assets" / "ekranlar.js")
    if not p.exists():
        pytest.skip("Arayüz kaynağı yok.")
    kaynak = p.read_text(encoding="utf-8")
    assert "previous_charts" in kaynak, (
        "Arayüz önceki grafikleri isteğe eklemiyor")
    assert "ASISTAN.mesajlar" in kaynak, "State yerine DOM okunuyor olabilir"


def test_sozlesme_alani_istege_bagli(client, saglayici):
    """Alanı göndermeyen istemci kırılmamalı."""
    cevap = _gonder(client, "Bilgisayar mühendisliği nedir?")
    assert cevap["answer"].strip()
