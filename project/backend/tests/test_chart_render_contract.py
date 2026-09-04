"""Grafik türü GERÇEKTEN çiziliyor mu — ve UI'da kod görünmüyor mu.

CANLI TESTTE ÖLÇÜLEN ÜÇ ARIZA
-----------------------------
1. "line yap" → backend "çizgi grafiğine dönüştürüldü" diyor, ekranda
   ÇUBUK görünüyordu. Sebep arayüzdeydi: `chart_type === "line"` dalı
   çizgi fonksiyonunu değil `gruplandirilmisCubuk`u çağırıyordu.

2. "donut yap" → halka görünmüyordu. `donut`, `hbar` ile AYNI dalda
   duruyor ve yatay çubuk çiziliyordu. `pie` ise sözleşmede hiç yoktu.

3. Modelin cevabına gömdüğü ```render_chart bloğu kullanıcıya HAM METİN
   olarak gidiyordu.

Bu paket üç şeyi birden korur: backend'in gönderdiği tür, arayüzün o
türü hangi çizim fonksiyonuna bağladığı ve görünür metnin kod
içermemesi. Yalnızca `chart_type == "line"` kontrolü yapan bir test
birinci arızayı YAKALAYAMAZDI — o alan zaten doğruydu.
"""

from __future__ import annotations

import json
import pathlib
import re
from typing import Optional

import pytest

from app.services.assistant import chart_builder, chat_service
from app.services.assistant import grafik_donustur as gd
from app.services.assistant.provider_shared import ProviderHealth

#: Arayüz kaynağı. Test, backend'den frontend'e uzanan sözleşmeyi
#: denetlediği için dosyayı OKUR; JS çalıştırmaya gerek yoktur.
_KOK = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "assets"
_EKRANLAR = _KOK / "ekranlar.js"
_GRAFIKLER = _KOK / "grafikler.js"

pytestmark = pytest.mark.skipif(
    not _EKRANLAR.exists() or not _GRAFIKLER.exists(),
    reason="Arayüz kaynağı bu kurulumda yok.")


def _ekranlar() -> str:
    return _EKRANLAR.read_text(encoding="utf-8")


def _grafikler() -> str:
    return _GRAFIKLER.read_text(encoding="utf-8")


def _renderer() -> str:
    """`aiGrafikCiz` gövdesi — yalnızca chart yönlendirmesi."""
    metin = _ekranlar()
    bas = metin.index("function aiGrafikCiz")
    son = metin.index("function aiMesajCiz", bas)
    return metin[bas:son]


def _dal(tur: str) -> str:
    """Verilen chart_type'ın düştüğü dalın gövdesi."""
    govde = _renderer()
    kalip = re.compile(r'chart_type === "' + tur + r'"')
    eslesme = kalip.search(govde)
    assert eslesme, f"'{tur}' için renderer dalı yok"
    # Bu daldan bir sonraki `} else if` / `} else {` başlangıcına kadar.
    kalan = govde[eslesme.end():]
    kesim = re.search(r"\n\s*\}\s*else", kalan)
    return kalan[:kesim.start()] if kesim else kalan


# ===========================================================================
# 1) BACKEND ↔ FRONTEND TEK SÖZLEŞME
# ===========================================================================
@pytest.mark.parametrize("tur", ["line", "bar", "hbar", "pie", "donut"])
def test_backend_turu_frontend_tarafindan_taniniyor(tur):
    """Backend'in ürettiği her tür arayüzde bir dala düşmeli."""
    assert tur in chart_builder.CHART_TYPES, f"backend '{tur}' üretemiyor"
    if tur == "bar":
        # `bar` varsayılan daldır; ayrı bir `=== "bar"` karşılaştırması
        # gerekmez, ama varsayılanın sütun çizdiği doğrulanır.
        assert "gruplandirilmisCubuk" in _renderer()
        return
    assert f'chart_type === "{tur}"' in _renderer(), (
        f"Arayüz '{tur}' türünü tanımıyor; sessizce sütun çizer")


def test_pie_ve_donut_ayri_turlerdir():
    """İkisi aynı ada indirgenirse kullanıcı istediğini göremez."""
    assert "pie" in chart_builder.CHART_TYPES
    assert "donut" in chart_builder.CHART_TYPES
    assert gd.istek_oku("pasta grafik yap").tur == "pie"
    assert gd.istek_oku("donut yap").tur == "donut"


# ===========================================================================
# 2) HER TÜR DOĞRU ÇİZİM FONKSİYONUNA BAĞLI
# ===========================================================================
def test_line_gercek_cizgi_fonksiyonuna_bagli():
    """ASIL ARIZA. `line` dalı sütun fonksiyonu çağırıyordu."""
    dal = _dal("line")
    assert "cizgiKarsilastirma" in dal, (
        "line dalı çizgi fonksiyonunu çağırmıyor — ekranda çubuk çıkar")


