"""KARŞILAŞTIRMA KÜMESİ ve YÖNETİM GÖSTERGELERİ.

Bu paketin tek bir iddiası var: **karşılaştırma kümesini hiyerarşi
belirler ve küme asla ebeveynin dışına taşmaz.**

  üniversite → dış kıyas kurumları
  fakülte    → üniversitedeki diğer AKADEMİK fakülteler (Rektörlük yok)
  bölüm      → AYNI fakültedeki bölümler
  program    → AYNI bölümdeki programlar

Ayrıca yönetim panosunun ve öğrenci analitiğinin gerçekten ölçülmüş
göstergelerden oluştuğu, ölçülmemiş olanların 0 değil `None` döndüğü
doğrulanır.
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
    BenchmarkInstitution,
    CurriculumCourse,
    Department,
    Faculty,
    YksPlacementRecord,
)
from app.services import decision_analytics_service as analitik
from app.services import peer_comparison_service as kiyas
from app.services.curriculum_canonical import rebuild_canonical
from app.services.scope import resolve
from app.services.unit_types import ADMINISTRATIVE, FACULTY, VOCATIONAL_SCHOOL

YIL = "2025-2026"


@pytest.fixture()
def db() -> Iterator[Session]:
    """İki akademik fakülte + bir MYO + REKTÖRLÜK.

    Mühendislik'te iki bölüm, birinde iki program: böylece dört
    kapsam seviyesinin dördü de gerçek kardeşle test edilebilir.
    """
    motor = create_engine(
        "sqlite://", future=True,
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(motor)
    s = sessionmaker(bind=motor, future=True)()

    muh = Faculty(name="MÜHENDİSLİK FAKÜLTESİ", code="MUH",
                  unit_type=FACULTY, is_active=True)
    fen = Faculty(name="FEN FAKÜLTESİ", code="FEN",
                  unit_type=FACULTY, is_active=True)
    myo = Faculty(name="MESLEK YÜKSEKOKULU", code="MYO",
                  unit_type=VOCATIONAL_SCHOOL, is_active=True)
    rek = Faculty(name="REKTÖRLÜK", code="REK",
                  unit_type=ADMINISTRATIVE, is_active=True)
    s.add_all([muh, fen, myo, rek])
    s.flush()

    yaz = Department(name="YAZILIM MÜHENDİSLİĞİ BÖLÜMÜ", code="YAZMUH",
                     faculty_id=muh.id, is_active=True)
    bil = Department(name="BİLGİSAYAR MÜHENDİSLİĞİ BÖLÜMÜ", code="BILMUH",
                     faculty_id=muh.id, is_active=True)
    mat = Department(name="MATEMATİK BÖLÜMÜ", code="MAT",
                     faculty_id=fen.id, is_active=True)
    myo_b = Department(name="BİLGİSAYAR PROGRAMCILIĞI", code="BILPROG",
                       faculty_id=myo.id, is_active=True)
    idari = Department(name="PERSONEL DAİRESİ", code="PDB",
                       faculty_id=rek.id, is_active=True)
    s.add_all([yaz, bil, mat, myo_b, idari])
    s.flush()

    # YAZMUH'ta İKİ program → program seviyesinde gerçek kardeş var.
    yaz_tr = AcademicProgram(name="Yazılım Müh.", code="YAZ-TR",
                             department_id=yaz.id, degree_level="Lisans",
                             is_active=True)
    yaz_en = AcademicProgram(name="Yazılım Müh. (İng.)", code="YAZ-EN",
                             department_id=yaz.id, degree_level="Lisans",
                             is_active=True)
    bil_pr = AcademicProgram(name="Bilgisayar Müh.", code="BIL-PR",
                             department_id=bil.id, degree_level="Lisans",
                             is_active=True)
    mat_pr = AcademicProgram(name="Matematik", code="MAT-PR",
                             department_id=mat.id, degree_level="Lisans",
                             is_active=True)
    myo_pr = AcademicProgram(name="Bilgisayar Prog.", code="MYO-PR",
                             department_id=myo_b.id, degree_level="Önlisans",
                             is_active=True)
    s.add_all([yaz_tr, yaz_en, bil_pr, mat_pr, myo_pr])
    s.flush()

    # --- kadro: YAZ=3 (2'si ders yüklü), BIL=2, MAT=1, MYO=1, idari=4 ---
    def personel(no, bolum, unvan, yuk, yayin=0):
        return AcademicStaff(staff_number=no, first_name="A", last_name=no,
                             title=unvan, department_id=bolum, academic_year=YIL,
                             is_active=True, publication_count=yayin,
                             teaching_load_hours=yuk)

    s.add_all([
        personel("Y1", yaz.id, "PROFESÖR", 12, 8),
        personel("Y2", yaz.id, "DOÇENT", 24, 4),
        personel("Y3", yaz.id, "ARAŞTIRMA GÖREVLİSİ", 0, 0),
        personel("B1", bil.id, "PROFESÖR", 6, 2),
        personel("B2", bil.id, "DOKTOR ÖĞRETİM ÜYESİ", 8, 1),
        personel("M1", mat.id, "PROFESÖR", 10, 5),
        personel("V1", myo_b.id, "ÖĞRETİM GÖREVLİSİ", 15, 0),
    ] + [personel(f"I{i}", idari.id, "MEMUR", 0) for i in range(4)])
    s.flush()

    y1 = s.execute(select(AcademicStaff).where(
        AcademicStaff.staff_number == "Y1")).scalar_one()
    s.add_all([
        AcademicStaffCourse(academic_staff_id=y1.id, academic_year=YIL,
                            course_name="Yazılım Mimarisi", weekly_hours=3,
                            source_dataset="t"),
        AcademicStaffCourse(academic_staff_id=y1.id, academic_year="2024-2025",
                            course_name="Algoritmalar", weekly_hours=3,
                            source_dataset="t"),
    ])

    # --- müfredat: YAZ=2, BIL=1, MAT=1 ---
    def ders(bolum, kod, ad, iz):
        return CurriculumCourse(department_id=bolum, course_code=kod,
                                course_name=ad, name_is_reliable=True,
                                source_type="web", source_dataset="t",
                                source_file="f", source_fingerprint=iz)

    s.add_all([
        ders(yaz.id, "SE 101", "Giriş", "a"),
        ders(yaz.id, "SE 201", "Veri Yapıları", "b"),
        ders(bil.id, "CE 101", "Devreler", "c"),
        ders(mat.id, "MT 101", "Analiz", "d"),
    ])

    # --- YKS: dört yıl, düşen alım ---
    for program, taban in ((yaz_tr, 40), (yaz_en, 20), (bil_pr, 30), (mat_pr, 25)):
        for i, yil in enumerate((2022, 2023, 2024, 2025)):
            s.add(YksPlacementRecord(
                academic_program_id=program.id, placement_year=yil,
                academic_year=f"{yil}-{yil + 1}",
                placement_program_name=f"{program.code} {yil}",
                score_type="SAY", scholarship_type="Burslu",
                quota=taban, placed_students=taban - i * 5,
                base_score=400 + i, success_rank=90000 - i * 1000,
                source_dataset="t", source_file="f",
            ))

    s.add_all([
        BenchmarkInstitution(name="A Üniversitesi", country="Türkiye",
                             institution_type="similar", is_active=True),
        BenchmarkInstitution(name="B Üniversitesi", country="Türkiye",
                             institution_type="competitor", is_competitor=True,
                             is_active=True),
    ])
    s.flush()
    rebuild_canonical(s)
    s.commit()
    try:
        yield s
    finally:
        s.close()
        motor.dispose()


def _fid(db: Session, kod: str) -> int:
    return db.execute(select(Faculty.id).where(Faculty.code == kod)).scalar_one()


def _bid(db: Session, kod: str) -> int:
    return db.execute(
        select(Department.id).where(Department.code == kod)).scalar_one()


def _pid(db: Session, kod: str) -> int:
    return db.execute(
        select(AcademicProgram.id).where(AcademicProgram.code == kod)
    ).scalar_one()


# ==========================================================================
# 1. Karşılaştırma kümesi hiyerarşiyi izler
# ==========================================================================


def test_universite_dis_kurumlarla_karsilastirilir(db: Session) -> None:
    o = kiyas.peer_comparison(db, resolve(db))
    assert o["basis"] == "external_institutions"
    assert {k["name"] for k in o["external_institutions"]} == {
        "A Üniversitesi", "B Üniversitesi"}
    # Üniversite seviyesinde İÇ birim karşılaştırması yapılmaz.
    assert o["peers"] == []


def test_fakulte_kardes_fakultelerle_karsilastirilir(db: Session) -> None:
    o = kiyas.peer_comparison(db, resolve(db, faculty_id=_fid(db, "MUH")))
    assert o["basis"] == "sibling_faculties"
    adlar = {r["name"] for r in o["peers"]}
    assert adlar == {"MÜHENDİSLİK FAKÜLTESİ", "FEN FAKÜLTESİ",
                     "MESLEK YÜKSEKOKULU"}
    # DIŞ kurumlar bu seviyede GÖSTERİLMEZ.
    assert o["external_institutions"] == []


def test_rektorluk_fakulte_karsilastirmasina_girmez(db: Session) -> None:
    """İdari birim akademik bir kardeş değildir; kadrosu da karışmamalı."""
    o = kiyas.peer_comparison(db, resolve(db, faculty_id=_fid(db, "MUH")))
    assert "REKTÖRLÜK" not in {r["name"] for r in o["peers"]}


def test_bolum_yalnizca_kendi_fakultesindeki_bolumlerle(db: Session) -> None:
    o = kiyas.peer_comparison(db, resolve(db, department_id=_bid(db, "BILMUH")))
    assert o["basis"] == "sibling_departments"
    adlar = {r["name"] for r in o["peers"]}
    assert adlar == {"BİLGİSAYAR MÜHENDİSLİĞİ BÖLÜMÜ",
                     "YAZILIM MÜHENDİSLİĞİ BÖLÜMÜ"}
    # Başka fakültenin bölümü ASLA girmez.
    assert "MATEMATİK BÖLÜMÜ" not in adlar
    assert o["parent"]["name"] == "MÜHENDİSLİK FAKÜLTESİ"
    assert o["external_institutions"] == []


def test_program_yalnizca_kendi_bolumundeki_programlarla(db: Session) -> None:
    o = kiyas.peer_comparison(db, resolve(db,
                                          academic_program_id=_pid(db, "YAZ-TR")))
    assert o["basis"] == "sibling_programs"
    kodlar = {r["code"] for r in o["peers"]}
    assert kodlar == {"YAZ-TR", "YAZ-EN"}
    assert "BIL-PR" not in kodlar
    assert o["parent"]["name"] == "YAZILIM MÜHENDİSLİĞİ BÖLÜMÜ"


def test_secili_birim_kumede_isaretlenir(db: Session) -> None:
    o = kiyas.peer_comparison(db, resolve(db, department_id=_bid(db, "BILMUH")))
    secili = [r for r in o["peers"] if r["is_selected"]]
    assert len(secili) == 1
    assert secili[0]["name"] == "BİLGİSAYAR MÜHENDİSLİĞİ BÖLÜMÜ"


def test_kardessiz_birimde_karsilastirma_yok(db: Session) -> None:
    """Tek satırlık "karşılaştırma" karar üretmez; available False."""
    o = kiyas.peer_comparison(db, resolve(db, department_id=_bid(db, "MAT")))
    assert o["peer_count"] == 1
    assert o["sibling_count"] == 0
    assert o["available"] is False


def test_siralama_kume_icinde_hesaplanir(db: Session) -> None:
    o = kiyas.peer_comparison(db, resolve(db, department_id=_bid(db, "YAZMUH")))
    # YAZMUH: 2 program × 4 kohort; BILMUH: 1 program. Öğrencide 1.
    assert o["ranks"]["student_count"] == 1
    # Öğrenci/akademisyen oranında KÜÇÜK iyidir; sıralama ona göre.
    assert o["ranks"]["students_per_academic_staff"] in (1, 2)


# ==========================================================================
# 2. Alt birim kırılımı — pano seviyeye göre değişir
# ==========================================================================


def test_universitede_kirilim_fakultelerdir(db: Session) -> None:
    k = kiyas.child_breakdown(db, resolve(db))
    assert k["child_kind"] == "faculty"
    assert {r["name"] for r in k["rows"]} == {
        "MÜHENDİSLİK FAKÜLTESİ", "FEN FAKÜLTESİ", "MESLEK YÜKSEKOKULU"}


def test_fakultede_kirilim_bolumlerdir(db: Session) -> None:
    k = kiyas.child_breakdown(db, resolve(db, faculty_id=_fid(db, "MUH")))
    assert k["child_kind"] == "department"
    assert {r["name"] for r in k["rows"]} == {
        "YAZILIM MÜHENDİSLİĞİ BÖLÜMÜ", "BİLGİSAYAR MÜHENDİSLİĞİ BÖLÜMÜ"}


def test_bolumde_kirilim_programlardir(db: Session) -> None:
    k = kiyas.child_breakdown(db, resolve(db, department_id=_bid(db, "YAZMUH")))
    assert k["child_kind"] == "program"
    assert {r["code"] for r in k["rows"]} == {"YAZ-TR", "YAZ-EN"}


def test_programda_kirilim_yok_yapraktir(db: Session) -> None:
    k = kiyas.child_breakdown(db, resolve(db,
                                          academic_program_id=_pid(db, "YAZ-TR")))
    assert k["rows"] == []
    assert k["is_leaf"] is True


def test_kirilim_ust_kapsama_tasmaz(db: Session) -> None:
    """MUH kırılımında FEN'in bölümü GÖRÜNEMEZ."""
    k = kiyas.child_breakdown(db, resolve(db, faculty_id=_fid(db, "MUH")))
    assert "MATEMATİK BÖLÜMÜ" not in {r["name"] for r in k["rows"]}


