"""Üniversite alt birimlerinin TÜR sınıflandırması.

NEDEN AYRI BİR KATMAN
---------------------
`faculties` tablosu tarihsel olarak üniversitenin bütün çocuklarını
tutuyor: fakülteler, meslek yüksekokulu, enstitüler ve REKTÖRLÜK. Hepsini
"fakülte" diye göstermek üç somut hataya yol açıyordu:

  1. "Üniversitede 7 fakülte var" — oysa biri Rektörlük, biri MYO.
  2. Akademik karşılaştırmalarda idari personel akademik kadroya karışıyor.
  3. Rektörlük'ün öğrenci sayısı 0 olduğu için doluluk grafiği bozuluyor.

Tür bilgisi bir kez burada belirlenir; hem aktarım (import) hem de
API/arayüz aynı kaynaktan okur. Sınıflandırma AD'a bakar çünkü tür
bilgisi kaynak veride ayrı bir alan olarak yoktur — ama sonuç
`faculties.unit_type` sütununa YAZILIR ve sonraki bütün filtrelemeler
ad değil, o sütun ve ID ilişkileri üzerinden yapılır.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Final, FrozenSet, Tuple

# --------------------------------------------------------------------------
# Kapalı liste
# --------------------------------------------------------------------------

FACULTY: Final = "FACULTY"
VOCATIONAL_SCHOOL: Final = "VOCATIONAL_SCHOOL"
INSTITUTE: Final = "INSTITUTE"
ADMINISTRATIVE: Final = "ADMINISTRATIVE"

UNIT_TYPES: Final[Tuple[str, ...]] = (
    FACULTY,
    VOCATIONAL_SCHOOL,
    INSTITUTE,
    ADMINISTRATIVE,
)

#: Akademik grafikte ve akademik karşılaştırmalarda görünen türler.
#: Rektörlük ve benzeri idari birimler BURADA YOKTUR.
ACADEMIC_UNIT_TYPES: Final[FrozenSet[str]] = frozenset(
    {FACULTY, VOCATIONAL_SCHOOL, INSTITUTE}
)

#: Sistem / yönetim yapısına ait türler.
ADMINISTRATIVE_UNIT_TYPES: Final[FrozenSet[str]] = frozenset({ADMINISTRATIVE})

#: Arayüzde gösterilecek Türkçe adlar.
UNIT_TYPE_LABELS: Final[dict] = {
    FACULTY: "Fakülte",
    VOCATIONAL_SCHOOL: "Meslek Yüksekokulu",
    INSTITUTE: "Enstitü",
    ADMINISTRATIVE: "İdari Birim",
}


# --------------------------------------------------------------------------
# Sınıflandırma
# --------------------------------------------------------------------------

_TR = str.maketrans("ÇĞİIÖŞÜçğıiöşü", "CGIIOSUcgiiosu")


def _sadelestir(metin: str) -> str:
    """Türkçe harfleri sadeleştirip büyük harfe çevirir.

    `"İ".upper()` gibi tuzaklardan kaçınmak için önce harf çevirisi yapılır.
    """
    if not metin:
        return ""
    d = unicodedata.normalize("NFKD", metin.translate(_TR))
    return "".join(c for c in d if not unicodedata.combining(c)).upper()


# Sıra ÖNEMLİDİR: ilk eşleşen kazanır.
# "MESLEK YÜKSEKOKULU" hem "YUKSEKOKUL" hem "MESLEK" içerir; MYO kuralı
# enstitü kuralından önce gelir. Rektörlük kuralı en başta durur çünkü
# idari birim adları bazen "… FAKÜLTESİ SEKRETERLİĞİ" gibi karışık olur.
_KURALLAR: Final[Tuple[Tuple[str, str], ...]] = (
    (ADMINISTRATIVE, r"REKTORLUK|REKTORLUGU|GENEL SEKRETER|DAIRE BASKANLIGI"
                     r"|IDARI BIRIM|IDARI VE MALI|BASKANLIGI|KOORDINATORLUGU"
                     r"|MUDURLUGU(?! .*OKUL)|SEKRETERLIGI"
                     # Uygulama ve araştırma MERKEZLERİ öğrenci kaydı ve
                     # kadrosu olan akademik birimler değildir; fakülte
                     # karşılaştırmasına girerlerse 0 öğrencili bir
                     # "fakülte" gibi görünürler.
                     r"|ARASTIRMA MERKEZI|UYGULAMA VE ARASTIRMA"
                     r"|ARASTIRMA VE UYGULAMA|\bMERKEZI\b"),
    (VOCATIONAL_SCHOOL, r"MESLEK YUKSEKOKUL|MESLEK Y\.?O\.?|MYO\b"),
    (INSTITUTE, r"ENSTITU|LISANSUSTU"),
    (FACULTY, r"FAKULTE"),
    # Adında "yüksekokul" geçen ama "meslek" geçmeyen birimler (ör.
    # "Uygulamalı Bilimler Yüksekokulu") akademiktir; MYO'ya en yakın tür.
    (VOCATIONAL_SCHOOL, r"YUKSEKOKUL"),
)


def classify_unit(name: str, code: str = "") -> str:
    """Birim adından türünü çıkarır.

    Eşleşme yoksa `FACULTY` döner: veri tabanındaki mevcut (demo) kayıtların
    davranışı değişmesin diye. Bu, "bilinmiyor" demek değildir; adlandırma
    kuralına uymayan yeni bir birim türü çıkarsa kural listesine eklenmelidir.
    """
    metin = f"{_sadelestir(name)} {_sadelestir(code)}"
    for tur, desen in _KURALLAR:
        if re.search(desen, metin):
            return tur
    return FACULTY


def is_academic(unit_type: str) -> bool:
    """Bu tür akademik grafikte / karşılaştırmalarda yer alır mı?"""
    return unit_type in ACADEMIC_UNIT_TYPES
