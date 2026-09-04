"""PANO TUTARLILIĞI — ekranda iki farklı sayı belirmesini engelleyen testler.

Bu dosya, canlı arayüzde gözlenen üç somut hatanın nöbetçisidir:

  1. Aynı fakülte panosunda "Toplam Öğrenci" 2.213, kenar panelde
     "Öğrenci sayısı" 1.689 yazıyordu. Sebep: iki bileşen İKİ FARKLI
     MODÜLDEN besleniyordu — biri ÖSYM türevi `student_count`, diğeri
     `student-analytics` modülünün `active_student_count` alanı. İkinci
     alan, veritabanında öğrenci satırı varsa onları sayar; örnek veri
     yüklü bir kurulumda ayrışma kaçınılmazdır.

  2. Dönem seçici açılışta 2026-2027'yi seçiyor, gerçek verisi
     2025-2026'da biten bütün paneller boş görünüyordu. Sebep: seçici
     örnek veri modülünün tablosundan besleniyordu.

  3. Müfredat ders sayısı, kaydı olmayan kapsamda "0" basıyordu; "sıfır
     ders" ile "veri aktarılmadı" ekranda ayırt edilemiyordu.

Testler bu hataları YENİDEN ÜRETİR (örnek öğrenci satırı + ileri tarihli
dönem ekleyerek) ve düzeltmenin ayakta kaldığını doğrular.
"""

from datetime import date, datetime
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
    Department,
    Faculty,
    ProgramEnrollmentSnapshot,
    Student,
    UniversityStudentHeadcount,
    YksPlacementRecord,
)
from app.models.university_headcount import HOME_UNIVERSITY
from app.services import (
    data_period_service,
    decision_analytics_service,
    staff_scope,
    student_count,
)
from app.services.scope import resolve
from app.services.unit_types import FACULTY


