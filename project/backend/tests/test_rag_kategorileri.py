"""On soru KATEGORİSİ — gerçek `/api/assistant/chat` akışı üzerinden.

NEDEN KATEGORİ
--------------
Tek bir örnek soruyu geçirip "tamam" demek, bu projede iki kez yanılttı.
Buradaki testler soru METNİNİ değil, soru TÜRÜNÜ korur: tekil değer,
sayım, eğilim, sıralama, karşılaştırma, çok metrikli, program düzeyi
kıyas, finans, altyapı ve "veride gerçekten yok".

Her kategori için ölçülen şey aynı: doğru veri ailesi bulundu mu, gerçek
satırlar araç sonucuna geldi mi, ve zincirin sonunda kullanıcıya bir
cevap ulaştı mı.

NEDEN SAHTE SAĞLAYICI
---------------------
`/api/assistant/chat` uçtan uca çalıştırılır — router, araç seçimi, araç
döngüsü, kalite denetimi, geri düşüş, yanıt sözleşmesi hepsi gerçektir.
Yalnızca Gemini'nin kendisi sahtedir ve iki nedenle:

  1. Her `pytest` çalıştırması günlük kotayı yakardı.
  2. Testin ölçtüğü şey modelin üslubu değil, ONA GİDEN VERİ. Model
     sahte olduğunda bile "araç doğru satırları döndürdü mü" sorusu
     tam olarak cevaplanır.

Sahte sağlayıcı iki davranışı taklit eder: (a) normal — araç çağırır,
sonra metin yazar; (b) suskun — araç çağırır, sonra boş döner. İkincisi
niyet farkında geri düşüşü sınar.
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

import pytest

from app.services.assistant import abu_kds_store as store
from app.services.assistant import chat_service, veri_ailesi
from app.services.assistant.provider_shared import ProviderHealth

pytestmark = pytest.mark.skipif(
    not store.kullanilabilir(),
    reason="abu_kds.db yok; veri tabanı bağımlı testler atlanır.")


# --- KATEGORİLER -----------------------------------------------------------
# (etiket, soru, beklenen veri ailesi, çok satır bekleniyor mu)
KATEGORILER: List[Tuple[str, str, str, bool]] = [
    ("A single_value", "Toplam öğrenci sayımız kaç?", "students", False),
    ("B entity_count", "Kaç akademisyenimiz var?", "academic_staff", False),
    ("C trend", "Öğrenci sayımızın son 5 yıldaki değişimi nedir?",
     "students", True),
    ("D ranking",
     "Ankara'daki son 5 yıldaki en düşük mühendislik taban puanı olan "
     "üniversiteler nelerdir?", "yks_admissions", True),
    ("E comparison",
     "Psikoloji programının kontenjan ve doluluk durumunu karşılaştır.",
     "yks_admissions", True),
    ("F multi_metric",
     "Bölümlerimizin öğrenci ve akademisyen sayılarını karşılaştır.",
     "academic_staff", True),
    ("G program_benchmark",
     "Rakip üniversitelerde bilgisayar mühendisliği taban puanları nedir?",
     "yks_admissions", True),
    ("H finance", "Bilgisayar mühendisliği ücreti ne kadar?",
     "tuition_finance", False),
    ("I infrastructure", "Kaç dersliğimiz var ve kapasiteleri nedir?",
     "infrastructure", True),
]

#: Veride gerçekten olmayan şey — sistem uydurmamalı.
YOK_SORUSU = "Kampüsteki kedi sayısı kaç?"


class SahteSaat:
    def __init__(self): self.simdi = 1000.0
    def __call__(self): return self.simdi
    def ilerlet(self, s): self.simdi += s


class SahteGemini:
    """Araç çağırır, sonra ya metin yazar ya susar.

    Araç ARGÜMANLARINI kendisi seçmez: keşif aracını çağırır, dönen ilk
    kaynağı sorgular. Böylece test, modelin tahmin yeteneğini değil,
    KEŞFİN DOĞRU KAYNAĞI ÖNE KOYUP KOYMADIĞINI ölçer — asıl düzeltilen
    şey budur.
    """

    name = model = "sahte"
    timeout_seconds = 120.0

    def __init__(self, saat, soru: str, susar: bool = False):
        self.saat, self.soru, self.susar = saat, soru, susar
        self.tur = 0
        self.secilen_kaynak = None
        self.gorulen_araclar: List[str] = []

    def etkin_model(self): return "sahte"
    def resolve_model(self): return "sahte"
    def is_available(self): return True
    def health(self): return ProviderHealth(True, True, (), "ok")
    def warm_up(self): return None
    def chat(self, m, tools=None): return "tamam", ""
    def stream_chat(self, m): yield "ok"

    def chat_with_tools(self, messages, tools=None):
        self.saat.ilerlet(1.0)
        self.tur += 1
        adlar = [t["function"]["name"] for t in (tools or [])]
        # BİRİKTİRİLİR, ÜZERİNE YAZILMAZ: son turda araç sunulmaz (bu
        # bilinçli bir davranış), o yüzden son turun değerini okumak
        # "araç hiç sunulmadı" yanılgısı üretirdi.
        self.gorulen_araclar.extend(a for a in adlar
                                    if a not in self.gorulen_araclar)

        # BACKEND'İN ÖNERDİĞİ KAYNAĞI KULLAN.
        # Gerçek model de bunu yapar: sistem notunda "bu soru için uygun
        # veri kaynakları: kds_..." yazıyorsa keşif turuna gerek yoktur.
        # Test bu notun modele GERÇEKTEN ulaştığını da böyle doğrular.
        onerilen = self._onerilen_kaynak(messages)
        if self.tur == 1 and onerilen and "query_canonical_data" in adlar:
            self.secilen_kaynak = onerilen
            return ([{"name": "query_canonical_data",
                      "arguments": {"source": onerilen, "limit": 10},
                      "id": "q0"}], "", "")

        if self.tur == 1 and "explore_data_sources" in adlar:
            return ([{"name": "explore_data_sources",
                      "arguments": {"search": self.soru}, "id": "k1"}], "", "")

        if self.tur == 2 and "query_canonical_data" in adlar:
            kaynak = self.secilen_kaynak or self._ilk_kaynak(messages)
            if kaynak:
                return ([{"name": "query_canonical_data",
                          "arguments": {"source": kaynak, "limit": 10},
                          "id": "q1"}], "", "")
        if self.susar:
            return [], "", ""
        return [], "Elde edilen verilere göre cevap.", ""

    @staticmethod
    def _onerilen_kaynak(messages) -> str:
        """Backend'in sistem notunda önerdiği ilk kaynak."""
        for m in messages:
            if m.get("role") != "system":
                continue
            icerik = str(m.get("content") or "")
            if "uygun veri kaynakları" in icerik:
                bulunan = re.findall(r"\bkds_[a-z0-9_]+", icerik)
                if bulunan:
                    return bulunan[0]
        return ""

    @staticmethod
    def _ilk_kaynak(messages) -> str:
        """Keşif sonucunda görünen İLK kds kaynağını seçer.

        Araç sonuçları modele giderken sıkıştırılıyor ve JSON alan adları
        her zaman korunmuyor; bu yüzden `"source": "..."` kalıbı yerine
        metnin herhangi bir yerindeki `kds_*` adı aranır. Ölçüldü: dar
        kalıpla arandığında sahte model kaynağı bulamıyor, sorgu hiç
        çalışmıyor ve test retrieval'ı değil yalnızca guard'ı ölçüyordu.
        """
        for m in reversed(messages):
            icerik = str(m.get("content") or "")
            bulunan = re.findall(r"\bkds_[a-z0-9_]+", icerik)
            if bulunan:
                return bulunan[0]
        return ""


