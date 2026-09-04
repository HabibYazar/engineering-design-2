"""Grafik türü değiştirme — "bunları line yap", "pie chart olsun".

ÖLÇÜLEN ARIZA
-------------
Kullanıcı grafiği aldıktan sonra türünü değiştirmek istediğinde sistem
çoğu zaman dönüştüremiyor, bazen de "tek bir noktayı temsil ettiği için
çizgi grafik oluşturulamaz" diyordu — oysa ekrandaki grafikte beş
yıllık veri duruyordu.

KÖK NEDEN
---------
Takip mesajı bağımsız bir SORU gibi işleniyordu. "bunları line yap"
cümlesinde ne metrik var, ne varlık, ne yıl; retrieval haklı olarak
hiçbir şey bulamıyor ve "tek nokta" gerekçesi oradan çıkıyordu. Oysa
istenen veri bir önceki cevapta hazır duruyordu.

    A) bar → "bunları line graph yap"     → aynı veri, line
    B) bar → "pie chart yap"              → uygunsa pay grafiği
    C) "aynı şeyi donut olarak göster"    → dönüşüyor
    D) "bar yerine çizgi grafik olsun"    → hedef tür doğru okunuyor
    E) çok metrikli liste → "bunları line yap" → hepsi dönüşüyor
    F) veri paya uygun değil              → alternatif + kısa not
    G) çoklu veri varken "tek nokta" reddi YOK
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import pytest

from app.services.assistant import chart_builder, chat_service
from app.services.assistant import grafik_donustur as gd
from app.services.assistant.provider_shared import ProviderHealth


def _grafik(tur: str = "bar", *, kategoriler=None, veri=None,
            ad: str = "Taban puanı", **ek) -> Dict[str, Any]:
    """Gerçek `chart_builder` şemasıyla grafik — test şeması uydurulmaz."""
    return chart_builder._chart(
        tur, f"{ad} — test",
        kategoriler or ["2021", "2022", "2023", "2024", "2025"],
        [{"name": ad, "data": veri or [380.0, 400.5, 415.2, 392.0, 414.7],
          "unit": "puan"}], **ek)


# ===========================================================================
# NİYET ALGISI
# ===========================================================================
@pytest.mark.parametrize("mesaj,tur", [
    ("bunları line graph yap", "line"),
    ("çizgi grafik olsun", "line"),
    ("bunu pasta grafik yap", "pie"),
    ("pie chart çizebilir misin", "pie"),
    ("donut olsun", "donut"),
    ("halka grafik yap", "donut"),
    ("bunları sütun grafikte göster", "bar"),
    ("aynı şeyi pie olarak ver", "pie"),
    ("yatay bar yap", "hbar"),
    ("aynı veriyi pasta grafikte göster", "pie"),
    ("çizgi grafiğe çevir", "line"),
    ("make it a line chart", "line"),
])
def test_tur_niyeti_okunuyor(mesaj, tur):
    istek = gd.istek_oku(mesaj)
    assert istek.tur == tur, mesaj
    assert istek.sadece_tur, mesaj


@pytest.mark.parametrize("mesaj,tur", [
    ("bar chart yerine line", "line"),
    ("line yerine bar chart", "bar"),
    ("pie yerine çubuk grafik", "bar"),
])
def test_yerine_kalibinda_hedef_tur_kazaniyor(mesaj, tur):
    """"X yerine Y" ifadesinde istenen Y'dir; ilk geçen tür değil."""
    assert gd.istek_oku(mesaj).tur == tur, mesaj


@pytest.mark.parametrize("mesaj", [
    "2025 doluluk oranını bar chart göster",
    "Son 5 yılda mühendisliklerin trendini çiz",
    "kaç akademisyenimiz var",
    "hangi bölümler geriledi",
])
def test_yeni_soru_donusturme_sayilmiyor(mesaj):
    """Yeni bir soruyu dönüştürme sanmak, sorulanı görmezden gelmektir."""
    assert not gd.istek_oku(mesaj).sadece_tur, mesaj