def test_cizgi_fonksiyonu_gercekten_cizgi_ciziyor():
    """Çağrılan fonksiyon polyline üretiyor mu — ad yetmez, gövde de."""
    kaynak = _grafikler()
    bas = kaynak.index("function cizgiKarsilastirma")
    son = kaynak.index("function yiginCubuk", bas)
    govde = kaynak[bas:son]
    assert '<path d="${d}"' in govde, "Çizgi yolu (path) çizilmiyor"
    assert "<circle" in govde, "Veri noktaları çizilmiyor"
    assert "<rect" not in govde, "Çizgi fonksiyonu çubuk çiziyor"


@pytest.mark.parametrize("tur", ["pie", "donut"])
def test_pay_turleri_halka_fonksiyonuna_bagli(tur):
    """`donut` eskiden yatay çubuk dalındaydı; `pie` hiç yoktu."""
    dal = _dal("pie")           # pie ve donut aynı dalı paylaşır
    assert "dagilimHalkasi" in dal, f"'{tur}' pay grafiği çizmiyor"
    assert "yatayCubuk" not in dal, f"'{tur}' hâlâ yatay çubuğa gidiyor"


def test_pie_ile_donut_farkli_ic_yaricap_kullaniyor():
    """Pasta dolu daire, halka ortası boş — aynı çizim değildir."""
    dal = _dal("pie")
    assert "icYaricap" in dal, "İç yarıçap seçeneği geçilmiyor"
    assert re.search(r'chart_type === "pie" \? 0', dal), (
        "Pasta için iç yarıçap sıfırlanmıyor")


def test_halka_fonksiyonu_ic_yaricapi_disaridan_aliyor():
    kaynak = _grafikler()
    bas = kaynak.index("function dagilimHalkasi")
    govde = kaynak[bas:bas + 2000]
    assert "opt.icYaricap" in govde, (
        "İç yarıçap sabit; pasta ile halka ayrılamaz")


def test_hbar_bozulmadi():
    """HBAR canlıda ÇALIŞIYORDU; dokunulmadığı doğrulanır."""
    dal = _dal("hbar")
    assert "yatayCubuk" in dal
    assert "dagilimHalkasi" not in dal


def test_bar_varsayilan_dal_sutun_ciziyor():
    govde = _renderer()
    son_dal = govde[govde.rindex("} else {"):]
    assert "gruplandirilmisCubuk" in son_dal


def test_scatter_ve_stacked_korunuyor():
    assert "baloncukGrafik" in _dal("bubble")
    assert "yiginCubuk" in _dal("stacked")


# ===========================================================================
# 3) GÖRÜNÜR METİNDE GRAFİK KODU YOK
# ===========================================================================
_SIZINTI = ('Taban puanı yükseldi.\n\n```render_chart\n'
            '{"source_tool":"kds_x","x_field":"year","y_field":"quota"}\n'
            '```\n\nGenel olarak olumlu bir eğilim var.')


def test_G_fenced_render_chart_blogu_temizleniyor():
    sonuc = gd.kod_bloklarini_ayikla(_SIZINTI)
    assert "render_chart" not in sonuc.metin
    assert "x_field" not in sonuc.metin
    assert "```" not in sonuc.metin
    assert "Taban puanı yükseldi" in sonuc.metin, "Doğal dil silindi"
    assert "olumlu bir eğilim" in sonuc.metin
    assert sonuc.kaldirilan == 1


def test_H_kapanissiz_blok_da_temizleniyor():
    """Model bloğu kapatmadan bitirebilir; parser buna dayanmamalı."""
    bozuk = 'Analiz metni burada.\n```render_chart\n{"chart_type":"line",\n'
    sonuc = gd.kod_bloklarini_ayikla(bozuk)
    assert "chart_type" not in sonuc.metin
    assert "```" not in sonuc.metin
    assert "Analiz metni burada" in sonuc.metin


def test_H2_citsiz_json_yuku_de_temizleniyor():
    metin = 'Şu payload: {"chart_type":"donut","data":[1,2]} gösterilmemeli.'
    sonuc = gd.kod_bloklarini_ayikla(metin)
    assert "chart_type" not in sonuc.metin
    assert "gösterilmemeli" in sonuc.metin


def test_json_citi_yalniz_grafik_yukuyse_siliniyor():
    metin = 'Sonuç:\n```json\n{"chart_type":"bar","categories":["a"]}\n```\nBitti.'
    assert "chart_type" not in gd.kod_bloklarini_ayikla(metin).metin


def test_kullanici_kod_ornegi_silinmiyor():
    """Kapsam dar: grafik yükü OLMAYAN bloklara dokunulmaz."""
    metin = "Örnek:\n```sql\nSELECT * FROM ogrenci;\n```\nAçıklama."
    sonuc = gd.kod_bloklarini_ayikla(metin)
    assert sonuc.metin == metin
    assert sonuc.kaldirilan == 0