@pytest.fixture()
def db() -> Iterator[Session]:
    motor = create_engine(
        "sqlite://", future=True,
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(motor)
    s = sessionmaker(bind=motor, future=True)()

    # Gerçek aktarıcı her hiyerarşi satırına sağlayıcı damgası basar;
    # fikstür de basar, yoksa sağlayıcı denetimi bunları "kaynaksız"
    # sayar (ve haklı olarak "mixed" moduna geçer).
    DAMGA = "Kaynak: YÖK Akademik toplayıcısı"
    muh = Faculty(name="MÜHENDİSLİK VE MİMARLIK FAKÜLTESİ", code="MUH",
                  unit_type=FACULTY, description=DAMGA, is_active=True)
    huk = Faculty(name="HUKUK FAKÜLTESİ", code="HUK",
                  unit_type=FACULTY, description=DAMGA, is_active=True)
    s.add_all([muh, huk])
    s.flush()

    bil = Department(name="BİLGİSAYAR MÜHENDİSLİĞİ", code="BIL",
                     faculty_id=muh.id, is_active=True)
    elk = Department(name="ELEKTRİK-ELEKTRONİK", code="ELK",
                     faculty_id=muh.id, is_active=True)
    hukb = Department(name="HUKUK", code="HUKB", faculty_id=huk.id, is_active=True)
    s.add_all([bil, elk, hukb])
    s.flush()

    programlar = {}
    for kod, bolum in (("BIL-PR", bil), ("ELK-PR", elk), ("HUK-PR", hukb)):
        p = AcademicProgram(name=kod, code=kod, department_id=bolum.id,
                            degree_level="Lisans", is_active=True)
        s.add(p)
        programlar[kod] = p
    s.flush()

    # ÖSYM yerleştirmeleri — yetkili öğrenci sayısının kaynağı.
    for kod, yerlesen in (("BIL-PR", 100), ("ELK-PR", 60), ("HUK-PR", 40)):
        for yil in (2024, 2025):
            s.add(YksPlacementRecord(
                academic_program_id=programlar[kod].id, placement_year=yil,
                academic_year=f"{yil}-{yil + 1}", placement_program_name=kod,
                score_type="SAY", scholarship_type="Burslu",
                quota=yerlesen + 20, placed_students=yerlesen,
                source_dataset="t", source_file="f"))

    # Kadro + ders kaydı (dönem çözücüsünün çekirdek kümelerinden biri).
    for i, bolum in enumerate((bil, elk, hukb)):
        p = AcademicStaff(staff_number=f"AK{i}", first_name="Ad",
                          last_name=f"Soyad{i}", title="PROFESÖR",
                          department_id=bolum.id, academic_year="2025-2026",
                          is_active=True)
        s.add(p)
        s.flush()
        s.add(AcademicStaffCourse(
            academic_staff_id=p.id, academic_year="2025-2026",
            course_name=f"Ders {i}", weekly_hours=3,
            source_dataset="t", source_url="f"))

    # YÖK kayıtlı öğrenci sayısı (üniversite düzeyi).
    for yil, sayi in (("2024-2025", 380), ("2025-2026", 420)):
        s.add(UniversityStudentHeadcount(
            university_name=HOME_UNIVERSITY, academic_year=yil,
            university_type="VAKIF", city="ANKARA", education_mode="BİRİNCİ Ö.",
            degree_level="LISANS", gender="E", student_count=sayi,
            source_dataset="t", source_file="f"))
    s.commit()
    try:
        yield s
    finally:
        s.close()
        motor.dispose()


def _muh(db: Session) -> int:
    return db.execute(select(Faculty.id).where(Faculty.code == "MUH")).scalar_one()


# ==========================================================================
# 1. TEK YETKİLİ ÖĞRENCİ SAYISI
# ==========================================================================


def test_fakulte_ogrenci_sayisi_tek_kuraldan_gelir(db: Session) -> None:
    """Kapsamın öğrenci sayısı, ÖSYM türevi kuraldan gelir ve tektir."""
    kapsam = resolve(db, faculty_id=_muh(db))
    kadro = decision_analytics_service.staffing_overview(db, kapsam)
    govde = decision_analytics_service.student_body_overview(db, kapsam)

    assert kadro["student_count"] == 320          # (100+100) + (60+60), iki kohort
    assert govde["student_count"] == kadro["student_count"]
    assert kadro["student_count_source"] == "yks_turevi"


def test_ornek_ogrenci_satirlari_yetkili_sayiyi_DEGISTIRMEZ(db: Session) -> None:
    """Örnek/demo öğrenci satırları eklendiğinde sayı KAYMAZ.

    Canlı hatanın tam mekanizması: veritabanına örnek öğrenci satırları
    girildiğinde `student-analytics` modülünün `active_student_count`
    değeri onları sayar. Kenar panel o alanı okuduğu için KPI ile
    ayrışıyordu. Yetkili kural yalnızca ÖSYM kayıtlarına bakar; bu test
    onun demo satırlarından etkilenmediğini sabitler.
    """
    kapsam = resolve(db, faculty_id=_muh(db))
    onceki = decision_analytics_service.staffing_overview(db, kapsam)["student_count"]

    bil = db.execute(
        select(AcademicProgram).where(AcademicProgram.code == "BIL-PR")
    ).scalar_one()
    for i in range(37):
        db.add(Student(
            student_number=f"DEMO{i:04d}", first_name="Demo", last_name=f"O{i}",
            gender="K", nationality="TR", is_international=False,
            scholarship_rate_percent=0, enrollment_year=2024,
            current_status="active", preparatory_school=False,
            academic_program_id=bil.id, is_active=True))
    db.flush()

    sonraki = decision_analytics_service.staffing_overview(db, kapsam)["student_count"]
    assert sonraki == onceki == 320


def test_universite_ile_fakulte_sayilari_karismaz(db: Session) -> None:
    """Üniversitede YÖK sayısı, fakültede ÖSYM türevi — sızıntı yok."""
    uni = decision_analytics_service.staffing_overview(db, None)
    fak = decision_analytics_service.staffing_overview(db, resolve(db, faculty_id=_muh(db)))

    assert (uni["student_count"], uni["student_count_source"]) == (420, "yok_kayitli")
    assert (fak["student_count"], fak["student_count_source"]) == (320, "yks_turevi")
    # Üniversite sayısı fakülteye YAZILMAZ.
    assert fak["student_count"] != uni["student_count"]


def test_kardes_fakulte_sizmaz(db: Session) -> None:
    huk = db.execute(select(Faculty.id).where(Faculty.code == "HUK")).scalar_one()
    assert decision_analytics_service.staffing_overview(
        db, resolve(db, faculty_id=huk))["student_count"] == 80


# ==========================================================================
# 2. DÖNEM ÇÖZÜCÜSÜ
# ==========================================================================


def test_ileri_tarihli_ornek_donem_varsayilani_KAYDIRMAZ(db: Session) -> None:
    """Örnek veri 2026-2027 eklese bile varsayılan dönem 2025-2026 kalır.

    Eski seçici `program_enrollment_snapshots` tablosunu okuyordu; o
    tabloya ileri tarihli bir satır düştüğü anda arayüz gerçek verisi
    olmayan bir yılı seçiyordu.
    """
    assert data_period_service.latest_operating_period(db) == "2025-2026"

    prog = db.execute(select(AcademicProgram)).scalars().all()
    for p in prog:
        db.add(ProgramEnrollmentSnapshot(
            academic_program_id=p.id, academic_year="2026-2027",
            quota=50, enrolled_student_count=0, graduated_student_count=0,
            dropped_out_student_count=0, non_renewed_student_count=0))
    db.flush()

    ozet = data_period_service.period_summary(db)
    assert ozet["default_period"] == "2025-2026"
    assert "2026-2027" not in ozet["selectable_periods"]


def test_secilebilir_donemler_akademisyen_gecmisiyle_sismez(db: Session) -> None:
    """1992 gibi tek kümede kalan tarihî yıllar seçiciye düşmez."""
    p = db.execute(select(AcademicStaff)).scalars().first()
    db.add(AcademicStaffCourse(
        academic_staff_id=p.id, academic_year="1992-1993",
        course_name="Eski Ders", weekly_hours=3,
        source_dataset="t", source_url="f"))
    db.flush()

    ozet = data_period_service.period_summary(db)
    assert "1992-1993" in ozet["dataset_years"]["teaching_load"]
    assert "1992-1993" not in ozet["selectable_periods"]


def test_donem_kapsami_hangi_kumede_veri_var_soyler(db: Session) -> None:
    ozet = data_period_service.period_summary(db)
    kapsam = ozet["coverage_by_period"]["2025-2026"]
    assert "yks_placements" in kapsam and "enrolled_headcount" in kapsam


def test_gecmis_donem_panelleri_gelecek_yila_dusmez(db: Session) -> None:
    """2024 seçimi hiçbir panelde 2025 etiketi/verisi üretmez."""
    kapsam = resolve(db, faculty_id=_muh(db))

    govde = decision_analytics_service.student_body_overview(
        db, kapsam, "2024-2025")
    assert govde["requested_period"] == "2024-2025"
    assert govde["student_count"] == 160
    assert govde["latest_placement_year"] == 2024
    assert max(y["placement_year"] for y in govde["cohorts"]) == 2024

    # Kadro ve ders yükü yalnız 2025'te var; 2024 etiketi altında
    # 2025 değerlerine sessizce düşülmemeli.
    kadro = decision_analytics_service.staffing_overview(
        db, kapsam, "2024-2025")
    assert kadro["available"] is False
    assert kadro["academic_staff_count"] is None
    assert decision_analytics_service.teaching_load_trend(
        db, kapsam, "2024-2025") == []
    assert decision_analytics_service.course_concentration(
        db, kapsam, "2024-2025")["available"] is False
    burs = decision_analytics_service.scholarship_breakdown(
        db, kapsam, "2024-2025")
    assert burs["years"] == [2024]
    assert all(max(t["series"], key=lambda x: x["placement_year"])
               ["placement_year"] == 2024 for t in burs["types"])


def test_universite_kayitli_sayisi_secili_doneme_uyar(db: Session) -> None:
    eski = decision_analytics_service.student_body_overview(
        db, resolve(db), "2024-2025")
    yeni = decision_analytics_service.student_body_overview(
        db, resolve(db), "2025-2026")
    assert eski["student_count"] == 380
    assert yeni["student_count"] == 420


# ==========================================================================
# 3. MÜFREDAT: SIFIR MI, ÖLÇÜLMEDİ Mİ
# ==========================================================================


def test_mufredat_kaydi_yoksa_sifir_DEGIL_none(db: Session) -> None:
    """Kaydı olmayan kapsamda 0 basılmaz; ölçülmediği söylenir."""
    yuk = decision_analytics_service.curriculum_load(
        db, resolve(db, faculty_id=_muh(db)))
    assert yuk["curriculum_course_count"] is None
    assert yuk["curriculum_measured"] is False
    assert yuk["available"] is False


# ==========================================================================
# 4. KADRO ÇİFT SAYIMI — canlıda gözlendi
# ==========================================================================


def test_cok_yilli_kadro_anlik_goruntusu_ciftlemez(db: Session) -> None:
    """Aynı kişinin İKİNCİ yıl satırı kadroyu ve yayını ikiye katlamaz.

    CANLI KANIT
    -----------
    `academic_staff` kişi başına yıla göre satır tutar. Süzgeç yokken:

        satır sayısı 360 · tekil kişi 180
        fakülte "Akademik Personel"  216  (gerçek 108)
        fakülte "Yayın Sayısı"     2.062  (gerçek 1.031)
        üniversite yayın toplamı   3.142  (gerçek 1.571)

    Kurumun gerçek verisinde şu an tek yıl olduğu için hata görünmüyordu;
    ikinci yıl aktarıldığı anda bütün kadro göstergeleri sessizce
    ikiye katlanacaktı. Bir fakültenin üniversite toplamını AŞMASI da
    bu mekanizmayla mümkün hâle geliyordu.
    """
    kapsam = resolve(db, faculty_id=_muh(db))
    onceki_fak = decision_analytics_service.staffing_overview(
        db, kapsam)["academic_staff_count"]
    onceki_uni = decision_analytics_service.staffing_overview(
        db, None)["academic_staff_count"]
    assert (onceki_fak, onceki_uni) == (2, 3)

    # AYNI kişilerin bir sonraki yıl anlık görüntüsü eklenir.
    for p in list(db.execute(select(AcademicStaff)).scalars().all()):
        db.add(AcademicStaff(
            staff_number=p.staff_number + "-2627", first_name=p.first_name,
            last_name=p.last_name, title=p.title,
            department_id=p.department_id, academic_year="2026-2027",
            publication_count=p.publication_count, is_active=True))
    db.flush()

    assert staff_scope.latest_staff_period(db) == "2026-2027"
    sonraki_fak = decision_analytics_service.staffing_overview(
        db, kapsam)["academic_staff_count"]
    sonraki_uni = decision_analytics_service.staffing_overview(
        db, None)["academic_staff_count"]
    assert (sonraki_fak, sonraki_uni) == (2, 3), "kadro ikiye katlandı"


def test_fakulte_kadrosu_universiteyi_ASAMAZ(db: Session) -> None:
    """Hiçbir fakülte göstergesi üst kurumun toplamını geçemez."""
    uni = decision_analytics_service.staffing_overview(db, None)
    for f in db.execute(select(Faculty)).scalars():
        fak = decision_analytics_service.staffing_overview(
            db, resolve(db, faculty_id=f.id))
        assert fak["academic_staff_count"] <= uni["academic_staff_count"]
        assert (fak["total_publications"] or 0) <= (uni["total_publications"] or 0)


# ==========================================================================
# 5. KAYNAK ETİKETİ GERÇEĞİ SÖYLER
# ==========================================================================


def test_yerlestirme_kaydi_yokken_kaynak_OSYM_DEMEZ(db: Session) -> None:
    """ÖSYM kaydı yoksa sayı "ÖSYM türevi" olarak etiketlenmez.

    Canlı çelişki: dağılım paneli "ÖSYM yerleştirmelerinden türetilen"
    derken hemen yanındaki trend paneli "Bu kapsamda yerleştirme kaydı
    yok" diyordu. Sayı öğrenci kayıtlarından geliyordu ama ÖSYM
    etiketiyle sunuluyordu.
    """
    # Bütün yerleştirme kayıtları silinir, yerine öğrenci satırı konur.
    for r in db.execute(select(YksPlacementRecord)).scalars().all():
        db.delete(r)
    bil = db.execute(
        select(AcademicProgram).where(AcademicProgram.code == "BIL-PR")
    ).scalar_one()
    for i in range(12):
        db.add(Student(
            student_number=f"S{i:04d}", first_name="Ad", last_name=f"Soyad{i}",
            gender="K", nationality="TR", is_international=False,
            scholarship_rate_percent=0, enrollment_year=2024,
            current_status="active", preparatory_school=False,
            academic_program_id=bil.id, is_active=True))
    db.flush()

    sayi, kaynak = student_count.total_for_scope_detailed(
        db, resolve(db, faculty_id=_muh(db)))
    assert sayi == 12
    assert kaynak == "ogrenci_kaydi", "kaynak yanlış etiketlendi"


# ==========================================================================
# 6. VERİ KAYNAĞI DURUMU
# ==========================================================================


def test_gercek_veri_varken_mod_real(db: Session) -> None:
    assert data_period_service.data_source_state(db)["mode"] == "real"


def test_cekirdek_bosken_ornek_veri_UYARI_verir(db: Session) -> None:
    """Çekirdek gerçek veri yokken pano bunu SÖYLEMEK zorunda.

    Canlıda pano tamamen örnek veritabanı üzerinde çalışıyor ve uydurma
    sayıları kurumsal gerçekmiş gibi gösteriyordu. Bir karar destek
    sisteminde bu, boş ekrandan daha tehlikelidir.
    """
    for M in (YksPlacementRecord, UniversityStudentHeadcount, AcademicStaffCourse):
        for r in db.execute(select(M)).scalars().all():
            db.delete(r)
    db.flush()

    durum = data_period_service.data_source_state(db)
    assert durum["mode"] == "demo"
    assert durum["is_trustworthy"] is False
    assert "ÖRNEK" in durum["message"]


# ==========================================================================
# 7. HİYERARŞİ SAĞLAYICISI — aynı fakültenin iki kez görünmesi
# ==========================================================================


def test_ornek_hiyerarsi_artigi_SAGLAYICIYLA_ayirt_edilir(db: Session) -> None:
    """Damgasız hiyerarşi satırı tespit edilir; gerçek olan korunur.

    CANLI KANIT
    -----------
    `import_all_real_data.py` --purge olmadan çalıştırıldığında eski örnek
    hiyerarşi yerinde kalmıştı:

        id=4 MUHMIM  MÜHENDİSLİK VE MİMARLIK FAKÜLTESİ  → 803  (gerçek)
        id=8 FEA     Faculty of Engineering and Arch.   → 2213 (örnek)

    Pano ikisini birden topluyor, dağılım 7.348 çıkıyordu (üniversite
    3.626). Ayırt etme AD BENZERLİĞİYLE DEĞİL, sağlayıcı damgasıyla ve
    ebeveyn zinciriyle yapılır.
    """
    from app.services import hierarchy_provenance

    # Gerçek (damgalı) fakülte + altında damgasız ama MEŞRU idari bölüm.
    gercek = Faculty(name="GERÇEK FAKÜLTE", code="GER", unit_type=FACULTY,
                     description="Kaynak: YÖK Akademik toplayıcısı",
                     is_active=True)
    db.add(gercek)
    db.flush()
    db.add(Department(name="REKTÖRLÜK", code="REK", faculty_id=gercek.id,
                      description="İdari birim — toplayıcıda bölüm bilgisi yok",
                      is_active=True))
    # Örnek veri artığı: damgasız fakülte + altında damgasız bölüm.
    ornek = Faculty(name="Faculty of Engineering and Architecture", code="FEA",
                    unit_type=FACULTY,
                    description="Mühendislik ve mimarlık alanındaki bölümler.",
                    is_active=True)
    db.add(ornek)
    db.flush()
    db.add(Department(name="Software Engineering", code="SWE",
                      faculty_id=ornek.id, description="Yazılım mühendisliği bölümü.",
                      is_active=True))
    db.flush()

    rapor = hierarchy_provenance.provenance_report(db)
    kaynaksiz_fak = {r["code"] for r in rapor["unmarked_units"]["faculties"]}
    kaynaksiz_bol = {r["code"] for r in rapor["unmarked_units"]["departments"]}

    assert "FEA" in kaynaksiz_fak, "örnek fakülte tespit edilmedi"
    assert "GER" not in kaynaksiz_fak, "gerçek fakülte yanlışlıkla işaretlendi"
    assert "SWE" in kaynaksiz_bol
    # EBEVEYN ZİNCİRİ: damgasız ama kurumsal fakültenin altındaki idari
    # bölüm KORUNUR — yalnızca damgaya bakan kural bunu siliyordu.
    assert "REK" not in kaynaksiz_bol, "meşru idari bölüm yanlış işaretlendi"
    assert rapor["clean"] is False


def test_alt_birim_dagilimi_YOK_kayitli_ETIKETI_KULLANMAZ(db: Session) -> None:
    """Dağılım paneli üst kapsamın yetkili ölçümünü kendine mal etmez.

    Üniversite kapsamında yetkili sayı YÖK kayıtlı öğrencidir; ama bu
    panelin SATIRLARI fakültelerdir ve YÖK sayısının fakülte kırılımı
    yoktur. Canlıda panel "Kaynak: YÖK kayıtlı" yazarken ÖSYM türevi
    değerleri listeliyordu.
    """
    from app.services import peer_comparison_service

    o = peer_comparison_service.child_breakdown(db, None)
    assert o["student_count_source"] != "yok_kayitli"
    assert o["student_count_source"] == "yks_turevi"
    # Toplamı kurumun yetkili sayısıyla kıyaslamak GEÇERSİZDİR.
    assert o["comparable_to_scope_total"] is False


def test_takma_ad_gercek_birimin_adini_TAKLIT_EDEMEZ(db: Session) -> None:
    """`display_names.json` var olan bir kurumsal adı üretemez.

    Demo kodu FEA, sözlükte "Mühendislik ve Mimarlık Fakültesi" olarak
    tanımlıydı; gerçek MUHMIM fakültesiyle ekranda aynı isimle
    görünüyordu. Sözlük artık çakışan takma adı uygulamaz.
    """
    from fastapi.testclient import TestClient

    import main
    from app.database import get_db

    db.add(Faculty(name="Faculty of Engineering and Architecture", code="FEA",
                   unit_type=FACULTY, description="Örnek.", is_active=True))
    db.flush()

    main.app.dependency_overrides[get_db] = lambda: db
    try:
        yanit = TestClient(main.app).get("/api/reference/display-names").json()
    finally:
        main.app.dependency_overrides.pop(get_db, None)

    # Gerçek fakülte "MÜHENDİSLİK VE MİMARLIK FAKÜLTESİ" mevcut olduğu
    # için FEA takma adı UYGULANMAZ.
    assert "FEA" not in yanit["faculties"]