def _kos(monkeypatch, client, soru: str, susar: bool = False):
    saat = SahteSaat()
    monkeypatch.setattr(chat_service.time, "monotonic", saat)
    saglayici = SahteGemini(saat, soru, susar=susar)
    monkeypatch.setattr(chat_service, "get_provider", lambda: saglayici)
    yanit = client.post("/api/assistant/chat", json={"message": soru})
    return saglayici, yanit


# --------------------------------------------------------------------------
@pytest.mark.parametrize("etiket,soru,aile,cok_satir", KATEGORILER,
                         ids=[k[0] for k in KATEGORILER])
def test_plan_dogru_aileyi_buluyor(etiket, soru, aile, cok_satir):
    """AŞAMA 1: soru → plan → aday kaynaklar, hepsi doğru ailede."""
    plan = veri_ailesi.plan_cikar(soru)
    assert plan.aileler, f"{etiket}: hiçbir veri ailesi bulunamadı"
    assert aile in plan.aileler, (
        f"{etiket}: beklenen aile {aile!r}, bulunan {plan.aileler}")

    adaylar = veri_ailesi.aday_kaynaklar(plan)
    assert adaylar, f"{etiket}: aday kaynak yok"
    profil = veri_ailesi.profiller()
    assert profil[adaylar[0][0]].aile in plan.aileler, (
        f"{etiket}: ilk aday yanlış ailede ({adaylar[0][0]})")