# ==========================================================================
# 3. Ölçüm satırları gerçek veriden
# ==========================================================================


def test_birim_olcumu_kadro_ve_ogrenciyi_birlestirir(db: Session) -> None:
    k = kiyas.child_breakdown(db, resolve(db, faculty_id=_fid(db, "MUH")))
    yaz = [r for r in k["rows"] if r["code"] == "YAZMUH"][0]
    assert yaz["academic_staff_count"] == 3
    assert yaz["active_teaching_staff_count"] == 2   # Y3'ün yükü 0
    assert yaz["curriculum_course_count"] == 2
    assert yaz["program_count"] == 2
    # 2 program × (40+35+30+25) ve (20+15+10+5) = 130 + 50 = 180
    assert yaz["student_count"] == 180
    assert yaz["students_per_academic_staff"] == 60.0


def test_olculmeyen_gosterge_sifir_degil_none(db: Session) -> None:
    """MYO'da müfredat dersi yok: 0 değil None dönmeli."""
    k = kiyas.child_breakdown(db, resolve(db))
    myo = [r for r in k["rows"] if r["code"] == "MYO"][0]
    assert myo["curriculum_course_count"] is None
    assert myo["student_count"] is None
    assert myo["students_per_academic_staff"] is None
    # Kadro gerçekten var; o None DEĞİL.
    assert myo["academic_staff_count"] == 1


