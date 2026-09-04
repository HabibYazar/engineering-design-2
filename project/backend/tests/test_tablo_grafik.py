"""Önceki cevapta GRAFİK yoksa ama VERİ varsa yine grafik çizilir.

ÖLÇÜLEN ARIZA
-------------
Kullanıcı beş satırlık bir taban puan tablosu içeren cevap aldı, sonra
"line yap" dedi. Sistem "Önceki grafiğin verisi bu konuşmada
bulunamadı" dedi.

Cevap yanlıştı çünkü ARANAN ŞEY YANLIŞTI: dönüştürme yalnızca önceki
GRAFİĞİ arıyordu. Ekranda grafik yoktu, TABLO vardı — ve o tablo
pekâlâ çizilebilir.

KAYNAK ÖNCELİĞİ
---------------
    1. previous_charts        — kullanıcının gördüğü grafik
    2. yapılandırılmış sonuç  — araç/analiz çıktısı
    3. görünür metindeki tablo — SON ÇARE

Metin ayrıştırma en sonda: yapılandırılmış veri elde varken metni
yeniden okumak, aynı sayıyı iki kez yorumlama riskini davet eder.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from app.services.assistant import chart_builder, chat_service
from app.services.assistant import grafik_donustur as gd
from app.services.assistant import tablo_oku
from app.services.assistant.provider_shared import ProviderHealth

#: Canlı UI'da ölçülen cevabın aynısı: grafik YOK, tablo VAR.
TABLOLU_CEVAP = """Ankara'daki en düşük taban puanlı mühendislik programları:

| Üniversite | Bölüm | Yıl | Taban Puan |
|---|---|---|---:|
| Türk Hava Kurumu Üniversitesi | Mekatronik Müh. | 2023 | 302,45 |
| Atılım Üniversitesi | İmalat Müh. | 2023 | 305,12 |
| Çankaya Üniversitesi | Malzeme Bilimi ve Müh. | 2022 | 308,65 |
| Ostim Teknik Üniversitesi | Yazılım Müh. | 2023 | 310,20 |
| Başkent Üniversitesi | Biyomedikal Müh. | 2022 | 312,40 |

