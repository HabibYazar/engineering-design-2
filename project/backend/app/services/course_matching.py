"""Akademisyenin verdiği dersleri müfredat dersleriyle eşleştirir.

İKİ GERÇEK KAYNAK
-----------------
`academic_staff_courses`  YÖK Akademik — kim, hangi yıl, hangi dersi verdi
                          (ders KODU yok; ad + dil + saat var)
`curriculum_courses`      üniversitenin müfredat kataloğu
                          (ders KODU var)

EŞLEŞTİRME SIRASI
-----------------
1. **Ders kodu** — personel kaydında kod varsa (ad içinde "CENG 101" gibi
   geçiyorsa) önce kodla eşleşir. Kod en güçlü kanıttır.
2. **Ders adı** — normalize edilmiş ad birebir aynıysa eşleşir.
3. **Birim bağlamı** — her iki aramada da aday havuzu, akademisyenin
   BÖLÜMÜNÜN müfredatıyla sınırlıdır. Aynı ad iki bölümde geçebilir;
   bölüm kısıtı olmadan bir akademisyene başka bölümün dersi atfedilirdi.

SAHTE EŞLEŞME ÜRETİLMEZ
-----------------------
Bulanık/benzerlik eşleştirmesi YOK. "Veri Yapıları" ile "Veri Yapıları ve
Algoritmalar" birbirine benzer ama AYRI derslerdir. Eşleşme bulunamazsa
`matched_curriculum_course_id` NULL kalır — bu bir hata değil, kaynakların
farklı olmasının doğal sonucudur.

ARAYÜZE TEKNİK ETİKET GİTMEZ
----------------------------
Eşleşmenin koddan mı addan mı geldiği burada bilinir ama arayüzde
"eşleşme güveni" gibi bir etiket gösterilmez; kullanıcı ders adını ve
kodunu görür.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AcademicStaff, AcademicStaffCourse, CurriculumCourse

_TR = str.maketrans("ÇĞİIÖŞÜçğıiöşü", "CGIIOSUcgiiosu")

#: "CENG 101", "MATH101", "IE 241" gibi ders kodu kalıbı.
_KOD = re.compile(r"\b([A-ZÇĞİÖŞÜ]{2,6})\s*[- ]?\s*(\d{3})\b")


def normalize_course_name(ad: Optional[str]) -> str:
    """Ders adını karşılaştırılabilir hâle getirir.

    Türkçe harf sadeleştirmesi + noktalama/boşluk tekleştirme. Sözcük
    ATILMAZ: "Veri Yapıları" ile "Veri Yapıları II" farklı derslerdir ve
    farklı kalmalıdır.
    """
    if not ad:
        return ""
    d = unicodedata.normalize("NFKD", str(ad).translate(_TR))
    d = "".join(c for c in d if not unicodedata.combining(c)).upper()
    return re.sub(r"[^A-Z0-9]+", " ", d).strip()


def normalize_course_code(kod: Optional[str]) -> str:
    """"CENG 101" / "ceng101" / "CENG-101" → "CENG101"."""
    if not kod:
        return ""
    m = _KOD.search(str(kod).translate(_TR).upper())
    if m:
        return f"{m.group(1)}{m.group(2)}"
    return re.sub(r"[^A-Z0-9]+", "", str(kod).translate(_TR).upper())


def extract_code_from_name(ad: Optional[str]) -> Optional[str]:
    """Ders ADI içinde gömülü kodu bulur.

    YÖK Akademik ders kodunu ayrı bir alanda vermiyor; bazı ders adları
    kodu metnin içinde taşıyor ("CENG 101 Algoritmalar").
    """
    if not ad:
        return None
    m = _KOD.search(str(ad).translate(_TR).upper())
    return f"{m.group(1)}{m.group(2)}" if m else None


@dataclass(frozen=True)
class CourseMatch:
    """Bir personel ders kaydının müfredat karşılığı."""

    staff_course_id: int
    curriculum_course_id: Optional[int]
    curriculum_course_code: Optional[str]
    curriculum_course_name: Optional[str]
    academic_program_id: Optional[int]
    academic_program_name: Optional[str]
    department_id: Optional[int]
    department_name: Optional[str]
    #: "code" | "name" | None — İÇ KULLANIM, arayüze gösterilmez.
    match_basis: Optional[str] = None


class CurriculumMatcher:
    """Bir bölümün müfredatını bir kez indeksler, çok kez sorgulanır."""

    def __init__(self, db: Session, department_ids: Optional[Sequence[int]] = None):
        self.db = db
        sorgu = select(CurriculumCourse)
        if department_ids is not None:
            sorgu = sorgu.where(
                CurriculumCourse.department_id.in_(list(department_ids) or [-1])
            )
        dersler = list(db.execute(sorgu).scalars())

        # Bölüm bağlamı korunur: (bölüm, anahtar) → ders.
        self._kod: Dict[Tuple[int, str], CurriculumCourse] = {}
        self._ad: Dict[Tuple[int, str], CurriculumCourse] = {}
        for c in dersler:
            kod = normalize_course_code(c.course_code)
            if kod:
                self._kod.setdefault((c.department_id, kod), c)
            ad = normalize_course_name(c.course_name)
            if ad:
                self._ad.setdefault((c.department_id, ad), c)

    def match(self, staff_course: AcademicStaffCourse,
              department_id: Optional[int]) -> CourseMatch:
        """Tek bir personel ders kaydını eşleştirir."""
        bulunan: Optional[CurriculumCourse] = None
        dayanak: Optional[str] = None

        if department_id is not None:
            # 1) Ders adı içine gömülü kod.
            kod = extract_code_from_name(staff_course.course_name)
            if kod:
                bulunan = self._kod.get((department_id, kod))
                if bulunan is not None:
                    dayanak = "code"
            # 2) Normalize edilmiş ad.
            if bulunan is None:
                ad = normalize_course_name(staff_course.course_name)
                if ad:
                    bulunan = self._ad.get((department_id, ad))
                    if bulunan is not None:
                        dayanak = "name"

        if bulunan is None:
            return CourseMatch(
                staff_course_id=staff_course.id, curriculum_course_id=None,
                curriculum_course_code=None, curriculum_course_name=None,
                academic_program_id=None, academic_program_name=None,
                department_id=department_id, department_name=None,
            )

        program = bulunan.academic_program
        bolum = bulunan.department
        return CourseMatch(
            staff_course_id=staff_course.id,
            curriculum_course_id=bulunan.id,
            curriculum_course_code=bulunan.course_code,
            curriculum_course_name=bulunan.course_name,
            academic_program_id=bulunan.academic_program_id,
            academic_program_name=program.name if program else None,
            department_id=bulunan.department_id,
            department_name=bolum.name if bolum else None,
            match_basis=dayanak,
        )


def match_staff_courses(
    db: Session, academic_staff_id: int
) -> Tuple[List[AcademicStaffCourse], Dict[int, CourseMatch]]:
    """Bir akademisyenin bütün ders kayıtlarını eşleştirir."""
    personel = db.get(AcademicStaff, academic_staff_id)
    if personel is None:
        return ([], {})

    dersler = list(db.execute(
        select(AcademicStaffCourse)
        .where(AcademicStaffCourse.academic_staff_id == academic_staff_id)
        .order_by(
            AcademicStaffCourse.academic_year.desc(),
            AcademicStaffCourse.course_name,
        )
    ).scalars())

    matcher = CurriculumMatcher(db, [personel.department_id])
    return (dersler, {d.id: matcher.match(d, personel.department_id)
                      for d in dersler})


def coverage_for_scope(db: Session, scope=None) -> dict:
    """Kapsamdaki müfredat derslerinin ne kadarı fiilen okutuluyor?

    Yönetim sorusu: "katalogda duran dersler gerçekten veriliyor mu?"
    Eşleşen müfredat dersi = en az bir akademisyenin ders geçmişinde
    karşılığı bulunan ders.
    """
    # Ders kataloğunda program FK'sı olsa da akademisyen-ders geçmişinde
    # yoktur. Bu nedenle programdaki kataloğu ölçebiliriz fakat bölümün
    # öğretim eşleşmesini programa devredemeyiz.
    if scope is not None and getattr(scope, "is_program", False):
        toplam = len(list(db.execute(
            select(CurriculumCourse.id).where(
                CurriculumCourse.academic_program_id
                == scope.academic_program_id)
        ).scalars()))
        return {
            "available": False,
            "curriculum_course_count": toplam or None,
            "matched_curriculum_course_count": None,
            "coverage_percent": None,
            "unmatched_staff_course_count": None,
            "note": (
                "Ders verme kayıtlarında program kimliği yok; bölüm "
                "eşleşmesi seçili programa devredilmez."
            ),
        }

    bolum_ids = None
    if scope is not None and getattr(scope, "department_ids", None) is not None:
        bolum_ids = list(scope.department_ids)
        if not bolum_ids:
            return {"available": False, "curriculum_course_count": 0,
                    "matched_curriculum_course_count": 0,
                    "coverage_percent": None,
                    "unmatched_staff_course_count": 0}

    matcher = CurriculumMatcher(db, bolum_ids)

    # Yıl süzgeci: kişi başına yıla göre satır tutulduğu için süzgeçsiz
    # sayım aynı akademisyeni tekrar sayar (bkz. staff_scope.py).
    from app.services import staff_scope
    personel_sorgu = staff_scope.active_staff_query(db)
    if bolum_ids is not None:
        personel_sorgu = personel_sorgu.where(
            AcademicStaff.department_id.in_(bolum_ids)
        )
    personel = {p.id: p for p in db.execute(personel_sorgu).scalars()}
    if not personel:
        eslesen_ids = set()
        eslesmeyen = 0
    else:
        ders_sorgu = select(AcademicStaffCourse).where(
            AcademicStaffCourse.academic_staff_id.in_(list(personel))
        )
        eslesen_ids = set()
        eslesmeyen = 0
        for d in db.execute(ders_sorgu).scalars():
            kisi = personel.get(d.academic_staff_id)
            m = matcher.match(d, kisi.department_id if kisi else None)
            if m.curriculum_course_id is not None:
                eslesen_ids.add(m.curriculum_course_id)
            else:
                eslesmeyen += 1

    toplam_sorgu = select(CurriculumCourse.id)
    if bolum_ids is not None:
        toplam_sorgu = toplam_sorgu.where(
            CurriculumCourse.department_id.in_(bolum_ids)
        )
    toplam = len(list(db.execute(toplam_sorgu).scalars()))

    return {
        "available": bool(toplam),
        "curriculum_course_count": toplam,
        "matched_curriculum_course_count": len(eslesen_ids),
        "coverage_percent": (
            round(len(eslesen_ids) / toplam * 100, 2) if toplam else None
        ),
        "unmatched_staff_course_count": eslesmeyen,
    }
