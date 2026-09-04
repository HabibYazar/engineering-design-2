"""Kurumsal kişi adları — uydurma önleme ve güvenli temizleme.

KORUNAN DAVRANIŞ
----------------
Model doğrulanmamış bir kişi adı yazarsa cevabın TAMAMI reddedilmez.
Yalnızca ad, bağlamına uygun genel bir ifadeyle değiştirilir; analiz,
sayılar ve cümlenin geri kalanı aynen kullanıcıya gider.

Bu, tasarımın en kolay bozulan yeri: "isim uydurdu, cevabı at" kuralı
yazmak kısa vadede güvenli görünür ama kullanıcıyı cevapsız bırakır ve
grounded veriyi de yok eder. Aşağıdaki testler tam olarak bunu
engelliyor.

    A) grounded ad          → korunuyor
    B) grounded ad yok      → yalnız ad temizleniyor, gerisi duruyor
    C) grounded + uydurma   → biri kalıyor, diğeri temizleniyor
    D) hiç ad yok           → metin BİREBİR aynı
    E) kurum/bölüm adları   → hiçbiri silinmiyor
    F) RAG yok + model-only → ad temizlenir, model cevabı korunur
    G) kota/zaman aşımı     → sanitizer başka metni bozmuyor
"""

from __future__ import annotations

import time
from typing import List, Optional

import pytest

from app.services.assistant import chat_service, kisi_adi
from app.services.assistant.provider_shared import (AssistantProviderError,
                                                    ProviderHealth)
from app.services.assistant.tool_runner import ToolCallRecord

#: Kurum verisinde bulunmayan, modelin uydurabileceği ad.
UYDURMA = "Prof. Dr. Ahmet Yılmaz"
#: Kanıtta geçtiği varsayılan ad.
GERCEK = "Zeynep Aydın"

#: Kişi adı içermeyen, kurum adlarıyla dolu bir cevap.
KURUMSAL = ("Ankara Bilim Üniversitesi Mühendislik Fakültesi bünyesindeki "
            "Bilgisayar Mühendisliği ve Yazılım Mühendisliği programlarında "
            "doluluk oranı 2025'te %100'e ulaşmıştır.")

SORU = "Bilgisayar mühendisliği kadrosu hakkında bilgi ver"


class SahteSaat:
    def __init__(self): self.simdi = 1000.0
    def __call__(self): return self.simdi
    def ilerlet(self, s): self.simdi += s


class SahteGemini:
    name = "sahte"
    timeout_seconds = 120.0

    def __init__(self, saat, *, metin: str, hata: Optional[str] = None,
                 model: str = "birincil"):
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


def _kos(monkeypatch, client, metin: str, *, soru: str = SORU,
         hata: Optional[str] = None, kanit_adi: Optional[str] = None):
    """Gerçek `/api/assistant/chat` akışı.

    `kanit_adi` verilirse, o ad turun araç kanıtına yazılır — yani
    grounded sayılır. Kanıt gerçek `ToolCallRecord` olarak eklenir;
    böylece sanitizer'ın grounded kümeyi nereden okuduğu da doğrulanmış
    olur.
    """
    s = SahteGemini(SahteSaat(), metin=metin, hata=hata)
    monkeypatch.setattr(chat_service.time, "monotonic", s.saat)
    monkeypatch.setattr(chat_service, "get_provider", lambda: s)
    monkeypatch.setattr(chat_service, "_alternatif_modeller", lambda: [])

    if kanit_adi:
        gercek_session = chat_service.ToolSession

        class KanitliSession(gercek_session):        # type: ignore[misc]
            def __post_init__(self, *a, **k):
                pass

        def _kur(*args, **kwargs):
            oturum = gercek_session(*args, **kwargs)
            oturum.records.append(ToolCallRecord(
                name="query_canonical_data", arguments={},
                success=True,
                content='{"rows": [{"academic_staff_name": "%s"}]}'
                        % kanit_adi,
                data_source="Akademik kadro"))
            return oturum

        monkeypatch.setattr(chat_service, "ToolSession", _kur)
    return s, client.post("/api/assistant/chat", json={"message": soru})


# --------------------------------------------------------------- YÖNERGE
def test_yonerge_kisi_adi_uydurmayi_yasakliyor():
    """İlk savunma katmanı: model daha baştan uyarılıyor."""
    p = chat_service.SYSTEM_PROMPT.lower()
    assert "uydurma" in p and "kişi" in p
    assert "dekan" in p or "bölüm başkanı" in p
    # Kural KİŞİ ile sınırlı: kurum adları serbest kalmalı.
    assert "üniversite, fakülte, bölüm, program" in p