Genel olarak vakıf üniversiteleri alt sıralarda yer alıyor."""

BEKLENEN = [302.45, 305.12, 308.65, 310.20, 312.40]
#: Tablo içermeyen, yalnızca sayı geçen düz metin.
DUZ_CEVAP = ("2025 yılında toplam 1.234 öğrenci kayıt oldu ve doluluk "
             "oranı %98,7 olarak gerçekleşti. Bu, geçen yıla göre bir "
             "iyileşmedir.")

ZINCIR = (("line yap", "line"), ("pie yap", "pie"), ("donut yap", "donut"),
          ("bar yap", "bar"), ("hbar yap", "hbar"))


# ===========================================================================
# 1) TÜRKÇE SAYI
# ===========================================================================
@pytest.mark.parametrize("ham,beklenen", [
    ("302,45", 302.45),         # ondalık virgül
    ("1.234,56", 1234.56),      # binlik nokta + ondalık virgül
    ("1234", 1234.0),
    ("1.234.567", 1234567.0),   # yalnız binlik
    ("%98,7", 98.7),
    ("312.40", 312.40),         # İngilizce biçim de okunur
])
def test_turkce_sayi_okunuyor(ham, beklenen):
    """"1.234" ile "1,234" karıştırılırsa sessizce bin kat hata olur."""
    assert tablo_oku.sayi_oku(ham) == pytest.approx(beklenen)


@pytest.mark.parametrize("ham", ["", None, "yok", "-", "abc"])
def test_sayi_olmayan_deger_none_donuyor(ham):
    assert tablo_oku.sayi_oku(ham) is None


# ===========================================================================
# 2) MARKDOWN TABLO
# ===========================================================================
def test_tablo_ayristiriliyor():
    tablolar = tablo_oku.markdown_tablolar(TABLOLU_CEVAP)
    assert len(tablolar) == 1
    t = tablolar[0]
    assert t.basliklar == ["Üniversite", "Bölüm", "Yıl", "Taban Puan"]
    assert len(t.satirlar) == 5


def test_ayrac_satiri_zorunlu_degil():
    """Model biçim satırını atlayabilir; tablo yine tablodur."""
    metin = "| Program | Puan |\n| A | 10 |\n| B | 20 |"
    assert tablo_oku.markdown_tablolar(metin)


def test_etiket_sutunlari_birlestiriliyor():
    g = tablo_oku.tablodan_grafik(
        tablo_oku.markdown_tablolar(TABLOLU_CEVAP)[0], "line")[0]
    assert g["categories"][0] == ("Türk Hava Kurumu Üniversitesi — "
                                 "Mekatronik Müh.")
    assert len(g["categories"]) == 5


def test_yil_sutunu_deger_sanilmiyor():
    """Yılların grafiği bir veri değil, bir takvimdir."""
    g = tablo_oku.tablodan_grafik(
        tablo_oku.markdown_tablolar(TABLOLU_CEVAP)[0], "line")[0]
    assert g["series"][0]["data"] == BEKLENEN
    assert 2023 not in g["series"][0]["data"]


def test_yil_cok_ise_eksen_yil_olur():
    """Aynı programın zaman serisinde eksen yıldır."""
    metin = ("| Program | Yıl | Puan |\n|---|---|---|\n"
             "| Bilgisayar | 2021 | 380 |\n| Bilgisayar | 2022 | 400 |\n"
             "| Bilgisayar | 2023 | 415 |")
    g = tablo_oku.tablodan_grafik(tablo_oku.markdown_tablolar(metin)[0],
                                  "line")[0]
    assert g["categories"] == ["2021", "2022", "2023"]


# ===========================================================================
# 3) GÜVENLİK — HER SAYI GRAFİK DEĞİLDİR
# ===========================================================================
def test_duz_paragraftan_grafik_uretilmiyor():
    """Paragraftaki rastgele sayıları toplamak veri uydurmaktır."""
    assert not tablo_oku.grafiklenebilir("line", metin=DUZ_CEVAP).grafikler


def test_tek_veri_satiri_yetmiyor():
    metin = "| Program | Puan |\n|---|---|\n| A | 10 |"
    assert not tablo_oku.grafiklenebilir("line", metin=metin).grafikler


def test_sayisal_sutun_yoksa_grafik_yok():
    metin = ("| Program | Fakülte |\n|---|---|\n"
             "| A | Mühendislik |\n| B | Fen |")
    assert not tablo_oku.grafiklenebilir("line", metin=metin).grafikler


def test_etiket_sutunu_yoksa_grafik_yok():
    metin = "| Yıl | Dönem |\n|---|---|\n| 2021 | 2022 |\n| 2022 | 2023 |"
    assert not tablo_oku.grafiklenebilir("line", metin=metin).grafikler


def test_bos_girdi_cokme_uretmiyor():
    assert not tablo_oku.grafiklenebilir("line").grafikler
    assert not tablo_oku.grafiklenebilir("line", metin="").grafikler
    assert not tablo_oku.grafiklenebilir("line", yapisal={}).grafikler


# ===========================================================================
# 4) YAPILANDIRILMIŞ VERİ ÖNCELİKLİ
# ===========================================================================
def test_yapisal_veri_metinden_once_geliyor():
    """Elde yapısal veri varken metni yeniden okumak gereksiz risktir."""
    sonuc = tablo_oku.grafiklenebilir(
        "line",
        yapisal={"rows": [{"program": "A", "puan": 10},
                          {"program": "B", "puan": 20}]},
        metin=TABLOLU_CEVAP)
    assert sonuc.kaynak == "structured"
    assert sonuc.grafikler[0]["series"][0]["data"] == [10.0, 20.0]


def test_ic_ice_yapidan_kayit_listesi_bulunuyor():
    """Araç çıktıları farklı adlar kullanır; ad değil YAPI aranır."""
    for sarmal in ("rows", "records", "data", "items"):
        sonuc = tablo_oku.grafiklenebilir(
            "bar", yapisal={"sonuc": {sarmal: [
                {"ad": "A", "deger": 5}, {"ad": "B", "deger": 7}]}})
        assert sonuc.grafikler, sarmal


def test_yapisal_yoksa_metne_dusuluyor():
    sonuc = tablo_oku.grafiklenebilir("line", metin=TABLOLU_CEVAP)
    assert sonuc.kaynak == "markdown_table"
    assert sonuc.satir == 5


# ===========================================================================
# 5) UÇTAN UCA — GERÇEK /api/assistant/chat
# ===========================================================================
class SahteSaat:
    def __init__(self): self.simdi = 1000.0
    def __call__(self): return self.simdi
    def ilerlet(self, s): self.simdi += s


class SayanGemini:
    name = "sahte"
    timeout_seconds = 120.0

    def __init__(self, saat, metin: str):
        self.saat, self.model, self.metin, self.cagri = saat, "birincil", metin, 0

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
def tablolu(monkeypatch):
    """Model TABLO döndürür; grafik üretilmez (chart istenmiyor)."""
    s = SayanGemini(SahteSaat(), TABLOLU_CEVAP)
    monkeypatch.setattr(chat_service.time, "monotonic", s.saat)
    monkeypatch.setattr(chat_service, "get_provider", lambda: s)
    monkeypatch.setattr(chat_service, "_alternatif_modeller", lambda: [])
    return s


def _gonder(client, mesaj, konusma=None, **ek):
    govde = {"message": mesaj}
    if konusma:
        govde["conversation_id"] = konusma
    govde.update(ek)
    yanit = client.post("/api/assistant/chat", json=govde)
    assert yanit.status_code == 200, yanit.text
    return yanit.json()


def _tablolu_tur(client):
    """TURN 1: tablo var, charts BOŞ."""
    ilk = _gonder(client, "Ankara'daki en düşük taban puanlı programlar")
    assert not ilk["charts"], "Bu senaryoda grafik ÜRETİLMEMELİ"
    assert "302,45" in ilk["answer"], "Tablo cevaba gelmemiş"
    return ilk


@pytest.mark.parametrize("mesaj,beklenen", ZINCIR)
def test_grafiksiz_tablodan_grafik_uretiliyor(client, tablolu, mesaj,
                                              beklenen):
    """ANA KRİTER: grafik yok ama tablo var → gerçek grafik."""
    ilk = _tablolu_tur(client)
    once = tablolu.cagri

    sonra = _gonder(client, mesaj, ilk["conversation_id"])

    assert tablolu.cagri == once, f"'{mesaj}' için model çağrıldı"
    assert sonra["charts"], f"'{mesaj}' → grafik üretilmedi"
    turler = {g["chart_type"] for g in sonra["charts"]}
    assert turler <= {beklenen, "bar"}, turler
    assert "bulunamadı" not in sonra["answer"].lower()


def test_tablodan_uretilen_grafikte_veri_dogru(client, tablolu):
    ilk = _tablolu_tur(client)
    sonra = _gonder(client, "line yap", ilk["conversation_id"])
    g = sonra["charts"][0]
    assert g["series"][0]["data"] == BEKLENEN
    assert len(g["categories"]) == 5
    assert "Mekatronik" in g["categories"][0]


def test_zincirde_veri_degismiyor(client, tablolu):
    """line → pie → donut → bar → hbar: aynı beş sayı."""
    ilk = _tablolu_tur(client)
    konusma = ilk["conversation_id"]
    for mesaj, _ in ZINCIR:
        g = _gonder(client, mesaj, konusma)["charts"][0]
        assert g["series"][0]["data"] == BEKLENEN, mesaj


def test_zincirde_hic_model_cagrilmiyor(client, tablolu):
    ilk = _tablolu_tur(client)
    konusma = ilk["conversation_id"]
    once = tablolu.cagri
    for mesaj, _ in ZINCIR:
        _gonder(client, mesaj, konusma)
    assert tablolu.cagri == once, (
        f"Zincirde {tablolu.cagri - once} model turu açıldı")


def test_zincirde_db_sorgusu_yok(client, tablolu, monkeypatch):
    ilk = _tablolu_tur(client)
    sayac = {"n": 0}
    from app.services.assistant import veri_ailesi
    _plan = veri_ailesi.plan_cikar
    monkeypatch.setattr(veri_ailesi, "plan_cikar",
                        lambda *a, **k: (sayac.__setitem__("n", sayac["n"] + 1),
                                         _plan(*a, **k))[1])
    _gonder(client, "line yap", ilk["conversation_id"])
    assert sayac["n"] == 0, "Saf dönüşümde retrieval çalıştı"


def test_cevap_metni_deterministik(client, tablolu):
    ilk = _tablolu_tur(client)
    sonra = _gonder(client, "line yap", ilk["conversation_id"])
    assert "çizgi grafiğine dönüştürüldü" in sonra["answer"]
    assert "Mekatronik" not in sonra["answer"], "Model metni sızdı"


def test_istemcinin_gonderdigi_metin_de_calisiyor(client, tablolu):
    """Sunucu belleği boş olsa bile arayüzün payload'ı yeterli."""
    gd.unut("temiz")
    once = tablolu.cagri
    sonra = _gonder(client, "line yap", "temiz",
                    previous_answer=TABLOLU_CEVAP)
    assert tablolu.cagri == once
    assert sonra["charts"][0]["series"][0]["data"] == BEKLENEN