def test_idari_kadro_akademik_olcume_karismaz(db: Session) -> None:
    k = kiyas.child_breakdown(db, resolve(db))
    assert "REKTÖRLÜK" not in {r["name"] for r in k["rows"]}
    assert sum(r["academic_staff_count"] or 0 for r in k["rows"]) == 7


# ==========================================================================
# 4. Öğrenci analitiği — kohort, talep, değişim
# ==========================================================================


def test_ogrenci_govdesi_kohortlara_ayrilir(db: Session) -> None:
    g = analitik.student_body_overview(db, resolve(db,
                                                   department_id=_bid(db, "BILMUH")))
    assert g["available"] is True
    assert g["cohort_years"] == [2022, 2023, 2024, 2025]
    assert [c["placed_students"] for c in g["cohorts"]] == [30, 25, 20, 15]
    # Kohortların toplamı = resmî öğrenci sayısı. İki sayı ayrışamaz.
    assert g["student_count"] == 90
    assert sum(c["placed_students"] for c in g["cohorts"]) == g["student_count"]


def test_kohort_paylari_yuzde_olarak_doner(db: Session) -> None:
    g = analitik.student_body_overview(db, resolve(db,
                                                   department_id=_bid(db, "BILMUH")))
    paylar = [c["cohort_share_percent"] for c in g["cohorts"]]
    assert paylar[0] == round(30 / 90 * 100, 2)
    assert abs(sum(paylar) - 100) < 0.05


