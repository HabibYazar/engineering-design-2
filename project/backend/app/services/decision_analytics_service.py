"""KARAR DESTEK GÖSTERGELERİ — yalnızca elimizdeki gerçek veriden.

TASARIM İLKESİ
--------------
Her gösterge, veritabanında GERÇEKTEN dolu olan bir alandan türetilir:

    academic_staff            unvan, yayın, danışmanlık, ders yükü
    academic_staff_courses    yıl bazında verilen dersler ve saatleri
    academic_programs         resmî öğrenci sayısı (ÖSYM'den türetilmiş)
    yks_placement_records     4 yıllık kontenjan / yerleşen / taban puan / sıra
    curriculum_courses        müfredat ders sayısı

Elimizde OLMAYAN veriden gösterge ÜRETİLMEZ: atıf, patent, proje, maaş,
mezun istihdamı, ders geçme oranı. Bunlar için sıfır dolu kart basmak,
kullanıcıya "ölçtük ve sıfır çıktı" demek olurdu.

SIFIR KARTLARI
--------------
Bir gösterge hesaplanamıyorsa `None` döner ve `available: false` ile
işaretlenir. Arayüz bu kartları ya gizler ya da sona alır; boş bir "0"
ile dolu bir "0"ı aynı görünürlükte göstermek yanlış karar aldırır.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    AcademicProgram,
    AcademicStaff,
    AcademicStaffCourse,
    CurriculumCanonicalCourse,
    Department,
    YksPlacementRecord,
)
from app.services import staff_scope, student_count

if TYPE_CHECKING:
    from app.services.scope import Scope


def _oran(pay, payda, basamak: int = 2) -> Optional[float]:
    """Payda yoksa/sıfırsa None — 0 döndürmek "oran sıfır" demek olurdu."""
    if not payda:
        return None
    return round(float(pay) / float(payda), basamak)


def son_kadro_donemi(db: Session) -> Optional[str]:
    """`academic_staff` içindeki en güncel akademik yıl.

    Kural `app.services.staff_scope` içinde TEK yerde durur; burada
    yalnızca geriye dönük uyumluluk için yeniden dışa verilir.
    """
    return staff_scope.latest_staff_period(db)


def _staff_query(scope: Optional["Scope"], db: Session,
                 donem: Optional[str] = None):
    """Kapsamdaki AKTİF akademik kadro — kişi başına TEK satır.

    Yıl süzgeci ŞARTTIR: `academic_staff` kişi başına yıla göre satır
    tutar ve süzgeçsiz sayım aynı kişiyi her yıl için tekrar sayar
    (canlıda 180 kişilik kadro 360, fakülte kadrosu 108 yerine 216
    görünüyordu). Ayrıntılı gerekçe: `app/services/staff_scope.py`.
    """
    return staff_scope.active_staff_query(db, scope, donem)


# ---------------------------------------------------------------------------
# 1) Kadro yeterliliği ve öğrenci/personel oranları
# ---------------------------------------------------------------------------


def staffing_overview(db: Session, scope: Optional["Scope"] = None,
                      donem: Optional[str] = None) -> dict:
    """Öğrenci/akademisyen ve akademisyen/öğrenci göstergeleri.

    İkisi de döner çünkü aynı bilgi iki farklı karar sorusunu cevaplar:
      · öğrenci/akademisyen → "sınıflar ne kadar kalabalık?"
      · akademisyen/öğrenci → "öğrenci başına ne kadar akademik kaynak?"
    """
    # Personel kaynağında program FK'sı yoktur. Bölüm kadrosunu seçili
    # programa devretmek sessiz ebeveyn geri dönüşü olacağından kadro
    # metrikleri program düzeyinde ölçülemez kalır.
    if scope is not None and scope.is_program:
        ogrenci, ogrenci_kaynak = student_count.total_for_scope_detailed(
            db, scope, donem)
        return {
            "available": False,
            "requested_period": donem,
            "staff_period": None,
            "academic_staff_count": None,
            "active_teaching_staff_count": None,
            "student_count": ogrenci,
            "student_count_source": ogrenci_kaynak,
            "students_per_academic_staff": None,
            "students_per_active_teaching_staff": None,
            "academic_staff_per_student": None,
            "academics_per_100_students": None,
            "average_teaching_load_hours": None,
            "staff_with_teaching_load": None,
            "staff_without_teaching_load": None,
            "average_publications_per_academic": None,
            "total_publications": None,
            "note": (
                "Akademik kadro kaynakta bölüm düzeyine bağlıdır; bölüm "
                "toplamı seçili programa devredilmez."
            ),
        }
    # DÖNEM: kadro anlık görüntüsü seçilen yıldan okunur. O yılın kaydı
    # yoksa 0 DÖNMEZ — "bu dönemde ölçülmedi" durumu döner; sıfır, "hiç
    # akademisyen yok" demek olurdu.
    if donem and not staff_scope.staff_period_available(db, donem):
        return {
            "available": False,
            "requested_period": donem,
            "available_periods": staff_scope.staff_periods(db),
            "academic_staff_count": None,
            "active_teaching_staff_count": None,
            "student_count": student_count.total_for_scope(db, scope, donem),
            "student_count_source": student_count.total_for_scope_detailed(
                db, scope, donem)[1],
            "students_per_academic_staff": None,
            "students_per_active_teaching_staff": None,
            "academic_staff_per_student": None,
            "academics_per_100_students": None,
            "average_teaching_load_hours": None,
            "staff_with_teaching_load": None,
            "staff_without_teaching_load": None,
            "average_publications_per_academic": None,
            "total_publications": None,
            "note": (f"{donem} döneminde akademik kadro anlık görüntüsü yok. "
                     "Başka bir yılın kadrosu bu dönemin etiketiyle "
                     "gösterilmez."),
        }
    personel = db.execute(_staff_query(scope, db, donem)).scalars().all()
    # Öğrenci sayısı ve KAYNAĞI birlikte alınır: üniversite kapsamında
    # YÖK kayıtlı sayısı yetkilidir, alt kapsamlarda ÖSYM türevi geçerlidir.
    # Kaynağı da döndürmek, ekranın hangi ölçümü gösterdiğini yazabilmesi
    # ve iki farklı sayının sessizce yan yana durmaması içindir.
    ogrenci, ogrenci_kaynak = student_count.total_for_scope_detailed(
        db, scope, donem)

    ders_saatleri = [
        p.teaching_load_hours for p in personel
        if p.teaching_load_hours is not None and p.teaching_load_hours > 0
    ]
    yayinlar = [p.publication_count for p in personel
                if p.publication_count is not None]

    # FİİLEN DERS VEREN akademisyen sayısı ayrı tutulur: kadronun tamamı
    # üzerinden hesaplanan oran, ders vermeyenleri de payda saydığı için
    # yükü olduğundan hafif gösterir. Yönetim iki sayıyı da ister.
    aktif_ogretim = len(ders_saatleri)

    return {
        "available": True,
        "requested_period": donem,
        "staff_period": staff_scope.resolve_staff_period(db, donem),
        "academic_staff_count": len(personel),
        "active_teaching_staff_count": aktif_ogretim,
        "student_count": ogrenci,
        "student_count_source": ogrenci_kaynak,
        "students_per_academic_staff": _oran(ogrenci, len(personel))
        if ogrenci is not None else None,
        "students_per_active_teaching_staff": _oran(ogrenci, aktif_ogretim)
        if ogrenci is not None else None,
        # Küçük bir sayı olduğu için 3 basamak: 0,05 ile 0,047 farklıdır.
        "academic_staff_per_student": _oran(len(personel), ogrenci, 3)
        if ogrenci else None,
        # "100 öğrenciye kaç akademisyen" yönetimin okuduğu ölçektir.
        "academics_per_100_students": _oran(len(personel) * 100, ogrenci)
        if ogrenci else None,
        "average_teaching_load_hours": _oran(sum(ders_saatleri), len(ders_saatleri))
        if ders_saatleri else None,
        "staff_with_teaching_load": aktif_ogretim,
        "staff_without_teaching_load": len(personel) - aktif_ogretim,
        "average_publications_per_academic": _oran(sum(yayinlar), len(yayinlar))
        if yayinlar else None,
        "total_publications": sum(yayinlar) if yayinlar else None,
    }


def staffing_by_program(db: Session, scope: Optional["Scope"] = None,
                        donem: Optional[str] = None) -> List[dict]:
    """Program bazında kadro yeterliliği.

    Kadro BÖLÜME bağlıdır, programa değil. Bu yüzden satır, programın
    bağlı olduğu bölümün kadrosunu gösterir ve `staff_scope` alanıyla
    bunu açıkça söyler — programın kendi kadrosu sanılmasın.
    """
    prog_sorgu = (
        select(AcademicProgram)
        .options(selectinload(AcademicProgram.department).selectinload(
            Department.faculty))
    )
    if scope is not None and scope.program_ids is not None:
        prog_sorgu = prog_sorgu.where(AcademicProgram.id.in_(scope.program_ids))
    programlar = db.execute(prog_sorgu).scalars().unique().all()

    # Yıl süzgeci `staff_scope` üzerinden (çok yıllı anlık görüntü aynı
    # kişiyi tekrar sayardı).
    kadro = dict(db.execute(
        staff_scope.apply_staff_filters(
            select(AcademicStaff.department_id,
                   func.count(func.distinct(AcademicStaff.id)))
            .select_from(AcademicStaff), db, scope, donem)
        .group_by(AcademicStaff.department_id)
    ).all())
    sayilar = student_count.program_counts(db, scope, donem)

    satirlar = []
    for p in programlar:
        program_kadrosu_olculemez = scope is not None and scope.is_program
        personel = (None if program_kadrosu_olculemez
                    else kadro.get(p.department_id, 0))
        kayit = sayilar.get(p.id)
        ogrenci = kayit.student_count if kayit else None
        satirlar.append({
            "academic_program_id": p.id,
            "program_code": p.code,
            "program_name": p.name,
            "department_id": p.department_id,
            "department_name": p.department.name if p.department else None,
            "faculty_name": (
                p.department.faculty.name
                if p.department and p.department.faculty else None
            ),
            "student_count": ogrenci,
            "academic_staff_count": personel,
            "staff_scope": (
                "unavailable" if program_kadrosu_olculemez else "department"),
            "students_per_academic_staff": _oran(ogrenci, personel)
            if ogrenci is not None else None,
            "note": (
                "Personel kaynağı program kimliği taşımıyor; bölüm kadrosu "
                "seçili programa devredilmez."
                if program_kadrosu_olculemez else
                "Akademik kadro programın bağlı olduğu bölüm düzeyindedir."
            ),
        })
    # Yükü en ağır programlar üstte; None'lar sona.
    satirlar.sort(
        key=lambda r: (r["students_per_academic_staff"] is None,
                       -(r["students_per_academic_staff"] or 0))
    )
    return satirlar


def title_distribution(db: Session, scope: Optional["Scope"] = None,
                       donem: Optional[str] = None) -> List[dict]:
    """Akademik unvan dağılımı — kadro yapısının kalite göstergesi."""
    # Unvan dağılımı da TEK kadro kuralından geçer; aksi hâlde her yılın
    # anlık görüntüsü unvan sayılarını katlardı.
    sorgu = staff_scope.apply_staff_filters(
        select(AcademicStaff.title, func.count(func.distinct(AcademicStaff.id)))
        .select_from(AcademicStaff), db, scope, donem
    ).group_by(AcademicStaff.title).order_by(
        func.count(func.distinct(AcademicStaff.id)).desc())
    satirlar = db.execute(sorgu).all()
    toplam = sum(n for _, n in satirlar)
    return [
        {"title": t or "Bilinmiyor", "staff_count": n,
         "share_percent": round(n / toplam * 100, 2) if toplam else None}
        for t, n in satirlar
    ]


# ---------------------------------------------------------------------------
# 2) Ders yükü
# ---------------------------------------------------------------------------

#: Haftalık ders saati bantları. Sınırlar kurumun norm kadro
#: düzenlemesinden değil, dağılımı okunabilir kılmaktan gelir; bu yüzden
#: "norm" değil "bant" denir ve arayüzde eşik iddiası yapılmaz.
_YUK_BANTLARI = ((1, 5), (6, 10), (11, 15), (16, 20), (21, None))


def teaching_load_distribution(
    db: Session, scope: Optional["Scope"] = None,
    donem: Optional[str] = None
) -> dict:
    """Ders yükünün akademisyenler arasındaki dağılımı.

    Ortalama tek başına yanıltıcıdır: 10 saat ortalama, herkesin 10 saat
    verdiği bir bölümü de birkaç kişinin 25 saat verdiği bir bölümü de
    tarif edebilir. Dağılım bu ikisini ayırır.
    """
    personel = db.execute(_staff_query(scope, db, donem)).scalars().all()
    saatler = sorted(
        p.teaching_load_hours for p in personel
        if p.teaching_load_hours is not None and p.teaching_load_hours > 0
    )
    if not saatler:
        return {
            "available": False,
            "measured_staff_count": 0,
            "staff_without_load": len(personel),
            "bands": [],
            "note": "Ders yükü verisi bulunan akademisyen yok.",
        }

    bantlar = []
    for alt, ust in _YUK_BANTLARI:
        adet = sum(1 for s in saatler if s >= alt and (ust is None or s <= ust))
        bantlar.append({
            "label": f"{alt}-{ust} saat" if ust else f"{alt}+ saat",
            "min_hours": alt, "max_hours": ust, "staff_count": adet,
        })

    orta = saatler[len(saatler) // 2]

    # YOĞUNLAŞMA: toplam ders yükünün ne kadarını en yüklü %20 taşıyor?
    # %20'lik dilim toplamın yarısından fazlasını taşıyorsa öğretim
    # birkaç kişiye bağımlı demektir — bu bir kırılganlık göstergesidir.
    azalan = sorted(saatler, reverse=True)
    ust_dilim = max(1, round(len(azalan) * 0.2))
    toplam = sum(azalan)
    ust_pay = (round(sum(azalan[:ust_dilim]) / toplam * 100, 2)
               if toplam else None)

    # En yüklü / en az yüklü (ders veren) akademisyenler.
    yuklu = sorted(
        (p for p in personel
         if p.teaching_load_hours is not None and p.teaching_load_hours > 0),
        key=lambda p: p.teaching_load_hours, reverse=True,
    )
    kisi = lambda p: {
        "academic_staff_id": p.id,
        "full_name": f"{p.first_name} {p.last_name}".strip(),
        "title": p.title,
        "teaching_load_hours": p.teaching_load_hours,
    }

    return {
        "available": True,
        "measured_staff_count": len(saatler),
        "staff_without_load": len(personel) - len(saatler),
        "min_hours": saatler[0],
        "max_hours": saatler[-1],
        "median_hours": orta,
        "average_hours": round(sum(saatler) / len(saatler), 2),
        "total_hours": toplam,
        "top20_percent_share": ust_pay,
        "top20_percent_staff_count": ust_dilim,
        "highest_load_staff": [kisi(p) for p in yuklu[:5]],
        "lowest_load_active_staff": [kisi(p) for p in yuklu[-5:][::-1]],
        "bands": bantlar,
    }


def teaching_load_trend(
    db: Session, scope: Optional["Scope"] = None,
    donem: Optional[str] = None,
) -> List[dict]:
    """Yıllara göre toplam ders saati ve ders veren akademisyen sayısı.

    `academic_staff_courses` 1992'ye kadar uzanıyor; anlamlı karar için
    son 10 yıl yeterli ve grafiği okunabilir tutuyor.
    """
    if scope is not None and scope.is_program:
        # Ders verme kayıtları program FK'sı taşımıyor. Bölüm trendini
        # seçili programın trendi diye sunmak ebeveyn geri dönüşüdür.
        return []
    sorgu = (
        select(
            AcademicStaffCourse.academic_year,
            func.count(),
            func.count(func.distinct(AcademicStaffCourse.academic_staff_id)),
            func.sum(AcademicStaffCourse.weekly_hours),
        )
        .group_by(AcademicStaffCourse.academic_year)
        .order_by(AcademicStaffCourse.academic_year)
    )
    if scope is not None and scope.department_ids is not None:
        sorgu = sorgu.join(
            AcademicStaff, AcademicStaff.id == AcademicStaffCourse.academic_staff_id
        ).where(AcademicStaff.department_id.in_(scope.department_ids))
    if donem:
        # Trendler seçili dönemde biter. Geçmiş bir dönem seçiliyken
        # gelecekteki ders yükünü grafiğe taşımak dönem sızıntısıdır.
        sorgu = sorgu.where(AcademicStaffCourse.academic_year <= donem)

    satirlar = db.execute(sorgu).all()[-10:]
    return [
        {
            "academic_year": yil,
            "course_count": ders,
            "teaching_staff_count": kisi,
            "total_weekly_hours": int(saat) if saat is not None else None,
            "average_hours_per_staff": _oran(saat, kisi) if saat else None,
        }
        for yil, ders, kisi, saat in satirlar
    ]


# ---------------------------------------------------------------------------
# 3) Akademik üretkenlik
# ---------------------------------------------------------------------------


def publication_productivity(
    db: Session, scope: Optional["Scope"] = None,
    donem: Optional[str] = None
) -> List[dict]:
    """Bölüm bazında akademisyen başına yayın.

    Toplam yayın büyük bölümü otomatik üste taşır; asıl karar sorusu
    "kişi başına ne üretiliyor?" olduğu için sıralama orandan yapılır.
    """
    # YIL SÜZGECİ ŞART: `academic_staff` kişi başına yıla göre satır
    # tutar. Süzgeçsiz `SUM(publication_count)` aynı kişinin yayınını her
    # yıl için tekrar toplar — canlıda fakülte yayını 1.031 yerine 2.062,
    # üniversite toplamı 1.571 yerine 3.142 görünüyordu. Kural
    # `staff_scope` içinde tektir.
    sorgu = staff_scope.apply_staff_filters(
        select(
            AcademicStaff.department_id,
            func.count(func.distinct(AcademicStaff.id)),
            func.sum(AcademicStaff.publication_count),
            func.sum(AcademicStaff.advising_count),
        ).select_from(AcademicStaff), db, scope, donem
    ).group_by(AcademicStaff.department_id)

    bolumler = {
        d.id: d for d in db.execute(
            select(Department).options(selectinload(Department.faculty))
        ).scalars()
    }
    satirlar = []
    for bolum_id, kisi, yayin, tez in db.execute(sorgu).all():
        bolum = bolumler.get(bolum_id)
        satirlar.append({
            "department_id": bolum_id,
            "department_name": bolum.name if bolum else "Bilinmiyor",
            "faculty_name": bolum.faculty.name if bolum and bolum.faculty else None,
            "academic_staff_count": kisi,
            "total_publications": int(yayin or 0),
            "total_advising": int(tez or 0),
            "publications_per_academic": _oran(yayin or 0, kisi),
        })
    satirlar.sort(key=lambda r: r["publications_per_academic"] or 0, reverse=True)
    return satirlar


# ---------------------------------------------------------------------------
# 4) YKS trendleri (4 yıl)
# ---------------------------------------------------------------------------


def yks_trend(
    db: Session, scope: Optional["Scope"] = None,
    donem: Optional[str] = None,
) -> dict:
    """Kontenjan / yerleşen / doluluk ve taban puan – başarı sırası trendi.

    Doluluk, yıl bazında TOPLAM yerleşen / TOPLAM kontenjan olarak
    hesaplanır; program bazlı oranların ortalamasını almak küçük
    programlara büyük programlarla eşit ağırlık verirdi.

    Taban puan ve başarı sırası için EN İYİ değer alınır: taban puanda en
    yüksek, sırada en küçük sayı. Bunlar farklı ölçeklerdedir ve aynı
    eksende gösterilemez; iki ayrı seri döner.
    """
    sorgu = select(
        YksPlacementRecord.placement_year,
        func.sum(YksPlacementRecord.quota),
        func.sum(YksPlacementRecord.placed_students),
        func.max(YksPlacementRecord.base_score),
        func.min(YksPlacementRecord.success_rank),
    ).group_by(YksPlacementRecord.placement_year).order_by(
        YksPlacementRecord.placement_year
    )
    if scope is not None and scope.program_ids is not None:
        sorgu = sorgu.where(
            YksPlacementRecord.academic_program_id.in_(scope.program_ids)
        )
    if donem:
        secili_yil = student_count._donem_yili(donem)
        if secili_yil is None:
            return {
                "available": False,
                "requested_period": donem,
                "years": [],
                "momentum": {"available": False,
                             "note": "Geçerli bir akademik yıl seçilmedi."},
                "note": "Geçerli bir akademik yıl seçilmedi.",
            }
        # Geçmiş bir dönem seçildiğinde daha sonraki YKS yılları görünmez.
        sorgu = sorgu.where(YksPlacementRecord.placement_year <= secili_yil)

    seri = []
    for yil, kontenjan, yerlesen, taban, sira in db.execute(sorgu).all():
        seri.append({
            "placement_year": yil,
            "academic_year": f"{yil}-{yil + 1}",
            "quota": int(kontenjan) if kontenjan is not None else None,
            "placed_students": int(yerlesen) if yerlesen is not None else None,
            "occupancy_percent": (
                round(float(yerlesen) / float(kontenjan) * 100, 2)
                if kontenjan and yerlesen is not None else None
            ),
            "best_base_score": float(taban) if taban is not None else None,
            "best_success_rank": int(sira) if sira is not None else None,
        })
    # YIL BAZINDA DEĞİŞİM (YoY). Önceki yıl yoksa veya sıfırsa değişim
    # TANIMSIZDIR; 0 yazmak "değişmedi" demek olurdu.
    def _yoy(simdi, onceki):
        if simdi is None or onceki in (None, 0):
            return None
        return round((simdi - onceki) / onceki * 100, 2)

    for i, y in enumerate(seri):
        onceki = seri[i - 1] if i else None
        y["quota_change_percent"] = _yoy(
            y["quota"], onceki["quota"] if onceki else None)
        y["placed_change_percent"] = _yoy(
            y["placed_students"], onceki["placed_students"] if onceki else None)
        y["occupancy_change_points"] = (
            round(y["occupancy_percent"] - onceki["occupancy_percent"], 2)
            if onceki and y["occupancy_percent"] is not None
            and onceki["occupancy_percent"] is not None else None
        )
        y["base_score_change"] = (
            round(y["best_base_score"] - onceki["best_base_score"], 2)
            if onceki and y["best_base_score"] is not None
            and onceki["best_base_score"] is not None else None
        )
        # Başarı sırasında KÜÇÜLME iyileşmedir; işaret bilinçli çevrilir
        # ki grafikte "yukarı = iyi" okunabilsin.
        y["success_rank_improvement"] = (
            onceki["best_success_rank"] - y["best_success_rank"]
            if onceki and y["best_success_rank"] is not None
            and onceki["best_success_rank"] is not None else None
        )

    return {
        "available": bool(seri),
        "requested_period": donem,
        "years": seri,
        "momentum": _demand_momentum(seri),
        "note": (
            "Taban puan ve başarı sırası, kapsamdaki yerleştirme "
            "programlarının en iyi değerleridir."
        ),
    }


def _demand_momentum(seri: List[dict]) -> dict:
    """Son yılın talep yönü — VERİSİ OLAN sinyallerin ortak eğilimi.

    Dört sinyal: yerleşen sayısı, doluluk, taban puan, başarı sırası.
    Her biri +1 (iyileşme) / -1 (kötüleşme) / atlanır (veri yok) olarak
    sayılır. Ağırlıklandırma YAPILMAZ: sinyallerin göreli önemi kurumun
    stratejik tercihidir, veriden çıkarılamaz.

    En az iki yıl gerekir; tek yıllık veriden yön okunamaz.
    """
    if len(seri) < 2:
        return {"available": False,
                "note": "Yön için en az iki yıllık veri gerekir."}

    son = seri[-1]
    sinyaller = {
        "placed_students": son.get("placed_change_percent"),
        "occupancy": son.get("occupancy_change_points"),
        "base_score": son.get("base_score_change"),
        "success_rank": son.get("success_rank_improvement"),
    }
    olculen = {k: v for k, v in sinyaller.items() if v is not None}
    if not olculen:
        return {"available": False,
                "note": "Son yıl için karşılaştırılabilir sinyal yok."}

    iyi = sum(1 for v in olculen.values() if v > 0)
    kotu = sum(1 for v in olculen.values() if v < 0)
    yon = "artıyor" if iyi > kotu else "azalıyor" if kotu > iyi else "yatay"
    return {
        "available": True,
        "academic_year": son["academic_year"],
        "direction": yon,
        "improving_signals": iyi,
        "declining_signals": kotu,
        "measured_signal_count": len(olculen),
        "signals": olculen,
    }


# ---------------------------------------------------------------------------
# 5) Müfredat yükü ve kadro
# ---------------------------------------------------------------------------


def curriculum_load(db: Session, scope: Optional["Scope"] = None,
                    donem: Optional[str] = None) -> dict:
    """Müfredattaki ders sayısı ile akademik kadronun karşılaştırması.

    Ders sayısı KANONİK katmandan gelir. Ham tabloda aynı ders birden çok
    satırda bulunabildiği için ham sayım "ders yükü" göstergesini
    olduğundan büyük gösterirdi.
    """
    ders_sorgu = select(func.count()).select_from(CurriculumCanonicalCourse)
    if scope is not None and scope.is_program:
        ders_sorgu = ders_sorgu.where(
            CurriculumCanonicalCourse.academic_program_id
            == scope.academic_program_id)
    elif scope is not None and scope.department_ids is not None:
        ders_sorgu = ders_sorgu.where(
            CurriculumCanonicalCourse.department_id.in_(scope.department_ids)
        )
    ders = db.execute(ders_sorgu).scalar_one()
    # DÖNEM NOTU: kanonik müfredat dersleri YIL BOYUTU TAŞIMAZ
    # (`curriculum_canonical_courses` tablosunda akademik yıl sütunu
    # yoktur), bu yüzden ders sayısı dönemden BAĞIMSIZDIR ve bilinçli
    # olarak değişmez. Kadro sayısı ise dönemlidir.
    program_kadrosu_olculemez = scope is not None and scope.is_program
    personel = (None if program_kadrosu_olculemez else
                len(db.execute(_staff_query(scope, db, donem)).scalars().all()))

    # Kaç akademisyen BİRDEN ÇOK farklı ders veriyor? Çok dersli
    # akademisyen, uzmanlaşma yerine boşluk doldurduğunu gösterebilir.
    ders_sorgu = select(
        AcademicStaffCourse.academic_staff_id,
        func.count(func.distinct(AcademicStaffCourse.course_name)),
    ).group_by(AcademicStaffCourse.academic_staff_id)
    if scope is not None and scope.is_program:
        # Ders verme kayıtlarında program FK'sı yoktur; bölüm kayıtları
        # programa kopyalanmaz.
        from sqlalchemy import false
        ders_sorgu = ders_sorgu.where(false())
    elif scope is not None and scope.department_ids is not None:
        ders_sorgu = ders_sorgu.join(
            AcademicStaff, AcademicStaff.id == AcademicStaffCourse.academic_staff_id
        ).where(AcademicStaff.department_id.in_(scope.department_ids))
    farkli = dict(db.execute(ders_sorgu).all())
    coklu = sum(1 for n in farkli.values() if n > 1)

    from app.services.course_matching import coverage_for_scope

    # SIFIR MI, ÖLÇÜLMEDİ Mİ?
    # -----------------------
    # `count()` kayıt yokken 0 döner. Ama "bu birimin müfredatında 0 ders
    # var" ile "bu birimin müfredatı sisteme aktarılmadı" farklı şeylerdir
    # ve arayüzde farklı görünmelidir. Kapsamda HİÇ kanonik ders kaydı
    # yoksa sayı `None` döner; arayüz 0 basmak yerine "veri bekleniyor"
    # rozeti gösterir. Rektörlük gibi akademik olmayan birimlerde de
    # doğru davranış budur.
    kayit_var = ders > 0
    return {
        "curriculum_course_count": ders if kayit_var else None,
        "curriculum_measured": kayit_var,
        "academic_staff_count": personel,
        "courses_per_academic_staff": _oran(ders, personel) if kayit_var else None,
        "staff_teaching_multiple_courses": (
            None if program_kadrosu_olculemez else coklu),
        "staff_with_course_records": (
            None if program_kadrosu_olculemez else len(farkli)),
        "average_distinct_courses_per_teaching_staff": _oran(
            sum(farkli.values()), len(farkli))
            if farkli and not program_kadrosu_olculemez else None,
        "curriculum_coverage": coverage_for_scope(db, scope),
        "available": bool(kayit_var and personel)
        if not program_kadrosu_olculemez else False,
        "note": (
            "Akademik kadro ve ders verme kayıtları program kimliği "
            "taşımıyor; bölüm değerleri programa devredilmez."
            if program_kadrosu_olculemez else None
        ),
        # Ders sayısı dönem seçiminden etkilenmez; arayüz bunu yazar.
        "course_count_is_period_independent": True,
    }


# ---------------------------------------------------------------------------
# Toplu görünüm
# ---------------------------------------------------------------------------


def overview(db: Session, scope: Optional["Scope"] = None,
             donem: Optional[str] = None) -> dict:
    """Panonun tek istekte ihtiyaç duyduğu bütün göstergeler.

    Tek uç, arayüzün 7 ayrı istek atmasını önler ve bütün göstergelerin
    AYNI kapsamdan geldiğini garanti eder.
    """
    return {
        "scope": {
            "level": scope.level if scope is not None else "university",
            "label": scope.label if scope is not None else "Üniversite geneli",
        },
        "requested_period": donem,
        "staffing": staffing_overview(db, scope, donem),
        "title_distribution": title_distribution(db, scope, donem),
        "teaching_load": teaching_load_distribution(db, scope, donem),
        "teaching_load_trend": teaching_load_trend(db, scope, donem),
        "publication_productivity": publication_productivity(db, scope, donem),
        "yks_trend": yks_trend(db, scope, donem),
        "curriculum_load": curriculum_load(db, scope, donem),
        "course_concentration": course_concentration(db, scope, donem),
    }


def course_concentration(db: Session, scope: Optional["Scope"] = None,
                         donem: Optional[str] = None) -> dict:
    """Öğretim kaç kişiye bağımlı?

    Ders KAYDI sayısına göre en yüklü %20'nin toplam içindeki payı.
    Yüksek pay, birkaç kişinin ayrılmasının müfredatı riske atacağı
    anlamına gelir — bu bir kadro planlama sinyalidir.
    """
    if scope is not None and scope.is_program:
        return {
            "available": False,
            "requested_period": donem,
            "note": (
                "Ders verme kayıtları program kimliği taşımıyor; bölüm "
                "yoğunlaşması seçili programa devredilmez."
            ),
        }

    sorgu = (
        select(AcademicStaffCourse.academic_staff_id, func.count())
        .group_by(AcademicStaffCourse.academic_staff_id)
    )
    if scope is not None and scope.department_ids is not None:
        sorgu = sorgu.join(
            AcademicStaff, AcademicStaff.id == AcademicStaffCourse.academic_staff_id
        ).where(AcademicStaff.department_id.in_(scope.department_ids))
    # Ders kayıtları dönemlidir. Açık seçim aynen uygulanır; seçim yoksa
    # yalnızca en güncel ders yılı kullanılır. Bütün yılları toplamak aynı
    # akademisyeni ve dersi tekrar tekrar sayardı.
    if donem is None:
        from app.services.curriculum_service import latest_course_year
        hedef_donem = latest_course_year(db)
    else:
        hedef_donem = donem
    if hedef_donem is not None:
        sorgu = sorgu.where(
            AcademicStaffCourse.academic_year == hedef_donem)

    sayilar = sorted((n for _, n in db.execute(sorgu).all()), reverse=True)
    if not sayilar:
        return {"available": False,
                "note": "Kapsamda ders kaydı bulunan akademisyen yok."}

    toplam = sum(sayilar)
    dilim = max(1, round(len(sayilar) * 0.2))
    return {
        "available": True,
        "teaching_staff_count": len(sayilar),
        "total_course_records": toplam,
        "top20_percent_staff_count": dilim,
        "top20_percent_share": round(sum(sayilar[:dilim]) / toplam * 100, 2),
        "max_courses_by_one_staff": sayilar[0],
        "median_courses_per_staff": sayilar[len(sayilar) // 2],
    }


# ---------------------------------------------------------------------------
# 6) ÖĞRENCİ GÖVDESİ — kohort, talep ve büyüme
# ---------------------------------------------------------------------------


def student_body_overview(db: Session, scope: Optional["Scope"] = None,
                          donem: Optional[str] = None) -> dict:
    """Öğrenci analitiğinin karar veren çekirdeği.

    Elimizdeki gerçek veri ÖSYM yerleştirmesidir; bireysel öğrenci kaydı
    yoktur. Bu yüzden bu ekran GPA/mezuniyet/terk uydurmaz — bunun yerine
    yönetimin gerçekten karar aldığı büyüklükleri verir:

      · öğrenci gövdesi (son ≤4 kohortun toplamı)
      · kohortların yıl bazında dağılımı — hangi yıl büyüdük/küçüldük
      · kontenjan / yerleşen / doluluk ve bunların yıllık değişimi
      · talep baskısı: kontenjan doluyor mu, taşıyor mu, boş mu kalıyor
      · öğrenci/akademisyen ve öğrenci/fiilen ders veren akademisyen

    KOHORT = bir yerleştirme yılında yerleşen öğrenci sayısı. Bu bir
    tahmin değil, ÖSYM'nin açıkladığı sayının kendisidir.
    """
    from app.services import university_headcount_service as kayitli

    trend = yks_trend(db, scope, donem)
    kadro = staffing_overview(db, scope, donem)
    # Kaynağı da alınır: üniversite kapsamında YÖK kayıtlı sayısı, alt
    # kapsamlarda ÖSYM türevi. Ekran hangi ölçümü gösterdiğini yazabilsin
    # diye kaynak alan olarak dışa verilir.
    toplam, toplam_kaynak = student_count.total_for_scope_detailed(
        db, scope, donem)

    yillar = trend["years"]
    istenen_yil = student_count._donem_yili(donem) if donem else None
    # Seçili dönem gelecekteki kohortları dışarıda bırakır. Cari
    # kontenjan/yerleşen alanı yalnızca seçilen yılın satırından gelir;
    # o yıl yoksa daha yeni/eski yıla sessizce düşülmez.
    pencere_yillari = [
        y for y in yillar
        if istenen_yil is None or y["placement_year"] <= istenen_yil
    ]
    # Öğrenci gövdesini oluşturan kohortlar: `student_count` ile AYNI
    # pencere kullanılır, aksi hâlde "kohortların toplamı ≠ toplam
    # öğrenci" gibi açıklanamaz bir tutarsızlık çıkardı.
    kohortlar = [y for y in pencere_yillari
                 if y["placed_students"] is not None
                 ][-student_count.RECENT_COHORT_YEARS:]
    kohort_toplami = sum(k["placed_students"] for k in kohortlar) or None

    for k in kohortlar:
        k["cohort_share_percent"] = (
            round(k["placed_students"] / kohort_toplami * 100, 2)
            if kohort_toplami else None
        )

    if istenen_yil is not None:
        son = next((y for y in yillar
                    if y["placement_year"] == istenen_yil), None)
    else:
        son = kohortlar[-1] if kohortlar else None
    onceki = next((y for y in reversed(kohortlar)
                   if son is not None
                   and y["placement_year"] < son["placement_year"]), None)

    # Kontenjan ve yerleşen TOPLAMLARI aynı pencereden; doluluk oranı
    # program bazlı oranların ortalaması DEĞİL, toplamların oranıdır.
    kont_toplam = sum(k["quota"] for k in kohortlar
                      if k["quota"] is not None) or None
    yer_toplam = kohort_toplami

    return {
        "available": bool(kohortlar),
        "requested_period": donem,
        "period_has_placement_data": son is not None,
        # --- gövde ---
        "student_count": toplam,
        "student_count_source": toplam_kaynak,
        "cohort_count": len(kohortlar),
        "cohort_years": [k["placement_year"] for k in kohortlar],
        "cohorts": kohortlar,
        # --- cari yerleştirme dönemi ---
        "latest_placement_year": son["placement_year"] if son else None,
        "latest_quota": son["quota"] if son else None,
        "latest_placed_students": son["placed_students"] if son else None,
        "latest_occupancy_percent": son["occupancy_percent"] if son else None,
        # --- değişim: bir önceki kohorta göre ---
        "intake_change_percent": son.get("placed_change_percent") if son else None,
        "quota_change_percent": son.get("quota_change_percent") if son else None,
        "occupancy_change_points": (
            son.get("occupancy_change_points") if son else None),
        "base_score_change": son.get("base_score_change") if son else None,
        "success_rank_improvement": (
            son.get("success_rank_improvement") if son else None),
        "previous_cohort_size": onceki["placed_students"] if onceki else None,
        # --- pencere toplamları ---
        "window_quota_total": kont_toplam,
        "window_placed_total": yer_toplam,
        "window_occupancy_percent": (
            round(yer_toplam / kont_toplam * 100, 2)
            if kont_toplam and yer_toplam is not None else None),
        # --- kadro ile ilişki ---
        "academic_staff_count": kadro["academic_staff_count"] or None,
        "active_teaching_staff_count": (
            kadro["active_teaching_staff_count"] or None),
        "students_per_academic_staff": kadro["students_per_academic_staff"],
        "students_per_active_teaching_staff": (
            kadro["students_per_active_teaching_staff"]),
        "academics_per_100_students": kadro["academics_per_100_students"],
        # --- yön ve baskı ---
        "demand_momentum": trend["momentum"],
        "demand_pressure": _demand_pressure(son),
        # --- YÖK KAYITLI ÖĞRENCİ SAYISI (yalnızca üniversite düzeyi) ---
        # `student_count` alanına DOKUNMAZ. Bu ayrı bir ölçümdür:
        # kohort toplamı değil, o yıl fiilen kayıtlı olan öğrenci sayısı.
        # Alt kapsamlarda `available: False` döner; üniversite toplamını
        # fakülteye/programa dağıtmak uydurma olurdu.
        "enrolled_headcount": kayitli.enrolled_headcount(
            db, scope, donem=donem),
    }


def _demand_pressure(son: Optional[dict]) -> dict:
    """Kontenjan–talep dengesi. Eşikler AÇIKÇA bildirilir.

    Bunlar mevzuattan gelen sınırlar değildir; okunabilir bir yorum
    sağlamak için seçilmiş bantlardır ve API bunu `thresholds` alanıyla
    söyler. Yönetim kendi eşiğini uygulamak isterse ham `occupancy`
    değeri zaten yanındadır.
    """
    if not son or son.get("occupancy_percent") is None:
        return {"available": False,
                "note": "Doluluk hesaplanacak kontenjan/yerleşen verisi yok."}
    d = son["occupancy_percent"]
    if d >= 100:
        durum, aciklama = "talep_fazlasi", "Kontenjan tamamen doldu."
    elif d >= 85:
        durum, aciklama = "dengeli", "Kontenjan büyük ölçüde doluyor."
    elif d >= 60:
        durum, aciklama = "gevsek", "Kontenjanın bir kısmı boş kalıyor."
    else:
        durum, aciklama = "talep_yetersiz", "Kontenjanın önemli kısmı boş."
    return {
        "available": True,
        "placement_year": son["placement_year"],
        "occupancy_percent": d,
        "unfilled_quota": (
            son["quota"] - son["placed_students"]
            if son.get("quota") is not None
            and son.get("placed_students") is not None
            and son["quota"] > son["placed_students"] else None),
        "status": durum,
        "explanation": aciklama,
        "thresholds": {"talep_fazlasi": 100, "dengeli": 85, "gevsek": 60},
    }


# ---------------------------------------------------------------------------
# 7) YÖNETİM PANOSU — "bu ekrandan hangi kararı alırım?"
# ---------------------------------------------------------------------------


def operational_warnings(db: Session, scope: Optional["Scope"] = None,
                         donem: Optional[str] = None
                         ) -> List[dict]:
    """Gerçek veriden türetilen operasyonel uyarılar.

    Her uyarı, hangi sayıdan çıktığını taşır: yönetici uyarıyı görünce
    "neye göre?" diye sormak zorunda kalmasın. Ölçülmemiş gösterge
    uyarı üretmez — "veri yok" bir risk sinyali değildir.
    """
    uyarilar: List[dict] = []

    kadro = staffing_overview(db, scope, donem)
    yuk = teaching_load_distribution(db, scope, donem)
    yogunlasma = course_concentration(db, scope, donem)
    talep = student_body_overview(db, scope, donem)

    def ekle(kod, seviye, baslik, deger, aciklama):
        uyarilar.append({"code": kod, "severity": seviye, "title": baslik,
                         "measured_value": deger, "explanation": aciklama})

    # 1. Ders vermeyen kadro oranı.
    toplam_kadro = kadro["academic_staff_count"]
    if toplam_kadro:
        vermeyen = kadro["staff_without_teaching_load"]
        oran = round(vermeyen / toplam_kadro * 100, 1)
        if oran >= 50:
            ekle("teaching_coverage", "yuksek",
                 "Kadronun yarıdan fazlasında ders yükü kaydı yok",
                 oran, f"{vermeyen}/{toplam_kadro} akademisyen için ders "
                       "yükü saati kayıtlı değil.")

    # 2. Ders yükü yoğunlaşması — öğretim kaç kişiye bağımlı?
    if yuk.get("available") and yuk.get("top20_percent_share") is not None:
        if yuk["top20_percent_share"] >= 50:
            ekle("load_concentration", "yuksek",
                 "Ders yükü az sayıda akademisyende toplanmış",
                 yuk["top20_percent_share"],
                 f"En yüklü {yuk['top20_percent_staff_count']} kişi toplam "
                 f"saatin %{yuk['top20_percent_share']}'ini taşıyor.")

    if yogunlasma.get("available") and yogunlasma["top20_percent_share"] >= 50:
        ekle("course_concentration", "orta",
             "Ders kayıtları az sayıda akademisyende toplanmış",
             yogunlasma["top20_percent_share"],
             f"En çok ders veren {yogunlasma['top20_percent_staff_count']} "
             f"kişi ders kayıtlarının %{yogunlasma['top20_percent_share']}'ini "
             "üstleniyor.")

    # 3. Öğrenci/akademisyen oranı.
    oran = kadro["students_per_academic_staff"]
    if oran is not None and oran >= 40:
        ekle("student_staff_ratio", "yuksek",
             "Öğrenci/akademisyen oranı yüksek", oran,
             f"Akademisyen başına {oran} öğrenci düşüyor.")

    # 4. Talep.
    baski = talep["demand_pressure"]
    if baski.get("available") and baski["status"] == "talep_yetersiz":
        ekle("low_occupancy", "yuksek", "Kontenjan doluluğu düşük",
             baski["occupancy_percent"],
             f"{baski['placement_year']} yerleştirmesinde doluluk "
             f"%{baski['occupancy_percent']}.")
    if talep.get("demand_momentum", {}).get("direction") == "azalıyor":
        ekle("demand_declining", "orta", "Talep göstergeleri geriliyor",
             talep["demand_momentum"]["declining_signals"],
             "Yerleşen, doluluk, taban puan ve başarı sırası "
             "sinyallerinin çoğunluğu geriledi.")

    sira = {"kritik": 0, "yuksek": 1, "orta": 2}
    uyarilar.sort(key=lambda u: sira.get(u["severity"], 3))
    return uyarilar


def executive_overview(db: Session, scope: Optional["Scope"] = None,
                       donem: Optional[str] = None) -> dict:
    """Yönetim panosunun TEK isteği.

    Kapsam seviyesine göre kırılım DEĞİŞİR:
      üniversite → fakülte karşılaştırması
      fakülte    → bölüm karşılaştırması
      bölüm      → program karşılaştırması
      program    → kırılım yok; birimin kendi operasyonel sağlığı

    Kırılımı seviye başına ayrı ayrı yazmak yerine tek bir hiyerarşi
    kuralına bağlıyoruz (`peer_comparison_service.child_breakdown`);
    yeni bir seviye eklendiğinde burada değişiklik gerekmez.
    """
    from app.services import peer_comparison_service as kiyas
    from app.services.scope import Scope

    scope = scope or Scope()
    kirilim = kiyas.child_breakdown(db, scope, donem)
    return {
        "scope": {"level": scope.level, "label": scope.label},
        "requested_period": donem,
        "staffing": staffing_overview(db, scope, donem),
        "teaching_load": teaching_load_distribution(db, scope, donem),
        "course_concentration": course_concentration(db, scope, donem),
        "title_distribution": title_distribution(db, scope, donem),
        "publication_productivity": publication_productivity(db, scope, donem),
        "curriculum_load": curriculum_load(db, scope, donem),
        "student_body": student_body_overview(db, scope, donem),
        # Alt birim kırılımı; yaprakta `rows` boş, `unit` dolu olur.
        "breakdown": kirilim,
        "unit": kiyas.unit_self(db, scope, donem)
        if kirilim["is_leaf"] else None,
        "warnings": operational_warnings(db, scope, donem),
    }


# ---------------------------------------------------------------------------
# 8) BURS TÜRÜ KIRILIMI — kontenjan, doluluk, taban puan, başarı sırası
# ---------------------------------------------------------------------------


def scholarship_breakdown(db: Session, scope: Optional["Scope"] = None,
                          donem: Optional[str] = None) -> dict:
    """ÖSYM burs türlerine göre kontenjan/yerleşen/doluluk ve puan.

    Kaynak `yks_placement_records.scholarship_type` alanıdır ve GERÇEK
    veridir: Burslu (tam burs), %50 İndirimli, Ücretli. Kurumun
    yayımlamadığı bir burs türü (ör. başarı bursu) burada UYDURULMAZ —
    listede yer almaz.

    Her tür için yıl serisi de döner; burs politikasının doluluğa
    etkisi ancak yıllar üzerinden okunabilir.
    """
    sorgu = select(
        YksPlacementRecord.scholarship_type,
        YksPlacementRecord.placement_year,
        func.sum(YksPlacementRecord.quota),
        func.sum(YksPlacementRecord.placed_students),
        func.max(YksPlacementRecord.base_score),
        func.min(YksPlacementRecord.success_rank),
    ).group_by(
        YksPlacementRecord.scholarship_type, YksPlacementRecord.placement_year
    ).order_by(YksPlacementRecord.placement_year)
    if scope is not None and scope.program_ids is not None:
        sorgu = sorgu.where(
            YksPlacementRecord.academic_program_id.in_(scope.program_ids))
    istenen = student_count._donem_yili(donem) if donem else None
    if istenen is not None:
        # Tarihsel seçimde grafik de o yılda biter. KPI'yı 2024'ten,
        # seriyi 2025'e kadar çizmek aynı panel içinde dönem sızıntısıydı.
        sorgu = sorgu.where(YksPlacementRecord.placement_year <= istenen)

    turler: Dict[str, dict] = {}
    yillar: set = set()
    for tur, yil, kont, yer, taban, sira in db.execute(sorgu):
        ad = tur or "Belirtilmemiş"
        yillar.add(int(yil))
        k = turler.setdefault(ad, {"scholarship_type": ad, "years": {}})
        k["years"][int(yil)] = {
            "placement_year": int(yil),
            "quota": int(kont) if kont is not None else None,
            "placed_students": int(yer) if yer is not None else None,
            "occupancy_percent": (round(float(yer) / float(kont) * 100, 2)
                                  if kont and yer is not None else None),
            "best_base_score": float(taban) if taban is not None else None,
            "best_success_rank": int(sira) if sira is not None else None,
        }

    sirali_yillar = sorted(yillar)
    # DÖNEM: "güncel" kartlar ve trend seçilen yılda biter. O yılın yerleştirme
    # kaydı yoksa BAŞKA yıla düşülmez; kartlar boş (None) döner ve
    # arayüz "bu dönemde ölçülmedi" gösterir. Gelecek yıllar trendden de
    # çıkarılır.
    if istenen is not None:
        son = istenen if istenen in yillar else None
    else:
        son = sirali_yillar[-1] if sirali_yillar else None

    satirlar = []
    for ad, k in turler.items():
        seri = [k["years"][y] for y in sirali_yillar if y in k["years"]]
        guncel = k["years"].get(son)
        satirlar.append({
            "scholarship_type": ad,
            "series": seri,
            "quota": guncel["quota"] if guncel else None,
            "placed_students": guncel["placed_students"] if guncel else None,
            "occupancy_percent": guncel["occupancy_percent"] if guncel else None,
            "best_base_score": guncel["best_base_score"] if guncel else None,
            "best_success_rank": guncel["best_success_rank"] if guncel else None,
        })
    # Kontenjanı büyük olan üstte; ölçek okunabilirliği için.
    satirlar.sort(key=lambda r: -(r["quota"] or 0))

    return {
        "available": bool(satirlar) and son is not None,
        "requested_period": donem,
        "period_has_data": son is not None,
        "latest_placement_year": son,
        "years": sirali_yillar,
        "types": satirlar,
        "note": ("Burs türleri ÖSYM yerleştirme kayıtlarından gelir; "
                 "kurumun yayımlamadığı burs türü listede yer almaz."),
    }


# ---------------------------------------------------------------------------
# Yönetilen tamamlayıcı analitikler — kişi kaydı yok, yetkili veri öncelikli
# ---------------------------------------------------------------------------

COURSE_SURVEY_KEYS = (
    "average_course_evaluation_score",
    "course_satisfaction_rate",
    "instructor_satisfaction_rate",
    "course_survey_response_rate",
    "course_evaluation_count",
)
EMPLOYMENT_KEYS = (
    "graduate_employment_rate",
    "employment_within_6_months_rate",
    "employment_within_12_months_rate",
    "sector_alignment_rate",
)
PUBLICATION_QUALITY_KEYS = ("q1_publication_rate", "estimated_h_index")
SUPPLEMENTARY_FACILITY_KEYS = (
    "office_count", "office_area_m2", "library_count", "library_area_m2",
    "common_area_count", "common_area_m2", "study_area_capacity",
)


def _governed_provenance(rows: List[dict]) -> dict:
    """Birden çok yönetilen satırı tek, yanıltmayan kaynak künyesine indirger."""
    if not rows:
        return {
            "source_type": None, "source_label": None, "provenance": None,
            "is_synthetic": False, "uploaded_source_id": None, "filename": None,
        }
    source_ids = {row.get("uploaded_source_id") for row in rows}
    filenames = {row.get("filename") for row in rows if row.get("filename")}
    labels = {row.get("source_label") for row in rows if row.get("source_label")}
    synthetic = any(bool(row.get("is_synthetic")) for row in rows)
    return {
        "source_type": "uploaded",
        "source_label": next(iter(labels)) if len(labels) == 1 else "Yönetilen yüklenmiş analitikler",
        "provenance": "SYNTHETIC_GENERATED" if synthetic else "Yönetilen yüklenmiş veri",
        "is_synthetic": synthetic,
        "uploaded_source_id": next(iter(source_ids)) if len(source_ids) == 1 else None,
        "filename": next(iter(filenames)) if len(filenames) == 1 else None,
    }


def _weighted_metric(grouped: Dict[int, dict], metric_key: str,
                     weights: Dict[int, Decimal]) -> Optional[float]:
    pairs = []
    for program_id, metrics in grouped.items():
        value = metrics.get(metric_key)
        weight = weights.get(program_id, Decimal("0"))
        if value is not None and weight > 0:
            pairs.append((Decimal(str(value)), weight))
    total_weight = sum((weight for _, weight in pairs), Decimal("0"))
    if total_weight <= 0:
        return None
    return round(float(sum(value * weight for value, weight in pairs) / total_weight), 2)


def course_survey_overview(db: Session, scope: "Scope", academic_year: str) -> dict:
    """Program toplamlarından kapsam duyarlı anket özeti; öğrenci yanıtı/PII yoktur."""
    from app.services import data_source_service

    governed = data_source_service.governed_records(
        db, metric_keys=COURSE_SURVEY_KEYS, academic_year=academic_year,
        scope=scope, record_scope_type="program", entity_type="academic_program",
    )
    grouped: Dict[int, dict] = {}
    for row in governed:
        if row["program_id"] is not None:
            grouped.setdefault(row["program_id"], {})[row["metric_key"]] = row["value"]
    grouped = {
        program_id: metrics for program_id, metrics in grouped.items()
        if all(key in metrics for key in COURSE_SURVEY_KEYS)
    }
    if not grouped:
        return {
            "available": False, "academic_year": academic_year, "scope": scope.label,
            "note": "Bu kapsam ve dönemde yönetilen ders anketi özeti yok.",
        }

    success = data_source_service.governed_records(
        db, metric_keys=("measured_student_count",), academic_year=academic_year,
        scope=scope, record_scope_type="program", entity_type="academic_program",
    )
    eligible = {
        row["program_id"]: Decimal(str(row["value"])) for row in success
        if row["program_id"] in grouped and row["value"] is not None
    }
    evaluation_weights = {
        program_id: Decimal(str(metrics["course_evaluation_count"]))
        for program_id, metrics in grouped.items()
    }
    evaluation_count = int(sum(evaluation_weights.values(), Decimal("0")))
    eligible_count = int(sum(eligible.values(), Decimal("0")))
    response_rate = (
        round(evaluation_count / eligible_count * 100, 2) if eligible_count else
        _weighted_metric(grouped, "course_survey_response_rate", evaluation_weights)
    )
    complete_rows = [row for row in governed if row["program_id"] in grouped]
    return {
        "available": True, "academic_year": academic_year, "scope": scope.label,
        "program_count": len(grouped), "evaluation_count": evaluation_count,
        "eligible_student_count": eligible_count or None,
        "average_course_evaluation_score": _weighted_metric(
            grouped, "average_course_evaluation_score", evaluation_weights),
        "course_satisfaction_rate": _weighted_metric(
            grouped, "course_satisfaction_rate", evaluation_weights),
        "instructor_satisfaction_rate": _weighted_metric(
            grouped, "instructor_satisfaction_rate", evaluation_weights),
        "course_survey_response_rate": response_rate,
        "note": "Toplulaştırılmış analitik tahmin; öğrenci düzeyinde yanıt veya kişisel veri içermez.",
        **_governed_provenance(complete_rows),
    }


def student_employment_overview(db: Session, scope: "Scope", academic_year: str) -> dict:
    """Program oranlarını mezun sayısıyla ağırlıklandırır; kişi kaydı üretmez."""
    from app.services import data_source_service

    governed = data_source_service.governed_records(
        db, metric_keys=EMPLOYMENT_KEYS, academic_year=academic_year,
        scope=scope, record_scope_type="program", entity_type="academic_program",
    )
    grouped: Dict[int, dict] = {}
    for row in governed:
        if row["program_id"] is not None:
            grouped.setdefault(row["program_id"], {})[row["metric_key"]] = row["value"]
    grouped = {
        program_id: metrics for program_id, metrics in grouped.items()
        if all(key in metrics for key in EMPLOYMENT_KEYS)
    }
    if not grouped:
        return {
            "available": False, "academic_year": academic_year, "scope": scope.label,
            "note": "Bu kapsam ve dönemde yönetilen mezun istihdam analitiği yok.",
        }

    graduate_rows = data_source_service.governed_records(
        db, metric_keys=("graduate_count",), academic_year=academic_year,
        scope=scope, record_scope_type="program", entity_type="academic_program",
    )
    graduate_weights = {
        row["program_id"]: Decimal(str(row["value"])) for row in graduate_rows
        if row["program_id"] in grouped and row["value"] is not None
    }
    graduate_count = int(sum(graduate_weights.values(), Decimal("0")))
    result = {
        "available": True, "academic_year": academic_year, "scope": scope.label,
        "program_count": len(grouped), "graduate_count": graduate_count,
        **{
            key: _weighted_metric(grouped, key, graduate_weights)
            for key in EMPLOYMENT_KEYS
        },
        "regional_employment_rate": None,
        "regional_employment_count": None,
        "note": "Toplulaştırılmış analitik tahmin; mezun düzeyinde kişi kaydı içermez.",
        **_governed_provenance([row for row in governed if row["program_id"] in grouped]),
    }
    if scope.is_university and graduate_count:
        regional = data_source_service.availability(
            db, metric_key="regional_graduates_employed", academic_year=academic_year,
            scope_type="university", faculty_id=None, department_id=None, program_id=None,
        )
        if regional.get("resolved_value") is not None:
            count = int(Decimal(str(regional["resolved_value"])))
            result["regional_employment_count"] = count
            result["regional_employment_rate"] = round(count / graduate_count * 100, 2)
    return result


def _availability_for_scope(db: Session, metric_key: str, academic_year: str,
                            scope: "Scope") -> dict:
    from app.services import data_source_service

    return data_source_service.availability(
        db, metric_key=metric_key, academic_year=academic_year,
        scope_type=scope.level, faculty_id=scope.faculty_id,
        department_id=scope.department_id, program_id=scope.academic_program_id,
    )


def publication_quality_overview(db: Session, scope: "Scope", academic_year: str) -> dict:
    if scope.level not in {"university", "faculty"}:
        return {
            "available": False, "academic_year": academic_year, "scope": scope.label,
            "note": "Q1/H-indeks tahmini yalnızca kurum ve fakülte seviyesinde modellenmiştir.",
        }
    q1 = _availability_for_scope(db, "q1_publication_rate", academic_year, scope)
    h_index = _availability_for_scope(db, "estimated_h_index", academic_year, scope)
    return {
        "available": q1.get("resolved_value") is not None and h_index.get("resolved_value") is not None,
        "academic_year": academic_year, "scope": scope.label,
        "q1_publication_rate": q1.get("resolved_value"),
        "estimated_h_index": h_index.get("resolved_value"),
        "q1_source": q1, "h_index_source": h_index,
        "source_type": q1.get("source_type") if q1.get("source_type") == h_index.get("source_type") else "mixed",
        "source_label": q1.get("source_label"),
        "provenance": "SYNTHETIC_GENERATED" if q1.get("is_synthetic") or h_index.get("is_synthetic") else q1.get("provenance"),
        "is_synthetic": bool(q1.get("is_synthetic") or h_index.get("is_synthetic")),
        "uploaded_source_id": q1.get("uploaded_source_id") if q1.get("uploaded_source_id") == h_index.get("uploaded_source_id") else None,
        "filename": q1.get("filename") if q1.get("filename") == h_index.get("filename") else None,
        "note": "Dergi çeyreklik ve yayın-bazlı atıf verisi bulunmadığı için açıkça analitik tahmindir; YÖK Akademik sınıflaması değildir.",
    }


def salary_scenarios(db: Session, scope: "Scope", academic_year: str) -> dict:
    """Maaş bordrosu uydurmaz; gider toplamından toplu planlama senaryosu türetir."""
    if not scope.is_university:
        return {
            "available": False, "academic_year": academic_year, "scope": scope.label,
            "note": "Akademik personel gideri yalnızca kurum düzeyinde yönetilmektedir.",
        }
    expense = _availability_for_scope(db, "academic_personnel_expense", academic_year, scope)
    if expense.get("resolved_value") is None:
        return {
            "available": False, "academic_year": academic_year, "scope": scope.label,
            "note": "Akademik personel gideri bulunmadığı için senaryo hesaplanamadı.",
        }
    annual = Decimal(str(expense["resolved_value"]))
    staffing = staffing_overview(db, scope, academic_year)
    staff_count = int(staffing.get("academic_staff_count") or 0)
    return {
        "available": True, "academic_year": academic_year, "scope": scope.label,
        "academic_staff_count": staff_count,
        "estimated_annual_academic_payroll_musd": round(float(annual), 3),
        "estimated_monthly_academic_payroll_musd": round(float(annual / Decimal("12")), 3),
        "estimated_average_annual_academic_cost_usd": (
            round(float(annual * Decimal("1000000") / staff_count), 2) if staff_count else None
        ),
        "payroll_scenario_base_musd": round(float(annual), 3),
        "payroll_scenario_plus_10_musd": round(float(annual * Decimal("1.10")), 3),
        "payroll_scenario_plus_20_musd": round(float(annual * Decimal("1.20")), 3),
        "source_type": expense.get("source_type"), "source_label": expense.get("source_label"),
        "provenance": expense.get("provenance"), "is_synthetic": expense.get("is_synthetic", False),
        "uploaded_source_id": expense.get("uploaded_source_id"), "filename": expense.get("filename"),
        "note": "Akademik personel gideriyle birebir uzlaşan toplu planlama senaryosu; bireysel maaş/bordro kaydı değildir.",
    }


def supplementary_facility_overview(db: Session, scope: "Scope", academic_year: str) -> dict:
    if not scope.is_university:
        return {
            "available": False, "academic_year": academic_year, "scope": scope.label,
            "note": "Tamamlayıcı ofis/kütüphane/ortak alan envanteri yalnızca kurum düzeyindedir.",
        }
    metrics = {
        key: _availability_for_scope(db, key, academic_year, scope)
        for key in SUPPLEMENTARY_FACILITY_KEYS
    }
    if any(row.get("resolved_value") is None for row in metrics.values()):
        return {
            "available": False, "academic_year": academic_year, "scope": scope.label,
            "note": "Tamamlayıcı mekân analitiğinin bütün bileşenleri bulunamadı.",
        }
    values = {key: float(row["resolved_value"]) for key, row in metrics.items()}
    provenance_rows = list(metrics.values())
    return {
        "available": True, "academic_year": academic_year, "scope": scope.label,
        **values,
        "supplementary_area_m2": round(
            values["office_area_m2"] + values["library_area_m2"] + values["common_area_m2"], 2),
        "note": "Yetkili 80 derslik/laboratuvar satırından ayrı, toplulaştırılmış tamamlayıcı sentetik envanterdir.",
        **_governed_provenance(provenance_rows),
    }
