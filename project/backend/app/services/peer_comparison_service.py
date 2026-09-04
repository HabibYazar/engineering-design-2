"""KARŞILAŞTIRMA KÜMESİ — kiminle kıyaslandığımızı HİYERARŞİ belirler.

PROBLEM
-------
Karşılaştırma ekranı hangi birime inilirse inilsin DIŞ üniversiteleri
gösteriyordu. Bir bölüm başkanına "sizin bölümünüz Bilkent'e göre..."
demek bir karar üretmez; onun sorduğu soru "kendi fakültemdeki diğer
bölümlere göre neredeyim?"dir.

KURAL
-----
Karşılaştırma kümesi, seçili düğümün EBEVEYNİ tarafından tanımlanır:

    ÜNİVERSİTE  → dış kıyas kurumları (benchmark_institutions)
    FAKÜLTE     → üniversitedeki DİĞER akademik fakülteler
    BÖLÜM       → AYNI fakültedeki diğer bölümler
    PROGRAM     → AYNI bölümdeki diğer programlar

Küme asla ebeveynin dışına taşmaz. Bu bir üslup tercihi değil,
yapısal bir kısıttır: kardeşler `Department.faculty_id == <fakülte>` /
`AcademicProgram.department_id == <bölüm>` sorgusuyla, yani GERÇEK
kimlik ilişkisiyle bulunur. Ad benzerliğine bakılmaz.

ÜNİVERSİTE SEVİYESİNDE İKİ FARKLI SORU
--------------------------------------
"Kurum dışarıya göre nerede?" (kıyas kurumları) ile "içeride hangi
fakülte nerede?" (fakülte kırılımı) farklı sorulardır. Birincisi
`peer_comparison`, ikincisi `child_breakdown` ile cevaplanır; ikisi
karıştırılmaz.

ÖLÇÜLMEYEN GÖSTERGE
-------------------
Her satırda her gösterge olmayabilir. Olmayan `None` döner; 0
DÖNMEZ — "kadro sıfır" ile "kadro bilinmiyor" farklı kararlar
doğurur.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AcademicProgram,
    AcademicStaff,
    AcademicStaffCourse,
    BenchmarkInstitution,
    CurriculumCanonicalCourse,
    Department,
    Faculty,
    YksPlacementRecord,
)
from app.services import student_count
from app.services import staff_scope
from app.services.scope import (
    DEPARTMENT_LEVEL,
    FACULTY_LEVEL,
    PROGRAM_LEVEL,
    UNIVERSITY,
    Scope,
)
from app.services.unit_types import ACADEMIC_UNIT_TYPES

#: Hangi seviyede kimlerle karşılaştırıldığı. Arayüz bu değere göre
#: başlık yazar; metni kendisi uydurmaz.
PEER_BASIS: Dict[str, str] = {
    UNIVERSITY: "external_institutions",
    FACULTY_LEVEL: "sibling_faculties",
    DEPARTMENT_LEVEL: "sibling_departments",
    PROGRAM_LEVEL: "sibling_programs",
}

PEER_BASIS_LABEL: Dict[str, str] = {
    "external_institutions": "Dış kıyas kurumları",
    "sibling_faculties": "Üniversitedeki diğer fakülteler",
    "sibling_departments": "Aynı fakültedeki diğer bölümler",
    "sibling_programs": "Aynı bölümdeki diğer programlar",
}


# ==========================================================================
# Birim tanımı — karşılaştırılabilir tek satır
# ==========================================================================


@dataclass(frozen=True)
class Unit:
    """Ölçülecek birim ve ALTINDA kalan gerçek kimlikler.

    Metrikler daima program/bölüm kimlikleri üzerinden toplanır; birim
    türü ne olursa olsun hesaplama aynı yerden gelir, böylece fakülte
    toplamı ile bölüm toplamları birbirini tutar.
    """

    kind: str            # "faculty" | "department" | "program"
    id: int
    code: Optional[str]
    name: str
    department_ids: FrozenSet[int]
    program_ids: FrozenSet[int]
    parent_name: Optional[str] = None


def _faculty_units(db: Session, faculty_ids: Sequence[int]) -> List[Unit]:
    if not faculty_ids:
        return []
    fakulteler = db.execute(
        select(Faculty).where(Faculty.id.in_(list(faculty_ids)))
    ).scalars().all()
    bolumler = db.execute(
        select(Department.id, Department.faculty_id)
        .where(Department.faculty_id.in_(list(faculty_ids)))
    ).all()
    programlar = db.execute(
        select(AcademicProgram.id, AcademicProgram.department_id)
    ).all()
    bolum_fak = {b: f for b, f in bolumler}

    birimler = []
    for f in fakulteler:
        bid = frozenset(b for b, fk in bolumler if fk == f.id)
        pid = frozenset(p for p, d in programlar if bolum_fak.get(d) == f.id)
        birimler.append(Unit("faculty", f.id, f.code, f.name, bid, pid))
    return birimler


def _department_units(db: Session, department_ids: Sequence[int]) -> List[Unit]:
    if not department_ids:
        return []
    bolumler = db.execute(
        select(Department).where(Department.id.in_(list(department_ids)))
    ).scalars().all()
    fak_adlari = dict(db.execute(select(Faculty.id, Faculty.name)).all())
    programlar = db.execute(
        select(AcademicProgram.id, AcademicProgram.department_id)
        .where(AcademicProgram.department_id.in_(list(department_ids)))
    ).all()
    return [
        Unit("department", b.id, b.code, b.name,
             frozenset({b.id}),
             frozenset(p for p, d in programlar if d == b.id),
             fak_adlari.get(b.faculty_id))
        for b in bolumler
    ]


def _program_units(db: Session, program_ids: Sequence[int]) -> List[Unit]:
    if not program_ids:
        return []
    programlar = db.execute(
        select(AcademicProgram).where(AcademicProgram.id.in_(list(program_ids)))
    ).scalars().all()
    bolum_adlari = dict(db.execute(select(Department.id, Department.name)).all())
    return [
        Unit("program", p.id, p.code, p.name,
             frozenset({p.department_id}), frozenset({p.id}),
             bolum_adlari.get(p.department_id))
        for p in programlar
    ]


# ==========================================================================
# Metrikler
# ==========================================================================


def _oran(pay, payda, basamak: int = 2) -> Optional[float]:
    if not payda or pay is None:
        return None
    return round(float(pay) / float(payda), basamak)


def _staff_by_department(db: Session,
                         academic_year: Optional[str] = None) -> Dict[int, dict]:
    """Bölüm başına kadro sayıları — tek sorgu, sonra bellekte toplanır."""
    # Yıl süzgeci `staff_scope` üzerinden gelir; olmazsa aynı kişi her
    # akademik yıl için tekrar sayılır (bkz. staff_scope.py).
    satirlar = db.execute(
        staff_scope.apply_staff_filters(
            select(AcademicStaff.department_id, AcademicStaff.teaching_load_hours)
            .select_from(AcademicStaff), db, donem=academic_year)
    ).all()
    out: Dict[int, dict] = {}
    for dept, saat in satirlar:
        k = out.setdefault(dept, {"total": 0, "active": 0, "hours": []})
        k["total"] += 1
        if saat is not None and saat > 0:
            k["active"] += 1
            k["hours"].append(saat)
    return out


def _latest_placement_by_program(
    db: Session, academic_year: Optional[str] = None
) -> Dict[int, dict]:
    """Programın EN GÜNCEL yerleştirme yılındaki kontenjan/yerleşen.

    Doluluk için son yıl kullanılır: yönetimin kontrol edebildiği karar
    değişkeni bu yılın kontenjanıdır, dört yılın toplamı değil.
    """
    sorgu = select(
            YksPlacementRecord.academic_program_id,
            YksPlacementRecord.placement_year,
            func.sum(YksPlacementRecord.quota),
            func.sum(YksPlacementRecord.placed_students),
        ).group_by(
            YksPlacementRecord.academic_program_id,
            YksPlacementRecord.placement_year,
        )
    if academic_year:
        yil = student_count._donem_yili(academic_year)
        if yil is None:
            return {}
        sorgu = sorgu.where(YksPlacementRecord.placement_year == yil)
    satirlar = db.execute(sorgu).all()
    en_yeni: Dict[int, dict] = {}
    for pid, yil, kont, yer in satirlar:
        onceki = en_yeni.get(pid)
        if onceki is None or yil > onceki["placement_year"]:
            en_yeni[pid] = {
                "placement_year": int(yil),
                "quota": int(kont) if kont is not None else None,
                "placed_students": int(yer) if yer is not None else None,
            }
    return en_yeni


def _courses_by_department(db: Session) -> Dict[int, int]:
    """Kanonik (tekilleştirilmiş) ders sayısı — ham satır değil."""
    return {
        d: n for d, n in db.execute(
            select(CurriculumCanonicalCourse.department_id, func.count())
            .group_by(CurriculumCanonicalCourse.department_id)
        ).all()
    }


def _teaching_records_by_department(db: Session, academic_year: Optional[str]
                                    ) -> Dict[int, dict]:
    """Cari dönemde fiilen ders veren kişi ve ders kaydı sayısı."""
    if not academic_year:
        return {}
    satirlar = db.execute(
        select(AcademicStaff.department_id,
               AcademicStaffCourse.academic_staff_id)
        .join(AcademicStaff,
              AcademicStaff.id == AcademicStaffCourse.academic_staff_id)
        .where(AcademicStaffCourse.academic_year == academic_year)
    ).all()
    out: Dict[int, dict] = {}
    for dept, sid in satirlar:
        k = out.setdefault(dept, {"records": 0, "staff": set()})
        k["records"] += 1
        k["staff"].add(sid)
    return out


def measure_units(db: Session, units: Sequence[Unit],
                  academic_year: Optional[str] = None) -> List[dict]:
    """Birim listesini aynı gösterge setiyle ölçer.

    Bütün toplu sorgular BİR KEZ çalışır; birim başına sorgu atmak 30
    birimde 150 sorgu demekti.
    """
    if not units:
        return []

    from app.services.curriculum_service import latest_course_year

    kadro = _staff_by_department(db, academic_year)
    yerlestirme = _latest_placement_by_program(db, academic_year)
    dersler = _courses_by_department(db)
    # Açık dönem seçimi başka bir ders yılına düşmez. Dönem seçilmediyse
    # geriye dönük uyumluluk için en güncel ders yılı kullanılır.
    cari_yil = academic_year or latest_course_year(db)
    ogretim = _teaching_records_by_department(db, cari_yil)
    ogrenci_kayit = student_count.program_counts(db, donem=academic_year)

    satirlar = []
    for u in units:
        # Personel, müfredat ve ders verme kayıtları program FK'sı
        # taşımıyorsa bölüm değeri programa kopyalanmaz.
        programda_olculemez = u.kind == "program"
        personel = None if programda_olculemez else sum(
            kadro.get(d, {}).get("total", 0) for d in u.department_ids)
        aktif = None if programda_olculemez else sum(
            kadro.get(d, {}).get("active", 0) for d in u.department_ids)
        saatler = [] if programda_olculemez else [
            s for d in u.department_ids
            for s in kadro.get(d, {}).get("hours", [])]

        ogrenciler = [ogrenci_kayit[p].student_count for p in u.program_ids
                      if p in ogrenci_kayit
                      and ogrenci_kayit[p].student_count is not None]
        ogrenci = sum(ogrenciler) if ogrenciler else None

        kontenjanlar = [yerlestirme[p] for p in u.program_ids if p in yerlestirme]
        kontenjan = sum(k["quota"] for k in kontenjanlar
                        if k["quota"] is not None) or None
        yerlesen = sum(k["placed_students"] for k in kontenjanlar
                       if k["placed_students"] is not None) or None

        ders = (None if programda_olculemez else
                (sum(dersler.get(d, 0) for d in u.department_ids) or None))
        ogretenler = set()
        ders_kaydi = 0
        for d in (() if programda_olculemez else u.department_ids):
            k = ogretim.get(d)
            if k:
                ogretenler |= k["staff"]
                ders_kaydi += k["records"]

        satirlar.append({
            "unit_kind": u.kind,
            "unit_id": u.id,
            "code": u.code,
            "name": u.name,
            "parent_name": u.parent_name,
            "requested_period": academic_year,
            "placement_year": (
                student_count._donem_yili(academic_year)
                if academic_year else None),
            "program_count": len(u.program_ids) or None,
            "department_count": (len(u.department_ids)
                                 if u.kind == "faculty" else None),
            # --- öğrenci ---
            "student_count": ogrenci,
            "quota": kontenjan,
            "placed_students": yerlesen,
            "occupancy_percent": (round(yerlesen / kontenjan * 100, 2)
                                  if kontenjan and yerlesen is not None else None),
            # --- kadro ---
            "academic_staff_count": personel or None,
            "active_teaching_staff_count": aktif or None,
            "students_per_academic_staff": _oran(ogrenci, personel),
            "students_per_active_teaching_staff": _oran(ogrenci, aktif),
            "academics_per_100_students": _oran(
                (personel * 100) if personel else None, ogrenci),
            "average_teaching_load_hours": _oran(sum(saatler), len(saatler))
            if saatler else None,
            # --- müfredat / öğretim ---
            "curriculum_course_count": ders,
            "courses_per_active_academic": _oran(ders, aktif),
            "current_teaching_staff_count": len(ogretenler) or None,
            "current_course_records": ders_kaydi or None,
        })

    # Öğrenci sayısı ölçülenler üstte, büyükten küçüğe.
    satirlar.sort(key=lambda r: (r["student_count"] is None,
                                 -(r["student_count"] or 0)))
    return satirlar


# ==========================================================================
# 1) Kardeş karşılaştırması — "kiminle kıyaslanıyorum?"
# ==========================================================================


def _sibling_units(db: Session, scope: Scope) -> List[Unit]:
    """Seçili düğümün kardeşleri. KİMLİK ilişkisiyle bulunur."""
    if scope.level == FACULTY_LEVEL:
        # Kardeşler: üniversitenin diğer AKADEMİK birimleri. Rektörlük
        # akademik bir fakülte değildir; listeye girmez.
        ids = [
            f for (f,) in db.execute(
                select(Faculty.id).where(
                    Faculty.unit_type.in_(ACADEMIC_UNIT_TYPES))
            )
        ]
        return _faculty_units(db, ids)

    if scope.level == DEPARTMENT_LEVEL:
        ids = [
            d for (d,) in db.execute(
                select(Department.id).where(
                    Department.faculty_id == scope.faculty_id)
            )
        ]
        return _department_units(db, ids)

    if scope.level == PROGRAM_LEVEL:
        ids = [
            p for (p,) in db.execute(
                select(AcademicProgram.id).where(
                    AcademicProgram.department_id == scope.department_id)
            )
        ]
        return _program_units(db, ids)

    return []


def _selected_id(scope: Scope) -> Optional[int]:
    return {
        FACULTY_LEVEL: scope.faculty_id,
        DEPARTMENT_LEVEL: scope.department_id,
        PROGRAM_LEVEL: scope.academic_program_id,
    }.get(scope.level)


def _parent_info(db: Session, scope: Scope) -> dict:
    """Karşılaştırmanın ÜST SINIRI — hangi kutunun içindeyiz?"""
    if scope.level == DEPARTMENT_LEVEL and scope.faculty_id:
        f = db.get(Faculty, scope.faculty_id)
        return {"kind": "faculty", "id": scope.faculty_id,
                "name": f.name if f else None}
    if scope.level == PROGRAM_LEVEL and scope.department_id:
        d = db.get(Department, scope.department_id)
        return {"kind": "department", "id": scope.department_id,
                "name": d.name if d else None}
    if scope.level == FACULTY_LEVEL:
        return {"kind": "university", "id": None, "name": "Üniversite"}
    return {"kind": None, "id": None, "name": None}


def _external_institutions(db: Session) -> List[dict]:
    kurumlar = db.execute(
        select(BenchmarkInstitution)
        .where(BenchmarkInstitution.is_active.is_(True))
        .order_by(BenchmarkInstitution.name)
    ).scalars().all()
    return [
        {
            "unit_kind": "external_institution",
            "unit_id": k.id,
            "name": k.name,
            "country": k.country,
            "city": k.city,
            "institution_type": k.institution_type,
            "is_competitor": k.is_competitor,
        }
        for k in kurumlar
    ]


def peer_comparison(db: Session, scope: Optional[Scope] = None,
                    academic_year: Optional[str] = None) -> dict:
    """Seçili kapsamın karşılaştırma kümesi.

    Küme ebeveyn tarafından sınırlanır; hiçbir seviyede yukarı taşmaz.
    """
    scope = scope or Scope()
    temel = PEER_BASIS[scope.level]

    if scope.level == UNIVERSITY:
        kurumlar = _external_institutions(db)
        return {
            "level": UNIVERSITY,
            "requested_period": academic_year,
            "basis": temel,
            "basis_label": PEER_BASIS_LABEL[temel],
            "parent": {"kind": None, "id": None, "name": None},
            "subject": {"kind": "university", "id": None,
                        "name": "Ankara Bilim Üniversitesi"},
            "peers": [],
            "external_institutions": kurumlar,
            "peer_count": len(kurumlar),
            "available": bool(kurumlar),
            "note": ("Üniversite seviyesinde karşılaştırma DIŞ kurumlarla "
                     "yapılır. İç birim kırılımı için fakülte dağılımına "
                     "bakınız."),
        }

    birimler = _sibling_units(db, scope)
    olculen = measure_units(db, birimler, academic_year)
    secili = _selected_id(scope)
    for r in olculen:
        r["is_selected"] = r["unit_id"] == secili

    # Seçili birimin kümedeki sırası — "kaçıncıyım?" sorusunun cevabı.
    def _sira(anahtar: str, buyuk_iyi: bool = True) -> Optional[int]:
        degerli = [r for r in olculen if r.get(anahtar) is not None]
        if not degerli or secili is None:
            return None
        sirali = sorted(degerli, key=lambda r: r[anahtar], reverse=buyuk_iyi)
        for i, r in enumerate(sirali, start=1):
            if r["unit_id"] == secili:
                return i
        return None

    kendi = next((r for r in olculen if r["is_selected"]), None)
    return {
        "level": scope.level,
        "requested_period": academic_year,
        "basis": temel,
        "basis_label": PEER_BASIS_LABEL[temel],
        "parent": _parent_info(db, scope),
        "subject": {"kind": scope.level, "id": secili,
                    "name": kendi["name"] if kendi else scope.label},
        "peers": olculen,
        # Dış kurumlar bu seviyelerde GÖSTERİLMEZ.
        "external_institutions": [],
        "peer_count": len(olculen),
        "sibling_count": max(0, len(olculen) - 1),
        "available": len(olculen) > 1,
        "ranks": {
            "student_count": _sira("student_count"),
            "occupancy_percent": _sira("occupancy_percent"),
            "academic_staff_count": _sira("academic_staff_count"),
            # Öğrenci/akademisyen oranında KÜÇÜK daha iyidir.
            "students_per_academic_staff": _sira(
                "students_per_academic_staff", buyuk_iyi=False),
        },
        "note": (
            "Karşılaştırma yalnızca "
            f"{PEER_BASIS_LABEL[temel].lower()} ile yapılır; "
            "üst kapsama taşmaz."
            if len(olculen) > 1
            else "Bu kapsamda karşılaştırılacak kardeş birim yok."
        ),
    }


# ==========================================================================
# 2) Alt birim kırılımı — "içeride kim nerede?"
# ==========================================================================


def child_breakdown(db: Session, scope: Optional[Scope] = None,
                    donem: Optional[str] = None) -> dict:
    """Seçili kapsamın BİR ALT seviyesindeki birimlerin karşılaştırması.

    Yönetim panosu bunu kullanır:
      üniversite → fakülteler
      fakülte    → bölümler
      bölüm      → programlar
      program    → alt kırılım yok (birimin kendi sağlığı gösterilir)
    """
    scope = scope or Scope()

    if scope.level == UNIVERSITY:
        ids = [
            f for (f,) in db.execute(
                select(Faculty.id).where(
                    Faculty.unit_type.in_(ACADEMIC_UNIT_TYPES))
            )
        ]
        birimler, alt = _faculty_units(db, ids), "faculty"
    elif scope.level == FACULTY_LEVEL:
        birimler = _department_units(db, sorted(scope.department_ids or ()))
        alt = "department"
    elif scope.level == DEPARTMENT_LEVEL:
        birimler = _program_units(db, sorted(scope.program_ids or ()))
        alt = "program"
    else:
        birimler, alt = [], None

    satirlar = measure_units(db, birimler, donem)

    # KAYNAK ETİKETİ SATIRLARI ANLATIR, KAPSAMI DEĞİL.
    # ------------------------------------------------------------------
    # Burada eskiden `total_for_scope_detailed(db, scope)` çağrılıyordu.
    # O fonksiyon KAPSAMIN yetkili sayısını üretir ve ÜNİVERSİTE kapsamında
    # "yok_kayitli" döner. Oysa bu panelin satırları ALT birimlerdir ve
    # YÖK kayıtlı öğrenci sayısının fakülte kırılımı YOKTUR.
    #
    # Canlıda sonuç şuydu: üniversite panosunda dağılım paneli "Kaynak:
    # YÖK kayıtlı" yazıyor, ama listelediği fakülte değerleri ÖSYM
    # türeviydi ve toplamları (3.348) üniversitenin YÖK sayısıyla (3.626)
    # tutmuyordu. Etiket, gösterdiği sayıları anlatmıyordu.
    #
    # Artık kaynak, SATIRLARIN kendi programlarından toplanır; üst
    # kapsamın yetkili ölçümü buraya SIZAMAZ.
    from app.services import student_count as _sc

    yontemler = set()
    for pid, kayit in _sc.program_counts(db, scope, donem).items():
        if kayit.student_count is not None:
            yontemler.add(kayit.source_method)
    if yontemler == {_sc.OFFICIAL_SOURCE_METHOD}:
        kaynak = "yks_turevi"
    elif yontemler == {_sc.STUDENT_RECORD_SOURCE_METHOD}:
        kaynak = "ogrenci_kaydi"
    elif yontemler:
        kaynak = "karisik"
    else:
        kaynak = None
    # Tek satırlık "karşılaştırma" bilgi vermez; yaprak sayılır.
    toplam = sum(r["student_count"] for r in satirlar
                 if r.get("student_count") is not None) or None
    return {
        "level": scope.level,
        "scope": {"level": scope.level, "label": scope.label},
        "requested_period": donem,
        "child_kind": alt,
        "student_count_source": kaynak,
        "student_count_total": toplam,
        # ÜST KAPSAMIN YETKİLİ SAYISIYLA KIYASLANAMAZ.
        # Üniversite düzeyinde yetkili sayı YÖK kayıtlı öğrencidir ve
        # lisansüstü, yatay geçiş, DGS ile geleni de kapsar; bu satırlar
        # ise ÖSYM yerleştirmelerinden türetilir. İki ölçüm farklı
        # tanımlara sahiptir; toplamlarının eşit ÇIKMAMASI beklenir.
        "comparable_to_scope_total": False,
        "rows": satirlar,
        "row_count": len(satirlar),
        "available": len(satirlar) > 1,
        "is_leaf": len(satirlar) <= 1,
    }


def unit_self(db: Session, scope: Optional[Scope] = None,
              donem: Optional[str] = None) -> Optional[dict]:
    """Seçili birimin KENDİ ölçüm satırı (yaprakta operasyonel sağlık)."""
    scope = scope or Scope()
    if scope.level == PROGRAM_LEVEL and scope.academic_program_id:
        birim = _program_units(db, [scope.academic_program_id])
    elif scope.level == DEPARTMENT_LEVEL and scope.department_id:
        birim = _department_units(db, [scope.department_id])
    elif scope.level == FACULTY_LEVEL and scope.faculty_id:
        birim = _faculty_units(db, [scope.faculty_id])
    else:
        return None
    olculen = measure_units(db, birim, donem)
    return olculen[0] if olculen else None