def test_alim_degisimi_onceki_kohorta_gore(db: Session) -> None:
    g = analitik.student_body_overview(db, resolve(db,
                                                   department_id=_bid(db, "BILMUH")))
    assert g["latest_placement_year"] == 2025
    assert g["previous_cohort_size"] == 20
    # 15 vs 20 → %-25
    assert g["intake_change_percent"] == -25.0
    assert g["quota_change_percent"] == 0.0


def test_doluluk_ve_talep_baskisi(db: Session) -> None:
    g = analitik.student_body_overview(db, resolve(db,
                                                   department_id=_bid(db, "BILMUH")))
    assert g["latest_quota"] == 30
    assert g["latest_occupancy_percent"] == 50.0
    b = g["demand_pressure"]
    assert b["available"] is True
    assert b["status"] == "talep_yetersiz"
    assert b["unfilled_quota"] == 15
    # Eşikler AÇIKÇA bildirilir; gizli sabit değil.
    assert b["thresholds"]["dengeli"] == 85


def test_ogrenci_kadro_oranlari_ayni_ekranda(db: Session) -> None:
    g = analitik.student_body_overview(db, resolve(db,
                                                   department_id=_bid(db, "YAZMUH")))
    assert g["academic_staff_count"] == 3
    assert g["active_teaching_staff_count"] == 2
    assert g["students_per_academic_staff"] == 60.0
    assert g["students_per_active_teaching_staff"] == 90.0


