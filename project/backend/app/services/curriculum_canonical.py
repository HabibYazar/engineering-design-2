"""Müfredatın KANONİK katmanı — uygulamanın gördüğü temiz ders listesi.

NEDEN GEREKLİ
-------------
`curriculum_courses` ham aktarımdır ve PDF çıkarımının izlerini taşır:

  * aynı ders birden çok satırda ("ATA 101" ve "ATA101")
  * ders adı yerine DÖNEM BAŞLIĞI ("Fall", "Güz 3", "SPRING 3")
  * ders adına yapışmış içindekiler noktaları
    ("Calculus I .................... 19")
  * ders adı yerine yalnız rakam ("3")

Bunlar ayrı ders DEĞİLDİR. Ham satırlar SİLİNMEZ — kaynağın ne dediği
izlenebilir kalmalı — ama arayüz ve analizler bu kanonik katmanı okur.

ÜÇ İŞLEM
--------
1. **Ad temizleme.** Noktalı dolgu ve sondaki sayfa numarası atılır;
   geriye gerçek ad kalır. Dönem başlığı veya yalnız rakam olan adlar
   KULLANILABİLİR SAYILMAZ.

2. **Birleştirme.** Anahtar: (bölüm, normalize kod). Kod yoksa
   (bölüm, normalize ad). "ATA 101" ile "ATA101" aynı derstir.
   Birleşen satırlar arasından EN İYİ ad seçilir (bkz. `_ad_puani`).

3. **Sınıf ataması.** Ders kodundaki üç haneli sayının ilk basamağı
   sınıfı verir: 1xx→1, 2xx→2, 3xx→3, 4xx→4. Çıkarılamıyorsa
   `class_year = None` ve ders "Diğer / Seçmeli" grubuna düşer.
   Bu bir TAHMİN değil, Türkiye'deki yaygın kodlama kuralının
   uygulanmasıdır; uymayan kod zorlanmaz.

ADI KURTARILAMAYAN DERS SİLİNMEZ
--------------------------------
"FALL 3" adlı satırların KODU gerçektir (IAD 121 gibi). Ders gerçekten
vardır, yalnızca adı yanlış çıkarılmıştır. Böyle bir ders kanonik
listede KODUYLA görünür; uydurma bir ad üretilmez.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import CurriculumCanonicalCourse, CurriculumCourse, Department

_TR = str.maketrans("ÇĞİIÖŞÜçğıiöşü", "CGIIOSUcgiiosu")

#: "CENG 101" / "CENG101" / "CENG-101" → ("CENG", "101")
_KOD = re.compile(r"^\s*([A-ZÇĞİÖŞÜ]{2,6})\s*[-_ ]?\s*(\d{3})\b")

#: İçindekiler dolgusu ve peşindeki sayfa numarası.
_NOKTA_DOLGU = re.compile(r"\s*[.·•]{2,}.*$")

#: Ad yerine geçmiş DÖNEM BAŞLIĞI. Sonundaki rakam kredi/saat sütunudur.
_DONEM_BASLIGI = re.compile(
    r"^(fall|spring|summer|guz|bahar|yaz|semester|donem|yariyil)"
    r"(\s*[-/ ]?\s*[ivx0-9]+)?\s*$"
)

#: Yalnız rakam, noktalama veya tek-iki harf: ad taşımıyor.
_ANLAMSIZ = re.compile(r"^[\s\d.,\-–—_/()]*$")

#: Sınıf basamağı → görünen ad. Arayüz bu adları kullanır.
CLASS_LABELS: Dict[Optional[int], str] = {
    1: "1. Sınıf",
    2: "2. Sınıf",
    3: "3. Sınıf",
    4: "4. Sınıf",
    5: "5. Sınıf",
    None: "Diğer / Seçmeli",
}


def _fold(metin: Optional[str]) -> str:
    if not metin:
        return ""
    d = unicodedata.normalize("NFKD", str(metin).translate(_TR))
    return "".join(c for c in d if not unicodedata.combining(c)).upper()


def clean_course_name(ham: Optional[str]) -> Optional[str]:
    """Ders adını temizler; kullanılabilir ad yoksa `None`.

    `None` dönmesi "bu satır ders değil" demek DEĞİLDİR — "bu satırın
    adı okunamıyor" demektir. Kodu varsa ders yine de kanonik listede
    yer alır.
    """
    if not ham:
        return None
    ad = _NOKTA_DOLGU.sub("", str(ham)).strip()
    # Sondaki yalnız kalmış sayfa/kredi numarası.
    ad = re.sub(r"\s+\d{1,3}$", "", ad).strip()
    if not ad or _ANLAMSIZ.match(ad):
        return None
    if _DONEM_BASLIGI.match(_fold(ad).lower()):
        return None
    if len(ad) < 3:
        return None
    return ad


def normalize_code(ham: Optional[str]) -> Optional[str]:
    """"ATA 101" / "ata101" → "ATA101". Kalıba uymuyorsa `None`."""
    if not ham:
        return None
    m = _KOD.match(_fold(ham))
    return f"{m.group(1)}{m.group(2)}" if m else None


def normalize_name_key(ad: Optional[str]) -> str:
    """Birleştirme anahtarı için ad normalizasyonu."""
    if not ad:
        return ""
    return re.sub(r"[^A-Z0-9]+", " ", _fold(ad)).strip()


def class_year_from_code(kod: Optional[str]) -> Optional[int]:
    """Koddaki üç haneli sayının ilk basamağı = sınıf."""
    n = normalize_code(kod)
    if not n:
        return None
    m = re.search(r"(\d)\d{2}$", n)
    if not m:
        return None
    basamak = int(m.group(1))
    return basamak if 1 <= basamak <= 5 else None


def _ad_puani(ad: Optional[str]) -> tuple:
    """Birleşen satırlar arasından en iyi adı seçmek için puan.

    Tercih sırası:
      1. Kullanılabilir ad (None değil)
      2. TAMAMI BÜYÜK HARF OLMAYAN — "Atatürk İlkeleri" okunabilir,
         "ATATÜRK İLKELERİ" başlık artığı olma ihtimali yüksek
      3. Daha uzun ad (daha az kırpılmış)
    """
    if not ad:
        return (0, 0, 0)
    buyuk_degil = 0 if ad.isupper() else 1
    return (1, buyuk_degil, len(ad))


@dataclass
class CanonicalCourse:
    """Birleştirilmiş tek gerçek ders."""

    department_id: int
    canonical_key: str
    course_code: Optional[str]
    course_name: Optional[str]
    class_year: Optional[int]
    academic_program_id: Optional[int] = None
    languages: List[str] = field(default_factory=list)
    source_types: List[str] = field(default_factory=list)
    source_row_count: int = 0
    source_row_ids: List[int] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        """Arayüzde görünecek ad. Ad okunamıyorsa KOD gösterilir."""
        return self.course_name or self.course_code or "Adsız ders"


def build_canonical(
    db: Session, department_ids: Optional[Sequence[int]] = None
) -> List[CanonicalCourse]:
    """Ham satırlardan kanonik ders listesini üretir (yazmadan)."""
    sorgu = select(CurriculumCourse).options(
        selectinload(CurriculumCourse.academic_program)
    )
    if department_ids is not None:
        sorgu = sorgu.where(
            CurriculumCourse.department_id.in_(list(department_ids) or [-1])
        )
    ham = list(db.execute(sorgu).scalars())

    kovalar: Dict[Tuple[int, str], CanonicalCourse] = {}
    for r in ham:
        kod = normalize_code(r.course_code)
        ad = clean_course_name(r.course_name)

        # Ne kodu ne kullanılabilir adı olan satır bir ders değildir.
        # (Yalnız "3" veya yalnız "Fall" olan, kodu da bulunmayan satırlar.)
        if not kod and not ad:
            continue

        anahtar = kod or normalize_name_key(ad)
        if not anahtar:
            continue

        kova = kovalar.get((r.department_id, anahtar))
        if kova is None:
            kova = CanonicalCourse(
                department_id=r.department_id,
                canonical_key=anahtar,
                course_code=r.course_code.strip() if r.course_code else None,
                course_name=ad,
                class_year=class_year_from_code(r.course_code),
                academic_program_id=r.academic_program_id,
            )
            kovalar[(r.department_id, anahtar)] = kova
        else:
            # En iyi adı sakla.
            if _ad_puani(ad) > _ad_puani(kova.course_name):
                kova.course_name = ad
            if kova.course_code is None and r.course_code:
                kova.course_code = r.course_code.strip()
            if kova.class_year is None:
                kova.class_year = class_year_from_code(r.course_code)
            if kova.academic_program_id is None:
                kova.academic_program_id = r.academic_program_id

        kova.source_row_count += 1
        kova.source_row_ids.append(r.id)
        if r.source_type and r.source_type not in kova.source_types:
            kova.source_types.append(r.source_type)

    return sorted(
        kovalar.values(),
        key=lambda c: (c.class_year is None, c.class_year or 0,
                       c.course_code or "", c.display_name),
    )


def rebuild_canonical(db: Session) -> Dict[str, int]:
    """Kanonik tabloyu ham satırlardan yeniden kurar.

    Tam yeniden kurulum yapılır: ham veri değiştiğinde artık geçerli
    olmayan kanonik satır kalmasın. Ham tabloya DOKUNULMAZ.
    """
    dersler = build_canonical(db)

    db.execute(CurriculumCanonicalCourse.__table__.delete())
    for c in dersler:
        db.add(CurriculumCanonicalCourse(
            department_id=c.department_id,
            academic_program_id=c.academic_program_id,
            canonical_key=c.canonical_key,
            course_code=c.course_code,
            course_name=c.course_name,
            display_name=c.display_name,
            class_year=c.class_year,
            source_row_count=c.source_row_count,
            source_types=", ".join(c.source_types) or None,
        ))
    db.flush()

    ham_sayi = db.execute(
        select(func.count()).select_from(CurriculumCourse)
    ).scalar_one()
    adsiz = sum(1 for c in dersler if c.course_name is None)
    return {
        "raw_rows": ham_sayi,
        "canonical_rows": len(dersler),
        "merged_or_dropped": ham_sayi - len(dersler),
        "courses_without_usable_name": adsiz,
        "classified": sum(1 for c in dersler if c.class_year is not None),
        "unclassified": sum(1 for c in dersler if c.class_year is None),
    }
