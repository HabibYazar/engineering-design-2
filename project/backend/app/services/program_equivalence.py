"""PROGRAM EŞDEĞERLİĞİ — "bu program hangi programla kıyaslanabilir?"

NEDEN AYRI BİR MODÜL
--------------------
Rakip ücret kıyası eskiden yalnızca ÜNİVERSİTE düzeyindeydi: her kurumun
bütün programlarının medyanı tek bir çubuk olurdu. Yazılım Mühendisliği
seçiliyken bile ekranda kurum medyanları görünüyordu; yani ekrandaki
kapsam ile sayının kapsamı BİRBİRİNİ TUTMUYORDU.

Rakip tablosunda program adı (`competitor_tuition_fees.program_name`)
zaten var. Eksik olan şey, iki farklı kurumun yazdığı iki farklı metnin
AYNI programı mı anlattığına karar veren kuraldı. Bu modül o kuralı
tek yerde, açıkça ve DETERMİNİSTİK olarak tanımlar.

BULANIK EŞLEŞTİRME YOK
----------------------
Benzerlik oranı, alt dize araması ya da düzenleme uzaklığı KULLANILMAZ.
Sebebi somut: veri kümesinde
    "Arka-Yüz Yazılım Geliştirme"      (ön lisans)
    "Yapay Zeka Mühendisliği"
    "Bilişim Sistemleri Mühendisliği"
gibi kayıtlar var. "Yazılım" alt dizesini arayan bir kural birincisini
Yazılım Mühendisliği sanardı; "Bilgisayar"a benzerlik arayan bir kural
üçüncüsünü Bilgisayar Mühendisliği sanardı. İkisi de yanlış olurdu ve
yanlışlık ekranda doğru gibi görünürdü.

Bunun yerine her ad KANONİK BİR ANAHTARA indirgenir ve yalnızca
ANAHTARLARI BİREBİR AYNI olan kayıtlar eşleşir. Anahtar üretimi üç
adımdır ve her adım geri döndürülebilir biçimde belgelenmiştir:

    1) Yazım normalizasyonu  (Türkçe harfler, parantez, yapısal ekler)
    2) Toplu-satır elemesi   ("Tüm Programlar", "Mühendislik Fakültesi")
    3) Açık eşanlam sözlüğü  (Yazılım Mühendisliği ↔ Software Engineering)

Sözlükte olmayan bir ad kendi normalize hâlini anahtar olarak kullanır;
böylece sözlüğe eklenmemiş programlar da birebir eşleşebilir, ama asla
BAŞKA bir programla eşleşemez.

TOPLU SATIRLAR NEDEN DIŞARIDA
-----------------------------
Kaynakta "Diğer Tüm Programlar", "Lisans Programları (Genel)",
"Mühendislik Fakültesi*" gibi satırlar var. Bunlar bir programın değil,
bir kurumun ya da fakültenin toptan fiyatıdır. Program kıyasında bunları
kullanmak, tam da düzeltmeye çalıştığımız hatayı geri getirirdi: kurum
ortalamasını program fiyatı diye göstermek. Bu yüzden program/bölüm
kapsamında toplu satırlar KOHORTA ALINMAZ; bir kurumun o programı yoksa
kurum grafikten ÇIKARILIR, yerine genel ücreti konmaz.
"""

from __future__ import annotations

import re
import csv
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Dict, Final, Iterable, List, Optional, Set, Tuple

#: Türkçe harfleri ASCII karşılığına indirger. `casefold()` KULLANILMAZ:
#: "İ".lower() i + birleşen nokta üretir ve karşılaştırmayı bozar.
_TR: Final = str.maketrans("ÇĞİIÖŞÜçğıiöşü", "CGIIOSUcgiiosu")

#: Parantez içi: dil, süre, burs, "Genel" gibi nitelemeler. Bunlar
#: programın KİMLİĞİ değildir; ayrı ayrı ele alınır (dil bilgisi
#: `program_language` ile ayrıca çıkarılır).
_PARANTEZ: Final = re.compile(r"\([^)]*\)")

#: Anlam taşımayan yapısal ekler. DİKKAT: "PROGRAMLARI" burada YOK —
#: o ek toplu satırın işaretidir ve elemede kullanılır.
_YAPISAL_EK: Final = re.compile(
    r"\b(FAKULTESI|FAKULTE|YUKSEKOKULU|MYO|BOLUMU|BOLUM|PROGRAMI|PROGRAM"
    r"|ANABILIM|DALI|PR|LISANS|ONLISANS|BACHELORS?|UNDERGRADUATE|DEGREE)\b\.?"
)

