"""Müfredat, ders eşleştirme ve karar destek göstergeleri.

  * müfredat kataloğu OPERASYONEL VERİDİR — kalite/doğrulama ayrımı yok
  * personel ders geçmişi müfredatla eşleştirilir (kod → ad → bölüm)
  * sahte eşleşme üretilmez, bölüm bağlamı korunur
  * karar göstergeleri yalnızca DOLU veriden üretilir; veri yoksa
    `None` / `available: false` döner (sıfır kartı basılmaz)
"""

from typing import Iterator

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import (
    AcademicProgram,
    AcademicStaff,
    AcademicStaffCourse,
    CurriculumCourse,
    Department,
    Faculty,
    YksPlacementRecord,
)
from app.services import curriculum_service as mufredat
from app.services import decision_analytics_service as analitik
from app.services.curriculum_canonical import (
    class_year_from_code,
    clean_course_name,
    normalize_code,
    rebuild_canonical,
)
from app.services.scope import resolve
from app.services.unit_types import FACULTY

YIL = "2025-2026"


@pytest.fixture()
def db() -> Iterator[Session]:
    """İki bölümlü tek fakülte; ders, kadro ve YKS verisi farklı desende."""
    motor = create_engine(
        "sqlite://", future=True,
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(motor)
    s = sessionmaker(bind=motor, future=True)()

    fak = Faculty(name="MÜHENDİSLİK FAKÜLTESİ", code="MUH",
                  unit_type=FACULTY, is_active=True)
    s.add(fak)
    s.flush()
    yaz = Department(name="YAZILIM MÜHENDİSLİĞİ BÖLÜMÜ", code="YAZMUH",
                     faculty_id=fak.id, is_active=True)
    bil = Department(name="BİLGİSAYAR MÜHENDİSLİĞİ BÖLÜMÜ", code="BILMUH",
                     faculty_id=fak.id, is_active=True)
    s.add_all([yaz, bil])
    s.flush()

    yaz_pr = AcademicProgram(name="Yazılım Mühendisliği", code="YAZ-PR",
                             department_id=yaz.id, degree_level="Lisans",
                             is_active=True)
    bil_pr = AcademicProgram(name="Bilgisayar Mühendisliği", code="BIL-PR",
                             department_id=bil.id, degree_level="Lisans",
                             is_active=True)
    s.add_all([yaz_pr, bil_pr])
    s.flush()

    # --- kadro: YAZ=2 (biri ders yüklü), BIL=3 ---
    p1 = AcademicStaff(staff_number="Y1", first_name="A", last_name="Bir",
                       title="PROFESÖR", department_id=yaz.id,
                       academic_year=YIL, is_active=True,
                       publication_count=10, teaching_load_hours=12)
    p2 = AcademicStaff(staff_number="Y2", first_name="B", last_name="İki",
                       title="DOKTOR ÖĞRETİM ÜYESİ", department_id=yaz.id,
                       academic_year=YIL, is_active=True,
                       publication_count=4, teaching_load_hours=0)
    s.add_all([p1, p2])
    for i in range(3):
        s.add(AcademicStaff(
            staff_number=f"B{i}", first_name="C", last_name=f"Üç{i}",
            title="ARAŞTIRMA GÖREVLİSİ", department_id=bil.id,
            academic_year=YIL, is_active=True, publication_count=1,
            teaching_load_hours=6,
        ))
    s.flush()

    # --- ders geçmişi: p1'in iki yılı, biri saatsiz ---
    s.add_all([
        AcademicStaffCourse(academic_staff_id=p1.id, academic_year="2025-2026",
                            course_name="Yazılım Mimarisi", language="Türkçe",
                            weekly_hours=3, source_dataset="test"),
        AcademicStaffCourse(academic_staff_id=p1.id, academic_year="2025-2026",
                            course_name="Veri Yapıları", language="İngilizce",
                            weekly_hours=4, source_dataset="test"),
        AcademicStaffCourse(academic_staff_id=p1.id, academic_year="2024-2025",
                            course_name="Algoritmalar", language="Türkçe",
                            weekly_hours=None, source_dataset="test"),
    ])

    # --- müfredat: YAZ=3 (biri güvenilmez), BIL=1 ---
    s.add_all([
        CurriculumCourse(department_id=yaz.id, academic_program_id=yaz_pr.id,
                         course_code="SE 101", course_name="Giriş",
                         name_is_reliable=True, source_type="web",
                         source_dataset="t", source_file="f", source_fingerprint="a"),
        CurriculumCourse(department_id=yaz.id, course_code=None,
                         course_name="Seçmeli", name_is_reliable=True,
                         source_type="booklet", source_dataset="t",
                         source_file="f", source_fingerprint="b"),
        CurriculumCourse(department_id=yaz.id, course_code="SE 999",
                         course_name="X 101 Bozuk Y 202 Metin Z 303 Yapisik",
                         name_is_reliable=False, source_type="booklet",
                         source_dataset="t", source_file="f",
                         source_fingerprint="c"),
        CurriculumCourse(department_id=bil.id, course_code="CE 101",
                         course_name="Devreler", name_is_reliable=True,
                         source_type="web", source_dataset="t",
                         source_file="f", source_fingerprint="d"),
    ])

    # --- YKS: iki yıl, iki varyant ---
    for yil, kont, yer, taban, sira in (
        (2024, 40, 38, 400.5, 90000), (2025, 50, 55, 420.75, 70000)
    ):
        s.add(YksPlacementRecord(
            academic_program_id=yaz_pr.id, placement_year=yil,
            academic_year=f"{yil}-{yil+1}",
            placement_program_name=f"Yaz {yil}", score_type="SAY",
            scholarship_type="Burslu", quota=kont, placed_students=yer,
            base_score=taban, success_rank=sira,
            source_dataset="t", source_file="f",
        ))
    s.flush()

    # Uygulama HAM tabloyu değil, ondan TÜRETİLEN kanonik katmanı okur.
    # Aktarım betiği de son adımda bunu yapar; fixture aynı sırayı izler.
    rebuild_canonical(s)
    s.commit()
    try:
        yield s
    finally:
        s.close()
        motor.dispose()


def _bid(db: Session, kod: str) -> int:
    return db.execute(
        select(Department.id).where(Department.code == kod)).scalar_one()


def _sid(db: Session, no: str) -> int:
    return db.execute(
        select(AcademicStaff.id).where(AcademicStaff.staff_number == no)
    ).scalar_one()


# ==========================================================================
# 1. Müfredat görünür ve kalite bayrağı korunuyor
# ==========================================================================


def test_mufredat_ozeti_tum_satirlari_sayar(db: Session) -> None:
    """Aktarılan satırlar operasyonel veridir; kalite ayrımı yapılmaz."""
    o = mufredat.course_overview(db)
    assert o["total_course_count"] == 4
    assert o["missing_code_count"] == 1
    # Kalite alanı API yüzeyinden KALDIRILDI.
    assert "unverified_course_count" not in o


def test_ders_listesi_kalite_bayragi_dondurmez(db: Session) -> None:
    """`name_is_reliable` veritabanında kalır ama API'den dönmez."""
    satirlar = mufredat.list_courses(db)
    assert satirlar
    for r in satirlar:
        assert "name_is_reliable" not in r


def test_butun_satirlar_normal_veri_olarak_listelenir(db: Session) -> None:
    """PDF'ten sorunlu çıkan satır da listede görünür, gizlenmez."""
    adlar = {r["course_name"] for r in mufredat.list_courses(db)}
    assert "X 101 Bozuk Y 202 Metin Z 303 Yapisik" in adlar
    assert len(adlar) == 4


def test_arama_kod_ve_ad_icinde_calisir(db: Session) -> None:
    assert len(mufredat.list_courses(db, search="SE 101")) == 1
    assert len(mufredat.list_courses(db, search="Devre")) == 1


def test_mufredat_kapsama_uyar(db: Session) -> None:
    kapsam = resolve(db, department_id=_bid(db, "YAZMUH"))
    kodlar = {r["course_name"] for r in mufredat.list_courses(db, kapsam)}
    assert "Devreler" not in kodlar
    assert len(kodlar) == 3


def test_bolum_bazinda_ders_sayisi_kadroyla_birlikte_doner(db: Session) -> None:
    """Ders sayısı tek başına karar verdirmez; kadro da aynı satırda."""
    satirlar = {r["department_name"]: r
                for r in mufredat.courses_by_department(db)}
    yaz = satirlar["YAZILIM MÜHENDİSLİĞİ BÖLÜMÜ"]
    assert yaz["course_count"] == 3
    assert yaz["academic_staff_count"] == 2
    assert yaz["courses_per_staff"] == 1.5


def test_kaynak_dagilimi_kokeni_gosterir(db: Session) -> None:
    kaynaklar = {r["source_type"]: r["course_count"]
                 for r in mufredat.source_type_breakdown(db)}
    assert kaynaklar == {"web": 2, "booklet": 2}


# ==========================================================================
# 2. Akademisyen ders drill-down
# ==========================================================================


def test_dersler_akademik_yila_gore_gruplanir(db: Session) -> None:
    d = mufredat.staff_courses(db, _sid(db, "Y1"))
    assert d["total_course_count"] == 3
    assert [y["academic_year"] for y in d["years"]] == ["2025-2026", "2024-2025"]


def test_yil_toplami_saati_bilinen_derslerden(db: Session) -> None:
    d = mufredat.staff_courses(db, _sid(db, "Y1"))
    guncel = d["years"][0]
    assert guncel["course_count"] == 2
    assert guncel["total_weekly_hours"] == 7


def test_saati_hic_bilinmeyen_yil_sifir_degil_none(db: Session) -> None:
    """"0 saat ders veriyor" ile "saat bilgisi yok" farklı şeylerdir."""
    d = mufredat.staff_courses(db, _sid(db, "Y1"))
    eski = d["years"][1]
    assert eski["course_count"] == 1
    assert eski["total_weekly_hours"] is None
    assert eski["courses"][0]["weekly_hours"] is None


def test_dersi_olmayan_akademisyen_bos_liste_dondurur(db: Session) -> None:
    """Uydurma ders ataması yapılmaz."""
    d = mufredat.staff_courses(db, _sid(db, "Y2"))
    assert d["total_course_count"] == 0
    assert d["years"] == []


def test_bilinmeyen_personel_bos_sozluk(db: Session) -> None:
    assert mufredat.staff_courses(db, 999999) == {}


def test_ders_sayilari_kapsama_uyar(db: Session) -> None:
    """Rozet sayıları da kapsam dışına çıkmaz."""
    kapsam = resolve(db, department_id=_bid(db, "BILMUH"))
    assert mufredat.staff_course_counts(db, kapsam) == {}
    kapsam_yaz = resolve(db, department_id=_bid(db, "YAZMUH"))
    # Varsayılan CARİ DÖNEM: 2025-2026'daki 2 kayıt.
    assert mufredat.staff_course_counts(db, kapsam_yaz) == {_sid(db, "Y1"): 2}
    assert mufredat.staff_course_counts(
        db, kapsam_yaz, academic_year=mufredat.ALL_YEARS) == {_sid(db, "Y1"): 3}


# ==========================================================================
# 3. Karar destek göstergeleri
# ==========================================================================


def test_ogrenci_personel_oranlari_ikisi_de_doner(db: Session) -> None:
    """Aynı bilgi iki farklı karar sorusunu cevaplar."""
    o = analitik.staffing_overview(db)
    assert o["academic_staff_count"] == 5
    assert o["student_count"] == 93          # 2024:38 + 2025:55
    assert o["students_per_academic_staff"] == 18.6
    assert o["academic_staff_per_student"] == 0.054


def test_ders_yuku_sifir_olan_personel_ortalamaya_girmez(db: Session) -> None:
    """0 saat, "ders vermiyor" demektir; ortalamayı aşağı çekmemeli."""
    o = analitik.staffing_overview(db)
    assert o["staff_with_teaching_load"] == 4     # 12 + 6*3
    assert o["staff_without_teaching_load"] == 1
    assert o["average_teaching_load_hours"] == 7.5


def test_unvan_dagilimi_yuzdeyle_doner(db: Session) -> None:
    satirlar = {r["title"]: r for r in analitik.title_distribution(db)}
    assert satirlar["ARAŞTIRMA GÖREVLİSİ"]["staff_count"] == 3
    assert satirlar["ARAŞTIRMA GÖREVLİSİ"]["share_percent"] == 60.0


def test_ders_yuku_dagilimi_bant_ve_ortanca_verir(db: Session) -> None:
    """Ortalama tek başına dengeli/yığılmış dağılımı ayırt edemez."""
    o = analitik.teaching_load_distribution(db)
    assert o["available"] is True
    assert o["measured_staff_count"] == 4
    assert o["median_hours"] == 6
    assert o["max_hours"] == 12
    assert sum(b["staff_count"] for b in o["bands"]) == 4


def test_ders_yuku_verisi_yoksa_available_false(db: Session) -> None:
    """Veri yokken sıfır dolu kart basılmaz.

    `teaching_load_hours` NOT NULL bir sütun; "ders yükü yok" durumu 0
    ile temsil ediliyor. Servis 0'ı ölçüm saymaz — 0 saatlik bir
    akademisyeni ortalamaya katmak ortalamayı sahte biçimde düşürürdü.
    """
    for p in db.execute(select(AcademicStaff)).scalars():
        p.teaching_load_hours = 0
    db.commit()
    o = analitik.teaching_load_distribution(db)
    assert o["available"] is False
    assert o["bands"] == []


def test_ders_yuku_trendi_yil_bazinda(db: Session) -> None:
    seri = {r["academic_year"]: r for r in analitik.teaching_load_trend(db)}
    assert seri["2025-2026"]["course_count"] == 2
    assert seri["2025-2026"]["total_weekly_hours"] == 7
    assert seri["2025-2026"]["teaching_staff_count"] == 1


def test_yayin_uretkenligi_kisi_basina_siralanir(db: Session) -> None:
    satirlar = analitik.publication_productivity(db)
    assert satirlar[0]["department_name"] == "YAZILIM MÜHENDİSLİĞİ BÖLÜMÜ"
    assert satirlar[0]["publications_per_academic"] == 7.0


def test_yks_trendi_dort_seriyi_birlikte_verir(db: Session) -> None:
    o = analitik.yks_trend(db)
    assert o["available"] is True
    y2025 = [y for y in o["years"] if y["placement_year"] == 2025][0]
    assert y2025["quota"] == 50
    assert y2025["placed_students"] == 55
    assert y2025["occupancy_percent"] == 110.0
    assert y2025["best_base_score"] == 420.75
    # Başarı sırasında KÜÇÜK sayı daha iyidir.
    assert y2025["best_success_rank"] == 70000


def test_mufredat_yuku_kadroyla_karsilastirilir(db: Session) -> None:
    o = analitik.curriculum_load(db)
    assert o["curriculum_course_count"] == 4
    assert o["academic_staff_count"] == 5
    assert o["courses_per_academic_staff"] == 0.8


def test_program_bazinda_kadro_yeterliligi_kapsam_bildirir(db: Session) -> None:
    """Kadro bölüme bağlı; satır bunu açıkça söylemeli."""
    satirlar = {r["program_code"]: r for r in analitik.staffing_by_program(db)}
    assert satirlar["YAZ-PR"]["staff_scope"] == "department"
    assert satirlar["YAZ-PR"]["academic_staff_count"] == 2
    assert satirlar["YAZ-PR"]["student_count"] == 93


def test_veri_olmayan_gosterge_none_doner(db: Session) -> None:
    """Sıfıra bölmek yerine None: "oran sıfır" demek yanlış olurdu."""
    kapsam = resolve(db, department_id=_bid(db, "BILMUH"))
    o = analitik.staffing_overview(db, kapsam)
    assert o["student_count"] is None
    assert o["students_per_academic_staff"] is None


def test_gostergeler_kapsama_uyar(db: Session) -> None:
    kapsam = resolve(db, department_id=_bid(db, "YAZMUH"))
    o = analitik.staffing_overview(db, kapsam)
    assert o["academic_staff_count"] == 2
    assert analitik.curriculum_load(db, kapsam)["curriculum_course_count"] == 3


def test_toplu_gorunum_tum_bolumleri_icerir(db: Session) -> None:
    o = analitik.overview(db)
    assert set(o) == {
        "scope", "requested_period",
        "staffing", "title_distribution", "teaching_load",
        "teaching_load_trend", "publication_productivity",
        "yks_trend", "curriculum_load", "course_concentration",
    }


# ==========================================================================
# 7. Ders eşleştirme (personel ders geçmişi ↔ müfredat)
# ==========================================================================


def test_ders_adi_ile_mufredata_eslesir(db: Session) -> None:
    """Ad birebir aynıysa eşleşir ve müfredat kodu satıra gelir."""
    from app.models import AcademicStaffCourse

    db.add(AcademicStaffCourse(
        academic_staff_id=_sid(db, "Y1"), academic_year="2025-2026",
        course_name="Giriş", language="Türkçe", weekly_hours=3,
        source_dataset="test",
    ))
    db.commit()
    d = mufredat.staff_courses(db, _sid(db, "Y1"))
    giris = [c for y in d["years"] for c in y["courses"]
             if c["course_name"] == "Giriş"][0]
    assert giris["course_code"] == "SE 101"
    assert giris["matched_course_name"] == "Giriş"


def test_ad_icindeki_kod_ile_eslesir(db: Session) -> None:
    """YÖK ders adı kodu metnin içinde taşıyabilir."""
    from app.models import AcademicStaffCourse

    db.add(AcademicStaffCourse(
        academic_staff_id=_sid(db, "Y1"), academic_year="2025-2026",
        course_name="SE 101 Yazılıma Giriş", language="Türkçe",
        weekly_hours=3, source_dataset="test",
    ))
    db.commit()
    d = mufredat.staff_courses(db, _sid(db, "Y1"))
    kayit = [c for y in d["years"] for c in y["courses"]
             if c["course_name"].startswith("SE 101")][0]
    assert kayit["course_code"] == "SE 101"


def test_benzer_ama_farkli_ders_eslestirilmez(db: Session) -> None:
    """Sahte eşleşme üretilmez: "Giriş" ≠ "Girişe Giriş"."""
    from app.models import AcademicStaffCourse

    db.add(AcademicStaffCourse(
        academic_staff_id=_sid(db, "Y1"), academic_year="2025-2026",
        course_name="Girişe Giriş", language="Türkçe", weekly_hours=2,
        source_dataset="test",
    ))
    db.commit()
    d = mufredat.staff_courses(db, _sid(db, "Y1"))
    kayit = [c for y in d["years"] for c in y["courses"]
             if c["course_name"] == "Girişe Giriş"][0]
    assert kayit["curriculum_course_id"] is None


def test_baska_bolumun_dersine_eslesmez(db: Session) -> None:
    """Bölüm bağlamı korunur: "Devreler" BILMUH müfredatındadır."""
    from app.models import AcademicStaffCourse

    db.add(AcademicStaffCourse(
        academic_staff_id=_sid(db, "Y1"), academic_year="2025-2026",
        course_name="Devreler", language="Türkçe", weekly_hours=3,
        source_dataset="test",
    ))
    db.commit()
    d = mufredat.staff_courses(db, _sid(db, "Y1"))
    kayit = [c for y in d["years"] for c in y["courses"]
             if c["course_name"] == "Devreler"][0]
    assert kayit["curriculum_course_id"] is None


def test_turetilen_sayilar_dogru(db: Session) -> None:
    d = mufredat.staff_courses(db, _sid(db, "Y1"))
    assert d["total_course_count"] == 3
    assert d["distinct_course_count"] == 3
    assert d["academic_year_count"] == 2
    assert d["total_weekly_hours"] == 7


def test_tekrarlayan_dersler_listelenir(db: Session) -> None:
    """Aynı ders birden çok yıl veriliyorsa süreklilik göstergesidir."""
    from app.models import AcademicStaffCourse

    db.add(AcademicStaffCourse(
        academic_staff_id=_sid(db, "Y1"), academic_year="2023-2024",
        course_name="Yazılım Mimarisi", language="Türkçe", weekly_hours=3,
        source_dataset="test",
    ))
    db.commit()
    d = mufredat.staff_courses(db, _sid(db, "Y1"))
    tekrar = {r["course_name"]: r["year_count"] for r in d["repeated_courses"]}
    assert tekrar.get("Yazılım Mimarisi") == 2


def test_mufredat_kavrama_orani(db: Session) -> None:
    """Katalogdaki derslerin ne kadarı fiilen okutuluyor?"""
    from app.models import AcademicStaffCourse
    from app.services import course_matching

    db.add(AcademicStaffCourse(
        academic_staff_id=_sid(db, "Y1"), academic_year="2025-2026",
        course_name="Giriş", language="Türkçe", weekly_hours=3,
        source_dataset="test",
    ))
    db.commit()
    k = course_matching.coverage_for_scope(db, resolve(db, department_id=_bid(db, "YAZMUH")))
    assert k["curriculum_course_count"] == 3
    assert k["matched_curriculum_course_count"] == 1
    assert k["coverage_percent"] == 33.33


def test_yogunlasma_ve_yoy_gostergeleri(db: Session) -> None:
    """Yeni karar göstergeleri gerçek veriden üretiliyor."""
    o = analitik.staffing_overview(db)
    assert o["active_teaching_staff_count"] == 4
    assert o["students_per_active_teaching_staff"] == 23.25
    assert o["academics_per_100_students"] == 5.38

    y = analitik.yks_trend(db)
    y2025 = [x for x in y["years"] if x["placement_year"] == 2025][0]
    assert y2025["quota_change_percent"] == 25.0
    assert y2025["placed_change_percent"] == 44.74
    assert y["momentum"]["available"] is True
    assert y["momentum"]["direction"] in ("artıyor", "azalıyor", "yatay")


# ==========================================================================
# 8. Kanonik müfredat katmanı: temizlik, birleştirme, sınıf ataması
# ==========================================================================


def test_kod_normalizasyonu_bosluk_ve_tireyi_yutar() -> None:
    assert normalize_code("ATA 101") == "ATA101"
    assert normalize_code("ata-101") == "ATA101"
    assert normalize_code("Güz 3") is None


def test_donem_basligi_ders_adi_sayilmaz() -> None:
    """"Güz 3" / "SPRING 3" bir ders DEĞİL, dönem başlığı artığıdır."""
    for artik in ("Güz 3", "SPRING 3", "Fall", "Bahar 3", "Yarıyıl II", "3"):
        assert clean_course_name(artik) is None, artik


def test_noktali_dolgu_ve_sayfa_numarasi_temizlenir() -> None:
    assert clean_course_name("Calculus I .................... 19") == "Calculus I"
    assert clean_course_name("Veri Yapıları 42") == "Veri Yapıları"


def test_sinif_ders_kodunun_ilk_basamagindan_gelir() -> None:
    assert class_year_from_code("CENG 101") == 1
    assert class_year_from_code("CENG 402") == 4
    # 9xx kalıba uymuyor: zorlanmaz, "Diğer / Seçmeli" grubuna düşer.
    assert class_year_from_code("SE 999") is None
    assert class_year_from_code(None) is None


def test_ayni_dersin_kopyalari_tek_satirda_birlesir(db: Session) -> None:
    """"SE 101" ile "SE101" aynı derstir; arayüzde bir kez görünür."""
    yaz = _bid(db, "YAZMUH")
    db.add(CurriculumCourse(
        department_id=yaz, course_code="SE101", course_name="GİRİŞ",
        name_is_reliable=True, source_type="booklet", source_dataset="t",
        source_file="f", source_fingerprint="dup",
    ))
    db.commit()
    ozet = rebuild_canonical(db)
    db.commit()
    assert ozet["raw_rows"] == 5
    assert ozet["canonical_rows"] == 4          # kopya birleşti
    kodlar = [r["course_code"] for r in mufredat.list_courses(db)]
    assert len(kodlar) == len(set(kodlar))


def test_birlesmede_okunabilir_ad_tercih_edilir(db: Session) -> None:
    """"GİRİŞ" başlık artığı olabilir; "Giriş" daha iyi adaydır."""
    db.add(CurriculumCourse(
        department_id=_bid(db, "YAZMUH"), course_code="SE101",
        course_name="GİRİŞ", name_is_reliable=True, source_type="booklet",
        source_dataset="t", source_file="f", source_fingerprint="dup2",
    ))
    db.commit()
    rebuild_canonical(db)
    db.commit()
    ad = {r["course_code"]: r["course_name"] for r in mufredat.list_courses(db)}
    assert ad["SE 101"] == "Giriş"


def test_ham_satirlar_asla_silinmez(db: Session) -> None:
    """Kanonikleştirme türetilmiş bir katmandır; kaynak korunur."""
    from sqlalchemy import func

    onceki = db.execute(
        select(func.count()).select_from(CurriculumCourse)).scalar_one()
    rebuild_canonical(db)
    db.commit()
    assert db.execute(
        select(func.count()).select_from(CurriculumCourse)).scalar_one() == onceki


def test_sinif_gruplama_her_bolum_icin_calisir(db: Session) -> None:
    """Gruplama BILMUH'a özel değil; kod kalıbı olan her programda çalışır."""
    gruplar = {g["label"]: g for g in mufredat.courses_by_class_year(
        db, resolve(db, department_id=_bid(db, "YAZMUH")))}
    assert gruplar["1. Sınıf"]["course_count"] == 1
    # Kodsuz "Seçmeli" ve 9xx kodlu satır sınıflandırılamaz.
    assert gruplar["Diğer / Seçmeli"]["course_count"] == 2
    assert sum(g["course_count"] for g in gruplar.values()) == 3


def test_sinif_gruplari_kapsam_disina_tasmaz(db: Session) -> None:
    gruplar = mufredat.courses_by_class_year(
        db, resolve(db, department_id=_bid(db, "BILMUH")))
    adlar = {c["course_name"] for g in gruplar for c in g["courses"]}
    assert adlar == {"Devreler"}


# ==========================================================================
# 9. Cari dönem: personel ekranı güncel faaliyeti gösterir
# ==========================================================================


def test_cari_akademik_yil_veriden_secilir(db: Session) -> None:
    assert mufredat.latest_course_year(db) == "2025-2026"


def test_personel_karti_once_cari_donemi_verir(db: Session) -> None:
    d = mufredat.staff_courses(db, _sid(db, "Y1"))
    assert d["current_academic_year"] == "2025-2026"
    assert d["teaches_in_current_year"] is True
    assert d["current_course_count"] == 2
    assert d["current_weekly_hours"] == 7
    # Geçmiş ikincil kalır ama kaybolmaz.
    assert [y["academic_year"] for y in d["history_years"]] == ["2024-2025"]
    assert d["history_year_count"] == 1
    assert d["total_course_count"] == 3


def test_ders_sayaci_varsayilan_olarak_cari_yil(db: Session) -> None:
    kapsam = resolve(db, department_id=_bid(db, "YAZMUH"))
    assert mufredat.staff_course_counts(db, kapsam) == {_sid(db, "Y1"): 2}
    assert mufredat.staff_course_counts(db, kapsam, academic_year="all") == {
        _sid(db, "Y1"): 3}


def test_cari_donem_ozeti_yalnizca_aktif_ogretenleri_sayar(db: Session) -> None:
    o = mufredat.current_teaching_summary(
        db, resolve(db, department_id=_bid(db, "YAZMUH")))
    assert o["current_academic_year"] == "2025-2026"
    assert o["teaching_staff_count"] == 1     # Y2 ders vermiyor
    assert o["academic_staff_count"] == 2
    assert o["course_record_count"] == 2
