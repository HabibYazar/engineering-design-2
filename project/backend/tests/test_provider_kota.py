"""Sağlayıcı arızası — tek merkezî politika, tüm sorular için aynı.

CEVAP ÖNCELİĞİ (soru türünden bağımsız)
---------------------------------------
    1. Birincil Gemini cevabı
    2. Yapılandırılmış ALTERNATİF BULUT Gemini modeli
    3. Eldeki yapılandırılmış veriden deterministik cevap
    4. Hiçbiri yoksa dürüst bir sağlayıcı mesajı

YEREL MODEL HİÇBİR AŞAMADA YOKTUR. Ollama ve yerel çıkarım projeden
kaldırıldı; kota bir ağ sınırıdır ve yerel bir modele düşmek, başka bir
sistemin cevabını Gemini cevabı gibi sunmak olurdu.

MUTLAK KURAL
------------
Kota yaşandı ve elde yapılandırılmış veri VAR ise, kullanıcı
"güvenilir bir yanıt üretilemedi" mesajını ASLA görmez.
"""

from __future__ import annotations

from typing import List, Optional

import pytest

from app.services.assistant import chat_service, query_policy
from app.services.assistant.provider_shared import (
    AssistantProviderError, ProviderHealth)

YASAK = "güvenilir bir yanıt üretilemedi"
NOT_ALTERNATIF = "alternatif Gemini modeli"
NOT_VERIDEN = "sistemdeki mevcut verilere dayanarak"
NOT_VERI_YOK = "kullanılabilir kurumsal veri bulunmuyor"

#: Araç sonucu üreten soru — yapılandırılmış veri elde kalır.
VERILI = "Öğrenci kayıtlarının genel durumu nedir"
#: Veritabanında karşılığı olmayan ama AÇIK soru.
VERISIZ = "Yükseköğretimde kalite güvencesi ne anlama gelir?"
#: Metriği belirtilmemiş analitik soru. Artık netleştirme sorusu
#: üretmez; backend çok metrikli kanıt hesaplar (bkz. coklu_metrik).
BELIRSIZ = "Son iki yılda hangi mühendislikler yükseldi?"

SORGU = ("query_canonical_data", {"source": "students", "limit": 20})


class SahteSaat:
    def __init__(self): self.simdi = 1000.0
    def __call__(self): return self.simdi
    def ilerlet(self, s): self.simdi += s


class SahteGemini:
    """Model adına göre davranan sahte sağlayıcı.

    `kotali_modeller`: bu adlarla çağrıldığında kota hatası fırlatır.
    Böylece "birincil model kotada, alternatif çalışıyor" durumu
    gerçekçi biçimde kurulabilir — çağrı sayısı değil, MODEL ADI ayırt
    edicidir.
    """

    name = "sahte"
    timeout_seconds = 120.0

    def __init__(self, saat, *, model: str = "birincil",
                 kotali_modeller: Optional[List[str]] = None,
                 arac: bool = False, hata_turu: str = "rate_limit",
                 metin: str = "Model cevabı."):
        self.saat, self.model = saat, model
        self.kotali = set(kotali_modeller or [])
        self.arac, self.hata_turu, self.metin = arac, hata_turu, metin
        self.cagri = 0
        self.kullanilan_modeller: List[str] = []

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
        self.kullanilan_modeller.append(self.model)
        if self.arac and self.cagri == 1 and tools:
            return ([{"name": SORGU[0], "arguments": SORGU[1], "id": "c1"}],
                    "", "")
        if self.model in self.kotali:
            raise AssistantProviderError("kota", kind=self.hata_turu)
        return [], self.metin, ""


def _kos(monkeypatch, client, soru: str, saglayici: SahteGemini,
         alternatifler: Optional[List[str]] = None):
    monkeypatch.setattr(chat_service.time, "monotonic", saglayici.saat)
    monkeypatch.setattr(chat_service, "get_provider", lambda: saglayici)
    monkeypatch.setattr(chat_service, "_alternatif_modeller",
                        lambda: list(alternatifler or []))
    return client.post("/api/assistant/chat", json={"message": soru})


# --------------------------------------------------------------- A
def test_A_birincil_basarili_kota_notu_yok(monkeypatch, client):
    """Normal çalışmada hiçbir şey değişmez."""
    s = SahteGemini(SahteSaat(), arac=True, metin="Verilere göre cevap.")
    yanit = _kos(monkeypatch, client, VERILI, s, ["yedek"])
    assert yanit.status_code == 200
    metin = yanit.json()["answer"]
    assert "Verilere göre" in metin
    assert "kota" not in metin.lower()
    assert s.kullanilan_modeller == ["birincil"] * s.cagri


