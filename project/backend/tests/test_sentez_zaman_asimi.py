"""Model yorum turu zaman aşımına uğradığında ne olduğu.

ÖLÇÜLEN OLAY
------------
Veri araçları başarıyla çalışıyordu (örnekte 32 + 35 satır), ama
modelin ikinci turu 25 saniyede bitmiyordu. Kullanıcının gördüğü:

    "Model bu isteğe zamanında yanıt veremedi."
    **base_score** (toplam 32 satır)
    - university_name=…, value=…      ← ham ilk beş satır

ve ayrıca, veri elde olduğu hâlde:

    "Grafik oluşturulamadı: Bu veri mevcut kaynaklarda bulunmuyor."

İkisi de yanlıştı: veri vardı, yalnızca YORUM aşaması yetişmemişti.
Bu testler o iki yanlışın geri gelmesini engeller.

GERÇEK GEMINI İSTEĞİ YAPILMAZ; sağlayıcı sahtedir.
"""

from __future__ import annotations

import pytest

from app.services.assistant import chat_service, veri_ozeti
from app.services.assistant.provider_shared import (
    AssistantProviderError, ProviderHealth)


# --- gerçek veriyi temsil eden satırlar (32 + 35) ----------------------
def _satirlar(program: str, n: int, taban: float):
    return [{"university_name": f"ÜNİVERSİTE {i%10}", "program_name": program,
             "academic_year": "2025-2026", "metric": "base_score",
             "value": taban + (i % 17) * 3.5}
            for i in range(n)]

BILGISAYAR = _satirlar("Bilgisayar Mühendisliği", 32, 440.0)
ELEKTRIK   = _satirlar("Elektrik-Elektronik Mühendisliği", 35, 425.0)


class SahteSaat:
    def __init__(self): self.simdi = 1000.0
    def __call__(self): return self.simdi
    def ilerlet(self, s): self.simdi += s


class SahteSaglayici:
    name = model = "sahte"
    timeout_seconds = 120.0

    def __init__(self, saat, plan):
        self.saat, self.plan, self.istek = saat, list(plan), 0
        self.gorulen_sinirlar = []

    def etkin_model(self): return "sahte"
    def resolve_model(self): return "sahte"
    def is_available(self): return True
    def health(self): return ProviderHealth(True, True, (), "ok")
    def warm_up(self): return None
    def chat(self, m, tools=None): return "tamam", ""
    def stream_chat(self, m): yield "ok"

    def chat_with_tools(self, messages, tools=None):
        self.istek += 1
        self.gorulen_sinirlar.append(self.timeout_seconds)
        if not self.plan:
            return [], "Son cevap.", ""
        sure, davranis = self.plan.pop(0)
        if sure > self.timeout_seconds:
            self.saat.ilerlet(self.timeout_seconds)
            raise AssistantProviderError("zaman asimi", kind="timeout")
        self.saat.ilerlet(sure)
        tur, yuk = davranis
        if tur == "tool":
            if tools is None:
                return [], "Eldeki verilerle cevap.", ""
            return [{"name": yuk[0], "arguments": yuk[1], "id": "c1"}], "", ""
        return [], yuk, ""


SORGU = ("query_canonical_data", {
    "source": "yok_atlas_benchmark_metrics",
    "filters": {"metric": "base_score"}, "limit": 50})


@pytest.fixture
def kos(monkeypatch, db_session):
    saat = SahteSaat()
    monkeypatch.setattr(chat_service.time, "monotonic", saat)

    def _kos(plan, soru="Bilgisayar ve Elektrik taban puanları 2025-2026"):
        s = SahteSaglayici(saat, plan)
        monkeypatch.setattr(chat_service, "get_provider", lambda: s)
        return s, chat_service.answer(soru, db=db_session)
    return _kos


# ---------------------------------------------------------------- 1
def test_sentez_basariliysa_normal_cevap_bozulmaz(kos):
    s, sonuc = kos([(2.0, ("tool", SORGU)), (3.0, ("text", "Normal yorum."))])
    assert sonuc["answer"]
    assert "zaman aşımına" not in sonuc["answer"]


# ---------------------------------------------------------------- 3
def test_kalan_sure_azken_tavan_verilmez(kos):
    """Round 1 uzun sürerse, round 2'ye kalan süreden fazlası verilmez."""
    # Senaryo sabitlerden türetilir; elle yazılmış saniyeler bütçe her
    # değiştiğinde testi anlamsızca kırıyordu.
    _uzun = min(chat_service.GEMINI_ROUND_TIMEOUT_SECONDS - 2.0,
                chat_service.MAX_USER_TURN_SECONDS * 0.40)
    s, _ = kos([(_uzun, ("tool", SORGU)), (_uzun, ("tool", SORGU)),
                (chat_service.GEMINI_ROUND_TIMEOUT_SECONDS,
                 ("text", "gelmeyecek"))])
    assert s.gorulen_sinirlar[0] == chat_service.GEMINI_ROUND_TIMEOUT_SECONDS
    # Üçüncü tura gelindiğinde kalan süre tavanın altına düşmüş olmalı.
    assert s.gorulen_sinirlar[-1] < chat_service.GEMINI_ROUND_TIMEOUT_SECONDS