def test_niyet_algisi_hizli():
    """Deterministik ve hafif: model çağrısı yok."""
    gd.istek_oku("ısınma")
    basladi = time.perf_counter()
    for _ in range(2000):
        gd.istek_oku("bunları line graph yap")
    sure = (time.perf_counter() - basladi) / 2000
    assert sure < 0.001, f"Çağrı başına {sure * 1000:.3f} ms"


# ===========================================================================
# A–D · TEKİL DÖNÜŞTÜRME
# ===========================================================================
@pytest.mark.parametrize("hedef", ["line", "bar", "hbar", "pie", "donut"])
def test_A_D_tur_donusuyor_veri_korunuyor(hedef):
    """Veri KOPYALANIR, yeniden hesaplanmaz — metinle ayrışamaz."""
    kaynak = _grafik("bar")
    yeni, _ = gd.donustur(kaynak, hedef)
    assert yeni is not None
    assert yeni["chart_type"] == hedef
    assert yeni["categories"] == kaynak["categories"]
    assert yeni["series"][0]["data"] == kaynak["series"][0]["data"]


def test_ayni_tur_istenirse_grafik_bozulmuyor():
    kaynak = _grafik("line")
    yeni, notu = gd.donustur(kaynak, "line")
    assert yeni["chart_type"] == "line"
    assert notu == ""


def test_desteklenmeyen_tur_reddediliyor():
    assert gd.donustur(_grafik(), "hologram") == (None, "")


def test_bos_grafik_cokme_uretmiyor():
    assert gd.donustur({}, "line") == (None, "")
    assert gd.donustur({"series": []}, "line") == (None, "")
    assert gd.donustur_hepsi([], "line") == ([], [])


# ===========================================================================
# E · ÇOK METRİKLİ LİSTE
# ===========================================================================
def test_E_coklu_grafik_listesi_donusuyor():
    liste = [_grafik("bar", ad="Taban puanı"),
             _grafik("bar", ad="Doluluk oranı", veri=[90.0, 92.0, 95.0,
                                                     97.0, 99.0]),
             _grafik("bar", ad="Kontenjan", veri=[100, 110, 120, 130, 140])]
    yeni, notlar = gd.donustur_hepsi(liste, "line")
    assert len(yeni) == 3
    assert all(g["chart_type"] == "line" for g in yeni)
    assert notlar == []


def test_E2_her_metrik_ayri_grafikte_kaliyor():
    """Dönüştürme metrikleri birleştirmez; bileşik skor üretilmez."""
    liste = [_grafik("bar", ad="Taban puanı"),
             _grafik("bar", ad="Doluluk oranı", veri=[90.0, 92.0, 95.0,
                                                     97.0, 99.0])]
    yeni, _ = gd.donustur_hepsi(liste, "line")
    assert len(yeni) == len(liste)
    assert {g["series"][0]["name"] for g in yeni} == {"Taban puanı",
                                                     "Doluluk oranı"}


def test_E3_uygunsuz_olan_digerlerini_dusurmuyor():
    """Bir grafik paya uygun değilse yalnız o sütuna düşer."""
    liste = [_grafik("bar", ad="Artış", veri=[10.0, -5.0, 20.0, 8.0, 3.0]),
             _grafik("bar", ad="Kontenjan", veri=[100, 110, 120, 130, 140])]
    yeni, notlar = gd.donustur_hepsi(liste, "donut")
    assert len(yeni) == 2
    turler = [g["chart_type"] for g in yeni]
    assert "donut" in turler and "bar" in turler
    assert notlar, "Alternatife düşüldü ama sebep söylenmedi"


# ===========================================================================
# F · UYGUN OLMAYAN DÖNÜŞÜM
# ===========================================================================
def test_F_negatif_deger_paya_donmuyor_alternatif_veriliyor():
    """Negatif değer bir payı temsil edemez — ama cevap çökmez."""
    kaynak = _grafik("bar", veri=[10.0, -5.0, 20.0, 8.0, 3.0])
    yeni, notu = gd.donustur(kaynak, "donut")
    assert yeni is not None, "Uygun olmayan dönüşümde grafik tümden kayboldu"
    assert yeni["chart_type"] == "bar"
    assert "negatif" in notu.lower()
    assert yeni["series"][0]["data"] == kaynak["series"][0]["data"]