def test_ogrenci_analitigi_kapsama_uyar(db: Session) -> None:
    g = analitik.student_body_overview(db, resolve(db,
                                                   academic_program_id=_pid(db, "YAZ-EN")))
    # Yalnızca YAZ-EN: 20+15+10+5
    assert g["student_count"] == 50
    assert g["latest_quota"] == 20


def test_yks_kaydi_olmayan_kapsamda_sifir_uydurulmaz(db: Session) -> None:
    g = analitik.student_body_overview(db, resolve(db,
                                                   department_id=_bid(db, "BILPROG")))
    assert g["available"] is False
    assert g["student_count"] is None
    assert g["latest_occupancy_percent"] is None
    assert g["demand_pressure"]["available"] is False


# ==========================================================================
# 5. Yönetim panosu
# ==========================================================================


def test_pano_seviyeye_gore_kirilim_secer(db: Session) -> None:
    assert analitik.executive_overview(
        db, resolve(db))["breakdown"]["child_kind"] == "faculty"
    assert analitik.executive_overview(
        db, resolve(db, faculty_id=_fid(db, "MUH"))
    )["breakdown"]["child_kind"] == "department"
    assert analitik.executive_overview(
        db, resolve(db, department_id=_bid(db, "YAZMUH"))
    )["breakdown"]["child_kind"] == "program"


def test_pano_yaprakta_birimin_kendi_olcumunu_verir(db: Session) -> None:
    o = analitik.executive_overview(
        db, resolve(db, academic_program_id=_pid(db, "YAZ-TR")))
    assert o["breakdown"]["is_leaf"] is True
    assert o["unit"]["code"] == "YAZ-TR"
    assert o["unit"]["student_count"] == 130


def test_pano_yonetim_gostergelerini_icerir(db: Session) -> None:
    o = analitik.executive_overview(db, resolve(db, faculty_id=_fid(db, "MUH")))
    k = o["staffing"]
    assert k["academic_staff_count"] == 5
    assert k["active_teaching_staff_count"] == 4
    assert k["students_per_academic_staff"] is not None
    assert k["academics_per_100_students"] is not None
    assert o["teaching_load"]["median_hours"] is not None
    assert o["teaching_load"]["top20_percent_share"] is not None
    assert o["curriculum_load"]["curriculum_course_count"] == 3
    assert o["student_body"]["cohort_count"] == 4


def test_mufredat_sayisi_kanonik_katmandan(db: Session) -> None:
    """Ham satır değil, tekilleştirilmiş ders sayısı raporlanır."""
    db.add(CurriculumCourse(
        department_id=_bid(db, "BILMUH"), course_code="CE101",
        course_name="DEVRELER", name_is_reliable=True, source_type="booklet",
        source_dataset="t", source_file="f", source_fingerprint="dup"))
    db.commit()
    rebuild_canonical(db)
    db.commit()
    o = analitik.curriculum_load(db, resolve(db, department_id=_bid(db, "BILMUH")))
    assert o["curriculum_course_count"] == 1     # kopya birleşti


def test_uyarilar_olculmus_degerden_turer(db: Session) -> None:
    uyarilar = analitik.operational_warnings(
        db, resolve(db, department_id=_bid(db, "BILMUH")))
    kodlar = {u["code"] for u in uyarilar}
    # Doluluk %50 → düşük doluluk uyarısı.
    assert "low_occupancy" in kodlar
    for u in uyarilar:
        assert u["measured_value"] is not None
        assert u["explanation"]


def test_verisi_olmayan_kapsamda_uyari_uretilmez(db: Session) -> None:
    """"Veri yok" bir risk sinyali değildir."""
    uyarilar = analitik.operational_warnings(
        db, resolve(db, department_id=_bid(db, "BILPROG")))
    assert "low_occupancy" not in {u["code"] for u in uyarilar}
    assert "demand_declining" not in {u["code"] for u in uyarilar}