#: Toplu/çoklu satır işaretleri. Program düzeyinde kıyasa GİRMEZLER.
_TOPLU_KALIP: Final = (
    re.compile(r"\bTUM\s+PROGRAMLAR"),        # "Tüm Programlar", "Diğer Tüm Programlar"
    re.compile(r"\bDIGER\b"),                 # "Diğer …"
    re.compile(r"PROGRAMLARI?\s*$"),          # "… Programları", "… Programlar"
    re.compile(r"FAKULTESI\s*$"),             # "Mühendislik Fakültesi*"
    re.compile(r"YUKSEKOKULU\s*$"),
    re.compile(r"\bGENEL\s*$"),
)

#: AÇIK EŞANLAM SÖZLÜĞÜ.
#: Sol taraf: normalize edilmiş ad. Sağ taraf: kanonik anahtar.
#: Yeni bir eşanlam ancak İNSAN KARARIYLA buraya eklenir; kod kendiliğinden
#: eşanlam ÜRETMEZ. Anahtar adları İngilizce çünkü iki dilin de üstünde
#: bir kimliktir; ekranda gösterilmez.
_ESANLAM: Final[Dict[str, str]] = {
    # --- mühendislik ---
    "YAZILIM MUHENDISLIGI": "SOFTWARE_ENG",
    "SOFTWARE ENGINEERING": "SOFTWARE_ENG",
    "BILGISAYAR MUHENDISLIGI": "COMPUTER_ENG",
    "COMPUTER ENGINEERING": "COMPUTER_ENG",
    "BILISIM SISTEMLERI MUHENDISLIGI": "INFO_SYS_ENG",
    "INFORMATION SYSTEMS ENGINEERING": "INFO_SYS_ENG",
    "ELEKTRIK ELEKTRONIK MUHENDISLIGI": "EEE",
    "ELECTRICAL ELECTRONICS ENGINEERING": "EEE",
    "ELECTRICAL AND ELECTRONICS ENGINEERING": "EEE",
    "ENDUSTRI MUHENDISLIGI": "INDUSTRIAL_ENG",
    "INDUSTRIAL ENGINEERING": "INDUSTRIAL_ENG",
    "MAKINE MUHENDISLIGI": "MECHANICAL_ENG",
    "MECHANICAL ENGINEERING": "MECHANICAL_ENG",
    "INSAAT MUHENDISLIGI": "CIVIL_ENG",
    "CIVIL ENGINEERING": "CIVIL_ENG",
    "YAPAY ZEKA MUHENDISLIGI": "AI_ENG",
    "ARTIFICIAL INTELLIGENCE ENGINEERING": "AI_ENG",
    # --- sosyal / idari ---
    "ISLETME": "BUSINESS_ADMIN",
    "BUSINESS ADMINISTRATION": "BUSINESS_ADMIN",
    "YONETIM BILISIM SISTEMLERI": "MIS",
    "MANAGEMENT INFORMATION SYSTEMS": "MIS",
    "PSIKOLOJI": "PSYCHOLOGY",
    "PSYCHOLOGY": "PSYCHOLOGY",
    "HUKUK": "LAW",
    "LAW": "LAW",
    "SIYASET BILIMI VE KAMU YONETIMI": "POLITICAL_SCI_PA",
    "POLITICAL SCIENCE AND PUBLIC ADMINISTRATION": "POLITICAL_SCI_PA",
    "INGILIZCE MUTERCIM TERCUMANLIK": "EN_TRANSLATION",
    "INGILIZCE MUTERCIM VE TERCUMANLIK": "EN_TRANSLATION",
    "MUTERCIM TERCUMANLIK": "EN_TRANSLATION",
    "ENGLISH TRANSLATION AND INTERPRETING": "EN_TRANSLATION",
    # --- tasarım / mimarlık ---
    "MIMARLIK": "ARCHITECTURE",
    "ARCHITECTURE": "ARCHITECTURE",
    "IC MIMARLIK VE CEVRE TASARIMI": "INTERIOR_ARCH",
    "IC MIMARLIK VE CEVRE TASARIM": "INTERIOR_ARCH",
    "INTERIOR ARCHITECTURE AND ENVIRONMENTAL DESIGN": "INTERIOR_ARCH",
    "ENDUSTRIYEL TASARIM": "INDUSTRIAL_DESIGN",
    "INDUSTRIAL DESIGN": "INDUSTRIAL_DESIGN",
    "YENI MEDYA VE ILETISIM": "NEW_MEDIA_COMM",
    "NEW MEDIA AND COMMUNICATION": "NEW_MEDIA_COMM",
    "FILM TASARIM VE YONETIMI": "FILM_DESIGN",
    "FILM TASARIMI VE YONETIMI": "FILM_DESIGN",
    "FILM DESIGN AND DIRECTING": "FILM_DESIGN",
    "VERI MUHENDISLIGI": "COMPUTING_SOFTWARE_AI_DATA",
    "VERI BILIMI VE MUHENDISLIGI": "COMPUTING_SOFTWARE_AI_DATA",
}

