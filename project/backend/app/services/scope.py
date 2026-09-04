"""HİYERARŞİK KAPSAM — tek ve zorunlu süzme katmanı.

PROBLEM
-------
Arayüzde bir programa (ör. YAZMUH) inildiğinde grafikler ve tablolar hâlâ
kardeş programların verisini gösteriyordu. İki ayrı sebebi vardı:

  1. Arayüz `?faculty=MUHMIM&program=YAZMUH` gibi KOD gönderiyordu; uçlar
     ise `faculty_id` / `academic_program_id` bekliyor. FastAPI tanımadığı
     sorgu parametresini sessizce ATAR — filtre hiç uygulanmıyordu.
  2. Bazı uçlar (finans, kapasite, KPI, sürdürülebilirlik, erken uyarı,
     sanayi katkısı) hiçbir kapsam parametresi kabul etmiyordu; hangi birim
     seçilirse seçilsin üniversite geneli veriyi döndürüyorlardı.

ÇÖZÜM
-----
Kapsam artık tek bir yerde çözülür ve **ID ilişkileri** üzerinden yürür;
ad/kod metni tahmini yapılmaz. `resolve()` seçili kapsamı doğrular ve o
kapsamın ALTINDA KALAN tüm program/bölüm/fakülte kimliklerini döndürür.
Servisler bu kümelerle süzer.

KURALLAR (kullanıcı gereksinimi)
--------------------------------
  UNIVERSITY  : akademik birimler arası karşılaştırma serbest
  FACULTY     : yalnızca o fakültenin bölüm ve programları
  DEPARTMENT  : yalnızca o bölümün programları
  PROGRAM     : YALNIZCA seçili program — kardeş program ASLA görünmez

Alt kapsam, üst kapsamın veya kardeşlerin verisini sızdıramaz. Tutarsız
kombinasyon (başka fakültenin bölümü gibi) 400 ile reddedilir; sessizce
"en yakın" kapsama düşürülmez, çünkü bu kullanıcıya yanlış veriyi doğru
başlıkla gösterirdi.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final, FrozenSet, List, Optional

from fastapi import HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AcademicProgram, Department, Faculty
from app.services.unit_types import ACADEMIC_UNIT_TYPES

UNIVERSITY: Final = "university"
FACULTY_LEVEL: Final = "faculty"
DEPARTMENT_LEVEL: Final = "department"
PROGRAM_LEVEL: Final = "program"

#: En genişten en dara.
LEVELS: Final = (UNIVERSITY, FACULTY_LEVEL, DEPARTMENT_LEVEL, PROGRAM_LEVEL)


@dataclass(frozen=True)
class Scope:
    """Çözülmüş kapsam: hangi seviyede olduğumuz ve hangi ID'leri kapsadığı.

    `program_ids` / `department_ids` / `faculty_ids` daima **kapsam içindeki
    tüm torunları** içerir. Üniversite seviyesinde hepsi `None`'dır; bu
    "filtre yok" demektir, "hiçbir şey yok" değil.
    """

    level: str = UNIVERSITY
    faculty_id: Optional[int] = None
    department_id: Optional[int] = None
    academic_program_id: Optional[int] = None

    faculty_ids: Optional[FrozenSet[int]] = None
    department_ids: Optional[FrozenSet[int]] = None
    program_ids: Optional[FrozenSet[int]] = None

    #: Ekranda gösterilecek kapsam adı ("Yazılım Mühendisliği Bölümü" gibi).
    label: str = "Üniversite geneli"

    #: Kapsam içindeki program KODLARI. Kod bekleyen eski servisler için;
    #: eşleme yine ID üzerinden yapılır, kod yalnızca çıktı biçimidir.
    program_codes: FrozenSet[str] = field(default_factory=frozenset)

    @property
    def is_university(self) -> bool:
        return self.level == UNIVERSITY

    @property
    def is_program(self) -> bool:
        return self.level == PROGRAM_LEVEL

    def allows_program(self, program_id: Optional[int]) -> bool:
        """Bu program kapsam içinde mi?"""
        if self.program_ids is None:
            return True
        return program_id in self.program_ids

    def allows_department(self, department_id: Optional[int]) -> bool:
        if self.department_ids is None:
            return True
        return department_id in self.department_ids

    def allows_faculty(self, faculty_id: Optional[int]) -> bool:
        if self.faculty_ids is None:
            return True
        return faculty_id in self.faculty_ids

    def allows_program_code(self, code: Optional[str]) -> bool:
        """Yalnızca program KODU olan (eski) veri satırları için."""
        if self.program_ids is None:
            return True
        return bool(code) and code in self.program_codes

    def filter_rows(self, rows, *, program_id="program_id",
                    department_id="department_id", faculty_id="faculty_id",
                    program_code=None):
        """Sözlük veya nesne listesini kapsama göre süzer.

        En dar bilinen alan kullanılır: program > bölüm > fakülte. Satırda
        hiçbir kapsam alanı yoksa satır DIŞARIDA BIRAKILIR — kapsamı
        bilinmeyen bir satırı içeride tutmak, tam olarak düzeltmeye
        çalıştığımız sızıntıdır.
        """
        if self.program_ids is None and self.department_ids is None \
                and self.faculty_ids is None:
            return list(rows)

        def oku(satir, ad):
            if ad is None:
                return None
            if isinstance(satir, dict):
                return satir.get(ad)
            return getattr(satir, ad, None)

        secilen = []
        for satir in rows:
            pid = oku(satir, program_id)
            did = oku(satir, department_id)
            fid = oku(satir, faculty_id)
            pcode = oku(satir, program_code)

            if pid is not None:
                uygun = self.allows_program(pid)
            elif pcode is not None and self.program_ids is not None:
                uygun = self.allows_program_code(pcode)
            elif did is not None:
                uygun = self.allows_department(did)
            elif fid is not None:
                uygun = self.allows_faculty(fid)
            else:
                uygun = False
            if uygun:
                secilen.append(satir)
        return secilen


def _hata(mesaj: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=mesaj)


def resolve(
    db: Session,
    faculty_id: Optional[int] = None,
    department_id: Optional[int] = None,
    academic_program_id: Optional[int] = None,
) -> Scope:
    """Kapsamı doğrular ve torun ID kümelerini hesaplar.

    En dar parametre kazanır: program verilmişse fakülte/bölüm ondan
    türetilir. Böylece istemcinin gönderdiği üst seviye bilgisi, alt seviye
    ile ÇELİŞİYORSA sessizce kabul edilmez.
    """
    # --- PROGRAM ---
    if academic_program_id is not None:
        program = db.get(AcademicProgram, academic_program_id)
        if program is None:
            raise _hata(f"Program bulunamadı: id={academic_program_id}")
        bolum = db.get(Department, program.department_id)
        if bolum is None:
            raise _hata(f"Programın bölümü bulunamadı: id={academic_program_id}")
        if department_id is not None and department_id != bolum.id:
            raise _hata(
                f"Tutarsız kapsam: {program.code} programı "
                f"{department_id} numaralı bölüme ait değil."
            )
        if faculty_id is not None and faculty_id != bolum.faculty_id:
            raise _hata(
                f"Tutarsız kapsam: {program.code} programı "
                f"{faculty_id} numaralı fakülteye ait değil."
            )
        return Scope(
            level=PROGRAM_LEVEL,
            faculty_id=bolum.faculty_id,
            department_id=bolum.id,
            academic_program_id=program.id,
            faculty_ids=frozenset({bolum.faculty_id}),
            department_ids=frozenset({bolum.id}),
            # TEK program. Kardeşler burada YOKTUR.
            program_ids=frozenset({program.id}),
            program_codes=frozenset({program.code}),
            label=program.name,
        )

    # --- BÖLÜM ---
    if department_id is not None:
        bolum = db.get(Department, department_id)
        if bolum is None:
            raise _hata(f"Bölüm bulunamadı: id={department_id}")
        if faculty_id is not None and faculty_id != bolum.faculty_id:
            raise _hata(
                f"Tutarsız kapsam: {bolum.code} bölümü "
                f"{faculty_id} numaralı fakülteye ait değil."
            )
        programlar = db.execute(
            select(AcademicProgram.id, AcademicProgram.code)
            .where(AcademicProgram.department_id == bolum.id)
        ).all()
        return Scope(
            level=DEPARTMENT_LEVEL,
            faculty_id=bolum.faculty_id,
            department_id=bolum.id,
            faculty_ids=frozenset({bolum.faculty_id}),
            department_ids=frozenset({bolum.id}),
            program_ids=frozenset(p.id for p in programlar),
            program_codes=frozenset(p.code for p in programlar),
            label=bolum.name,
        )

    # --- FAKÜLTE ---
    if faculty_id is not None:
        fakulte = db.get(Faculty, faculty_id)
        if fakulte is None:
            raise _hata(f"Fakülte bulunamadı: id={faculty_id}")
        bolum_ids = [
            b for (b,) in db.execute(
                select(Department.id).where(Department.faculty_id == fakulte.id)
            )
        ]
        programlar = db.execute(
            select(AcademicProgram.id, AcademicProgram.code)
            .where(AcademicProgram.department_id.in_(bolum_ids or [-1]))
        ).all()
        return Scope(
            level=FACULTY_LEVEL,
            faculty_id=fakulte.id,
            faculty_ids=frozenset({fakulte.id}),
            department_ids=frozenset(bolum_ids),
            program_ids=frozenset(p.id for p in programlar),
            program_codes=frozenset(p.code for p in programlar),
            label=fakulte.name,
        )

    # --- ÜNİVERSİTE ---
    return Scope()


def academic_faculty_ids(db: Session) -> List[int]:
    """Akademik birimlerin ID'leri — idari birimler (Rektörlük) hariç.

    Üniversite seviyesindeki "fakülteleri karşılaştır" görünümleri bunu
    kullanır; aksi hâlde Rektörlük 0 öğrencili bir fakülte gibi grafiğe
    girer.
    """
    return [
        f for (f,) in db.execute(
            select(Faculty.id).where(Faculty.unit_type.in_(ACADEMIC_UNIT_TYPES))
        )
    ]


# --------------------------------------------------------------------------
# FastAPI bağımlılığı
# --------------------------------------------------------------------------


def scope_params(
    faculty_id: Optional[int] = Query(default=None, ge=1,
                                      description="Kapsam: fakülte kimliği"),
    department_id: Optional[int] = Query(default=None, ge=1,
                                         description="Kapsam: bölüm kimliği"),
    academic_program_id: Optional[int] = Query(
        default=None, ge=1, description="Kapsam: program kimliği"),
) -> dict:
    """Kapsam sorgu parametrelerini tek yerde tanımlar.

    Router'lar bunu `Depends` ile alır; parametre adları böylece bütün
    uçlarda AYNI kalır. Arayüz tek bir kapsam sözlüğü gönderir.
    """
    return {
        "faculty_id": faculty_id,
        "department_id": department_id,
        "academic_program_id": academic_program_id,
    }
