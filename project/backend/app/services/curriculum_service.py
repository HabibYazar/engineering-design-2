"""Müfredat kataloğu ve akademisyen ders kayıtları için sorgu katmanı.

İKİ AYRI GERÇEK KAYNAK, İKİ AYRI SORU
------------------------------------
`curriculum_courses`      → "bu programın müfredatında hangi dersler var?"
                            (üniversitenin yayımladığı ders kataloğu)
`academic_staff_courses`  → "bu akademisyen hangi dersleri veriyor?"
                            (YÖK Akademik'in kişi bazlı ders geçmişi)

İkisi ad üzerinden EŞLEŞTİRİLMEZ. Aynı adın iki farklı ders olması
mümkündür; yanlış eşleştirme bir akademisyene vermediği dersi atfetmek
olurdu. İki kaynak yan yana sunulur, birleştirilmez.

VERİ POLİTİKASI
---------------
Aktarılan müfredat satırları KURUMUN OPERASYONEL VERİSİDİR. "Doğrulanmış /
doğrulanmamış" ayrımı API yüzeyinden kaldırılmıştır: bu ayrım kullanıcıya
kendi verisini şüpheli göstermekten başka bir işe yaramıyordu.

`curriculum_courses.name_is_reliable` sütunu, aktarımın hangi satırları
PDF'ten sorunlu çıkardığını izleyebilmek için VERİTABANINDA durur; hiçbir
uç noktada döndürülmez ve hiçbir arayüz etiketine dönüşmez.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.services import staff_scope
from app.models import (
    AcademicProgram,
    CurriculumCanonicalCourse,
    AcademicStaff,
    AcademicStaffCourse,
    CurriculumCourse,
    Department,
    Faculty,
)

if TYPE_CHECKING:
    from app.services.scope import Scope


# ---------------------------------------------------------------------------
# Müfredat kataloğu
# ---------------------------------------------------------------------------


def _canonical_query(scope: Optional["Scope"]):
    """KANONİK ders sorgusu — arayüzün gördüğü temiz katman.

    Ham `curriculum_courses` tablosu PDF çıkarımının kopyalarını ve
    dönem başlığı gibi artıklarını taşır; uygulama onu değil, ondan
    türetilen `curriculum_canonical_courses` tablosunu okur.
    """
    sorgu = select(CurriculumCanonicalCourse).options(
        selectinload(CurriculumCanonicalCourse.department).selectinload(
            Department.faculty),
        selectinload(CurriculumCanonicalCourse.academic_program),
    )
    if scope is None:
        return sorgu
    if scope.is_program:
        return sorgu.where(
            CurriculumCanonicalCourse.academic_program_id
            == scope.academic_program_id)
    if scope.department_ids is not None:
        return sorgu.where(
            CurriculumCanonicalCourse.department_id.in_(scope.department_ids))
    return sorgu


def _scoped_query(scope: Optional["Scope"]):
    """Müfredat sorgusuna kapsam süzgecini uygular.

    Süzme ID ile yapılır. Program kapsamında yalnızca doğrudan programa
    bağlı satırlar görünür. Bölüme bağlı ama programı belirsiz satırları
    programa devretmek sessiz ebeveyn geri dönüşü olurdu; bu durumda
    arayüz açıkça "bu kapsamda veri yok" gösterir.
    """
    sorgu = select(CurriculumCourse).options(
        selectinload(CurriculumCourse.department).selectinload(Department.faculty),
        selectinload(CurriculumCourse.academic_program),
    )
    if scope is None:
        return sorgu
    if scope.is_program:
        return sorgu.where(
            CurriculumCourse.academic_program_id == scope.academic_program_id
        )
    if scope.department_ids is not None:
        return sorgu.where(
            CurriculumCourse.department_id.in_(scope.department_ids)
        )
    return sorgu


def _course_row(course) -> dict:
    bolum = course.department
    return {
        "id": course.id,
        "course_code": course.course_code,
        # Adı okunamayan derste kod gösterilir; uydurma ad üretilmez.
        "course_name": getattr(course, "display_name", None) or course.course_name,
        "class_year": getattr(course, "class_year", None),
        "department_id": course.department_id,
        "department_name": bolum.name if bolum else None,
        "faculty_name": bolum.faculty.name if bolum and bolum.faculty else None,
        "academic_program_id": course.academic_program_id,
        "academic_program_name": (
            course.academic_program.name if course.academic_program else None
        ),
        # Kanonik satırda kaynak türleri birleştirilmiş tek metindir;
        # ham satırda tek tür + belge adı vardır. İkisi de desteklenir.
        "source_type": getattr(course, "source_types", None)
        or getattr(course, "source_type", None),
        "source_reference": getattr(course, "source_reference", None),
        # Kaç ham satırdan birleştiği — izlenebilirlik.
        "source_row_count": getattr(course, "source_row_count", 1),
    }


def list_courses(
    db: Session,
    scope: Optional["Scope"] = None,
    search: Optional[str] = None,
    source_type: Optional[str] = None,
    skip: int = 0,
    limit: int = 200,
) -> List[dict]:
    """Müfredat derslerini süzer ve sayfalar.

    `search` ders kodu VE ders adı içinde arar; kullanıcı hangisini
    yazdığını bilmek zorunda kalmasın diye.
    """
    sorgu = _canonical_query(scope)
    if source_type:
        sorgu = sorgu.where(
            CurriculumCanonicalCourse.source_types.like(f"%{source_type}%"))
    if search:
        kalip = f"%{search.strip()}%"
        sorgu = sorgu.where(
            func.lower(CurriculumCanonicalCourse.display_name).like(func.lower(kalip))
            | func.lower(
                func.coalesce(CurriculumCanonicalCourse.course_code, "")
            ).like(func.lower(kalip))
        )
    sorgu = sorgu.order_by(
        CurriculumCanonicalCourse.class_year.is_(None),
        CurriculumCanonicalCourse.class_year,
        CurriculumCanonicalCourse.course_code,
    ).offset(skip).limit(limit)
    return [_course_row(c) for c in db.execute(sorgu).scalars().unique()]


def courses_by_class_year(
    db: Session, scope: Optional["Scope"] = None,
    search: Optional[str] = None,
) -> List[dict]:
    """Dersleri SINIFA göre gruplar — açılır bölümler için.

    Sınıf, ders kodundaki üç haneli sayının ilk basamağından gelir
    (1xx→1. sınıf). Kod bu kalıba uymuyorsa ders "Diğer / Seçmeli"
    grubuna düşer; zorlama yapılmaz.

    Gruplar HER PROGRAM için aynı biçimde üretilir; hiçbir bölüme özel
    kural yoktur.
    """
    from app.services.curriculum_canonical import CLASS_LABELS

    sorgu = _canonical_query(scope)
    if search:
        kalip = f"%{search.strip()}%"
        sorgu = sorgu.where(
            func.lower(CurriculumCanonicalCourse.display_name).like(func.lower(kalip))
            | func.lower(
                func.coalesce(CurriculumCanonicalCourse.course_code, "")
            ).like(func.lower(kalip))
        )
    dersler = list(db.execute(
        sorgu.order_by(CurriculumCanonicalCourse.course_code)
    ).scalars().unique())

    kovalar: Dict[Optional[int], List[dict]] = {}
    for c in dersler:
        kovalar.setdefault(c.class_year, []).append(_course_row(c))

    # Sınıflar sırayla; "Diğer" daima sonda.
    sirali = sorted(kovalar, key=lambda y: (y is None, y or 0))
    return [
        {
            "class_year": y,
            "label": CLASS_LABELS.get(y, "Diğer / Seçmeli"),
            "course_count": len(kovalar[y]),
            "courses": kovalar[y],
        }
        for y in sirali
    ]


def course_overview(db: Session, scope: Optional["Scope"] = None) -> dict:
    """Kapsamdaki müfredatın özeti.

    Aktarılan satırlar kurumun operasyonel verisidir; kalite ayrımı
    yapılmaz.
    """
    temel = _canonical_query(scope).subquery()
    toplam = db.execute(select(func.count()).select_from(temel)).scalar_one()
    kodsuz = db.execute(
        select(func.count()).select_from(temel).where(temel.c.course_code.is_(None))
    ).scalar_one()
    bolum_sayisi = db.execute(
        select(func.count(func.distinct(temel.c.department_id)))
    ).scalar_one()
    siniflanan = db.execute(
        select(func.count()).select_from(temel).where(temel.c.class_year.isnot(None))
    ).scalar_one()
    # Ham satır sayısı da döner: "1205 satırdan 1003 gerçek ders" bilgisi
    # veri sahibinin görmek isteyeceği bir özettir.
    ham = _scoped_query(scope).subquery()
    ham_sayi = db.execute(select(func.count()).select_from(ham)).scalar_one()

    return {
        "total_course_count": toplam,
        "raw_row_count": ham_sayi,
        "classified_course_count": siniflanan,
        "missing_code_count": kodsuz,
        "department_count": bolum_sayisi,
        "source_types": source_type_breakdown(db, scope),
    }


def source_type_breakdown(db: Session, scope: Optional["Scope"] = None) -> List[dict]:
    """Derslerin hangi kaynak belgesinden geldiği — köken şeffaflığı."""
    temel = _scoped_query(scope).subquery()
    satirlar = db.execute(
        select(temel.c.source_type, func.count())
        .group_by(temel.c.source_type)
        .order_by(func.count().desc())
    ).all()
    return [{"source_type": t, "course_count": n} for t, n in satirlar]


def courses_by_department(
    db: Session, scope: Optional["Scope"] = None
) -> List[dict]:
    """Bölüm bazında ders sayısı ve o bölümün akademik kadro yükü.

    Ders sayısını TEK BAŞINA göstermek yanıltıcıdır: 120 dersli bir bölüm
    30 akademisyenle rahat, 3 akademisyenle sıkışıktır. Bu yüzden aynı
    satırda kadro sayısı ve ders/akademisyen oranı da döner.
    """
    temel = _canonical_query(scope).subquery()
    ders = db.execute(
        select(temel.c.department_id, func.count())
        .group_by(temel.c.department_id)
    ).all()

    kadro_sorgu = (
        select(AcademicStaff.department_id, func.count())
        .where(AcademicStaff.is_active.is_(True),
               AcademicStaff.academic_year == staff_scope.latest_staff_period(db))
        .group_by(AcademicStaff.department_id)
    )
    if scope is not None and scope.department_ids is not None:
        kadro_sorgu = kadro_sorgu.where(
            AcademicStaff.department_id.in_(scope.department_ids)
        )
    kadro = dict(db.execute(kadro_sorgu).all())

    bolumler = {
        d.id: d for d in db.execute(
            select(Department).options(selectinload(Department.faculty))
        ).scalars()
    }

    satirlar = []
    for bolum_id, ders_sayisi in ders:
        bolum = bolumler.get(bolum_id)
        personel = kadro.get(bolum_id, 0)
        satirlar.append({
            "department_id": bolum_id,
            "department_name": bolum.name if bolum else "Bilinmiyor",
            "faculty_name": bolum.faculty.name if bolum and bolum.faculty else None,
            "course_count": ders_sayisi,
            "academic_staff_count": personel,
            # Personel yoksa oran hesaplanmaz; 0'a bölmek yerine None.
            "courses_per_staff": (
                round(ders_sayisi / personel, 2) if personel else None
            ),
        })
    satirlar.sort(key=lambda r: r["course_count"], reverse=True)
    return satirlar


# ---------------------------------------------------------------------------
# Akademisyenin verdiği dersler
# ---------------------------------------------------------------------------


def latest_course_year(db: Session) -> Optional[str]:
    """Ders veri kümesindeki EN GÜNCEL akademik yıl.

    Sabit bir yıl yazmak yerine veriden okunur: kaynak güncellendiğinde
    "cari dönem" kendiliğinden ilerler.
    """
    return db.execute(
        select(func.max(AcademicStaffCourse.academic_year))
    ).scalar_one_or_none()


def staff_courses(db: Session, academic_staff_id: int) -> dict:
    """Bir akademisyenin ders geçmişi + müfredat eşleşmesi + türetilen sayılar.

    Yıllar YENİDEN ESKİYE sıralanır: kullanıcı önce güncel yükü görmek
    ister. Saat bilgisi olmayan ders 0 saat sayılmaz; yıl toplamında
    dışarıda kalır ve satırda "—" görünür.

    Her ders satırı, mümkünse müfredattaki karşılığını taşır
    (bkz. `course_matching`). Eşleşme bulunamazsa alanlar NULL kalır —
    uydurma eşleşme üretilmez ve arayüzde teknik bir "güven" etiketi
    gösterilmez.
    """
    from app.services.course_matching import match_staff_courses

    personel = db.get(AcademicStaff, academic_staff_id)
    if personel is None:
        return {}

    satirlar, eslesmeler = match_staff_courses(db, academic_staff_id)
    # CARİ DÖNEM: yönetim ekranı 30 yıllık geçmişi değil, güncel yükü
    # gösterir. Geçmiş yıllar ikincil bir bölümde kalır.
    cari_yil = latest_course_year(db)

    yillar: Dict[str, dict] = {}
    ders_adi_yillari: Dict[str, set] = {}
    eslesen_mufredat: set = set()
    toplam_saat = 0
    saat_bilinen = False

    for c in satirlar:
        m = eslesmeler.get(c.id)
        kova = yillar.setdefault(
            c.academic_year,
            {"academic_year": c.academic_year, "course_count": 0,
             "total_weekly_hours": 0, "hours_known": False, "courses": []},
        )
        kova["course_count"] += 1
        if c.weekly_hours is not None:
            kova["total_weekly_hours"] += c.weekly_hours
            kova["hours_known"] = True
            toplam_saat += c.weekly_hours
            saat_bilinen = True

        ders_adi_yillari.setdefault(c.course_name, set()).add(c.academic_year)
        if m and m.curriculum_course_id is not None:
            eslesen_mufredat.add(m.curriculum_course_id)

        kova["courses"].append({
            "id": c.id,
            "course_name": c.course_name,
            "language": c.language,
            "weekly_hours": c.weekly_hours,
            # --- müfredat eşleşmesi (varsa) ---
            "curriculum_course_id": m.curriculum_course_id if m else None,
            "course_code": m.curriculum_course_code if m else None,
            "matched_course_name": m.curriculum_course_name if m else None,
            "academic_program_name": m.academic_program_name if m else None,
            "department_name": m.department_name if m else None,
        })

    yil_listesi = sorted(yillar.values(), key=lambda y: y["academic_year"],
                         reverse=True)
    for y in yil_listesi:
        if not y.pop("hours_known"):
            # Hiçbir dersin saati bilinmiyorsa toplam 0 değil, YOK.
            y["total_weekly_hours"] = None

    # Birden çok yıl tekrarlanan dersler — süreklilik göstergesi.
    tekrarlayan = sorted(
        ({"course_name": ad, "year_count": len(yl),
          "years": sorted(yl, reverse=True)}
         for ad, yl in ders_adi_yillari.items() if len(yl) > 1),
        key=lambda r: r["year_count"], reverse=True,
    )

    # Cari dönem ile geçmiş AYRILIR: arayüz önce cari dönemi gösterir.
    cari = next((y for y in yil_listesi if y["academic_year"] == cari_yil), None)
    gecmis = [y for y in yil_listesi if y["academic_year"] != cari_yil]

    return {
        "academic_staff_id": personel.id,
        "staff_number": personel.staff_number,
        "full_name": f"{personel.first_name} {personel.last_name}".strip(),
        "title": personel.title,
        "department_id": personel.department_id,
        # --- CARİ DÖNEM (yönetim ekranının ana görünümü) ---
        "current_academic_year": cari_yil,
        "current": cari,
        "teaches_in_current_year": cari is not None,
        "current_course_count": cari["course_count"] if cari else 0,
        "current_distinct_course_count": (
            len({c["course_name"] for c in cari["courses"]}) if cari else 0),
        "current_weekly_hours": cari["total_weekly_hours"] if cari else None,
        # --- geçmiş (ikincil) ---
        "history_years": gecmis,
        "history_year_count": len(gecmis),
        # --- bütün geçmiş üzerinden türetilen sayılar ---
        "total_course_count": len(satirlar),
        "distinct_course_count": len(ders_adi_yillari),
        "academic_year_count": len(yil_listesi),
        "total_weekly_hours": toplam_saat if saat_bilinen else None,
        "matched_curriculum_course_count": len(eslesen_mufredat),
        "repeated_courses": tekrarlayan,
        "years": yil_listesi,
    }


#: `academic_year` verilmediğinde CARİ DÖNEM sayılır. Bu varsayılan
#: SERVİSTE durur, çağıranda değil: yönetim listesinin "bu kişi bu yıl
#: ders veriyor mu?" sorusunu sorması, çağıranın hatırlamasına
#: bırakılamayacak kadar önemlidir. Tüm geçmiş için `"all"` geçilir.
ALL_YEARS = "all"


def staff_course_counts(
    db: Session, scope: Optional["Scope"] = None,
    academic_year: Optional[str] = None,
) -> Dict[int, int]:
    """Kapsamdaki her akademisyenin ders kaydı sayısı.

    Varsayılan CARİ DÖNEMDİR (`latest_course_year`). Belirli bir dönem
    için yıl etiketi, tüm geçmiş için `ALL_YEARS` geçilir.
    """
    yil = (None if academic_year == ALL_YEARS
           else academic_year or latest_course_year(db))
    sorgu = (
        select(AcademicStaffCourse.academic_staff_id, func.count())
        .group_by(AcademicStaffCourse.academic_staff_id)
    )
    if yil:
        sorgu = sorgu.where(AcademicStaffCourse.academic_year == yil)
    if scope is not None and scope.department_ids is not None:
        sorgu = sorgu.join(
            AcademicStaff, AcademicStaff.id == AcademicStaffCourse.academic_staff_id
        ).where(AcademicStaff.department_id.in_(scope.department_ids))
    return {sid: n for sid, n in db.execute(sorgu).all()}


def current_teaching_summary(
    db: Session, scope: Optional["Scope"] = None
) -> dict:
    """Kapsamın CARİ DÖNEM öğretim tablosu — yönetim özeti.

    "Kaç akademisyen bu yıl fiilen ders veriyor, kaç ders, kaç saat?"
    Geçmiş yıllar bu özete girmez.
    """
    cari = latest_course_year(db)
    if not cari:
        return {"available": False, "current_academic_year": None}

    sorgu = select(AcademicStaffCourse).where(
        AcademicStaffCourse.academic_year == cari)
    if scope is not None and scope.department_ids is not None:
        sorgu = sorgu.join(
            AcademicStaff, AcademicStaff.id == AcademicStaffCourse.academic_staff_id
        ).where(AcademicStaff.department_id.in_(scope.department_ids))
    dersler = list(db.execute(sorgu).scalars())

    kisiler = {d.academic_staff_id for d in dersler}
    saatler = [d.weekly_hours for d in dersler if d.weekly_hours is not None]
    # Kadro sayımı TEK kuraldan geçer (bkz. staff_scope.py); yıl süzgeci
    # olmadan çok yıllı anlık görüntüler aynı kişiyi tekrar sayardı.
    kadro = staff_scope.active_staff_count(db, scope)

    return {
        "available": bool(dersler),
        "current_academic_year": cari,
        "teaching_staff_count": len(kisiler),
        "academic_staff_count": kadro,
        "not_teaching_count": max(0, kadro - len(kisiler)),
        "course_record_count": len(dersler),
        "distinct_course_count": len({d.course_name for d in dersler}),
        # Saati bilinmeyen ders toplamdan düşer, 0 sayılmaz.
        "total_weekly_hours": sum(saatler) if saatler else None,
        "average_hours_per_teaching_staff": (
            round(sum(saatler) / len(kisiler), 2)
            if saatler and kisiler else None),
    }