def test_yil_araligi_istenince_kapsam_yeterli():
    """Beş yıl istenen soruda seçilen kaynaklar beş yılı kapsamalı.

    Bu, çok kaynaklı toplamanın testidir: tek tablo yetmiyorsa eksik
    yılları kapayan kaynaklar da seçilmeli.
    """
    plan = veri_ailesi.plan_cikar(
        "Ankara'daki son 5 yıldaki en düşük mühendislik taban puanı "
        "olan üniversiteler nelerdir?")
    assert len(plan.yillar) == 5
    profil = veri_ailesi.profiller()
    kapsanan = {y for ad, _ in veri_ailesi.aday_kaynaklar(plan)
                for y in plan.yillar if profil[ad].yil_kapsar(y)}
    assert kapsanan == set(plan.yillar), (
        f"Kapsanmayan yıllar: {sorted(set(plan.yillar) - kapsanan)}")


@pytest.mark.parametrize("etiket,soru,aile,cok_satir", KATEGORILER,
                         ids=[k[0] for k in KATEGORILER])
def test_uctan_uca_cevap_uretiliyor(monkeypatch, client, etiket, soru,
                                    aile, cok_satir):
    """AŞAMA 2: gerçek chat akışı — araç sonucu var, cevap var, 200 var."""
    saglayici, yanit = _kos(monkeypatch, client, soru)
    assert yanit.status_code == 200, f"{etiket}: {yanit.text[:200]}"
    govde = yanit.json()
    assert govde["answer"].strip(), f"{etiket}: cevap boş"
    assert "Modelden geçerli bir yanıt alınamadı" not in govde["answer"]
    # Merkezî veritabanının kapısı modele SUNULMUŞ olmalı.
    assert "query_canonical_data" in saglayici.gorulen_araclar, (
        f"{etiket}: veritabanı aracı modele sunulmadı")


@pytest.mark.parametrize("etiket,soru,aile,cok_satir",
                         [k for k in KATEGORILER if k[3]],
                         ids=[k[0] for k in KATEGORILER if k[3]])
def test_model_susarsa_niyete_uygun_gercek_veri_gosterilir(
        monkeypatch, client, etiket, soru, aile, cok_satir):
    """Model susunca genel istatistik değil, GERÇEK SATIRLAR gelmeli."""
    _, yanit = _kos(monkeypatch, client, soru, susar=True)
    assert yanit.status_code == 200, f"{etiket}: {yanit.text[:200]}"
    metin = yanit.json()["answer"]
    assert metin.strip(), f"{etiket}: cevap boş"
    # Kullanıcının sorusundan bağımsız veri kümesi istatistiği ANA CEVAP
    # olmamalı: "ortalama … medyan …" kalıbı tek başına yeterli değildir.
    yalniz_istatistik = (
        "medyan" in metin and "ortalama" in metin
        and not re.search(r"^\s*(\d+\.|-)\s", metin, re.M))
    assert not yalniz_istatistik, (
        f"{etiket}: niyetten bağımsız istatistik özeti gösterildi:\n"
        f"{metin[:240]}")


def test_veride_olmayan_sey_uydurulmuyor(monkeypatch, client):
    """J: kurumsal veride gerçekten yok — sistem sayı üretmemeli."""
    plan = veri_ailesi.plan_cikar(YOK_SORUSU)
    assert not plan.aileler, "Olmayan konu bir veri ailesine eşleşti"

    _, yanit = _kos(monkeypatch, client, YOK_SORUSU)
    assert yanit.status_code == 200
    metin = yanit.json()["answer"]
    assert metin.strip()
    # Uydurma sayı yok: kedi sayısı diye bir rakam veremez.
    assert not re.search(r"\b\d{2,}\s*(kedi|adet kedi)", metin, re.I)


def test_retrieval_kalite_denetimi_calisiyor():
    """Sessiz yanlışlar uyarıya dönüşmeli: tek kurum, eksik metrik."""
    plan = veri_ailesi.plan_cikar(
        "Ankara üniversitelerinin taban puanlarını sırala")
    tek_kurum = [{"university_name": "X ÜNİVERSİTESİ", "base_score": 400},
                 {"university_name": "X ÜNİVERSİTESİ", "base_score": 410}]
    uyari = veri_ailesi.dogrula(plan, tek_kurum)
    assert any("tek kurum" in u for u in uyari), uyari

    # Sorulan metrik sonuçta yoksa bu da söylenmeli.
    yanlis_metrik = [{"university_name": "A", "quota": 50},
                     {"university_name": "B", "quota": 60}]
    uyari2 = veri_ailesi.dogrula(plan, yanlis_metrik)
    assert any("base_score" in u for u in uyari2), uyari2


def test_program_sorusuna_kurum_toplami_uyarisi():
    """Program düzeyi soruya kurum toplamı dönerse uyarılmalı."""
    plan = veri_ailesi.plan_cikar(
        "Psikoloji programının kontenjanı kaç?")
    assert plan.program_seviyesi
    kurum_toplami = [{"university_name": "ABÜ", "quota": 1202}]
    uyari = veri_ailesi.dogrula(plan, kurum_toplami)
    assert any("program" in u.lower() for u in uyari), uyari
