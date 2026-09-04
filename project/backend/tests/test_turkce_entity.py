"""Türkçe varlık çözümleme — ek toleransı ve karıştırmama.

Bu testler soru METNİNİ değil, DİL OLGUSUNU korur. Yeni bir program
eklendiğinde ya da bir soru başka kelimelerle sorulduğunda kırılmazlar;
kırıldıklarında gerçekten bir dil davranışı bozulmuştur.

Kategoriler:
  A) Türkçe ekler        — mühendislik / mühendisliği / mühendisliğinde
  B) Benzer adlar        — Bilgisayar Mühendisliği ≠ Programcılığı
  C) Varlık grubu        — "mühendislikler" tek program değil
  D) Fakülte / program   — ayrı kapsam
  E) Metrik kavramları   — doluluk / doluluğu / kontenjanı
  F) Belirsiz metrik     — "hangileri yükseldi?" → UNKNOWN
  G) Birleşik soru       — varlık + metrik + zaman + coğrafya
"""

from __future__ import annotations

import time

import pytest

from app.services.assistant import abu_kds_store as store
from app.services.assistant import entity_katalogu as ek
from app.services.assistant import veri_ailesi as va

pytestmark = pytest.mark.skipif(
    not store.kullanilabilir(),
    reason="abu_kds.db yok; katalog kurulamaz.")


# --------------------------------------------------------------- A
@pytest.mark.parametrize("varyant", [
    "mühendislik", "mühendisliği", "mühendisliklerin", "mühendisliğinde",
    "mühendislikler", "MÜHENDİSLİK", "Mühendisliğe",
])
def test_turkce_ekler_ayni_kavram(varyant):
    """Ek almış biçimler aynı kavrama düşmeli.

    Tam kelime sözlüğü kullanılsaydı bu listeye her yeni ek elle
    eklenmek zorunda kalırdı ve biri unutulduğunda soru sessizce
    kavramı kaçırırdı.
    """
    kok = ek.normalize("mühendislik").split()[0]
    token = ek.normalize(varyant).split()[0]
    assert ek.ayni_kavram(token, kok), f"{varyant!r} kavramı kaçtı"


@pytest.mark.parametrize("a,b", [
    ("bölüm", "bölümlerin"), ("fakülte", "fakültesindeki"),
    ("doluluk", "doluluğu"), ("kontenjan", "kontenjanı"),
    ("yerleşme", "yerleşen"), ("akademisyen", "akademik"),
])
def test_kisa_kavramlar_da_ek_tolere_eder(a, b):
    """Tür/metrik ipuçları kısa olabilir; onlar için eşik düşürülür."""
    assert ek.ayni_kavram(ek.normalize(a), ek.normalize(b),
                          kisa_kavram=True), f"{a} ~ {b} eşleşmedi"


# --------------------------------------------------------------- B
def test_benzer_adlar_karismaz():
    """ASIL RİSK. Tek ortak kelime aynı varlık demek değildir."""
    c1 = ek.coz("Bilgisayar Mühendisliği doluluk oranı")
    c2 = ek.coz("Bilgisayar Programcılığı kontenjanı")
    assert c1.varlik is not None and c2.varlik is not None
    assert "Mühendis" in c1.varlik.ad
    assert "Programcı" in c2.varlik.ad
    assert c1.varlik.ad != c2.varlik.ad


def test_tek_kelime_entity_secmez():
    """Yalnızca "bilgisayar" görmek bir programı seçmeye yetmez."""
    c = ek.coz("bilgisayar")
    # Ya hiç seçilmez ya belirsiz sayılır; kesin bir program seçilemez.
    assert c.varlik is None or c.belirsiz, (
        f"Tek kelimeden kesin varlık seçildi: {c.ozet()}")


def test_endustri_muhendisligi_ile_endustriyel_tasarim_ayrilir():
    """Token düzeyinde benzer, varlık düzeyinde farklı."""
    c = ek.coz("Endüstri Mühendisliği taban puanı")
    assert c.varlik is not None
    assert "Mühendis" in c.varlik.ad
    assert "Tasarım" not in c.varlik.ad


# --------------------------------------------------------------- C
@pytest.mark.parametrize("soru", [
    "Mühendislikler nasıl bir seyir izliyor?",
    "Mühendislik bölümleri arasında karşılaştırma yap",
    "Son iki yılda hangi mühendislikler yükseldi?",
])
def test_grup_ifadesi_tek_program_sanilmaz(soru):
    p = va.plan_cikar(soru)
    assert p.varlik_grubu == "engineering", p.ozet()
    assert p.varlik is None, (
        f"Grup ifadesinde tekil varlık seçildi: {p.varlik}")


def test_grup_uyeleri_veritabanindan_gelir():
    """Otuz mühendislik programı elle listelenmez, katalogdan bulunur."""
    uyeler = ek.grup_uyeleri("engineering")
    assert len(uyeler) >= 5, uyeler
    assert all("ühendis" in u or "ÜHEND" in u.upper() for u in uyeler[:10])


# --------------------------------------------------------------- D
def test_fakulte_ve_program_ayri_kapsam():
    fakulte = ek.tur_ipucu(ek.tokenlar("Mühendislik fakültesi"))
    program = ek.tur_ipucu(ek.tokenlar("Mühendislik programları"))
    assert fakulte == "faculty"
    assert program == "program"


def test_fakulte_icindeki_bolumler_iki_seviye_uretir():
    """"Fakültedeki bölümler" → kapsam fakülte, sorulan bölüm."""
    parcalar = ek.tokenlar("Mühendislik fakültesindeki bölümler")
    assert ek.tur_ipucu(parcalar) == "department"
    assert ek.kapsam_ipucu(parcalar) == "faculty"