def test_yonerge_modelin_gordugu_mesajlarda(monkeypatch, client):
    """Kural gerçekten MODELE gidiyor mu — dosyada durması yetmez."""
    s, _ = _kos(monkeypatch, client, "Kadro hakkında genel bilgi.")
    assert any("ASLA UYDURMA" in g for g in s.gordugu)


# --------------------------------------------------------------- A
def test_A_grounded_ad_korunuyor(monkeypatch, client):
    """Kanıtta geçen gerçek ad silinmez — aşırı sansür de bir arızadır."""
    metin = f"Bölüm kadrosunda {GERCEK} görev yapmaktadır."
    _, yanit = _kos(monkeypatch, client, metin, kanit_adi=GERCEK)
    assert yanit.status_code == 200
    assert GERCEK in yanit.json()["answer"]


def test_A2_grounded_ad_unvanla_yazilsa_da_korunuyor():
    """Unvan farkı ada dokunmamalı: "Prof. Dr. X" ile "X" aynı kişidir."""
    grounded = {kisi_adi.normalize(GERCEK)}
    sonuc = kisi_adi.sanitize(
        f"Kadroda Prof. Dr. {GERCEK} bulunmaktadır.", grounded)
    assert GERCEK in sonuc.metin
    assert sonuc.temizlenen == 0
    assert "Prof. Dr." in sonuc.metin, "Unvan koparılıp ad yalnız bırakıldı"


@pytest.mark.parametrize("yazim", [
    "ZEYNEP AYDIN", "zeynep aydın", "Zeynep  Aydın", "Zeynep Aydın'ın"])
def test_A3_yazim_farki_ayni_kisi_sayilir(yazim):
    """Büyük/küçük harf, Türkçe I/İ, fazla boşluk ve ek aynı kişidir."""
    assert kisi_adi.normalize(yazim) == kisi_adi.normalize(GERCEK)


def test_A4_benzer_ad_ayni_kisi_sanilmaz():
    """Gevşek eşleştirme, doğrulanmamış adı doğrulanmış gibi geçirirdi."""
    assert kisi_adi.normalize("Zeynep Aydıner") != kisi_adi.normalize(GERCEK)


# --------------------------------------------------------------- B
def test_B_ungrounded_ad_temizlenir_gerisi_kalir(monkeypatch, client):
    """ASIL KURAL: yalnız ad gider, analiz kalır."""
    metin = (f"{UYDURMA} bölüm başkanı olarak görev yapmaktadır ve "
             "doluluk oranı 2025'te %100'e ulaşmıştır.")
    _, yanit = _kos(monkeypatch, client, metin)
    cevap = yanit.json()["answer"]
    assert "Ahmet Yılmaz" not in cevap, f"Uydurma ad geçti: {cevap[:200]}"
    assert "doluluk oranı 2025'te %100'e ulaşmıştır" in cevap, (
        f"Cevabın geri kalanı kayboldu: {cevap[:300]}")
    assert "öğretim üyesi" in cevap, "Yerine doğal bir ifade konmadı"


def test_B2_cevap_reddedilmiyor(monkeypatch, client):
    """İsim yüzünden fallback'e düşülmez, hata dönmez, cevap boşalmaz."""
    metin = f"Kadroda {UYDURMA} bulunmaktadır."
    _, yanit = _kos(monkeypatch, client, metin)
    assert yanit.status_code == 200
    govde = yanit.json()
    assert govde["answer"].strip()
    assert "güvenilir bir yanıt üretilemedi" not in govde["answer"]
    assert "Bu bilgi için gerekli veriye ulaşamadım" not in govde["answer"]


def test_B3_mekanik_sansur_isareti_yok(monkeypatch, client):
    _, yanit = _kos(monkeypatch, client, f"Kadroda {UYDURMA} bulunmaktadır.")
    cevap = yanit.json()["answer"]
    for isaret in ("[SİLİNDİ]", "[REDACTED]", "***", "XXX", "[...]"):
        assert isaret not in cevap, f"Mekanik sansür işareti: {isaret}"