# --------------------------------------------------------------- B
def test_B_kotada_alternatif_bulut_modeli(monkeypatch, client):
    """Birincil kotada → yapılandırılmış alternatif model denenir."""
    s = SahteGemini(SahteSaat(), arac=True, kotali_modeller=["birincil"],
                    metin="Alternatif modelin cevabı.")
    yanit = _kos(monkeypatch, client, VERILI, s, ["yedek-model"])
    assert yanit.status_code == 200
    metin = yanit.json()["answer"]
    assert NOT_ALTERNATIF in metin, f"Kota notu yok: {metin[:200]}"
    assert "Alternatif modelin cevabı" in metin
    assert YASAK not in metin
    assert "yedek-model" in s.kullanilan_modeller, (
        f"Alternatif model denenmedi: {s.kullanilan_modeller}")


def test_B2_alternatif_deneme_sonrasi_model_geri_alinir(monkeypatch, client):
    """Sağlayıcının model alanı kalıcı olarak değişmemeli."""
    s = SahteGemini(SahteSaat(), arac=True, kotali_modeller=["birincil"])
    _kos(monkeypatch, client, VERILI, s, ["yedek-model"])
    assert s.model == "birincil", (
        f"Model alanı geri alınmadı: {s.model}")


# --------------------------------------------------------------- C
def test_C_alternatif_yoksa_grounded_deterministik(monkeypatch, client):
    """MUTLAK KURAL: veri varken yasak mesaj görünmez."""
    s = SahteGemini(SahteSaat(), arac=True, kotali_modeller=["birincil"])
    yanit = _kos(monkeypatch, client, VERILI, s, [])   # alternatif YOK
    assert yanit.status_code == 200
    metin = yanit.json()["answer"]
    assert YASAK not in metin, f"Yasak mesaj döndü: {metin[:200]}"
    assert NOT_VERIDEN in metin, f"Kota notu yok: {metin[:200]}"
    # Araç sonucu kaybolmamış olmalı.
    assert yanit.json()["used_tools"], "Sağlayıcı arızası veriyi sildi"


def test_C2_alternatif_de_kotaliysa_grounded(monkeypatch, client):
    """Alternatif de kotaysa yine deterministik cevaba düşülür."""
    s = SahteGemini(SahteSaat(), arac=True,
                    kotali_modeller=["birincil", "yedek-model"])
    yanit = _kos(monkeypatch, client, VERILI, s, ["yedek-model"])
    assert yanit.status_code == 200
    metin = yanit.json()["answer"]
    assert YASAK not in metin
    assert NOT_VERIDEN in metin


# --------------------------------------------------------------- D
def test_D_veri_de_yoksa_durust_saglayici_mesaji(monkeypatch, client):
    """En son durum: ne model ne veri. Sebep dürüstçe söylenir."""
    s = SahteGemini(SahteSaat(), arac=False, kotali_modeller=["birincil"])
    yanit = _kos(monkeypatch, client, VERISIZ, s, [])
    assert yanit.status_code == 200
    metin = yanit.json()["answer"]
    assert NOT_VERI_YOK in metin, f"Dürüst mesaj yok: {metin[:200]}"
    assert YASAK not in metin


# --------------------------------------------------------------- E
def test_E_rag_yok_gemini_calisiyor_model_only_korunur(monkeypatch, client):
    """Kota düzenlemesi model-only davranışını BOZMAMALI."""
    s = SahteGemini(SahteSaat(), arac=False,
                    metin="Kalite güvencesi şu anlama gelir.")
    yanit = _kos(monkeypatch, client, VERISIZ, s, ["yedek"])
    assert yanit.status_code == 200
    metin = yanit.json()["answer"]
    assert "Kalite güvencesi" in metin
    assert "kota" not in metin.lower(), "Kota olmadan kota notu eklendi"


