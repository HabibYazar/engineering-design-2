"""Kurumsal kişi adları — uydurmayı önle, uydurulduysa YALNIZ adı temizle.

NEDEN VAR
---------
Sayılar için katı bir kural var: kurumsal rakam yalnızca araç sonucundan
gelir. İSİMLER için böyle bir kural yoktu. Model "Bilgisayar Mühendisliği
bölüm başkanı Prof. Dr. Ahmet Yılmaz'dır" diye bir cümle kurabiliyor ve
bu cümle, yanlış bir sayıdan daha zararlı: okuyan kişi ismi doğrular
sanıyor, üstelik gerçek bir insanın adı yanlış bir göreve bağlanmış
olabiliyor.

İKİ KATMAN
----------
1. YÖNERGE — modele açıkça "kanıtta yoksa isim yazma" denir. İlk savunma
   budur ve çoğu turda yeterlidir.

2. BU MODÜL — yönergeye rağmen isim çıkarsa devreye girer. Burada tek
   bir tasarım kararı her şeyi belirliyor:

       CEVABIN TAMAMI REDDEDİLMEZ.

   Bir isim yüzünden bütün cevabı atmak, doğru olan analizi ve grounded
   sayıları da yok etmek demekti; kullanıcı hiç cevap alamazdı. Onun
   yerine yalnızca doğrulanmamış ad, bağlamına uygun genel bir ifadeyle
   değiştirilir. Cümlenin geri kalanı aynen kalır.

KAPSAM
------
Yalnızca KURUMSAL kişi adları. Üniversite, fakülte, bölüm, program ve
şehir adları hedef değildir ve silinmez — bunun için ad adaylarının
mevcut varlık kataloğuna karşı denetlenmesi yeterli oluyor; yeni bir
sözlük tutulmuyor.

NE YAPILMIYOR
-------------
· İkinci bir LLM çağrısı yok. Bu katman deterministik ve birkaç
  milisaniyelik.
· NER modeli, transformer, dış servis, ağ çağrısı yok.
· Kişi adı listesi koda yazılmıyor; grounded küme HER TURDA o turun
  kanıtından üretiliyor.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 1) TÜRKÇE NORMALİZASYON
# ---------------------------------------------------------------------------
# Python'un `lower()` metodu Türkçede yanlış çalışır: "İ" → "i̇" (birleşik
# nokta) ve "I" → "i". Karşılaştırma bu yüzden önce elle katlanır; yoksa
# "İLKER" ile "İlker" farklı iki kişi sanılırdı.
_KATLA = str.maketrans("ÇĞİIÖŞÜçğıiöşü", "CGIIOSUcgiiosu")


def normalize(ad: str) -> str:
    """Karşılaştırma biçimi: unvansız, aksansız, tek boşluklu, küçük harf.

    Gevşetme BİLİNÇLİ OLARAK SINIRLI. Bulanık eşleştirme burada
    tehlikeli olurdu: "Ahmet Yılmaz" ile "Ahmet Yılmazer"i aynı kişi
    saymak, doğrulanmamış bir adı doğrulanmış gibi geçirirdi. Yalnızca
    yazım farkları silinir, ad farkları değil.
    """
    metin = (ad or "").translate(_KATLA).lower()
    metin = _UNVAN_SIL.sub(" ", metin)
    metin = re.sub(r"['’´`]\w*", " ", metin)      # "yilmaz'in" → "yilmaz"
    metin = re.sub(r"[^\w\s]", " ", metin)
    return " ".join(metin.split())


# ---------------------------------------------------------------------------
# 2) UNVANLAR VE ROLLER
# ---------------------------------------------------------------------------
#: Akademik/idari unvan parçaları. Kapalı bir küme — Türkçede bu
#: kısaltmalar standarttır, yeni bir unvan icat edilmez.
_UNVAN_KISA = ("Prof", "Doç", "Doc", "Dr", "Öğr", "Ogr", "Arş", "Ars",
               "Gör", "Gor", "Uzm", "Yrd", "Av", "Op")
_UNVAN_TOKEN = (r"(?:(?:" + "|".join(_UNVAN_KISA) + r")\.\s*|Üyesi\s+)")
_UNVAN_SIL = re.compile(
    r"\b(?:" + "|".join(_UNVAN_KISA) + r")\.?\s*|\büyesi\b", re.I)

#: Ad parçası: BÜYÜK harfle başlar, devamı küçüktür. Bu biçim şartı
#: "ANKARA ÜNİVERSİTESİ" gibi tamamı büyük yazılmış kurum adlarını
#: kendiliğinden dışarıda bırakır.
_AD_TOKEN = r"[A-ZÇĞİÖŞÜ][a-zçğıöşü]{1,}"
#: Adın sonuna yapışan Türkçe ek: "Yılmaz'dır", "Yılmaz'ın".
_EK = r"(?:['’´][\wçğıöşü]*)?"

#: Unvanla yazılmış kişi adı. En güvenilir sinyal budur.
_UNVANLI = re.compile(
    r"(?P<unvan>(?:" + _UNVAN_TOKEN + r"){1,4})"
    r"(?P<ad>" + _AD_TOKEN + r"(?:\s+" + _AD_TOKEN + r"){0,2})"
    + _EK)

#: Unvansız ad adayı: en az iki ad parçası.
_AD_DIZISI = re.compile(
    r"\b(?P<ad>" + _AD_TOKEN + r"(?:\s+" + _AD_TOKEN + r"){1,2})" + _EK)

#: KURUMSAL KİŞİ bağlamı. Bu kelimelerden biri geçmeyen bir cümlede
#: unvansız ad aranmaz — yoksa "Ankara Bilim Üniversitesi" gibi her
#: büyük harfli ikili kişi sanılırdı. Kapsamı dar tutmak, yanlış
#: sansürden kaçınmanın en ucuz yolu.
_ROL = re.compile(
    r"(akademisyen|akademik kadro|ogretim uye|ogretim gorevli|"
    r"arastirma gorevli|profesor|docent|doktor ogretim|bolum baskan|"
    r"dekan|rektor|mudur|koordinator|danisman|personel|calisan|kadro|"
    r"hoca|yonetici|sorumlu|baskan)", re.I)

#: Kişi adı OLMADIĞI kesin olan sözcükler. Kurum türü sözlüğüdür,
#: kurum ADI listesi değil: yeni bir üniversite açıldığında güncelleme
#: gerektirmez.
_KURUM_SOZ = re.compile(
    r"^(universite|universitesi|fakulte|fakultesi|bolum|bolumu|program|"
    r"programi|enstitu|enstitusu|yuksekokul|meslek|rektorluk|dekanlik|"
    r"daire|mudurluk|merkez|merkezi|kampus|anabilim|dali|lisans|"
    r"onlisans|yuksek|doktora|ocak|subat|mart|nisan|mayis|haziran|"
    r"temmuz|agustos|eylul|ekim|kasim|aralik|pazartesi|sali|carsamba|"
    r"persembe|cuma|cumartesi|pazar)$", re.I)

#: Unvandan üretilen genel karşılık. Sansür etiketi değil, cümlenin
#: akışını bozmayan bir ifade: "[SİLİNDİ]" okuyanı rahatsız eder ve
#: cevabı kullanılamaz hale getirirdi.
_GENEL = (
    (("arş", "ars"), "bir araştırma görevlisi", "araştırma görevlileri"),
    (("gör", "gor"), "bir öğretim görevlisi", "öğretim görevlileri"),
    (("prof", "doç", "doc", "dr", "yrd", "üyesi", "uyesi"),
     "bir öğretim üyesi", "öğretim üyeleri"),
)
_GENEL_VARSAYILAN = ("ilgili kişi", "ilgili kişiler")

#: Sansür yapıldığında cevabın SONUNA eklenen tek cümle. Metinden bir
#: şey silinmez; yalnızca okuyan kişi, kaldırılan bilginin kurum
#: verisinde doğrulanmadığını bilir.
NOT_METNI = ("Not: Bu cevapta geçen kişi bilgileri kurum verisinde "
             "doğrulanamadığı için ad belirtilmemiştir.")


# ---------------------------------------------------------------------------
# 3) KURUM ADLARINI KORUMA
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _katalog_adlari() -> Tuple[Set[str], Set[str]]:
    """(ilk sözcükler, ad önekleri) — mevcut varlık kataloğundan.

    İKİ AYRI KÜME, İKİ AYRI İŞ:

      · İLK SÖZCÜKLER, ad taramasının kurum adına taşmasını keser:
        "Prof. Dr. Ahmet Yılmaz Ankara Üniversitesi'nde" cümlesinde
        "Ankara" ada yapışmamalı.

      · ÖNEKLER, bir ad adayının aslında kurum adı olup olmadığını
        söyler: "Bilgisayar Mühendisliği" katalogda geçer, kişi değil.
        Burada TAM İFADE denetlenir, tek tek sözcükler değil — aksi
        halde "Ahmet Yesevi Üniversitesi" katalogda diye gerçek bir
        "Ahmet Yılmaz" adı kişi sayılmaz ve sansürden kaçardı.

    Liste koda yazılmaz; yeni bir program ya da üniversite eklendiğinde
    kendiliğinden kapsanır. Katalog kurulamazsa boş kümeler döner ve
    tarama yalnızca kurum türü sözlüğüne dayanır.
    """
    try:
        from app.services.assistant import entity_katalogu
        k = entity_katalogu.katalog()
    except Exception:  # noqa: BLE001
        logger.debug("varlık kataloğu okunamadı", exc_info=True)
        return set(), set()
    ilk: Set[str] = set()
    onek: Set[str] = set()
    for varlik in getattr(k, "varliklar", []):
        parcalar = normalize(getattr(varlik, "ad", "")).split()
        if not parcalar:
            continue
        ilk.add(parcalar[0])
        for n in range(2, len(parcalar) + 1):
            onek.add(" ".join(parcalar[:n]))
    return ilk, onek


def _kurum_sozcugu(token: str) -> bool:
    """Tek sözcük düzeyinde kurum işareti — yalnızca KIRPMA için."""
    sade = normalize(token)
    if not sade:
        return True
    return bool(_KURUM_SOZ.match(sade)) or sade in _katalog_adlari()[0]


def _ad_kirp(ad: str, kuyruk: str = "") -> str:
    """Ad dizisini kurum adına taşmadan önce keser.

    NEDEN İKİLİ BAKIŞ: tek sözcüğe bakmak fazla katıydı. "Su" katalogda
    (Su Ürünleri Mühendisliği) diye "Arş. Gör. Can Su" adının soyadı
    kırpılıyordu. Bir sözcüğün kurum adı BAŞLATMASI yetmez; kendisinden
    sonra gelen sözcükle birlikte katalogdaki bir adı SÜRDÜRÜYOR olması
    gerekir. "Ankara" + "Üniversitesi" sürdürür ve orada kesilir; "Su" +
    "kadroda" sürdürmez ve ada dahil kalır.

    `kuyruk`, adın hemen ardından gelen metindir; son sözcüğün de
    denetlenebilmesi için gerekir.
    """
    ilk, onek = _katalog_adlari()
    parcalar = ad.split()
    sonraki = (kuyruk or "").split()
    tutulan: List[str] = []
    for i, parca in enumerate(parcalar):
        if i > 0:
            sade = normalize(parca)
            if _KURUM_SOZ.match(sade):
                break
            ardil = (parcalar[i + 1] if i + 1 < len(parcalar)
                     else (sonraki[0] if sonraki else ""))
            if sade in ilk and ardil:
                if f"{sade} {normalize(ardil)}" in onek:
                    break
        tutulan.append(parca)
    return " ".join(tutulan)


def _kisi_adi_olabilir(ad: str) -> bool:
    """Bu ifade bir KİŞİ adı olabilir mi.

    Tek tek sözcüklere bakılmaz: kişi adları da katalogdaki bir kurum
    adının sözcüğünü paylaşabilir. Denetlenen şey TAM ifadedir.
    """
    parcalar = ad.split()
    if not parcalar:
        return False
    if any(_KURUM_SOZ.match(normalize(p)) for p in parcalar):
        return False
    return normalize(ad) not in _katalog_adlari()[1]


# ---------------------------------------------------------------------------
# 4) GROUNDED KİŞİ ADI KÜMESİ
# ---------------------------------------------------------------------------
#: Kişi adı taşıyabilecek alan adları.
_KISI_ALAN = re.compile(
    r"(name|isim|ad_soyad|adsoyad|full_name|academic|staff|personnel|"
    r"instructor|ogretim|hoca|danisman|advisor|dekan|rektor|baskan|"
    r"yetkili|sorumlu|author|yazar)", re.I)
#: ...ama bu alanlar kişi değil KURUM taşır. `program_name` gibi bir
#: alanın değerini "doğrulanmış kişi" saymak, kurum adını kişi adı
#: yerine geçirirdi.
_KURUM_ALAN = re.compile(
    r"(program|university|universite|faculty|fakulte|department|bolum|"
    r"course|ders|city|sehir|source|kaynak|table|tablo|file|dosya|"
    r"metric|metrik|unit|birim)", re.I)


def _alan_kisi_mi(anahtar: str) -> bool:
    return bool(_KISI_ALAN.search(anahtar)) and not _KURUM_ALAN.search(anahtar)


def _degerleri_gez(veri: Any, kisi_alani: bool = False
                   ) -> Iterable[Tuple[bool, str]]:
    """JSON benzeri yapıyı dolaşır; (kişi alanı mı, değer) çiftleri verir."""
    if isinstance(veri, dict):
        for anahtar, deger in veri.items():
            yield from _degerleri_gez(deger, _alan_kisi_mi(str(anahtar)))
    elif isinstance(veri, (list, tuple)):
        for oge in veri:
            yield from _degerleri_gez(oge, kisi_alani)
    elif isinstance(veri, str):
        yield kisi_alani, veri


def _metinden_unvanli_adlar(metin: str) -> Set[str]:
    """Kanıt metninde unvanla geçen adlar — bunlar kesinlikle kişidir."""
    bulunan: Set[str] = set()
    for eslesme in _UNVANLI.finditer(metin or ""):
        ad = _ad_kirp(eslesme.group("ad"),
                      metin[eslesme.end("ad"):eslesme.end("ad") + 40])
        if ad and _kisi_adi_olabilir(ad):
            bulunan.add(normalize(ad))
    return bulunan


def grounded_adlar(session=None, *, ek_metinler: Sequence[str] = ()
                   ) -> Set[str]:
    """Bu turun kanıtında GERÇEKTEN geçen kurumsal kişi adları.

    İki yoldan toplanır ve ikisi de bu tura özgüdür:

      · kişi taşıdığı belli alanların değerleri (`name`, `academic_staff`,
        `danisman` gibi) — kurum alanları dışlanır,
      · kanıt metninde unvanla yazılmış adlar ("Prof. Dr. X").

    Veritabanındaki BÜTÜN insanlar kör biçimde güvenilir sayılmaz:
    o zaman model, o turda hiç sorgulanmamış bir kişiyi de serbestçe
    yazabilirdi.
    """
    adlar: Set[str] = set()
    kayitlar = list(getattr(session, "records", []) or []) if session else []
    for kayit in kayitlar:
        if not getattr(kayit, "success", False):
            continue
        veri: Any = None
        cikti = getattr(kayit, "output", None)
        if cikti is not None:
            try:
                veri = cikti.model_dump(mode="json")
            except Exception:  # noqa: BLE001
                veri = None
        if veri is None:
            try:
                veri = json.loads(kayit.content or "null")
            except Exception:  # noqa: BLE001
                veri = kayit.content
        for kisi_alani, deger in _degerleri_gez(veri):
            if kisi_alani:
                ad = _ad_kirp(deger.strip())
                if ad and _kisi_adi_olabilir(ad) and len(ad.split()) <= 4:
                    adlar.add(normalize(ad))
            adlar |= _metinden_unvanli_adlar(deger)

    for metin in ek_metinler:
        adlar |= _metinden_unvanli_adlar(metin or "")
    adlar.discard("")
    return adlar


# ---------------------------------------------------------------------------
# 5) CEVAPTAKİ ADLARI BULMA
# ---------------------------------------------------------------------------
@dataclass
class Aday:
    #: Metinde değiştirilecek tam aralık (unvan + ad + ek).
    bas: int
    son: int
    ad: str
    unvan: str = ""

    @property
    def anahtar(self) -> str:
        return normalize(self.ad)


_CUMLE = re.compile(r"[^.!?\n]+[.!?\n]?")


def adaylari_bul(metin: str) -> List[Aday]:
    """Cevaptaki kurumsal kişi adı adayları.

    İki dedektör var ve ikisi de İSABET öncelikli:

      1. UNVANLI — "Prof. Dr. Ahmet Yılmaz". Unvan kapalı bir kümedir,
         yanlış pozitif pratikte imkânsız.
      2. ROL BAĞLAMLI — unvan yoksa, yalnızca cümle kurumsal bir ROL
         sözcüğü içeriyorsa büyük harfli ad dizileri aranır. Bu şart
         olmadan her büyük harfli ikili kişi sanılır ve kurum adları
         silinirdi.

    Kurum, fakülte, bölüm, program ve şehir adları her iki yolda da
    varlık kataloğu ve kurum türü sözlüğüyle eleniyor.
    """
    metin = metin or ""
    adaylar: List[Aday] = []
    kapali: List[Tuple[int, int]] = []

    for eslesme in _UNVANLI.finditer(metin):
        ham = eslesme.group("ad")
        ad = _ad_kirp(ham, metin[eslesme.end("ad"):eslesme.end("ad") + 40])
        if not ad or not _kisi_adi_olabilir(ad):
            continue
        # DEĞİŞTİRİLECEK ARALIK, KIRPILAN AD KADARDIR.
        # Eşleşme kurum adına taşmış olabilir ("... Yılmaz Ankara
        # Üniversitesi'nde"); tüm eşleşmeyi silmek kurum adını da
        # götürürdü. Ad kısaldıysa aralık da kısalır.
        son = (eslesme.end() if len(ad) == len(ham)
               else eslesme.start("ad") + len(ad))
        adaylar.append(Aday(eslesme.start(), son, ad,
                            eslesme.group("unvan").strip()))
        kapali.append((eslesme.start(), son))

    for cumle in _CUMLE.finditer(metin):
        govde = cumle.group(0)
        if not _ROL.search(normalize(govde)):
            continue
        for eslesme in _AD_DIZISI.finditer(govde):
            bas = cumle.start() + eslesme.start()
            son = cumle.start() + eslesme.end()
            if any(b <= bas < s or b < son <= s for b, s in kapali):
                continue
            ham = eslesme.group("ad")
            ad = _ad_kirp(
                ham, govde[eslesme.end("ad"):eslesme.end("ad") + 40])
            # CÜMLE BAŞI BÜYÜK HARFİ AD SİNYALİ DEĞİLDİR.
            # ÖLÇÜLEN ARIZA: "Kadroda Zeynep Aydın görev yapıyor"
            # cümlesinde ad "Kadroda Zeynep Aydın" sanılıyor, grounded
            # kümeyle eşleşmiyor ve gerçek ad sansürleniyordu. Cümlenin
            # ilk sözcüğü, geriye en az iki parça kalıyorsa düşülür.
            # Sınır: cümle başında unvansız İKİ parçalı bir ad
            # ("Zeynep Aydın kadroda...") bu yolla yakalanmaz; unvanlı
            # biçim ve cümle içi geçişler yakalanır.
            # KURUM DENETİMİ ÖNCE, CÜMLE BAŞI KIRPMASI SONRA.
            # Sıra önemli: "Su Ürünleri Mühendisliği" cümle başındayken
            # önce "Su" düşürülürse geriye kalan "Ürünleri Mühendisliği"
            # katalogda bulunamaz ve program adı kişi sanılırdı.
            if not ad or not _kisi_adi_olabilir(ad):
                continue
            bas_ofset = 0
            if eslesme.start("ad") == 0 and len(ad.split()) > 2:
                bas_ofset = len(ad.split()[0]) + 1
                ad = " ".join(ad.split()[1:])
            if len(ad.split()) < 2 or not _kisi_adi_olabilir(ad):
                continue
            bas += bas_ofset
            if len(ad) + bas_ofset != len(ham):
                son = (cumle.start() + eslesme.start("ad")
                       + bas_ofset + len(ad))
            adaylar.append(Aday(bas, son, ad))
            kapali.append((bas, son))

    adaylar.sort(key=lambda a: a.bas)
    return adaylar


# ---------------------------------------------------------------------------
# 6) SANİTİZASYON
# ---------------------------------------------------------------------------
def _genel_ifade(unvan: str) -> Tuple[str, str]:
    sade = normalize(unvan) if unvan else ""
    ham = (unvan or "").lower()
    for parcalar, tekil, cogul in _GENEL:
        if any(p in ham for p in parcalar):
            return tekil, cogul
    return _GENEL_VARSAYILAN


#: "bir öğretim üyesi ve bir öğretim üyesi" → "öğretim üyeleri".
#: Aynı ifadenin arka arkaya tekrarı, sansürü görünür kılar; asıl amaç
#: cümlenin doğal kalması.
def _tekrarlari_birlestir(metin: str) -> str:
    for _, tekil, cogul in _GENEL + (("",) + _GENEL_VARSAYILAN,):
        if not tekil:
            continue
        kalip = re.compile(
            r"(?:" + re.escape(tekil) + r")"
            r"(?:\s*,\s*(?:" + re.escape(tekil) + r"))*"
            r"\s+ve\s+(?:" + re.escape(tekil) + r")")
        metin = kalip.sub(cogul, metin)
    return metin


@dataclass
class Sonuc:
    metin: str
    bulunan: int = 0
    grounded: int = 0
    temizlenen: int = 0
    #: Trace için; adların KENDİSİ loglanmaz.
    degisti: bool = False


def sanitize(metin: str, grounded: Optional[Set[str]] = None) -> Sonuc:
    """Doğrulanmamış kurumsal kişi adlarını genel ifadeyle değiştirir.

    MUTLAK KURAL: cevap silinmez, kısaltılmaz, reddedilmez. Yalnızca ad
    aralıkları değişir; cümlenin geri kalanı ve bütün grounded veri
    olduğu gibi kalır.

    Ad bulunmazsa metin BİREBİR döner — hiçbir normalizasyon, kırpma ya
    da yeniden biçimlendirme yapılmaz.
    """
    grounded = grounded or set()
    if not (metin or "").strip():
        return Sonuc(metin=metin or "")

    adaylar = adaylari_bul(metin)
    if not adaylar:
        return Sonuc(metin=metin)

    parcalar: List[str] = []
    imlec = 0
    grounded_sayisi = temizlenen = 0
    for aday in adaylar:
        if aday.anahtar in grounded:
            grounded_sayisi += 1
            continue                       # GROUNDED AD KORUNUR
        parcalar.append(metin[imlec:aday.bas])
        tekil, _ = _genel_ifade(aday.unvan)
        parcalar.append(tekil)
        imlec = aday.son
        temizlenen += 1
    parcalar.append(metin[imlec:])

    yeni = "".join(parcalar)
    if temizlenen:
        yeni = _tekrarlari_birlestir(yeni)
        yeni = re.sub(r"[ \t]{2,}", " ", yeni)
        if NOT_METNI not in yeni:
            yeni = yeni.rstrip() + "\n\n" + NOT_METNI
    return Sonuc(metin=yeni, bulunan=len(adaylar), grounded=grounded_sayisi,
                 temizlenen=temizlenen, degisti=bool(temizlenen))