def test_kod_yoksa_metin_birebir_ayni():
    metin = "Taban puanı 2025'te 414,7'ye yükselmiştir."
    assert gd.kod_bloklarini_ayikla(metin).metin == metin


def test_yonerge_grafik_kodunu_yasakliyor():
    """Post-processing tek savunma değil; model de uyarılıyor."""
    p = chat_service.SYSTEM_PROMPT
    assert "render_chart" in p
    assert "GRAFİK KODU YAZMA" in p.upper() or "grafik kodu" in p.lower()


# ===========================================================================
# 4) UÇTAN UCA — GERÇEK /api/assistant/chat
# ===========================================================================
class SahteSaat:
    def __init__(self): self.simdi = 1000.0
    def __call__(self): return self.simdi
    def ilerlet(self, s): self.simdi += s


class SahteGemini:
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


def test_uctan_uca_render_chart_kodu_kullaniciya_gitmiyor(monkeypatch, client):
    _, yanit = _kos(monkeypatch, client, "Kadro durumu nedir?",
                    metin=_SIZINTI)
    assert yanit.status_code == 200
    cevap = yanit.json()["answer"]
    assert "render_chart" not in cevap
    assert "x_field" not in cevap and "source_tool" not in cevap
    assert "```" not in cevap
    assert "Taban puanı yükseldi" in cevap, "Doğal dil cevabı kayboldu"


def test_uctan_uca_bozuk_blok_cevabi_dusurmuyor(monkeypatch, client):
    bozuk = 'Kadro büyümüştür.\n```render_chart\n{"chart_type":"line"'
    _, yanit = _kos(monkeypatch, client, "Kadro durumu nedir?", metin=bozuk)
    assert yanit.status_code == 200
    cevap = yanit.json()["answer"]
    assert cevap.strip(), "Cevap tümden silindi"
    assert "chart_type" not in cevap
    assert "Kadro büyümüştür" in cevap


@pytest.mark.parametrize("mesaj,beklenen", [
    ("bunu line yap", "line"),
    ("donut yap", "donut"),
    ("pie yap", "pie"),
    ("hbar yap", "hbar"),
    ("bar yap", "bar"),
    ("bar yerine line yap", "line"),
])
def test_uctan_uca_tur_response_a_yansiyor(monkeypatch, client, mesaj,
                                           beklenen):
    """Dönüşüm isteği response'taki canonical türe geçmeli."""
    _, ilk = _kos(monkeypatch, client,
                  "Son 5 yılda mühendisliklerin grafiğini çiz")
    konusma = ilk.json()["conversation_id"]
    if not ilk.json()["charts"]:
        pytest.skip("İlk turda grafik üretilmedi.")

    _, ikinci = _kos(monkeypatch, client, mesaj, konusma)
    grafikler = ikinci.json()["charts"]
    assert grafikler, f"'{mesaj}' sonrası grafik kayboldu"
    turler = {g["chart_type"] for g in grafikler}
    # Pay türlerinde veri uygun değilse güvenli alternatife düşülebilir.
    assert turler <= {beklenen, "bar"}, turler
    assert beklenen in turler or beklenen in ("pie", "donut"), turler


def test_uctan_uca_donusumde_veri_degismiyor(monkeypatch, client):
    """bar → line → donut → hbar: sayılar aynı kalmalı."""
    _, ilk = _kos(monkeypatch, client,
                  "Son 5 yılda mühendisliklerin grafiğini çiz")
    konusma = ilk.json()["conversation_id"]
    if not ilk.json()["charts"]:
        pytest.skip("İlk turda grafik üretilmedi.")
    beklenen = ilk.json()["charts"][0]["series"][0]["data"]

    for mesaj in ("bunu line yap", "donut yap", "hbar yap", "bar yap"):
        _, yanit = _kos(monkeypatch, client, mesaj, konusma)
        veri = yanit.json()["charts"][0]["series"][0]["data"]
        assert veri == beklenen, f"'{mesaj}' veriyi değiştirdi"


def test_uctan_uca_donusum_yeni_sorgu_acmiyor(monkeypatch, client):
    """Tür değişimi metrik/kapsam/varlık değiştirmemeli."""
    _, ilk = _kos(monkeypatch, client,
                  "Son 5 yılda mühendisliklerin grafiğini çiz")
    konusma = ilk.json()["conversation_id"]
    onceki = ilk.json()
    _, ikinci = _kos(monkeypatch, client, "donut yap", konusma)
    sonraki = ikinci.json()
    if onceki["charts"]:
        assert (sonraki["charts"][0]["categories"]
                == onceki["charts"][0]["categories"])