def test_F2_tek_dilim_paya_donmuyor():
    kaynak = _grafik("bar", kategoriler=["2025"], veri=[100.0])
    yeni, notu = gd.donustur(kaynak, "donut")
    assert yeni["chart_type"] == "bar"
    assert notu


def test_F3_pay_grafigi_tek_seriye_indirgeniyor():
    """İki seriyi aynı halkaya koymak iki bütünü karıştırmak olurdu."""
    cok_seri = chart_builder._chart(
        "bar", "İki seri", ["A", "B", "C"],
        [{"name": "2024", "data": [10, 20, 30]},
         {"name": "2025", "data": [15, 25, 35]}])
    yeni, _ = gd.donustur(cok_seri, "donut")
    assert yeni["chart_type"] == "donut"
    assert len(yeni["series"]) == 1


def test_F4_oran_verisi_yigilamaz():
    kaynak = _grafik("bar", veri=[90.0, 92.0, 95.0, 97.0, 99.0],
                     additive=False, measure_type="ratio")
    yeni, notu = gd.donustur(kaynak, "stacked")
    assert yeni["chart_type"] == "bar"
    assert notu


# ===========================================================================
# G · YANLIŞ "TEK NOKTA" REDDİ
# ===========================================================================
def test_G_coklu_veri_tek_nokta_sayilmiyor():
    """Beş kategorili bir grafik line'a çevrilebilmeli."""
    kaynak = _grafik("bar")
    assert gd._noktalar(kaynak) == 5
    yeni, notu = gd.donustur(kaynak, "line")
    assert yeni["chart_type"] == "line"
    assert notu == ""


def test_G2_tek_kategori_cok_seri_de_coklu_noktadir():
    """Nokta sayısı kategorilerden değil SERİ DEĞERLERİNDEN sayılır."""
    grafik = chart_builder._chart(
        "bar", "Tek yıl", ["2025"],
        [{"name": "A", "data": [10]}, {"name": "B", "data": [20]},
         {"name": "C", "data": [30]}])
    assert gd._noktalar(grafik) == 3
    yeni, _ = gd.donustur(grafik, "line")
    assert yeni["chart_type"] == "line"


def test_G3_cizilemez_iddiasi_grafik_varken_temizleniyor():
    """Grafik ekranda dururken "çizilemez" cümlesi olgusal olarak yanlış."""
    metin = ("Bu veri tek bir noktayı temsil ettiği için çizgi grafik "
             "oluşturulamaz. Taban puanı 2025'te 414,7'ye yükselmiştir.")
    temiz = gd.celiski_temizle(metin, "line")
    assert "oluşturulamaz" not in temiz
    assert "414,7" in temiz, "Analiz cümlesi de silindi"
    assert "çizgi grafiğine dönüştürüldü" in temiz


def test_G4_celiski_temizleme_analizi_korur():
    """Yalnızca olgusal olarak yanlış iddia düşer; yorum kalır."""
    metin = ("Taban puanı beş yılda 380'den 414,7'ye çıkmıştır. "
             "Bu artış rekabet gücünün yükseldiğini gösterir.")
    temiz = gd.celiski_temizle(metin, "line")
    assert "rekabet gücünün" in temiz
    assert "414,7" in temiz


def test_G5_metin_bossa_onay_cumlesi_veriliyor():
    assert gd.celiski_temizle("", "donut").strip()


# ===========================================================================
# UÇTAN UCA — GERÇEK /api/assistant/chat
# ===========================================================================
class SahteSaat:
    def __init__(self): self.simdi = 1000.0
    def __call__(self): return self.simdi
    def ilerlet(self, s): self.simdi += s


class SahteGemini:
    name = "sahte"
    timeout_seconds = 120.0

    def __init__(self, saat, metin: str = "Eğilim yukarı yönlü."):
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


def _kos(monkeypatch, client, mesaj: str, konusma: Optional[str] = None,
         metin: str = "Eğilim yukarı yönlü."):
    s = SahteGemini(SahteSaat(), metin)
    monkeypatch.setattr(chat_service.time, "monotonic", s.saat)
    monkeypatch.setattr(chat_service, "get_provider", lambda: s)
    monkeypatch.setattr(chat_service, "_alternatif_modeller", lambda: [])
    govde = {"message": mesaj}
    if konusma:
        govde["conversation_id"] = konusma
    return s, client.post("/api/assistant/chat", json=govde)