# --------------------------------------------------------------- F
def test_F_timeout_kota_notu_uretmez(monkeypatch, client):
    """Zaman aşımı kota değildir; uyarı eklenmez."""
    s = SahteGemini(SahteSaat(), arac=True, kotali_modeller=["birincil"],
                    hata_turu="timeout", metin="Hızlı denemenin cevabı.")
    yanit = _kos(monkeypatch, client, VERILI, s, ["yedek"])
    assert yanit.status_code == 200
    metin = yanit.json()["answer"]
    assert "kota" not in metin.lower(), f"Zaman aşımında kota notu: {metin[:200]}"


# --------------------------------------------------------------- G
def test_G_bos_cevap_kota_notu_uretmez(monkeypatch, client):
    """Boş cevap kota değildir."""

    class Suskun(SahteGemini):
        def chat_with_tools(self, messages, tools=None):
            self.saat.ilerlet(1.0)
            self.cagri += 1
            self.kullanilan_modeller.append(self.model)
            if self.arac and self.cagri == 1 and tools:
                return ([{"name": SORGU[0], "arguments": SORGU[1],
                          "id": "c1"}], "", "")
            return [], "", ""

    s = Suskun(SahteSaat(), arac=True)
    yanit = _kos(monkeypatch, client, VERILI, s, ["yedek"])
    assert yanit.status_code == 200
    metin = yanit.json()["answer"]
    assert metin.strip()
    assert "kota" not in metin.lower()


# --------------------------------------------------------------- H
def test_H_belirsiz_metrikte_de_yasak_mesaj_yok(monkeypatch, client):
    """Metrik belirtilmemiş soru artık netleştirmeyle KAÇAMAZ.

    DEĞİŞEN VARSAYIM: bu test eskiden "belirsiz soruda sağlayıcı hiç
    çağrılmaz, kullanıcı bir soru görür" diyordu. O davranış kaldırıldı;
    backend artık ölçüleri kendisi buluyor. Dolayısıyla kota politikası
    bu soru türünde de devrede olmalı ve elde kanıt varken kullanıcı
    yasak mesajı görmemeli.
    """
    s = SahteGemini(SahteSaat(), kotali_modeller=["birincil"])
    yanit = _kos(monkeypatch, client, BELIRSIZ, s, [])
    assert yanit.status_code == 200
    metin = yanit.json()["answer"]
    assert YASAK not in metin, f"Yasak mesaj döndü: {metin[:200]}"
    assert "Hangi ölçüyü" not in metin, "Netleştirme sorusu geri geldi"


def test_H2_belirsiz_metrikte_kotasiz_uyari_cikmaz(monkeypatch, client):
    """Kota yoksa kota notu da yok — soru türünden bağımsız."""
    s = SahteGemini(SahteSaat(), metin="Ölçülere göre şu tablo çıkıyor.")
    yanit = _kos(monkeypatch, client, BELIRSIZ, s, ["yedek"])
    assert yanit.status_code == 200
    metin = yanit.json()["answer"]
    assert "kota" not in metin.lower(), f"Kotasız kota notu: {metin[:200]}"


# --------------------------------------------------------------- GENEL
@pytest.mark.parametrize("soru", [VERILI, "Kaç akademisyenimiz var?",
                                  "Bilgisayar mühendisliği ücreti ne kadar?"])
def test_kota_yasak_mesaji_asla_uretmez(monkeypatch, client, soru):
    """MUTLAK REGRESYON — soru türünden bağımsız.

    Tek bir soru dizgisine göre değil, farklı veri ailelerinden
    sorularla ölçülür. Yeni bir soru türü eklendiğinde ayrı bir
    sağlayıcı-arızası dalı yazmak gerekmemeli.
    """
    s = SahteGemini(SahteSaat(), arac=True, kotali_modeller=["birincil"])
    yanit = _kos(monkeypatch, client, soru, s, [])
    assert yanit.status_code == 200
    assert YASAK not in yanit.json()["answer"]


def test_yerel_model_yok():
    """Projede yerel çıkarım YOKTUR ve geri gelmemeli.

    YORUM SATIRLARI HARİÇ TUTULUR: kodda "Ollama kaldırıldı" diye bir
    açıklama olması bir kusur değil, tam tersine kararın kaydıdır.
    Aranan şey ÇALIŞAN kod — import, çağrı, adres.
    """
    import inspect
    kod = [satir.split("#")[0]
           for satir in inspect.getsource(chat_service).splitlines()]
    kaynak = "\n".join(kod).lower()
    for yasak in ("ollama", "llama_cpp", "localhost:11434", "local_model"):
        assert yasak not in kaynak, f"Yerel AI izi: {yasak}"