#: Controlled program-family vocabulary.  Faculty aggregation uses this
#: mapping as a compatibility gate; unknown keys remain OTHER and are never
#: guessed into a family by similarity or a partial-name match.
ENGINEERING_ARCHITECTURE: Final = "ENGINEERING_ARCHITECTURE"
SOCIAL_SCIENCES: Final = "SOCIAL_SCIENCES"
ARTS_DESIGN: Final = "ARTS_DESIGN"
LAW_FAMILY: Final = "LAW"
HEALTH: Final = "HEALTH"
VOCATIONAL: Final = "VOCATIONAL"
OTHER: Final = "OTHER"

_PROGRAM_FAMILY_BY_KEY: Final[Dict[str, str]] = {
    # Engineering and architecture: explicit Atlas/current-project keys.
    **{
        key: ENGINEERING_ARCHITECTURE
        for key in {
            "SOFTWARE_ENG", "COMPUTER_ENG", "INFO_SYS_ENG", "EEE",
            "INDUSTRIAL_ENG", "MECHANICAL_ENG", "CIVIL_ENG", "AI_ENG",
            "BIYOMEDIKAL MUHENDISLIGI", "CEVRE MUHENDISLIGI",
            "ENERJI SISTEMLERI MUHENDISLIGI", "FIZIK MUHENDISLIGI",
            "GIDA MUHENDISLIGI", "HARITA MUHENDISLIGI",
            "HAVACILIK VE UZAY MUHENDISLIGI", "HIDROJEOLOJI MUHENDISLIGI",
            "JEOFIZIK MUHENDISLIGI", "JEOLOJI MUHENDISLIGI",
            "KIMYA MUHENDISLIGI", "MADEN MUHENDISLIGI",
            "MALZEME BILIMI VE NANOTEKNOLOJI MUHENDISLIGI",
            "MEKATRONIK MUHENDISLIGI", "METALURJI VE MALZEME MUHENDISLIGI",
            "NANOTEKNOLOJI MUHENDISLIGI", "NUKLEER ENERJI MUHENDISLIGI",
            "OTOMOTIV MUHENDISLIGI", "PETROL VE DOGALGAZ MUHENDISLIGI",
            "YAPAY ZEKA VE VERI MUHENDISLIGI", "ARCHITECTURE",
            "INTERIOR_ARCH", "SEHIR VE BOLGE PLANLAMA",
        }
    },
    **{
        key: SOCIAL_SCIENCES
        for key in {
            "PSYCHOLOGY", "BUSINESS_ADMIN", "MIS", "POLITICAL_SCI_PA",
            "SIYASET BILIMI VE ULUSLARARASI ILISKILER", "EN_TRANSLATION",
            "INGILIZCE OGRETMENLIGI",
        }
    },
    **{
        key: ARTS_DESIGN
        for key in {"INDUSTRIAL_DESIGN", "NEW_MEDIA_COMM", "FILM_DESIGN"}
    },
    "LAW": LAW_FAMILY,
    **{
        key: HEALTH
        for key in {
            "TIP", "DIS HEKIMLIGI", "ECZACILIK", "HEMSIRELIK",
            "FIZYOTERAPI VE REHABILITASYON", "BESLENME VE DIYETETIK",
        }
    },
    **{
        key: VOCATIONAL
        for key in {
            "BILGISAYAR PROGRAMCILIGI", "WEB TASARIMI VE KODLAMA",
            "ELEKTRONIK TEKNOLOJISI", "UCAK TEKNOLOJISI",
        }
    },
    "MATEMATIK": OTHER,
}

# ---------------------------------------------------------------------------
# DAR DİSİPLİN AİLESİ — "Benzer Bölümler" için
# ---------------------------------------------------------------------------
# NEDEN İKİNCİ BİR KATMAN
# -----------------------
# Yukarıdaki `_PROGRAM_FAMILY_BY_KEY` GENİŞ ailedir ve fakülte uyumluluğu
# için tasarlanmıştır: Maden Mühendisliği ile Yazılım Mühendisliği orada
# ikisi de ENGINEERING_ARCHITECTURE'dır. Bu, "aynı fakülteye ait mi?"
# sorusu için doğru, ama "akademik olarak benzer mi?" sorusu için
# FELAKETTİR — "mühendislik" bir benzerlik ölçütü değildir.
#
# Bu yüzden ikinci, DAHA DAR bir katman eklenir. Ayrı bir eşleştirme
# sistemi DEĞİLDİR: aynı kanonik anahtarları kullanır, yalnızca onları
# daha ince gruplara ayırır. Kayıt elle yazılır, tahmin yoktur.
#
# KAPALI LİSTE, FAIL-CLOSED
# -------------------------
# Listede olmayan anahtar `None` döner ve "benzer" kümesine GİREMEZ.
# Yeni bir program eklendiğinde sessizce bir aileye sızmaz; insan kararı
# gerekir. Yanlış bir benzerlik, eksik bir benzerlikten çok daha zararlıdır.
#
# AİLELER YALNIZCA VERİDE GERÇEKTEN BULUNAN PROGRAMLARDAN KURULDU
# ---------------------------------------------------------------
# `yok_atlas_benchmark_metrics` taranarak doğrulandı (bkz. rapor).