def test_uctan_uca_takip_mesaji_turu_degistiriyor(monkeypatch, client):
    """A + G: önce grafik, sonra "bunları line yap"."""
    _, ilk = _kos(monkeypatch, client,
                  "Son 5 yılda mühendisliklerin grafiğini çiz")
    assert ilk.status_code == 200
    konusma = ilk.json()["conversation_id"]
    if not ilk.json()["charts"]:
        pytest.skip("İlk turda grafik üretilmedi; dönüşüm ölçülemez.")

    _, ikinci = _kos(monkeypatch, client, "bunları line graph yap", konusma)
    assert ikinci.status_code == 200
    govde = ikinci.json()
    assert govde["charts"], "Takip mesajında grafik kayboldu"
    assert all(g["chart_type"] == "line" for g in govde["charts"])
    assert "oluşturulamaz" not in govde["answer"]


def test_uctan_uca_pay_grafigine_donusum(monkeypatch, client):
    _, ilk = _kos(monkeypatch, client,
                  "Son 5 yılda mühendisliklerin grafiğini çiz")
    konusma = ilk.json()["conversation_id"]
    if not ilk.json()["charts"]:
        pytest.skip("İlk turda grafik üretilmedi.")
    _, ikinci = _kos(monkeypatch, client, "aynı şeyi donut olarak göster",
                     konusma)
    turler = {g["chart_type"] for g in ikinci.json()["charts"]}
    assert turler, "Grafik kayboldu"
    assert turler <= {"donut", "bar"}, turler


def test_uctan_uca_onceki_grafik_yoksa_cevap_bozulmuyor(monkeypatch, client):
    """Dönüştürülecek grafik yoksa cevap çökmez; kısa gerekçe verilir."""
    _, yanit = _kos(monkeypatch, client, "bunları line graph yap")
    assert yanit.status_code == 200
    govde = yanit.json()
    assert govde["answer"].strip()
    if not govde["charts"]:
        assert govde["chart_reason"]


def test_uctan_uca_sozlesme_bozulmuyor(monkeypatch, client):
    """Arayüz `charts` alanını okumaya devam eder; şema aynı."""
    _, ilk = _kos(monkeypatch, client,
                  "Son 5 yılda mühendisliklerin grafiğini çiz")
    konusma = ilk.json()["conversation_id"]
    _, ikinci = _kos(monkeypatch, client, "bunu bar yap", konusma)
    for g in ikinci.json()["charts"]:
        assert g["type"] == "chart"
        assert g["chart_type"] in chart_builder.CHART_TYPES
        for seri in g["series"]:
            assert len(seri["data"]) == len(g["categories"])


def test_uctan_uca_normal_soru_etkilenmiyor(monkeypatch, client):
    """Dönüştürme kancası normal akışa karışmamalı."""
    _, yanit = _kos(monkeypatch, client, "Bilgisayar mühendisliği nedir?",
                    metin="Bilgisayar mühendisliği bir lisans programıdır.")
    govde = yanit.json()
    assert "lisans programıdır" in govde["answer"]
    assert govde["chart_requested"] is False


def test_uctan_uca_ek_model_cagrisi_yok(monkeypatch, client):
    """Dönüştürme için ikinci bir LLM turu açılmaz."""
    _, ilk = _kos(monkeypatch, client,
                  "Son 5 yılda mühendisliklerin grafiğini çiz")
    konusma = ilk.json()["conversation_id"]
    s, _ = _kos(monkeypatch, client, "bunları line yap", konusma)
    assert s.cagri <= 2, f"Dönüştürme için {s.cagri} model turu açıldı"


def test_hafiza_bos_liste_yazmiyor():
    """Grafiksiz bir tur, önceki turun grafiğini silmemeli."""
    gd.unut("t-1")
    gd.hatirla("t-1", [_grafik("bar")])
    gd.hatirla("t-1", [])
    assert gd.son_grafikler("t-1"), "Hafıza boş turda silindi"
    gd.unut("t-1")