def test_B4_sanitizasyon_ek_model_cagrisi_uretmiyor(monkeypatch, client):
    """Ad temizliği için model YENİDEN çağrılmaz.

    Mutlak bir sayı beklenmiyor: turun kaç tur sürdüğü mevcut bütçe ve
    grounding kurallarının işi. Ölçülen şey, uydurma bir adın bu sayıyı
    DEĞİŞTİRMEMESİ — yani sanitizasyonun sağlayıcıya hiç gitmemesi.
    """
    adsiz, _ = _kos(monkeypatch, client, "Kadro bilgisi bulunmamaktadır.")
    adli, _ = _kos(monkeypatch, client, f"Kadroda {UYDURMA} bulunmaktadır.")
    assert adli.cagri == adsiz.cagri, (
        f"Ad yüzünden ek çağrı: {adli.cagri} > {adsiz.cagri}")


# --------------------------------------------------------------- C
def test_C_grounded_kalir_ungrounded_gider():
    """Aynı cümlede ikisi varsa ayrım kişi bazında yapılır."""
    grounded = {kisi_adi.normalize(GERCEK)}
    sonuc = kisi_adi.sanitize(
        f"Kadroda {GERCEK} ve {UYDURMA} görev yapmaktadır.", grounded)
    assert GERCEK in sonuc.metin
    assert "Ahmet Yılmaz" not in sonuc.metin
    assert sonuc.grounded == 1 and sonuc.temizlenen == 1


# --------------------------------------------------------------- D
def test_D_kisi_adi_yoksa_metin_birebir_ayni(monkeypatch, client):
    """Sanitizer sessiz kalmalı: dokunmadığı metni yeniden biçimlendirmez."""
    _, yanit = _kos(monkeypatch, client, KURUMSAL)
    assert yanit.json()["answer"] == KURUMSAL


def test_D2_helper_de_birebir_donuyor():
    sonuc = kisi_adi.sanitize(KURUMSAL)
    assert sonuc.metin == KURUMSAL
    assert sonuc.bulunan == 0 and not sonuc.degisti


# --------------------------------------------------------------- E
@pytest.mark.parametrize("ad", [
    "Ankara Üniversitesi", "Gazi Üniversitesi", "Mühendislik Fakültesi",
    "Bilgisayar Mühendisliği", "Endüstri Mühendisliği",
    "Su Ürünleri Mühendisliği", "Ankara Bilim Üniversitesi"])
def test_E_kurum_adlari_silinmiyor(ad):
    """Kurum, fakülte, bölüm ve program adları filtrenin hedefi DEĞİL."""
    metin = f"{ad} kadrosunda değişiklik oldu."
    assert kisi_adi.sanitize(metin).metin == metin, ad


def test_E2_sehir_adi_kisi_adina_yapismaz():
    """ÖLÇÜLEN ARIZA: "... Yılmaz Ankara Üniversitesi'nde" cümlesinde
    kurum adı da adın parçası sayılıp siliniyordu."""
    sonuc = kisi_adi.sanitize(
        f"{UYDURMA} Ankara Üniversitesi'nde görev yapan bir akademisyendir.")
    assert "Ankara Üniversitesi" in sonuc.metin
    assert "Ahmet Yılmaz" not in sonuc.metin


def test_E3_soyadi_katalogda_gecse_de_kirpilmiyor():
    """ÖLÇÜLEN ARIZA: "Su" katalogda (Su Ürünleri Mühendisliği) diye
    "Can Su" adının soyadı ayrılıp cümlede kalıyordu."""
    sonuc = kisi_adi.sanitize("Arş. Gör. Can Su kadroda yer almaktadır.")
    assert " Su " not in sonuc.metin and not sonuc.metin.startswith("Su ")
    assert sonuc.temizlenen == 1


# --------------------------------------------------------------- F
def test_F_model_only_cevap_korunuyor(monkeypatch, client):
    """RAG yokken model yine cevap verir; yalnız kurumsal ad temizlenir."""
    metin = ("Kalite güvencesi, süreçlerin ölçütlere göre "
             f"değerlendirilmesidir. Bu alanda {UYDURMA} çalışmalar "
             "yürüten bir akademisyendir.")
    _, yanit = _kos(monkeypatch, client, metin,
                    soru="Yükseköğretimde kalite güvencesi nedir?")
    cevap = yanit.json()["answer"]
    assert "Kalite güvencesi, süreçlerin ölçütlere göre" in cevap, (
        f"Model-only cevap kayboldu: {cevap[:200]}")
    assert "Ahmet Yılmaz" not in cevap


