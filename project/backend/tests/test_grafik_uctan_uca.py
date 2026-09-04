"""Model grafik çizdirdiğinde uç ne döndürüyor — uçtan uca.

Sağlayıcı taklit edilir, GERİ KALAN HER ŞEY GERÇEKTİR: araç kayıt
defteri, araç çalıştırıcı, grafik kurulumu, router, politika katmanı.
Sınanan şey modelin zekâsı değil, "model grafik istedi" kararının
ekrandaki grafiğe kadar bozulmadan gitmesi.

VERİ KAYNAĞI NEDEN SAHTE
------------------------
Kaynak olarak gerçek bir veri aracı değil, bu dosyada tanımlı
`_test_quota_trend` kullanılıyor. Sebep: test veritabanı BOŞTUR
(`conftest.py` her oturumda geçici ve boş bir SQLite açar; geliştirme
verisine dokunmamak için). Gerçek araca bağlansaydı test, grafik yolu
bozulduğu için değil VERİ OLMADIĞI için kırılır ve iki durumu ayırt
edemezdik.

Sahte olan yalnızca satırların NEREDEN geldiği; bu satırların grafiğe
nasıl dönüştüğü baştan sona gerçek koddur. Grafik değerlerinin gerçek
veritabanı kaydıyla birebir aynı olduğu ayrıca `test_grafik_araci.py`
içinde ve canlı sistemde doğrulanmıştır.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from pydantic import BaseModel

from app.services.assistant import chat_service
from app.services.assistant.provider_shared import ProviderHealth
from app.services.assistant.tool_registry import ToolDefinition, registry
from main import app

# --- Deterministik veri kaynağı (bkz. modül başlığı) ----------------
HAM = {
    "program_label": "Bilgisayar Mühendisliği",
    "universities": [
        {"university": "BİLKENT", "series": [
            {"year": 2022, "quota": 1215.0}, {"year": 2023, "quota": 1191.0},
            {"year": 2024, "quota": 1153.0}]},
        {"university": "ODTÜ", "series": [
            {"year": 2022, "quota": 1034.0}, {"year": 2023, "quota": 1014.0},
            {"year": 2024, "quota": 1039.0}]},
        {"university": "HACETTEPE", "series": [
            {"year": 2022, "quota": 1005.0}, {"year": 2023, "quota": 840.0},
            {"year": 2024, "quota": 850.0}]},
    ],
}


class _Girdi(BaseModel):
    program: str = ""


class _Cikti(BaseModel):
    program_label: str
    universities: list


@pytest.fixture(autouse=True)
def _veri_araci():
    """Testin kaynağı — kayıt defterine geçici olarak eklenir."""
    if "_test_quota_trend" not in registry.names():
        registry.register(ToolDefinition(
            name="_test_quota_trend",
            description="Test verisi: program kontenjan trendi.",
            input_model=_Girdi,
            output_model=_Cikti,
            handler=lambda db, p: _Cikti(**HAM),
            timeout_seconds=5.0,
            required_permission=None,
            data_source="Test verisi",
        ))
    yield

# SORUYA METRİK EKLENDİ — DAVRANIŞ BİLİNÇLİ OLARAK DEĞİŞTİ.
# Önceki hâli ("… trendini yorumla") hangi ölçünün trendini sorduğunu
# söylemiyordu. Artık metriksiz analiz soruları netleştirme sorusuyla
# karşılanıyor (bkz. test_belirsiz_sorgu.py): model kendi kafasına göre
# bir ölçü seçip analiz üretmesin diye.
#
# Bu testin KORUDUĞU DEĞER metrik değil, KALIP: "kalıba uymayan bir
# soru da grafik üretebilmeli". O yüzden soru kalıpsız kalır, yalnızca
# hangi ölçünün sorulduğu belirtilir.
SORU = ("son beş yıldaki üniversiteler arasındaki bilgisayar "
        "mühendisliği taban puanı trendini yorumla")


class SahteSaglayici:
    """İki turluk bir model: önce veriyi çeker, sonra çizdirir."""

    name = "sahte"
    model = "sahte-model"

    def __init__(self, cagrilar):
        self._plan = list(cagrilar)
        self.gorulen_araclar = []

    # -- sözleşme --------------------------------------------------
    def etkin_model(self):
        return self.model

    def resolve_model(self):
        return self.model

    def is_available(self):
        return True

    def health(self):
        return ProviderHealth(True, True, (), "hazır")

    def warm_up(self):
        return None

    def chat(self, messages, tools=None):
        return "tamam", ""

    def chat_with_tools(self, messages, tools=None):
        if tools:
            self.gorulen_araclar = [
                (t.get("function") or {}).get("name") for t in tools]
        if self._plan:
            ad, arg = self._plan.pop(0)
            return ([{"name": ad, "arguments": arg, "id": f"c{len(self._plan)}"}],
                    "", "")
        return [], "Kontenjanlar 2022'den bu yana kademeli olarak azalmış.", ""

    def stream_chat(self, messages):
        yield "tamam"


@pytest.fixture(autouse=True)
def _temiz():
    chat_service.reset_conversations()
    yield
    chat_service.reset_conversations()


def _kos(monkeypatch, plan, soru=SORU):
    saglayici = SahteSaglayici(plan)
    monkeypatch.setattr(chat_service, "get_provider", lambda: saglayici)
    with TestClient(app) as client:
        cevap = client.post("/api/assistant/chat", json={"message": soru})
    assert cevap.status_code == 200, cevap.text
    return cevap.json(), saglayici


# ---------------------------------------------------------------------------
# ASIL ARIZA: KALIBA UYMAYAN SORU ARTIK ÇİZİLİYOR
# ---------------------------------------------------------------------------
def test_kalibsiz_soru_grafik_uretir(monkeypatch):
    """Eskiden bu soru "Grafik oluşturulamadı" ile bitiyordu.

    Sekiz regex kalıbının hiçbiri eşleşmiyordu; model doğru aracı
    çağırıp gerçek veriyi almış olmasına rağmen grafik yoktu.
    """
    govde, _ = _kos(monkeypatch, [
        ("_test_quota_trend", {"program": "Bilgisayar Mühendisliği"}),
        ("render_chart", {"source_tool": "_test_quota_trend",
                          "x_field": "year", "y_field": "quota",
                          "series_field": "university", "chart_type": "line",
                          "title": "Kontenjan trendi", "y_label": "Kontenjan"}),
    ])

    assert govde["charts"], "model çizdirdi ama grafik uca ulaşmadı"
    grafik = govde["charts"][0]
    assert grafik["chart_type"] == "line"
    assert len(grafik["series"]) > 1, "üniversiteler ayrı seri olmalı"
    assert "Grafik oluşturulamadı" not in govde["answer"]


def test_grafik_degerleri_kaynak_ciktinin_aynisi(monkeypatch):
    """Ekrandaki her nokta, aracın döndürdüğü satırla birebir aynı olmalı.

    Bu, grafiğin "yaklaşık" ya da yeniden hesaplanmış olmadığının
    kanıtı: tek bir değer kayarsa test kırılır.
    """
    govde, _ = _kos(monkeypatch, [
        ("_test_quota_trend", {"program": "Bilgisayar Mühendisliği"}),
        ("render_chart", {"source_tool": "_test_quota_trend",
                          "x_field": "year", "y_field": "quota",
                          "series_field": "university", "title": "t"}),
    ])
    grafik = govde["charts"][0]
    ciziliyor = {s["name"]: s["data"] for s in grafik["series"]}
    kategoriler = grafik["categories"]

    kontrol = 0
    for u in HAM["universities"]:
        for satir in u["series"]:
            i = kategoriler.index(str(satir["year"]))
            assert ciziliyor[u["university"]][i] == pytest.approx(
                satir["quota"]), f"{u['university']} {satir['year']} kaymış"
            kontrol += 1
    assert kontrol == 9


def test_model_uydurma_alan_verirse_grafik_cizilmez(monkeypatch):
    """Sahte grafik yerine hiç grafik. Sessiz yanlış olmaz."""
    govde, _ = _kos(monkeypatch, [
        ("_test_quota_trend", {"program": "Bilgisayar Mühendisliği"}),
        ("render_chart", {"source_tool": "_test_quota_trend",
                          "x_field": "yil", "y_field": "kontenjan",
                          "title": "t"}),
    ])
    assert govde["charts"] == []


def test_model_uydurma_sayi_gonderemez(monkeypatch):
    """Şemada olmayan bir veri alanı isteği tümden reddedilir."""
    govde, _ = _kos(monkeypatch, [
        ("_test_quota_trend", {"program": "Bilgisayar Mühendisliği"}),
        ("render_chart", {"source_tool": "_test_quota_trend",
                          "x_field": "year", "y_field": "quota", "title": "t",
                          "data": [9999, 8888, 7777]}),
    ])
    assert govde["charts"] == []
    assert "9999" not in json.dumps(govde, ensure_ascii=False)


def test_grafik_araci_modele_daima_sunulur(monkeypatch):
    _, saglayici = _kos(monkeypatch, [
        ("_test_quota_trend", {"program": "Bilgisayar Mühendisliği"})])
    assert "render_chart" in saglayici.gorulen_araclar


def test_grafik_istenmemisse_uyari_yazilmaz(monkeypatch):
    """"Grafik oluşturulamadı" yalnızca grafik İSTENMİŞSE anlamlıdır."""
    govde, _ = _kos(monkeypatch,
                    [("get_program_summary", {})],
                    soru="toplam öğrenci sayımız kaç?")
    assert "Grafik oluşturulamadı" not in govde["answer"]