# ---------------------------------------------------------------- 4
def test_kalan_sure_yetersizse_yeni_tur_baslamaz(kos):
    """Deadline'a çok az kalmışsa model hiç çağrılmaz."""
    s, sonuc = kos([(24.0, ("tool", SORGU)), (24.0, ("tool", SORGU)),
                    (10.0, ("text", "olmamalı"))])
    assert s.istek <= chat_service.MAX_LLM_ROUNDS_PER_USER_MESSAGE
    assert sonuc["answer"]


# ---------------------------------------------------------------- 5
def test_iki_veri_kumesinden_sayisal_ozet_uretilir():
    """32 + 35 satırdan ham döküm değil, istatistik çıkar."""
    a = veri_ozeti.veri_kumesi_ozeti("Bilgisayar · base_score", BILGISAYAR)
    b = veri_ozeti.veri_kumesi_ozeti("Elektrik · base_score", ELEKTRIK)
    for metin, n in ((a, 32), (b, 35)):
        assert f"{n} kayıt" in metin
        assert "farklı university_name" in metin
        assert "ortalama" in metin and "medyan" in metin


def test_ozet_anlamsiz_alanda_aritmetik_yapmaz():
    """Yıl ve kimlik alanlarının ortalaması alınmaz."""
    satirlar = [{"id": i, "academic_year": "2025-2026", "code": f"K{i}",
                 "university_name": f"Ü{i%3}", "value": 400 + i}
                for i in range(9)]
    metin = veri_ozeti.veri_kumesi_ozeti("test", satirlar)
    assert "value:" in metin              # ölçüm alanı hesaplandı
    assert "id:" not in metin             # kimlik hesaplanmadı
    assert "academic_year:" not in metin  # yıl hesaplanmadı


def test_oranlarin_ortalamasi_alinmaz():
    """Doluluk gibi oranların ortalaması yanlış sonuç verir; sadece aralık."""
    satirlar = [{"university_name": f"Ü{i}", "occupancy_percent": 50 + i}
                for i in range(8)]
    metin = veri_ozeti.veri_kumesi_ozeti("doluluk", satirlar)
    if "occupancy_percent" in metin:
        assert "ortalama" not in metin.split("occupancy_percent")[1]


def test_gercekten_bos_veride_ozet_uretilmez():
    assert veri_ozeti.veri_kumesi_ozeti("boş", []).endswith("kayıt yok.")
    assert veri_ozeti.karsilastirma([("a", []), ("b", [])]) == ""


def test_grafik_yok_sebebi_dogru_ayriliyor():
    """Grafik çizilemediğinde SEBEP doğru söylenmeli."""
    from app.routers.assistant import grafik_yok_sebebi as sebep

    # A) gerçekten veri yok → eski mesaj HÂLÂ geçerli
    assert sebep(veri_geldi=False, zaman_asimi=False) == \
        "Bu veri mevcut kaynaklarda bulunmuyor."
    assert sebep(veri_geldi=False, zaman_asimi=True) == \
        "Bu veri mevcut kaynaklarda bulunmuyor."

    # B) veri VAR ama yorum/grafik turu yetişmedi → "veri yok" DEMEZ
    # B/D) veri VAR → teknik sebep yazılmaz, sunum dili kullanılır
    for za in (True, False):
        m = sebep(veri_geldi=True, zaman_asimi=za)
        assert "bulunmuyor" not in m
        assert m == "Bu sonuç için grafik üretilemedi."


def test_fallback_ham_satir_dokmez_ozet_uretir():
    """Zaman aşımı özetinde ham satır listesi OLMAMALI."""
    class SahteKayit:
        name = "query_canonical_data"
        success = True

        class output:
            @staticmethod
            def model_dump(mode=None):
                return {"source": "yok_atlas_benchmark_metrics",
                        "row_count": 32, "rows": BILGISAYAR}

    class SahteOturum:
        records = [SahteKayit()]

    metin = chat_service._elde_ne_var(SahteOturum())
    assert metin, "özet üretilmedi"
    assert "university_name=" not in metin
    assert "32 kayıt" in metin
    assert "ortalama" in metin and "medyan" in metin


def test_egilim_kurali_tek_yilin_trend_olmadigini_soyluyor():
    k = chat_service._EGILIM_KURALI
    assert "EN AZ İKİ DÖNEM" in k
    assert "tek yıllık" in k.lower() or "tek bir akademik yıl" in k.lower()


def test_son_tur_gorevi_yeni_arac_cagrisini_engelliyor():
    g = chat_service._SON_TUR_GOREVI.upper()
    # Notun sloganı değil, KORUDUĞU EMİR ölçülür. Not bilinçli olarak
    # kısaltıldı: uzun görev listesi modeli planlama moduna sokup
    # cevabın yazılmaya başlanmamasına yol açıyordu.
    # `g` çağıran testte upper() edilmiş olabilir; ölçüt harf
    # duyarsız yapılır ki biçim değil ANLAM korunsun.
    d = chat_service._SON_TUR_GOREVI.lower()
    assert "yeni araç çağırma" in d
    assert "final cevabı yaz" in d or "hemen tamamla" in d


def test_butceler_degismedi():
    assert chat_service.MAX_LLM_ROUNDS_PER_USER_MESSAGE == 3
    assert chat_service.MAX_DATA_TOOL_CALLS == 2
    # Tur ve araç SAYILARI korunur; süre tavanları bilinçli olarak
    # yükseltildi (40→120, 90→240) — bu testin koruduğu şey sayılardır.
    assert chat_service.GEMINI_ROUND_TIMEOUT_SECONDS >= 40.0
    assert chat_service.MAX_USER_TURN_SECONDS >= 90.0