DISCIPLINE_COMPUTING: Final = "COMPUTING_SOFTWARE_AI_DATA"
DISCIPLINE_INDUSTRIAL: Final = "INDUSTRIAL_SYSTEMS"
DISCIPLINE_EEE: Final = "ELECTRICAL_ELECTRONICS"
DISCIPLINE_CIVIL_STRUCT: Final = "CIVIL_STRUCTURAL"
DISCIPLINE_MECH: Final = "MECHANICAL_MANUFACTURING"
DISCIPLINE_MATERIALS: Final = "MATERIALS_MINING_METALLURGY"
DISCIPLINE_EARTH_ENV: Final = "EARTH_ENVIRONMENT"
DISCIPLINE_PSYCHOLOGY: Final = "PSYCHOLOGY"
DISCIPLINE_BUSINESS: Final = "BUSINESS_MANAGEMENT"
DISCIPLINE_POLITICS: Final = "POLITICS_PUBLIC_ADMIN"
DISCIPLINE_TRANSLATION: Final = "LANGUAGE_TRANSLATION"
DISCIPLINE_LAW: Final = "LAW"
DISCIPLINE_ARCHITECTURE: Final = "ARCHITECTURE_INTERIOR"
DISCIPLINE_DESIGN_MEDIA: Final = "DESIGN_MEDIA_COMMUNICATION"

_DISCIPLINE_FAMILY_BY_KEY: Final[Dict[str, str]] = {
    # --- BİLİŞİM / YAZILIM / YAPAY ZEKÂ / VERİ ---
    # Hepsi Atlas verisinde GERÇEKTEN bulunan program adlarıdır.
    # "Yönetim Bilişim Sistemleri" BİLİNÇLİ OLARAK DIŞARIDA: işletme
    # kökenli bir programdır, mühendislik müfredatıyla kıyaslanamaz.
    "SOFTWARE_ENG": DISCIPLINE_COMPUTING,
    "COMPUTER_ENG": DISCIPLINE_COMPUTING,
    "AI_ENG": DISCIPLINE_COMPUTING,
    "YAPAY ZEKA VE VERI MUHENDISLIGI": DISCIPLINE_COMPUTING,
    "INFO_SYS_ENG": DISCIPLINE_COMPUTING,
    "BILGISAYAR BILIMLERI": DISCIPLINE_COMPUTING,

    # --- ENDÜSTRİ / SİSTEM ---
    # "Ağaç İşleri Endüstri Mühendisliği" DIŞARIDA: adında "Endüstri"
    # geçmesi onu endüstri mühendisliği yapmaz (malzeme/orman kökenli).
    "INDUSTRIAL_ENG": DISCIPLINE_INDUSTRIAL,

    # --- ELEKTRİK / ELEKTRONİK ---
    "EEE": DISCIPLINE_EEE,
    "MEKATRONIK MUHENDISLIGI": DISCIPLINE_EEE,

    # --- İNŞAAT / YAPI ---
    "CIVIL_ENG": DISCIPLINE_CIVIL_STRUCT,
    "HARITA MUHENDISLIGI": DISCIPLINE_CIVIL_STRUCT,

    # --- MAKİNE / ÜRETİM ---
    "MECHANICAL_ENG": DISCIPLINE_MECH,
    "OTOMOTIV MUHENDISLIGI": DISCIPLINE_MECH,
    "HAVACILIK VE UZAY MUHENDISLIGI": DISCIPLINE_MECH,

    # --- MALZEME / MADEN / METALURJİ ---
    "MADEN MUHENDISLIGI": DISCIPLINE_MATERIALS,
    "METALURJI VE MALZEME MUHENDISLIGI": DISCIPLINE_MATERIALS,
    "MALZEME BILIMI VE NANOTEKNOLOJI MUHENDISLIGI": DISCIPLINE_MATERIALS,
    "NANOTEKNOLOJI MUHENDISLIGI": DISCIPLINE_MATERIALS,

    # --- YER BİLİMLERİ / ÇEVRE ---
    "JEOLOJI MUHENDISLIGI": DISCIPLINE_EARTH_ENV,
    "HIDROJEOLOJI MUHENDISLIGI": DISCIPLINE_EARTH_ENV,
    "JEOFIZIK MUHENDISLIGI": DISCIPLINE_EARTH_ENV,
    "CEVRE MUHENDISLIGI": DISCIPLINE_EARTH_ENV,

    # --- SOSYAL / İDARİ ---
    "PSYCHOLOGY": DISCIPLINE_PSYCHOLOGY,
    "BUSINESS_ADMIN": DISCIPLINE_BUSINESS,
    "MIS": DISCIPLINE_BUSINESS,
    "POLITICAL_SCI_PA": DISCIPLINE_POLITICS,
    "SIYASET BILIMI VE ULUSLARARASI ILISKILER": DISCIPLINE_POLITICS,
    "EN_TRANSLATION": DISCIPLINE_TRANSLATION,
    "LAW": DISCIPLINE_LAW,

    # --- MİMARLIK / TASARIM / MEDYA ---
    "ARCHITECTURE": DISCIPLINE_ARCHITECTURE,
    "INTERIOR_ARCH": DISCIPLINE_ARCHITECTURE,
    "SEHIR VE BOLGE PLANLAMA": DISCIPLINE_ARCHITECTURE,
    "INDUSTRIAL_DESIGN": DISCIPLINE_DESIGN_MEDIA,
    "NEW_MEDIA_COMM": DISCIPLINE_DESIGN_MEDIA,
    "FILM_DESIGN": DISCIPLINE_DESIGN_MEDIA,
}