# --------------------------------------------------------------- E
@pytest.mark.parametrize("soru,beklenen", [
    ("Bilgisayar mühendisliğinin doluluğu nedir?", "occupancy"),
    ("Psikoloji kontenjanı kaç?", "quota"),
    ("Taban puanı nedir?", "base_score"),
    ("Kaç akademisyenimiz var?", "academic_staff"),
    ("Yerleşen sayısı kaç?", "placed"),
])
def test_metrik_kavrami_eklerden_etkilenmez(soru, beklenen):
    p = va.plan_cikar(soru)
    assert beklenen in p.kavramlar, f"{soru!r} → {p.kavramlar}"


def test_akademik_yil_akademisyen_metrigi_degildir():
    """"akademik yıl" ifadesi kadro metriği anlamına gelmez.

    Alt-dize eşleşmesi tek başına karar veremez; bu testin koruduğu şey
    tam olarak budur.
    """
    p = va.plan_cikar("2025-2026 akademik yılında toplam öğrenci sayısı kaç?")
    assert "student_count" in p.kavramlar
    assert "academic_staff" not in p.kavramlar, p.ozet()


# --------------------------------------------------------------- F
@pytest.mark.parametrize("soru", [
    "Son iki yılda hangi mühendislikler yükseldi?",
    "Hangi bölümler geriledi?",
    "Son üç yılda hangi programlar öne çıktı?",
])
def test_metrik_belirtilmemisse_bilinmiyor(soru):
    """Yükselen NE? Tahmin etmek sessizce yanlış cevap üretir."""
    p = va.plan_cikar(soru)
    assert p.metrik_bilinmiyor, p.ozet()
    assert "UNKNOWN" in p.ozet()


def test_metrik_bilinmiyorken_kaynak_secilmez():
    """Rastgele veri çekilmez: metrik yoksa aday kaynak da yoktur."""
    p = va.plan_cikar("Son iki yılda hangi mühendislikler yükseldi?")
    assert p.metrik_bilinmiyor
    assert not va.aday_kaynaklar(p), (
        "Metrik bilinmezken kaynak seçildi — rastgele veri riski")


def test_metrik_belirtilmisse_bilinmiyor_degil():
    p = va.plan_cikar("Son iki yılda hangi mühendisliklerin doluluğu arttı?")
    assert not p.metrik_bilinmiyor
    assert "occupancy" in p.kavramlar


# --------------------------------------------------------------- G
def test_birlesik_soru_tum_boyutlari_cikarir():
    p = va.plan_cikar(
        "Son iki yılda Ankara'daki bilgisayar mühendisliği doluluklarını "
        "üniversitelere göre karşılaştır.")
    assert p.niyet == "comparison"
    assert "occupancy" in p.kavramlar
    assert p.varlik is not None and "Mühendis" in p.varlik
    assert len(p.yillar) == 2
    assert p.universite_seviyesi


def test_dagimik_kelimeler_yanlis_varlik_secmez():
    """ÖLÇÜLEN YANLIŞ: "Ankara'daki … üniversitelere göre" sorusunda
    "ANKARA ÜNİVERSİTESİ" varlığı seçiliyordu — iki token da soruda
    geçiyor ama biri başta, diğeri sonda ve başka işlevle.
    """
    p = va.plan_cikar(
        "Son iki yılda Ankara'daki bilgisayar mühendisliği doluluklarını "
        "üniversitelere göre karşılaştır.")
    assert p.varlik != "ANKARA ÜNİVERSİTESİ", (
        "Dağınık kelimelerden yanlış üniversite seçildi")


def test_bitisik_yazilan_universite_dogru_secilir():
    """Karşı denetim: gerçekten bitişik yazıldığında seçilmeli."""
    c = ek.coz("Ankara Üniversitesi'nin öğrenci sayısı kaç?")
    assert c.varlik is not None
    assert "ANKARA ÜNİVERSİTESİ" in c.varlik.ad.upper()


# --------------------------------------------------------------- PERF
def test_katalog_tekrar_kurulmuyor():
    """Her sorguda DB şeması taranmamalı."""
    ek.katalog()
    once = ek.katalog.cache_info().misses
    for _ in range(20):
        va.plan_cikar("Bilgisayar mühendisliği doluluğu")
    assert ek.katalog.cache_info().misses == once, "Katalog yeniden kuruldu"
    assert va.profiller.cache_info().misses <= 1


def test_retrieval_hizli():
    """Gemini hariç retrieval milisaniyeler mertebesinde kalmalı."""
    ek.katalog()
    va.profiller()
    sorular = [
        "Bilgisayar mühendisliğinin doluluğu nedir?",
        "Mühendislik fakültesindeki bölümleri sırala",
        "Son 5 yılda taban puanları nasıl değişti?",
        "Psikoloji kontenjanı kaç?",
        "Ankara'daki üniversitelerin öğrenci sayıları",
    ] * 10
    basladi = time.perf_counter()
    for s in sorular:
        p = va.plan_cikar(s)
        va.aday_kaynaklar(p)
    ortalama = (time.perf_counter() - basladi) / len(sorular)
    # Cömert bir tavan: gerçek ölçüm ~1 ms. 50 ms'i aşıyorsa bir yerde
    # her sorguda DB'ye gidiliyordur.
    assert ortalama < 0.050, f"Sorgu başına {ortalama * 1000:.1f} ms"