def test_istemcinin_gonderdigi_yapisal_veri_calisiyor(client, tablolu):
    gd.unut("temiz2")
    once = tablolu.cagri
    sonra = _gonder(client, "bar yap", "temiz2",
                    previous_data={"rows": [{"ad": "A", "deger": 3},
                                            {"ad": "B", "deger": 9}]})
    assert tablolu.cagri == once
    assert sonra["charts"][0]["series"][0]["data"] == [3.0, 9.0]


# ===========================================================================
# 6) GERÇEKTEN VERİ YOKSA DÜRÜST CEVAP
# ===========================================================================
@pytest.fixture()
def duz(monkeypatch):
    s = SayanGemini(SahteSaat(), DUZ_CEVAP)
    monkeypatch.setattr(chat_service.time, "monotonic", s.saat)
    monkeypatch.setattr(chat_service, "get_provider", lambda: s)
    monkeypatch.setattr(chat_service, "_alternatif_modeller", lambda: [])
    return s


def test_grafiklenebilir_veri_yoksa_analiz_uretilmiyor(client, duz):
    """Veri yoksa da yeni bir konu araştırılmaz."""
    ilk = _gonder(client, "Kayıt durumu hakkında bilgi ver")
    once = duz.cagri
    sonra = _gonder(client, "line yap", ilk["conversation_id"])
    assert duz.cagri == once, "Veri yokken model çağrıldı"
    assert not sonra["charts"]
    assert "grafiklenebilir veri bulunamadı" in sonra["answer"].lower()
    assert sonra["chart_reason"]