#: Eşleşme derecesi — üst veride taşınır, arayüz ve asistan bunu gösterir.
MATCH_EXACT: Final = "exact"          # aynı kanonik anahtar, aynı yazım
MATCH_EQUIVALENT: Final = "equivalent"  # aynı kanonik anahtar, farklı yazım
MATCH_SIMILAR: Final = "similar"      # farklı anahtar, AYNI dar disiplin ailesi


def discipline_family(program_key: Optional[str]) -> Optional[str]:
    """Anahtarın DAR disiplin ailesi. Kayıtlı değilse `None`.

    `None` dönmesi bilinçlidir: kayıtlı olmayan bir program "benzer"
    kümesine giremez. Geniş aile (`canonical_program_family`) ile
    KARIŞTIRILMAMALIDIR; o fakülte uyumu içindir.
    """
    if not program_key:
        return None
    return _DISCIPLINE_FAMILY_BY_KEY.get(str(program_key))


def program_match_type(home_name: Optional[str],
                       peer_name: Optional[str]) -> Optional[str]:
    """İki program adı arasındaki eşleşme derecesi.

    exact       aynı kanonik anahtar ve aynı normalize yazım
    equivalent  aynı kanonik anahtar, farklı yazım (dil/ek varyantı)
    similar     farklı anahtar ama AYNI dar disiplin ailesi
    None        akademik olarak kıyaslanabilir değil

    Bulanık benzerlik, alt dize araması ve puanlama KULLANILMAZ.
    """
    hk = canonical_program_key(home_name)
    pk = canonical_program_key(peer_name)
    if not hk or not pk:
        return None

    # YETKİLİ TABLO ÖNCE.
    # ------------------------------------------------------------------
    # Ekibin hazırladığı eşleştirme dosyası bu ABÜ bölümünü kapsıyorsa
    # KARAR ONUNDUR. Tablo o bölüm için bir ilişki yazmamışsa cevap
    # "ilişki yok"tur; aşağıdaki disiplin-ailesi tahmini DEVREYE
    # GİRMEZ. Girseydi kaynağın bilerek dışarıda bıraktığı bir eşleşme
    # arka kapıdan geri gelirdi ve süzgeç yine tahmine dayanırdı.
    #
    # Tablo bölümü hiç tanımıyorsa (kapsam dışı) eski davranış aynen
    # sürer — kapsanmayan yerlerde ekran boşalmasın diye.
    if eslesme_tablosu_kapsiyor_mu(home_name):
        return yetkili_match_type(home_name, peer_name)

    if hk == pk:
        return (MATCH_EXACT
                if normalize_program_name(home_name) == normalize_program_name(peer_name)
                else MATCH_EQUIVALENT)
    hf = discipline_family(hk)
    return MATCH_SIMILAR if hf and hf == discipline_family(pk) else None

#: Parantez içinden çıkarılabilen öğretim dili.
_DIL_ISARETI: Final = (
    ("INGILIZCE", "İngilizce"), ("ENGLISH", "İngilizce"),
    ("TURKCE", "Türkçe"), ("TURKISH", "Türkçe"),
)


def _ascii_buyuk(ad: str) -> str:
    d = unicodedata.normalize("NFKD", str(ad).translate(_TR))
    return "".join(c for c in d if not unicodedata.combining(c)).upper()


