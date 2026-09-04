"""KARŞILAŞTIRMA EVRENİ NİYETİ — "kimlerle kıyaslayayım?"

Kullanıcının cümlesinden karşılaştırma evrenini DETERMİNİSTİK olarak
çıkarır. Dil modeli bu kararı VERMEZ; burada anahtar sözcüklerle
çözülür, çünkü yanlış evren sessizce yanlış bir kıyas üretir ve
kullanıcı bunu fark edemez.

İKİ AYRI BOYUT
--------------
    KURUM TÜRÜ    : all | state | foundation | similar
    AÇIK KURUM    : "ODTÜ ile karşılaştır" → o kurum

AÇIK KURUM DAİMA KAZANIR
------------------------
Ekranda "Vakıf" seçiliyken kullanıcı "ODTÜ ile karşılaştır" derse ODTÜ
gelir. Ekran süzgeci bir VARSAYILANDIR; o turdaki açık istek onu geçersiz
kılar. Aksi hâlde kullanıcı adını yazdığı kurumu göremez ve sebebini de
anlayamaz — ekranda kalan eski bir seçim yüzünden.

"BENZER" ARTIK TÜR DEMEK DEĞİL
------------------------------
"benzer üniversiteler" ölçek benzerliğidir; devlet de vakıf da içerebilir
(bkz. university_competitor_service.SIMILAR_LOWER/UPPER).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Dict, List, Optional, Tuple

FILTER_ALL = "all"
FILTER_STATE = "state"
FILTER_FOUNDATION = "foundation"
FILTER_SIMILAR = "similar"

#: Kurum türü kalıpları. Sıra ÖNEMLİ: "benzer ölçekli" ifadesi
#: "benzer"den önce denenir.
_KALIPLAR: Tuple[Tuple[str, "re.Pattern[str]"], ...] = (
    (FILTER_SIMILAR, re.compile(
        r"benzer\s+ölçek|benzer\s+olcek|ölçek\s*olarak\s*benzer|"
        r"aynı\s*ölçek|ayni\s*olcek|benzer\s+büyüklük", re.I)),
    (FILTER_STATE, re.compile(
        r"\bdevlet\s*üniversite|\bdevlet\s*universite|\bdevletler\b|"
        r"\bdevletlerle\b|\bkamu\s*üniversite|\bdevlet\s*okul", re.I)),
    (FILTER_FOUNDATION, re.compile(
        r"\bvakıf\b|\bvakif\b|\bözel\s*üniversite|\bozel\s*universite|"
        r"\bözel\s*okul", re.I)),
    (FILTER_ALL, re.compile(
        r"\btüm\s*üniversite|\btum\s*universite|\bbütün\s*üniversite|"
        r"\bhepsiyle\b|\btümüyle\s*karşılaştır|\bankara'?daki\s*tüm", re.I)),
    # En sona: yalın "benzer üniversiteler". Artık ÖLÇEK benzerliğidir,
    # tür kısıtı içermez.
    (FILTER_SIMILAR, re.compile(r"benzer\s+üniversite|benzer\s+universite", re.I)),
)

_TR = str.maketrans("ÇĞİIÖŞÜçğıiöşü", "CGIIOSUcgiiosu")


def _sade(metin: str) -> str:
    d = unicodedata.normalize("NFKD", str(metin or "").translate(_TR))
    d = "".join(c for c in d if not unicodedata.combining(c)).upper()
    return re.sub(r"[^A-Z0-9]+", " ", d).strip()


#: Yaygın kısaltmalar → kurumun tam adı. Elle yazılır; tahmin edilmez.
_KISALTMALAR: Dict[str, str] = {
    "ODTU": "ORTA DOĞU TEKNİK ÜNİVERSİTESİ",
    "METU": "ORTA DOĞU TEKNİK ÜNİVERSİTESİ",
    "AYBU": "ANKARA YILDIRIM BEYAZIT ÜNİVERSİTESİ",
    "ASBU": "ANKARA SOSYAL BİLİMLER ÜNİVERSİTESİ",
    "AHBV": "ANKARA HACI BAYRAM VELİ ÜNİVERSİTESİ",
    "TOBB": "TOBB EKONOMİ VE TEKNOLOJİ ÜNİVERSİTESİ",
    "THK": "TÜRK HAVA KURUMU ÜNİVERSİTESİ",
    "ABU": "ANKARA BİLİM ÜNİVERSİTESİ",
}


def detect_institution_filter(message: str) -> Optional[str]:
    """Cümledeki kurum türü niyeti. Yoksa None (çağıran varsayılanı seçer)."""
    for kip, kalip in _KALIPLAR:
        if kalip.search(message or ""):
            return kip
    return None


#: PROGRAM EŞLEŞTİRME NİYETİ — kurum türü niyetinden AYRI çözülür.
#: Sıra ÖNEMLİ: "ortak bölüm" ve "benzer bölüm" ifadeleri, tek başına
#: "aynı"dan önce denenir ki "aynı fakültedeki ortak bölümler" gibi bir
#: cümle yanlış kipe düşmesin.
MATCH_SAME = "same_program"
MATCH_SIMILAR = "similar_programs"
MATCH_SHARED = "shared_programs"

_ESLESME_KALIPLARI: Tuple[Tuple[str, "re.Pattern[str]"], ...] = (
    (MATCH_SHARED, re.compile(
        r"ortak\s+(bölüm|program|bolum)", re.IGNORECASE)),
    (MATCH_SIMILAR, re.compile(
        r"benzer\s+(bölüm|program|bolum)|yakın\s+(bölüm|program)"
        r"|aynı\s+alan|ayni\s+alan|benzer\s+alan", re.IGNORECASE)),
    (MATCH_SAME, re.compile(
        r"(aynı|ayni)\s+(bölüm|program|bolum)|birebir\s+(aynı|ayni)",
        re.IGNORECASE)),
)


def detect_matching_mode(message: str) -> Optional[str]:
    """Cümledeki program eşleştirme niyeti. Yoksa None.

    Kurum türü niyetini OKUMAZ ve ona yazmaz: "vakıf üniversiteleriyle
    benzer bölümler üzerinden karşılaştır" cümlesi iki boyutu da ayrı
    ayrı doldurur, biri diğerini bastırmaz.
    """
    for kip, kalip in _ESLESME_KALIPLARI:
        if kalip.search(message or ""):
            return kip
    return None


def detect_explicit_universities(message: str,
                                 bilinen_adlar: List[str]) -> List[str]:
    """Cümlede AÇIKÇA adı geçen kurumlar.

    `bilinen_adlar` veritabanındaki gerçek kurum adlarıdır; buradan
    seçim yapılır, yeni ad UYDURULMAZ. Eşleşme normalize tam-kelime
    içermeye dayanır; bulanık benzerlik kullanılmaz.
    """
    sade_mesaj = _sade(message)
    if not sade_mesaj:
        return []
    bulunan: List[str] = []

    for kisa, tam in _KISALTMALAR.items():
        if re.search(rf"\b{kisa}\b", sade_mesaj) and tam not in bulunan:
            if any(_sade(a) == _sade(tam) for a in bilinen_adlar):
                bulunan.append(tam)

    for ad in bilinen_adlar:
        sade_ad = _sade(ad)
        if not sade_ad:
            continue
        # "ÜNİVERSİTESİ" sözcüğü olmadan da yakalanabilsin:
        # "Atılım ile karşılaştır" → ATILIM ÜNİVERSİTESİ
        cekirdek = re.sub(r"\bUNIVERSITESI\b", "", sade_ad).strip()
        if not cekirdek or len(cekirdek) < 4:
            continue
        if cekirdek in sade_mesaj and ad not in bulunan:
            bulunan.append(ad)
    return bulunan


def resolve_comparison_universe(
    message: str,
    bilinen_adlar: List[str],
    ekran_filtresi: Optional[str] = None,
    ekran_eslesme: Optional[str] = None,
) -> dict:
    """Bu tur için karşılaştırma evreni.

    Öncelik sırası — PAZARLIK YOK:
      1. Cümlede AÇIKÇA adı geçen kurum(lar)  → ekran süzgecini EZER
      2. Cümledeki tür niyeti (devlet/vakıf/tümü/benzer)
      3. Ekranda seçili süzgeç
      4. "all" (varsayılan evren daraltılmaz)
    """
    # --- 2. BOYUT: PROGRAM EŞLEŞTİRME ---------------------------------
    # Kurum boyutundan ÖNCE ve ONDAN BAĞIMSIZ çözülür; hangi dala
    # girilirse girilsin aynı değer döner, böylece "ODTÜ ile benzer
    # bölümler üzerinden karşılaştır" cümlesinde ikinci boyut kaybolmaz.
    eslesme_niyeti = detect_matching_mode(message)
    if eslesme_niyeti:
        eslesme = {"mode": eslesme_niyeti, "source": "message_intent"}
    elif ekran_eslesme in (MATCH_SAME, MATCH_SIMILAR, MATCH_SHARED):
        eslesme = {"mode": ekran_eslesme, "source": "screen_selector"}
    else:
        # Bağlam varsayılanı çağıranın (kapsamı bilen katmanın) işidir;
        # burada uydurulmaz.
        eslesme = {"mode": None, "source": "context_default"}

    acik = detect_explicit_universities(message, bilinen_adlar)
    if acik:
        return {
            "mode": FILTER_ALL,          # açık kurum tür süzgecine takılmaz
            "explicit_universities": acik,
            "source": "explicit_institution",
            "note": ("Adı açıkça geçen kurum(lar) için ekrandaki tür "
                     "süzgeci uygulanmadı."),
            "matching_mode": eslesme["mode"],
            "matching_mode_source": eslesme["source"],
        }
    niyet = detect_institution_filter(message)
    if niyet:
        return {"mode": niyet, "explicit_universities": [],
                "source": "message_intent", "note": None,
                "matching_mode": eslesme["mode"],
                "matching_mode_source": eslesme["source"]}
    if ekran_filtresi in (FILTER_ALL, FILTER_STATE,
                          FILTER_FOUNDATION, FILTER_SIMILAR):
        return {"mode": ekran_filtresi, "explicit_universities": [],
                "source": "screen_filter", "note": None,
                "matching_mode": eslesme["mode"],
                "matching_mode_source": eslesme["source"]}
    return {"mode": FILTER_ALL, "explicit_universities": [],
            "source": "default", "note": None,
            "matching_mode": eslesme["mode"],
            "matching_mode_source": eslesme["source"]}