# ===========================================================================
# 7) KORUNAN DAVRANIŞLAR
# ===========================================================================
def test_onceki_grafik_varsa_o_kullaniliyor(client, tablolu):
    """Zincirin BİRİNCİ halkası hâlâ birinci: tablo ikinci sıradadır."""
    grafik = chart_builder._chart(
        "bar", "Hazır", ["A", "B"], [{"name": "x", "data": [1.0, 2.0]}])
    sonra = _gonder(client, "line yap", "oncelik-testi",
                    previous_charts=[grafik],
                    previous_answer=TABLOLU_CEVAP)
    assert sonra["charts"][0]["series"][0]["data"] == [1.0, 2.0], (
        "Grafik varken tabloya düşüldü")


def test_raw_chart_kodu_hala_temizleniyor(client, monkeypatch):
    s = SayanGemini(SahteSaat(),
                    'Kadro büyümüştür.\n```render_chart\n'
                    '{"source_tool":"x","x_field":"year"}\n```\nSonuç iyi.')
    monkeypatch.setattr(chat_service.time, "monotonic", s.saat)
    monkeypatch.setattr(chat_service, "get_provider", lambda: s)
    monkeypatch.setattr(chat_service, "_alternatif_modeller", lambda: [])
    cevap = _gonder(client, "Kadro durumu nedir?")
    assert "render_chart" not in cevap["answer"]
    assert "Kadro büyümüştür" in cevap["answer"]


def test_arayuz_onceki_cevabi_da_gonderiyor():
    import pathlib
    p = (pathlib.Path(__file__).resolve().parents[2]
         / "frontend" / "assets" / "ekranlar.js")
    if not p.exists():
        pytest.skip("Arayüz kaynağı yok.")
    kaynak = p.read_text(encoding="utf-8")
    assert "previous_answer" in kaynak
    assert "previous_charts" in kaynak
