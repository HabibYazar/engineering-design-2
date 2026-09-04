"""Türkçe varlık çözümleme — ek-toleranslı, ama karıştırmayan.

NEDEN
-----
Kaynak seçimi metrik düzeyinde iyileşti ama VARLIK düzeyinde kırılgandı.
İki ayrı ölçülen kusur:

1. TÜRKÇE EKLER. "mühendislik", "mühendisliği", "mühendisliklerin",
   "mühendisliğinde" aynı kavramdır; tam kelime sözlüğü bunların
   hepsini yazmayı gerektirir ve eklemeli bir dilde bu liste hiç
   bitmez. Bir ek unutulduğunda soru sessizce kavramı kaçırır.

2. BENZER ADLAR. Yalnızca "bilgisayar" kelimesine bakan bir eşleştirme
   "Bilgisayar Mühendisliği" ile "Bilgisayar Programcılığı"nı aynı
   sayar. Sayı doğru okunur, cevap yanlış olur — sessiz yanlış.

Bu iki kusur zıt yönlere çeker: ekleri tolere etmek eşleşmeyi
GENİŞLETİR, benzer adları ayırmak DARALTIR. Buradaki çözüm ikisini
farklı katmanlara koyar:

  · TOKEN düzeyinde tolerans — "muhendislik" ≈ "muhendisliginde"
  · VARLIK düzeyinde katılık — eşleşen token SAYISI ve KAPSAMI ölçülür

Böylece "bilgisayar mühendisliği" sorgusu iki token birden eşleşen
"Bilgisayar Mühendisliği"ni seçer; "Bilgisayar Programcılığı" yalnızca
bir token eşleştiği için geride kalır.

NE KULLANILMADI
---------------
Morfolojik çözümleyici, gövdeleyici, transformer, dış servis, vektör
veritabanı — hiçbiri. Hepsi ya ağır bir bağımlılık ya ağ çağrısı
demekti; bu katman her soruda çalışıyor ve milisaniyeler mertebesinde
kalmalı. Yerine iki deterministik kural var: Türkçe harf katlaması ve
ortak önek ölçüsü.

VARLIK ADLARI KODA YAZILMAZ
---------------------------
Katalog `abu_kds.db` içindeki GERÇEK değerlerden kurulur. Hiçbir
üniversite, fakülte ya da program adı burada elle yazılı değildir;
veritabanına yeni bir program eklendiğinde katalog kendiliğinden onu da
tanır.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, List, Optional, Sequence, Set, Tuple

from app.services.assistant import abu_kds_store as store

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 1) NORMALİZASYON
# ---------------------------------------------------------------------------
# Türkçe'de büyük/küçük harf dönüşümü İngilizce'den farklıdır: "İ" küçük
# harfe "i", "I" ise "ı" olur. Python'un `lower()` bunu bilmez ve
# "MÜHENDİSLİK".lower() → "mühendi̇slik" gibi birleşik karakterler
# üretebilir. Aşağıdaki tablo bu dönüşümü ÖNCE yapar, ardından NFKD ile
# kalan birleşik işaretler ayıklanır.
_KATLA = str.maketrans({
    "Ç": "c", "ç": "c", "Ğ": "g", "ğ": "g", "İ": "i", "I": "i", "ı": "i",
    "Ö": "o", "ö": "o", "Ş": "s", "ş": "s", "Ü": "u", "ü": "u",
    "Â": "a", "â": "a", "Î": "i", "î": "i", "Û": "u", "û": "u",
})

_BOSLUK = re.compile(r"[^a-z0-9]+")

#: Anlam taşımayan kelimeler — eşleşme skorunu şişirmesinler.
_DURAK = frozenset({
    "ve", "ile", "icin", "gore", "olan", "olarak", "bir", "bu", "su",
    "da", "de", "ki", "mi", "mu", "ne", "nedir", "kac", "kadar", "en",
    "daki", "deki", "nin", "nun", "the", "of", "and",
})


def normalize(metin: str) -> str:
    """Türkçe metni karşılaştırılabilir hâle getirir.

    Sonuç YALNIZCA iç kullanım içindir; kullanıcıya asla gösterilmez.
    """
    if not metin:
        return ""
    sade = str(metin).translate(_KATLA)
    sade = unicodedata.normalize("NFKD", sade)
    sade = "".join(c for c in sade if not unicodedata.combining(c))
    return _BOSLUK.sub(" ", sade.lower()).strip()


def tokenlar(metin: str) -> List[str]:
    """Anlamlı token listesi. Durak kelimeler ve tek harfler atılır."""
    return [t for t in normalize(metin).split()
            if len(t) > 2 and t not in _DURAK]


# ---------------------------------------------------------------------------
# 2) EK TOLERANSI — ORTAK ÖNEK ÖLÇÜSÜ
# ---------------------------------------------------------------------------
#: Ortak önek en az bu kadar karakter olmalı. 6, ölçülerek seçildi:
#: 5'te "bilgi" ile "bilgisayar" eşleşiyordu (yanlış), 7'de
#: "bolum"/"bolumu" gibi kısa ama gerçek eşleşmeler kaçıyordu.
_EN_AZ_ONEK = 6

#: Kısa kelimelerde önek kuralı çalışmaz; tam eşitlik aranır.
_KISA_ESIK = 6

#: Ek farkı bu kadar karakteri geçerse aynı kavram sayılmaz.
#: "muhendis"(8) → "muhendisliginde"(15): fark 7. Türkçe'de üst üste
#: binen ekler bu kadar uzayabildiği için sınır geniş tutuldu; ayrımı
#: zaten VARLIK düzeyindeki token sayısı yapıyor.
_EN_FAZLA_EK = 8


def ayni_kavram(a: str, b: str, *, kisa_kavram: bool = False) -> bool:
    """İki token aynı kavram ailesinden mi.

    Kural, Türkçe'nin yapısından çıkar: ekler SONA gelir, kök başta
    durur. Dolayısıyla iki kelimenin ortak ÖNEKİ yeterince uzunsa ve
    aradaki fark bir ek yığınıyla açıklanabiliyorsa aynı kavramdırlar.

        muhendislik / muhendisliginde  → ortak önek 11, fark 4  → aynı
        bilgisayar  / bilgi            → ortak önek  5          → farklı
        endustri    / endustriyel      → ortak önek  8, fark 3  → aynı

    Son örnek bilinçlidir: "Endüstri Mühendisliği" ile "Endüstriyel
    Tasarım" bu katmanda ayrılmaz, VARLIK katmanında ayrılır — ikinci
    tokenları farklıdır.
    """
    if a == b:
        return True

    # KISA KAVRAM KELİMELERİ AYRI ELE ALINIR.
    # ------------------------------------------------------------------
    # "bölüm" beş harftir ve genel önek kuralı (en az 6) onu hiç
    # eşleştiremez; "bölümlerin" kaçardı. Ama eşiği herkes için 5'e
    # indirmek "bilgi" ile "bilgisayar"ı aynı sayardı — biri ek almış
    # kelime, öbürü birleşik kelime ve ikisi de beş harfle başlıyor.
    #
    # Ayrım şudur: kısa kural YALNIZCA tür/metrik İPUÇLARI için açılır
    # ("bölüm", "fakülte", "doluluk"). Bunlar kapalı ve küçük bir küme;
    # varlık ADLARI hiçbir zaman bu yoldan geçmez, dolayısıyla
    # "bilgisayar" gibi adlar yanlış eşleşemez.
    en_az = 5 if kisa_kavram else _EN_AZ_ONEK
    esik = 5 if kisa_kavram else _KISA_ESIK
    if len(a) < esik or len(b) < esik:
        return False
    ortak = 0
    for x, y in zip(a, b):
        if x != y:
            break
        ortak += 1
    if ortak < en_az:
        return False
    return (max(len(a), len(b)) - ortak) <= _EN_FAZLA_EK


def _kok(token: str) -> str:
    """Ters indeks anahtarı — token'ın ilk `_EN_AZ_ONEK` karakteri.

    Aynı kavramın bütün ek biçimleri aynı kovaya düşer; kova içindeki
    kesin karşılaştırmayı `ayni_kavram` yapar. Böylece her sorguda
    bütün varlıkları taramak gerekmez.
    """
    return token[:_EN_AZ_ONEK]


# ---------------------------------------------------------------------------
# 3) KATALOG
# ---------------------------------------------------------------------------
#: Varlık türü → o türü taşıyan sütun adları (şemada aranır).
#: Sütun ADLARI kalıptır, varlık adları değil — hiçbir üniversite ya da
#: program adı burada yazılı değildir.
_TUR_SUTUN: Dict[str, re.Pattern] = {
    "university": re.compile(
        r"^(universite|university_name|universite_adi|kurum_adi)$", re.I),
    "faculty": re.compile(r"^(fakulte|faculty|faculty_name)$", re.I),
    "department": re.compile(
        r"^(bolum|department|department_name|bolum_grubu)$", re.I),
    "program": re.compile(r"^(program_name|program_adi)$", re.I),
}

#: Program adlarındaki burs/dil ekleri: "(Burslu)", "(%50 İndirimli)",
#: "(İngilizce)". Aynı programın varyantlarıdır; canonical ad için
#: soyulur, ama orijinal ad `varyantlar` içinde saklanır.
_PARANTEZ = re.compile(r"\s*\([^)]*\)")


@dataclass
class Varlik:
    tur: str
    ad: str                              # canonical (parantezsiz)
    tokenlar: Tuple[str, ...]
    kaynaklar: Tuple[str, ...] = ()
    varyant_sayisi: int = 1

    def __hash__(self) -> int:            # sözlük anahtarı olabilsin
        return hash((self.tur, self.ad))


@dataclass
class Katalog:
    varliklar: List[Varlik] = field(default_factory=list)
    #: kök → varlık indeksleri. Lineer tarama yapılmaz.
    indeks: Dict[str, Set[int]] = field(default_factory=dict)

    def adaylar(self, sorgu_tokenlari: Sequence[str]) -> Set[int]:
        bulunan: Set[int] = set()
        for t in sorgu_tokenlari:
            bulunan |= self.indeks.get(_kok(t), set())
        return bulunan


@lru_cache(maxsize=1)
def katalog() -> Katalog:
    """Varlık kataloğu — süreçte BİR KEZ kurulur.

    Her sorguda `sqlite_master`/`PRAGMA` taramak ve `SELECT DISTINCT`
    çalıştırmak retrieval'ı saniyelere çıkarırdı. Katalog süreç ömrü
    boyunca bellekte durur; veritabanı salt okunur olduğu için
    tutarsızlık riski yoktur. Sunucu yeniden başlarsa yeniden kurulur.
    """
    k = Katalog()
    if not store.kullanilabilir():
        return k

    gorulen: Dict[Tuple[str, str], int] = {}
    for kaynak, sutunlar in store.kaynaklar().items():
        for sutun in sutunlar:
            tur = next((t for t, kal in _TUR_SUTUN.items()
                        if kal.match(sutun)), None)
            if tur is None:
                continue
            try:
                satirlar = store.satirlar(
                    kaynak, secilen=[sutun], sinir=store.EN_FAZLA_SATIR)
            except Exception:  # noqa: BLE001
                continue
            for r in satirlar:
                ham = str(r.get(sutun) or "").strip()
                if not ham or len(ham) < 3:
                    continue
                ad = _PARANTEZ.sub("", ham).strip()
                if not ad:
                    continue
                anahtar = (tur, normalize(ad))
                if anahtar in gorulen:
                    v = k.varliklar[gorulen[anahtar]]
                    if kaynak not in v.kaynaklar:
                        v.kaynaklar = v.kaynaklar + (kaynak,)
                    v.varyant_sayisi += 1
                    continue
                tk = tuple(tokenlar(ad))
                if not tk:
                    continue
                gorulen[anahtar] = len(k.varliklar)
                k.varliklar.append(
                    Varlik(tur=tur, ad=ad, tokenlar=tk, kaynaklar=(kaynak,)))

    for i, v in enumerate(k.varliklar):
        for t in v.tokenlar:
            k.indeks.setdefault(_kok(t), set()).add(i)
    logger.info("Varlık kataloğu: %d varlık, %d indeks kovası",
                len(k.varliklar), len(k.indeks))
    return k


# ---------------------------------------------------------------------------
# 4) VARLIK GRUPLARI
# ---------------------------------------------------------------------------
#: Grup ipuçları: soruda geçen kelime → grubun ADI ve grubu tanımlayan
#: TOKEN. Grup üyeleri koda YAZILMAZ; katalogdan o token'ı taşıyan
#: varlıklar toplanarak bulunur. "Mühendislikler" dendiğinde otuz
#: mühendislik programını elle listelemek yerine katalog taranır.
_GRUP_IPUCU: Tuple[Tuple[str, str, str, str], ...] = (
    # (soruda aranan token, grup adı, üyeyi tanıyan token, varlık türü)
    ("muhendis", "engineering", "muhendis", "program"),
    ("fakulte", "faculty", "fakulte", "faculty"),
    ("yuksekokul", "vocational", "yuksekokul", "faculty"),
)

#: Üniversite türü grupları — bu bilgi ad değil, VERİ sütunudur
#: (`universite_turu` = VAKIF / DEVLET). Ad eşleştirmesiyle
#: bulunamayacağı için ayrı tutulur; kaynak seçimi bunu süzgeç olarak
#: kullanır.
_UNIVERSITE_TURU = (
    ("vakif", "foundation"),
    ("ozel", "foundation"),
    ("devlet", "state"),
)


#: Varlık TÜRÜNÜ işaret eden kısa kavram kelimeleri. Varlık ADI değil,
#: tür ipucudur; bu yüzden kısa önek kuralıyla eşleştirilirler.
TUR_IPUCU: Dict[str, Tuple[str, ...]] = {
    "university": ("universite", "kurum", "rektorluk"),
    "faculty": ("fakulte", "yuksekokul"),
    "department": ("bolum",),
    "program": ("program",),
}


def tur_ipucu(sorgu_tokenlari: Sequence[str]) -> Optional[str]:
    """Soru hangi varlık türünü işaret ediyor.

    Birden çok ipucu varsa EN DAR olan kazanır: "Mühendislik
    fakültesindeki bölümler" hem fakülte hem bölüm içerir ve sorulan şey
    bölümlerdir. Sıra bilinçlidir.
    """
    for tur in ("program", "department", "faculty", "university"):
        for ip in TUR_IPUCU[tur]:
            if any(ayni_kavram(t, ip, kisa_kavram=True)
                   for t in sorgu_tokenlari):
                return tur
    return None


def kapsam_ipucu(sorgu_tokenlari: Sequence[str]) -> Optional[str]:
    """Sorunun İÇİNDE geçtiği daha geniş tür (varsa).

    "Mühendislik fakültesindeki bölümler" → kapsam faculty, sorulan
    department. İkisi ayrı alanlardır; karıştırılırsa fakülte toplamı
    bölüm cevabı yerine geçer.
    """
    for tur in ("university", "faculty"):
        for ip in TUR_IPUCU[tur]:
            if any(ayni_kavram(t, ip, kisa_kavram=True)
                   for t in sorgu_tokenlari):
                return tur
    return None


def grup_coz(sorgu_tokenlari: Sequence[str]) -> Optional[str]:
    """Soru bir varlık GRUBU mu işaret ediyor."""
    for ipucu, grup, _, _ in _GRUP_IPUCU:
        if any(ayni_kavram(t, ipucu, kisa_kavram=True)
               for t in sorgu_tokenlari):
            return grup
    for ipucu, grup in _UNIVERSITE_TURU:
        if any(ayni_kavram(t, ipucu) or t == ipucu
               for t in sorgu_tokenlari):
            return grup
    return None


def grup_uyeleri(grup: str, tur: Optional[str] = None,
                 sinir: int = 60) -> List[str]:
    """Grubun gerçek üyeleri — katalogdan, elle liste olmadan."""
    ipucu = next((i for _, g, i, _ in _GRUP_IPUCU if g == grup), None)
    if ipucu is None:
        return []
    k = katalog()
    uyeler = [v.ad for i in k.indeks.get(_kok(ipucu), set())
              for v in (k.varliklar[i],)
              if (tur is None or v.tur == tur)
              and any(ayni_kavram(t, ipucu) for t in v.tokenlar)]
    return sorted(set(uyeler))[:sinir]


# ---------------------------------------------------------------------------
# 5) ÇÖZÜMLEME
# ---------------------------------------------------------------------------
@dataclass
class Cozum:
    varlik: Optional[Varlik] = None
    puan: float = 0.0
    belirsiz: bool = False               # iki aday çok yakın
    adaylar: List[Tuple[str, float]] = field(default_factory=list)
    grup: Optional[str] = None

    def ozet(self) -> str:
        if self.grup and not self.varlik:
            return f"group={self.grup}"
        if self.belirsiz:
            return "ambiguous(" + ",".join(
                a for a, _ in self.adaylar[:3]) + ")"
        if self.varlik:
            return f"{self.varlik.tur}:{self.varlik.ad}"
        return "-"


#: İki aday arasındaki fark bu oranın altındaysa seçim yapılmaz.
#: Yanlış varlık seçmek, seçmemekten kötüdür: kullanıcı yanlış programın
#: sayısını doğru sanır.
_BELIRSIZLIK_ORANI = 0.90

#: Bu puanın altındaki eşleşme yok sayılır — tek zayıf token yüzünden
#: rastgele bir program seçilmesin.
_EN_AZ_PUAN = 1.2


def _bitisiklik(varlik: Varlik, sorgu: Sequence[str]) -> float:
    """Varlık token'ları soruda YAN YANA mı geçiyor.

    ÖLÇÜLEN YANLIŞ: "Son iki yılda Ankara'daki bilgisayar mühendisliği
    doluluklarını ÜNİVERSİTELERE göre karşılaştır" sorusunda
    "ANKARA ÜNİVERSİTESİ" varlığının iki token'ı da soruda geçiyordu —
    ama biri başta, diğeri sonda ve tamamen başka bir işlevle. Kapsam
    ölçüsü %100 çıkıyor, varlık yanlış seçiliyordu.

    Gerçek bir varlık adı soruda bitişik yazılır ("Bilgisayar
    Mühendisliği"). Dağınık eşleşme tesadüftür. Bu ölçü 0..1 arası bir
    çarpan döndürür; tek tokenlı varlıklarda 1.0 (bitişiklik anlamsız).
    """
    if len(varlik.tokenlar) < 2:
        return 1.0
    konum: List[int] = []
    for vt in varlik.tokenlar:
        yer = next((i for i, st in enumerate(sorgu)
                    if ayni_kavram(vt, st)), None)
        if yer is not None:
            konum.append(yer)
    if len(konum) < 2:
        return 1.0
    yayilim = max(konum) - min(konum) + 1
    # İdeal: token sayısı kadar yayılım. Her fazladan kelime seyreltir.
    return max(0.25, len(konum) / yayilim)


def _puanla(varlik: Varlik, sorgu: Sequence[str],
            beklenen_tur: Optional[str]) -> float:
    """Çoklu token skorlaması.

    Tek token eşleşmesi YETMEZ: "bilgisayar" hem "Bilgisayar
    Mühendisliği"nde hem "Bilgisayar Programcılığı"nda geçer. Ayrımı
    yapan, sorgunun ve varlığın token kümelerinin NE KADARININ
    örtüştüğüdür.
    """
    eslesen = 0
    for vt in varlik.tokenlar:
        if any(ayni_kavram(vt, st) for st in sorgu):
            eslesen += 1
    if not eslesen:
        return 0.0

    varlik_kapsami = eslesen / len(varlik.tokenlar)
    sorgu_kapsami = eslesen / max(1, len(sorgu))

    yakinlik = _bitisiklik(varlik, sorgu)

    puan = eslesen * 1.0
    # Kapsam ve çok-token bonusu BİTİŞİKLİKLE ölçeklenir: dağınık
    # eşleşme bu bonusları hak etmez.
    puan += 2.5 * varlik_kapsami * yakinlik
    puan += 1.0 * sorgu_kapsami
    if eslesen >= 2:
        puan += 1.5 * yakinlik          # çok tokenlı eşleşme ayırt edici
    elif len(varlik.tokenlar) > 1:
        # TEK TOKEN, ÇOK TOKENLI VARLIK → ZAYIF EŞLEŞME.
        # "bilgisayar" kelimesi tek başına "Bilgisayar Bilimleri",
        # "Bilgisayar Mühendisliği" ve "Bilgisayar Programcılığı"nın
        # hepsine uyar. Birini seçmek yazı tura atmaktır; puan düşürülür
        # ki eşik altında kalsın ya da belirsiz sayılsın.
        puan -= 1.2
    if beklenen_tur and varlik.tur == beklenen_tur:
        puan += 1.0
    elif beklenen_tur and varlik.tur != beklenen_tur:
        puan -= 0.8
    return puan


def coz(soru: str, *, beklenen_tur: Optional[str] = None) -> Cozum:
    """Sorudaki varlığı çözer. Emin olamazsa BELİRSİZ döner."""
    sorgu = tokenlar(soru)
    if not sorgu:
        return Cozum()

    grup = grup_coz(sorgu)
    k = katalog()
    if not k.varliklar:
        return Cozum(grup=grup)

    puanlar: List[Tuple[float, Varlik]] = []
    for i in k.adaylar(sorgu):
        v = k.varliklar[i]
        p = _puanla(v, sorgu, beklenen_tur)
        if p >= _EN_AZ_PUAN:
            puanlar.append((p, v))
    if not puanlar:
        return Cozum(grup=grup)

    puanlar.sort(key=lambda x: (-x[0], len(x[1].ad)))
    adaylar = [(v.ad, round(p, 2)) for p, v in puanlar[:5]]
    en_iyi_puan, en_iyi = puanlar[0]

    # BELİRSİZLİK: ikinci aday çok yakınsa ve FARKLI bir varlıksa seçme.
    belirsiz = False
    # İlk FARKLI adayla karşılaştırılır. Aynı ad birden çok türde
    # (program ve department) katalogda bulunabiliyor; listenin ikinci
    # sırasındaki bu kopya, gerçek rakibi gizleyip belirsizliği
    # görünmez kılıyordu — ölçüldü: tek kelimelik "bilgisayar" sorgusu
    # bu yüzden kesin bir program seçiyordu.
    for ikinci_puan, ikinci in puanlar[1:]:
        if ikinci.ad == en_iyi.ad:
            continue
        if ikinci_puan >= en_iyi_puan * _BELIRSIZLIK_ORANI:
            belirsiz = True
        break

    # Grup ifadesi varsa ve tekil varlık zayıfsa grup kazanır:
    # "mühendislikler" tek bir programı değil, aileyi kasteder.
    if grup and en_iyi_puan < 4.0:
        return Cozum(puan=en_iyi_puan, adaylar=adaylar, grup=grup)

    return Cozum(varlik=None if belirsiz else en_iyi, puan=en_iyi_puan,
                 belirsiz=belirsiz, adaylar=adaylar, grup=grup)


def isinma() -> None:
    """Katalogu önceden kurar. Uygulama açılışında çağrılabilir."""
    try:
        katalog()
    except Exception:  # noqa: BLE001
        logger.warning("Varlık kataloğu kurulamadı", exc_info=True)
