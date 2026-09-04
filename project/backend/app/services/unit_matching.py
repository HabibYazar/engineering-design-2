"""Farklı gerçek kaynakların BİRİM ADLARINI aynı hiyerarşiye bağlar.

PROBLEM
-------
Aynı üniversiteyi iki kaynak iki farklı düzende anlatıyor:

  YÖK Akademik   → AKADEMİSYENİN bağlı olduğu örgütsel birim
                   fakülte → bölüm → anabilim dalı/program
                   "MÜHENDİSLİK VE MİMARLIK FAKÜLTESİ" /
                   "BİLGİSAYAR TEKNOLOJİLERİ BÖLÜMÜ" /
                   "BİLGİSAYAR PROGRAMCILIĞI PR."

  ÖSYM / YKS     → ÖĞRENCİNİN yerleştiği program
                   fakülte → "department" → yerleştirme programı
                   "Meslek Yüksekokulu" / "Bilgisayar Programcılığı" /
                   "Bilgisayar Programcılığı (Burslu) (2 Yıllık)"

Dikkat: ÖSYM'nin "department" dediği şey çoğu zaman YÖK'ün PROGRAMIDIR.
"Bilgisayar Programcılığı"nı yeni bir bölüm olarak açmak, gerçekte var
olan tek birimi ikiye bölerdi. Bu, "yazım farkı yüzünden kopya kayıt
oluşturma" kuralının en tehlikeli hâlidir: adlar farklı değil, SEVİYE
farklı.

ÇÖZÜM
-----
İki aşamalı arama, DARDAN GENİŞE:

    1) ad bir PROGRAM adına uyuyor mu?   → program + onun bölümü
    2) ad bir BÖLÜM adına uyuyor mu?     → bölüm
    3) hiçbiri                            → çağıran taraf karar verir
                                            (gerçekse oluşturur, değilse
                                             raporlar)

Eşleştirme normalize edilmiş ad üzerinden yapılır; ama sonuç her zaman
bir **ID**'dir. Normalizasyon yalnızca iki kaynağı buluşturmak içindir,
sonraki hiçbir sorgu ada bakmaz.

NORMALİZASYON NE YAPAR
----------------------
  * Türkçe harfleri sadeleştirir  (İ→I, Ğ→G …)
  * "(İngilizce)" gibi öğretim dili eklerini atar
  * "FAKÜLTESİ / BÖLÜMÜ / PROGRAMI / ANABİLİM DALI / PR." eklerini atar
  * noktalama ve fazla boşluğu tekleştirir

NE YAPMAZ: bulanık/benzerlik eşleştirmesi. "Bilişim Sistemleri
Mühendisliği" ile "Bilgisayar Mühendisliği" birbirine benzer ama AYRI
birimlerdir. Yakınlık puanıyla eşleştirmek iki gerçek bölümü birleştirir
ve bunu sessizce yapardı.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AcademicProgram, Department, Faculty
from app.services.unit_types import ACADEMIC_UNIT_TYPES

_TR = str.maketrans("ÇĞİIÖŞÜçğıiöşü", "CGIIOSUcgiiosu")

#: Eşleştirmede anlam taşımayan yapısal ekler.
_EKLER = re.compile(
    r"\b(FAKULTESI|FAKULTE|YUKSEKOKULU|BOLUMU|BOLUM|PROGRAMI|PROGRAM"
    r"|ANABILIM|BILIM|DALI|PR)\b\.?"
)
#: Öğretim dili / süre / burs ekleri — birim kimliğinin parçası değil.
_PARANTEZ = re.compile(
    r"\((?:INGILIZCE|ENGLISH|TURKCE|ALMANCA|FRANSIZCA|ARAPCA"
    r"|\d+\s*YILLIK|BURSLU|UCRETLI|%?\s*\d+\s*INDIRIMLI)\)"
)


def normalize_unit_name(ad: Optional[str]) -> str:
    """Birim adını karşılaştırılabilir hâle getirir."""
    if not ad:
        return ""
    d = unicodedata.normalize("NFKD", str(ad).translate(_TR))
    d = "".join(c for c in d if not unicodedata.combining(c)).upper()
    d = _PARANTEZ.sub(" ", d)
    d = _EKLER.sub(" ", d)
    return re.sub(r"[^A-Z0-9]+", " ", d).strip()


@dataclass(frozen=True)
class UnitMatch:
    """Bir kaynak adının hiyerarşideki karşılığı."""

    #: "program" | "department" | None
    level: Optional[str]
    faculty_id: Optional[int] = None
    department_id: Optional[int] = None
    academic_program_id: Optional[int] = None
    #: Veritabanındaki kanonik ad — raporlarda kullanılır.
    matched_name: Optional[str] = None

    @property
    def found(self) -> bool:
        return self.level is not None


class UnitIndex:
    """Mevcut hiyerarşinin normalize edilmiş ad dizini.

    Bir kez kurulur, aktarım boyunca kullanılır. Yeni birim eklendiğinde
    `remember_*` ile dizine yazılır; aksi hâlde aynı ad ikinci kez
    görüldüğünde tekrar oluşturulur (kopya kayıt).
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self._faculties: Dict[str, Faculty] = {}
        self._departments: Dict[str, Department] = {}
        self._programs: Dict[str, AcademicProgram] = {}
        self.reload()

    # -- kurulum -----------------------------------------------------
    def reload(self) -> None:
        self._faculties = {
            normalize_unit_name(f.name): f
            for f in self.db.execute(select(Faculty)).scalars()
        }
        self._departments = {
            normalize_unit_name(d.name): d
            for d in self.db.execute(select(Department)).scalars()
        }
        self._programs = {
            normalize_unit_name(p.name): p
            for p in self.db.execute(select(AcademicProgram)).scalars()
        }

    def remember_faculty(self, f: Faculty) -> None:
        self._faculties[normalize_unit_name(f.name)] = f

    def remember_department(self, d: Department) -> None:
        self._departments[normalize_unit_name(d.name)] = d

    def remember_program(self, p: AcademicProgram) -> None:
        self._programs[normalize_unit_name(p.name)] = p

    # -- arama -------------------------------------------------------
    def find_faculty(self, ad: str) -> Optional[Faculty]:
        """Fakülte/MYO/enstitü arar.

        İDARİ birimler (Rektörlük) bu aramadan DÖNMEZ: akademik bir
        kaynak satırı idari birime bağlanamaz. Böyle bir eşleşme,
        akademik veriyi idari yapıya sızdırırdı.
        """
        bulunan = self._faculties.get(normalize_unit_name(ad))
        if bulunan is None:
            return None
        if bulunan.unit_type not in ACADEMIC_UNIT_TYPES:
            return None
        return bulunan

    def resolve(self, ad: str, faculty: Optional[Faculty] = None) -> UnitMatch:
        """Kaynaktaki birim adını hiyerarşiye bağlar (önce program).

        `faculty` verilirse eşleşme o fakültenin altında olmak
        ZORUNDADIR. Aynı ad iki fakültede geçebilir; fakülte kısıtı
        olmadan yanlış dala bağlanma riski vardır.
        """
        anahtar = normalize_unit_name(ad)
        if not anahtar:
            return UnitMatch(level=None)

        program = self._programs.get(anahtar)
        if program is not None:
            bolum = self.db.get(Department, program.department_id)
            if faculty is None or (bolum and bolum.faculty_id == faculty.id):
                return UnitMatch(
                    level="program",
                    faculty_id=bolum.faculty_id if bolum else None,
                    department_id=program.department_id,
                    academic_program_id=program.id,
                    matched_name=program.name,
                )

        bolum = self._departments.get(anahtar)
        if bolum is not None:
            if faculty is None or bolum.faculty_id == faculty.id:
                return UnitMatch(
                    level="department",
                    faculty_id=bolum.faculty_id,
                    department_id=bolum.id,
                    matched_name=bolum.name,
                )

        return UnitMatch(level=None)