def test_F2_model_only_kapatilmadi(monkeypatch, client):
    """Kişi adı kuralı, kanıtsız cevap verme yeteneğini kapatmamalı."""
    metin = "Bologna süreci, yükseköğretimde uyum çerçevesidir."
    _, yanit = _kos(monkeypatch, client, metin, soru="Bologna süreci nedir?")
    assert "Bologna süreci" in yanit.json()["answer"]


# --------------------------------------------------------------- G
@pytest.mark.parametrize("hata", ["rate_limit", "timeout"])
def test_G_saglayici_arizasinda_metin_bozulmuyor(monkeypatch, client, hata):
    """Kota/zaman aşımı metinleri sanitizer'dan zarar görmeden geçer."""
    _, yanit = _kos(monkeypatch, client, "Cevap.", hata=hata,
                    soru="Kaç akademisyenimiz var?")
    assert yanit.status_code == 200
    assert yanit.json()["answer"].strip()


def test_G2_kota_notu_silinmiyor():
    """Kota notunda kişi adı yok; sanitizer ona dokunmamalı."""
    for notu in (chat_service.KOTA_NOTU_ALTERNATIF,
                 chat_service.KOTA_NOTU_VERIDEN,
                 chat_service.KOTA_NOTU_VERI_YOK,
                 chat_service.KONTROLLU_MESAJ):
        assert kisi_adi.sanitize(notu).metin == notu, notu[:40]


# --------------------------------------------------------------- KANIT
def test_grounded_kume_bu_turun_kanitindan_gelir():
    """DB'deki bütün insanlar kör biçimde güvenilir sayılmaz."""

    class SahteKayit:
        name, success, output = "query_canonical_data", True, None
        content = '{"rows": [{"staff_name": "Zeynep Aydın"}]}'

    class SahteOturum:
        records = [SahteKayit()]

    adlar = kisi_adi.grounded_adlar(SahteOturum())
    assert kisi_adi.normalize(GERCEK) in adlar
    assert kisi_adi.normalize("Ahmet Yılmaz") not in adlar


def test_basarisiz_arac_sonucu_grounded_saymaz():
    class SahteKayit:
        name, success, output = "query_canonical_data", False, None
        content = '{"rows": [{"staff_name": "Zeynep Aydın"}]}'

    class SahteOturum:
        records = [SahteKayit()]

    assert not kisi_adi.grounded_adlar(SahteOturum())


def test_kurum_alani_kisi_adi_sayilmaz():
    """`program_name` bir kişi değildir; onu grounded kişi saymak,
    kurum adını kişi adı yerine geçirirdi."""

    class SahteKayit:
        name, success, output = "query_canonical_data", True, None
        content = '{"rows": [{"program_name": "Bilgisayar Mühendisliği"}]}'

    class SahteOturum:
        records = [SahteKayit()]

    assert not kisi_adi.grounded_adlar(SahteOturum())


def test_kanitta_unvanla_gecen_ad_grounded_sayilir():
    """Serbest metinde "Prof. Dr. X" geçiyorsa o kişi kanıttadır."""

    class SahteKayit:
        name, success, output = "explore_data_sources", True, None
        content = '{"notes": "Danışman: Prof. Dr. Zeynep Aydın"}'

    class SahteOturum:
        records = [SahteKayit()]

    assert kisi_adi.normalize(GERCEK) in kisi_adi.grounded_adlar(SahteOturum())


# --------------------------------------------------------------- PERF
def test_sanitizasyon_hizli():
    """Hedef milisaniye altı; katalog yeniden kurulmaz."""
    kisi_adi.sanitize(KURUMSAL)                      # ısınma
    once = kisi_adi._katalog_adlari.cache_info().misses
    metin = (KURUMSAL + " " + f"Kadroda {UYDURMA} bulunmaktadır.") * 5
    basladi = time.perf_counter()
    for _ in range(50):
        kisi_adi.sanitize(metin)
    sure = (time.perf_counter() - basladi) / 50
    assert sure < 0.020, f"Çağrı başına {sure * 1000:.1f} ms"
    assert kisi_adi._katalog_adlari.cache_info().misses == once, (
        "Katalog her çağrıda yeniden kuruldu")


def test_ag_cagrisi_ve_ikinci_model_yok():
    """Ne dış servis ne ikinci LLM: katman deterministik olmalı."""
    import inspect
    kod = "\n".join(s.split("#")[0]
                    for s in inspect.getsource(kisi_adi).splitlines()).lower()
    for yasak in ("requests", "httpx", "urllib", "transformers", "spacy",
                  "get_provider", "chat_with_tools"):
        assert yasak not in kod, f"Ağır/uzak bağımlılık: {yasak}"