def program_language(ham_ad: Optional[str]) -> Optional[str]:
    """Ad içindeki parantezden öğretim dilini okur.

    Dil YAZMIYORSA `None` döner — uydurulmaz. "(İngilizce/Genel)" gibi
    karma yazımlarda ilk tanınan işaret alınır.
    """
    if not ham_ad:
        return None
    for parca in _PARANTEZ.findall(_ascii_buyuk(ham_ad)):
        for isaret, deger in _DIL_ISARETI:
            if isaret in parca:
                return deger
    return None


def normalize_program_name(ham_ad: Optional[str]) -> str:
    """Adı karşılaştırılabilir yazıma indirger (kanonik anahtar DEĞİL)."""
    if not ham_ad:
        return ""
    d = _ascii_buyuk(ham_ad)
    # "Bachelor's Program" is a structural suffix, not a different
    # program. Join the possessive before punctuation becomes whitespace so
    # the deterministic BACHELORS suffix rule can remove it.
    d = d.replace("'S", "S").replace("’S", "S")
    d = _PARANTEZ.sub(" ", d)          # dil/süre/burs nitelemeleri
    d = d.replace("*", " ")            # kaynaktaki dipnot yıldızı
    d = re.sub(r"[^A-Z0-9]+", " ", d).strip()
    return d


def is_aggregate_label(ham_ad: Optional[str]) -> bool:
    """Bu satır tek bir programı mı, bir yığını mı anlatıyor?

    `True` ise satır PROGRAM kıyasına giremez.
    """
    if not ham_ad:
        return True
    d = normalize_program_name(ham_ad)
    if not d:
        return True
    # VİRGÜL TOPLU SATIR İŞARETİ DEĞİLDİR.
    # ------------------------------------------------------------------
    # Burada "virgül varsa bu bir program listesidir" kuralı vardı.
    # Ölçüldü: kaynaktaki 11 virgüllü adın HİÇBİRİ liste değil, hepsi
    # tek YÖK programı ve her birinin tek program kodu var:
    #
    #     Radyo, Televizyon ve Sinema
    #     Elektrik Enerjisi Üretim, İletim ve Dağıtımı
    #     İngilizce, Fransızca Mütercim ve Tercümanlık
    #     Dezenfeksiyon, Sterilizasyon ve Antisepsi Teknikerliği
    #
    # Türkçede virgül sıralama bağlacıdır; program adının kendi
    # yazımının parçasıdır. Kural yüzünden bu programlar hiçbir zaman
    # kanonik anahtar alamadı ve veritabanına HİÇ giremedi (ölçüldü:
    # virgül içeren satır sayısı 0). 781 kayıt bu yüzden incelemeye
    # düşmüştü.
    #
    # Gerçek toplu satırlar `_TOPLU_KALIP` ile yakalanmaya devam eder:
    # "Mühendislik Programları", "Tüm Programlar", "Diğer …" gibi
    # adlar noktalamaya değil, açık toplu sözcüklere dayanır.
    return any(k.search(d) for k in _TOPLU_KALIP)


def canonical_program_key(ham_ad: Optional[str]) -> Optional[str]:
    """Kanonik program anahtarı. Toplu satırlarda `None`.

    Sözlükte bulunmayan ad, yapısal ekleri atılmış normalize hâlini
    anahtar olarak kullanır: birebir aynı yazan iki kayıt eşleşir,
    farklı yazan hiçbir kayıt eşleşmez.
    """
    if is_aggregate_label(ham_ad):
        return None
    d = normalize_program_name(ham_ad)
    if d in _ESANLAM:                       # ek atmadan önce tam ad denenir
        return _ESANLAM[d]
    sade = re.sub(r"\s+", " ", _YAPISAL_EK.sub(" ", d)).strip()
    if sade in _ESANLAM:
        return _ESANLAM[sade]
    return sade or None


def canonical_program_family(program_key: Optional[str]) -> str:
    """Return a controlled family for an already-canonical program key.

    The default is deliberately ``OTHER``.  This makes faculty aggregation
    fail closed: a new or misspelled program is not treated as engineering
    merely because it looks similar to a known engineering name.
    """
    if not program_key:
        return OTHER
    return _PROGRAM_FAMILY_BY_KEY.get(str(program_key), OTHER)


def canonical_faculty_key(name: Optional[str]) -> Optional[str]:
    """Deterministic faculty equivalence; never fuzzy or score based.

    Engineering faculty labels vary structurally (engineering, engineering
    and architecture, engineering and natural sciences). They form one
    explicit, documented category. Other faculties match only after exact
    normalization and structural suffix removal.
    """
    normalized = normalize_program_name(name)
    if not normalized:
        return None
    if "MUHENDISLIK" in set(normalized.split()):
        return "ENGINEERING_FACULTY"
    for suffix in (" FAKULTESI", " FAKULTE"):
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)].strip()
    return normalized or None


def keys_for_names(adlar: Iterable[Optional[str]]) -> Set[str]:
    """Bir ad kümesinin kanonik anahtarları (toplu satırlar elenir)."""
    return {k for k in (canonical_program_key(a) for a in adlar) if k}


#: Ekranda gösterilmeyecek yapısal kuyruklar (başlıkta çirkin durur).
_GOSTERIM_KUYRUK: Final = re.compile(
    r"\s*\b(PR|PROGRAMI|BÖLÜMÜ|BOLUMU|BÖLÜM)\b\.?\s*$", re.IGNORECASE)


def _tr_kucuk(s: str) -> str:
    """Türkçe küçültme. `lower()` tek başına I→i yapar; bu yanlıştır."""
    return s.replace("I", "ı").replace("İ", "i").lower()


def _tr_bas_harf(kelime: str) -> str:
    if not kelime:
        return kelime
    ilk = kelime[0]
    ilk = "İ" if ilk == "i" else ("I" if ilk == "ı" else ilk.upper())
    return ilk + kelime[1:]


#: Büyük harfe çevrilmeyen bağlaçlar.
_BAGLAC: Final = {"ve", "ile", "veya"}


def display_program_name(ham_ad: Optional[str]) -> str:
    """Başlıkta gösterilecek program adı.

    Veritabanındaki adlar kaynaktan TÜMÜ BÜYÜK HARF ve "PR." kuyruğuyla
    geliyor ("YAZILIM MÜHENDİSLİĞİ PR."). Bu hâliyle bir başlığa
    konamaz. Kuyruk atılır ve — yalnızca ad tümü büyükse — Türkçe
    kurallarıyla yeniden büyük/küçük yazılır. Zaten düzgün yazılmış bir
    ad OLDUĞU GİBİ bırakılır.
    """
    if not ham_ad:
        return ""
    ad = _GOSTERIM_KUYRUK.sub("", str(ham_ad).strip())
    harfler = [c for c in ad if c.isalpha()]
    if harfler and all(c == c.upper() for c in harfler):
        def _kelime(k: str) -> str:
            if k in _BAGLAC:
                return k
            # Tireli birleşikte iki taraf da büyür: "elektrik-elektronik".
            return "-".join(_tr_bas_harf(p) for p in k.split("-"))

        ad = " ".join(_kelime(k) for k in _tr_kucuk(ad).split())
    return ad.strip()


def describe_keys(anahtarlar: Iterable[str]) -> List[str]:
    """Anahtarları ekranda gösterilebilir hâle çevirir.

    Kanonik anahtar bir KİMLİKTİR, kullanıcıya gösterilecek ad değil;
    bu yüzden gösterim için sözlüğün Türkçe tarafı tercih edilir.
    """
    ters: Dict[str, str] = {}
    for ad, k in _ESANLAM.items():
        ters.setdefault(k, ad.title())
    return [ters.get(k, k.title()) for k in sorted(anahtarlar)]


def language_compatibility(bizim: Optional[str],
                           rakip: Optional[str]) -> Tuple[bool, str]:
    """İki öğretim dili karşılaştırılabilir mi?

    Döner: (aynı_dil_mi, durum)
      "ayni"          iki taraf da yazılı ve aynı
      "farkli"        iki taraf da yazılı ama farklı
      "belirtilmemis" en az bir tarafta dil yok — program yine kıyaslanır,
                      ama sınırlılık ÜST VERİDE bildirilir, dil UYDURULMAZ
    """
    if bizim and rakip:
        return (bizim == rakip, "ayni" if bizim == rakip else "farkli")
    return (False, "belirtilmemis")


# ===========================================================================
# YETKİLİ BÖLÜM EŞLEŞTİRME TABLOSU
# ===========================================================================
# `Aynı Bölümler` / `Benzer Bölümler` süzgeci artık ilişkiyi TAHMİN
# ETMİYOR. Kaynak: `data/bolum_eslesme/bolum_eslesme.csv` — ekibin
# hazırladığı `Ankara_Bilim_Ayni_Benzer_Bolumler_TAM.xlsx` dosyasından
# `build_bolum_eslesme.py` ile türetilir.
#
# NEDEN
# -----
# Aşağıdaki `program_match_type` iki adı karşılaştırıp `similar` kararını
# `discipline_family` sözlüğünden veriyordu. O sözlük elle yazılmış bir
# yakınlık tahminidir: "Yazılım Mühendisliği ile Bilgisayar Mühendisliği
# benzer mi?" sorusuna kod karar veriyordu. Artık kaynak karar veriyor —
# ve kaynağın kendi `Metadata` sayfası kararının nasıl verildiğini
# açıklıyor (AYNI: YÖK'ün `birimGrupAdi` alanı; BENZER: bölüm başına
# elle tanımlanmış anahtar kelimeler).
#
# KAPSAM SINIRI — REGRESYON KORUMASI
# ----------------------------------
# Tablo yalnızca KENDİ KAPSADIĞI ABÜ bölümleri için yetkilidir. Bir ABÜ
# bölümü tabloda hiç geçmiyorsa eski davranış aynen sürer; böylece
# tablonun kapsamadığı yerlerde ekran boşalmaz. Kapsadığı bölümlerde
# ise tablonun sessizliği "ilişki yok" demektir ve heuristik devreye
# GİRMEZ — yoksa Excel'in dışladığı bir eşleşme arka kapıdan geri
# gelirdi.
#
# DOSYA SÜREÇTE BİR KEZ OKUNUR (`@lru_cache`). Her istekte disk ya da
# Excel açılmaz.

def _eslesme_dosyasini_bul() -> Path:
    """`data/bolum_eslesme/bolum_eslesme.csv` dosyasını yukarı doğru arar.

    Sabit `parents[N]` yazmak kırılgan: bu modül
    `backend/app/services/` altında, veri ise `integration/data/`
    altında. Sayarak yazılan yol, dosya taşınınca ya da başka bir
    kopyadan çalıştırılınca sessizce boş tablo döndürüyordu — süzgeç
    de sessizce eski heuristiğe düşüyordu.
    """
    for ata in Path(__file__).resolve().parents:
        aday = ata / "data" / "bolum_eslesme" / "bolum_eslesme.csv"
        if aday.is_file():
            return aday
    return Path(__file__).resolve().parents[2] / "data" / "bolum_eslesme" / "bolum_eslesme.csv"


_ESLESME_DOSYASI: Final = _eslesme_dosyasini_bul()


@lru_cache(maxsize=1)
def _yetkili_eslesme() -> Tuple[Dict[Tuple[str, str], str], frozenset]:
    """(abu_key, peer_key) → ilişki  ve  tablodaki ABÜ bölümleri.

    Dosya yoksa BOŞ döner: sistem eski davranışıyla çalışmaya devam
    eder, hata vermez. Süzgecin kaynağı yoksa da ekran ayakta kalmalı.
    """
    eslesme: Dict[Tuple[str, str], str] = {}
    kapsanan: set = set()
    try:
        with open(_ESLESME_DOSYASI, encoding="utf-8") as fh:
            for satir in csv.DictReader(fh):
                a = (satir.get("abu_program_key") or "").strip()
                p = (satir.get("peer_program_key") or "").strip()
                iliski = (satir.get("relation") or "").strip()
                if not (a and p and iliski):
                    continue
                kapsanan.add(a)
                # Aynı çift iki sınıfta da geçerse "same" korunur:
                # daha güçlü iddia olan sınıflandırma kaybolmamalı.
                if eslesme.get((a, p)) != "same":
                    eslesme[(a, p)] = iliski
    except FileNotFoundError:
        pass
    return eslesme, frozenset(kapsanan)


def eslesme_tablosu_bilgisi() -> Dict[str, int]:
    """Teşhis için: tabloda kaç bölüm ve kaç ilişki var."""
    eslesme, kapsanan = _yetkili_eslesme()
    return {
        "abu_bolum_sayisi": len(kapsanan),
        "iliski_sayisi": len(eslesme),
        "same": sum(1 for v in eslesme.values() if v == "same"),
        "similar": sum(1 for v in eslesme.values() if v == "similar"),
    }


def yetkili_match_type(home_name: Optional[str],
                       peer_name: Optional[str]) -> Optional[str]:
    """Tablodaki ilişki; tablo bu bölümü kapsamıyorsa `None`.

    Dönüş `MATCH_EQUIVALENT` / `MATCH_SIMILAR` sözcükleriyle uyumludur
    ki çağıran kod değişmeden çalışsın.
    """
    hk = canonical_program_key(home_name)
    pk = canonical_program_key(peer_name)
    if not (hk and pk):
        return None
    eslesme, kapsanan = _yetkili_eslesme()
    if hk not in kapsanan:
        return None                      # tablo bu bölümü bilmiyor
    iliski = eslesme.get((hk, pk))
    if iliski == "same":
        # Aynı yazım ise "exact", farklı yazım ise "equivalent" —
        # mevcut ayrımı bozmamak için aynı kural uygulanır.
        return (MATCH_EXACT
                if normalize_program_name(home_name)
                == normalize_program_name(peer_name)
                else MATCH_EQUIVALENT)
    if iliski == "similar":
        return MATCH_SIMILAR
    return None


def eslesme_tablosu_kapsiyor_mu(home_name: Optional[str]) -> bool:
    """Bu ABÜ bölümü yetkili tabloda geçiyor mu?"""
    hk = canonical_program_key(home_name)
    return bool(hk and hk in _yetkili_eslesme()[1])
