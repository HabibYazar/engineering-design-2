"""PART3 — derslik envanteri ve eğitim ücretleri.

İddialar:
  · derslik satırları doğru ayrıştırılır; başlık/kural/özet satırı oda sayılmaz
  · sahiplik FAKÜLTE kimliğine çözülür; çözülemeyen sahip kaydı ELEMEZ
  · iki ayrı kapasite (fiziksel / öğrenci) karıştırılmaz
  · ölçülmemiş doluluk 0 DEĞİL None'dır ve toplamlara girmez
  · fakülteye tahsisli mekân BÖLÜM kapsamına inmez (kapsam sızıntısı yok)
  · ücret satırı program kimliğine bağlanır; eşleşmeyen satır saklanır
  · aynı ücretin iki sunumu tek satıra iner
  · part3 YETKİLİDİR: çakışan değer yazılır ve kayıt altına alınır
  · aktarım idempotenttir
"""

from decimal import Decimal
from typing import Iterator

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import import_part3 as part3
from app.database import Base
from app.models import (
    AcademicProgram,
    BenchmarkInstitution,
    CompetitorTuitionFee,
    DataSourceConflict,
    Department,
    Faculty,
    PhysicalFacility,
    ProgramTuitionFee,
)
from app.models.tuition_fee import (
    FEE_FULL,
    FEE_HALF_SCHOLARSHIP,
    LEVEL_BACHELOR,
)
from app.services import physical_resources_service as fiziksel
from app.services import tuition_service as ucret
from app.services.scope import resolve
from app.services.unit_types import FACULTY, VOCATIONAL_SCHOOL


@pytest.fixture()
def db() -> Iterator[Session]:
    motor = create_engine("sqlite://", future=True,
                          connect_args={"check_same_thread": False},
                          poolclass=StaticPool)
    Base.metadata.create_all(motor)
    s = sessionmaker(bind=motor, future=True)()

    muh = Faculty(name="MÜHENDİSLİK VE MİMARLIK FAKÜLTESİ", code="MUHMIM",
                  unit_type=FACULTY, is_active=True)
    itb = Faculty(name="İNSAN VE TOPLUM BİLİMLERİ FAKÜLTESİ", code="INSTOPBIL",
                  unit_type=FACULTY, is_active=True)
    myo = Faculty(name="MESLEK YÜKSEKOKULU", code="MESLEK",
                  unit_type=VOCATIONAL_SCHOOL, is_active=True)
    s.add_all([muh, itb, myo])
    s.flush()

    bil = Department(name="BİLGİSAYAR MÜHENDİSLİĞİ BÖLÜMÜ", code="BILMUH",
                     faculty_id=muh.id, is_active=True)
    eem = Department(name="ELEKTRİK-ELEKTRONİK MÜHENDİSLİĞİ BÖLÜMÜ",
                     code="ELEELEMUH", faculty_id=muh.id, is_active=True)
    psi = Department(name="PSİKOLOJİ BÖLÜMÜ", code="PSIKOLOJI",
                     faculty_id=itb.id, is_active=True)
    bilteknoloji = Department(name="BİLGİSAYAR TEKNOLOJİLERİ BÖLÜMÜ",
                              code="BILTEK", faculty_id=myo.id, is_active=True)
    s.add_all([bil, eem, psi, bilteknoloji])
    s.flush()

    s.add_all([
        AcademicProgram(name="BİLGİSAYAR MÜHENDİSLİĞİ PR.", code="BILMUH",
                        department_id=bil.id, degree_level="Lisans",
                        is_active=True),
        AcademicProgram(name="ELEKTRİK-ELEKTRONİK MÜHENDİSLİĞİ PR.",
                        code="ELEELEMUH", department_id=eem.id,
                        degree_level="Lisans", is_active=True),
        AcademicProgram(name="PSİKOLOJİ PR.", code="PSIKOLOJI",
                        department_id=psi.id, degree_level="Lisans",
                        is_active=True),
        AcademicProgram(name="İNSANSIZ HAVA ARACI TEKNOLOJİSİ VE "
                             "OPERATÖRLÜĞÜ PR.", code="INSHAVARA",
                        department_id=bilteknoloji.id,
                        degree_level="Önlisans", is_active=True),
    ])
    s.add(BenchmarkInstitution(
        name="TOBB EKONOMİ VE TEKNOLOJİ ÜNİVERSİTESİ", country="Türkiye",
        institution_type="competitor", is_competitor=True, is_active=True))
    s.commit()
    try:
        yield s
    finally:
        s.close()
        motor.dispose()


# --------------------------------------------------------------------------
# Kaynak satır üreticileri — gerçek dosyanın YAPISINI taklit eder
# --------------------------------------------------------------------------


def _oda(kat, kod, etiket, sinif_kap, ogr_kap, sahip):
    return {"floor": kat, "code": part3._oda_kodu(kod), "source_code": kod,
            "room_label": etiket, "capacity": sinif_kap,
            "student_capacity": ogr_kap, "owner": sahip}


@pytest.fixture()
def odalar():
    return [
        _oda(0, "C 017", None, 85, 83, "MMF"),
        _oda(0, "C 027", None, 88, 76, "ITBF"),      # Türkçe harfsiz yazım
        _oda(0, "C 076", None, 35, 33, "Hazırlık Okulu"),
        _oda(0, "L 002", "Film/stüd.", None, None, None),   # kapasitesi yok
        _oda(1, "L 121", "BIL LAB", 30, 30, "MMF-Lab"),
        _oda(2, "C 214", None, 30, 30, "İTBF"),
    ]


def _ucret(yil, fak, prog, dil, etiket, tutar, **ek):
    return {"academic_year": yil, "faculty_name": fak, "program_name": prog,
            "language": dil, "fee_label": etiket,
            "fee_type": part3.ucret_turu(etiket),
            "annual_fee": Decimal(str(tutar)), **ek}


# ==========================================================================
# 1. Derslik envanteri — ayrıştırma
# ==========================================================================


def test_oda_kodu_kaliba_uyanlari_secer():
    for kod in ("C 003", "C071", "L 008", "AMFİ4", "AMFİ 5", "LECTURE HALL 5"):
        assert part3._oda_mu(kod), kod
    # Başlık, kural metni ve birim özeti oda DEĞİLDİR.
    for kod in ("Ders Planlama Esasları", "1. Sabah 09.00", "İTBF", "MMF-Lab",
                "Toplam:", "TOPLAM"):
        assert not part3._oda_mu(kod), kod


def test_oda_kodu_bosluktan_bagimsiz():
    """"C 071" ve "C071" AYNI odadır; kod tekilliği buna dayanır."""
    assert part3._oda_kodu("C 071") == part3._oda_kodu("C071") == "C071"


def test_derslik_turu_kaynak_isaretlerinden():
    assert part3._derslik_turu("L 121", "BIL LAB", "MMF-Lab") == "laboratory"
    assert part3._derslik_turu("C 017", "", "MMF") == "classroom"
    assert part3._derslik_turu("AMFİ1", "MMF", "MMF") == "classroom"


# ==========================================================================
# 2. Derslik envanteri — aktarım ve eşleştirme
# ==========================================================================


def test_derslikler_fakulteye_baglanir(db: Session, odalar) -> None:
    a = part3.DerslikAktarimi(db)
    a.aktar(odalar, "derslikler.xlsx")
    db.commit()

    muh = db.execute(select(Faculty).where(Faculty.code == "MUHMIM")).scalar_one()
    itb = db.execute(
        select(Faculty).where(Faculty.code == "INSTOPBIL")).scalar_one()
    c017 = db.execute(
        select(PhysicalFacility).where(PhysicalFacility.code == "C017")
    ).scalar_one()
    assert c017.faculty_id == muh.id
    assert c017.department_id is None       # derslik BÖLÜME bağlanmaz

    # "ITBF" (harfsiz) ile "İTBF" AYNI fakültedir.
    for kod in ("C027", "C214"):
        f = db.execute(select(PhysicalFacility).where(
            PhysicalFacility.code == kod)).scalar_one()
        assert f.faculty_id == itb.id, kod


def test_fakulteye_cozulemeyen_sahip_kaydi_elemez(db: Session, odalar) -> None:
    """Hazırlık Okulu bir fakülte değildir; oda yine de kaydedilir."""
    a = part3.DerslikAktarimi(db)
    a.aktar(odalar, "derslikler.xlsx")
    db.commit()
    hazirlik = db.execute(select(PhysicalFacility).where(
        PhysicalFacility.code == "C076")).scalar_one()
    assert hazirlik.faculty_id is None
    assert hazirlik.owner_label == "Hazırlık Okulu"   # etiket KORUNDU
    assert any("C 076" in x for x in a.fakultesiz)


def test_iki_kapasite_karistirilmaz(db: Session, odalar) -> None:
    a = part3.DerslikAktarimi(db)
    a.aktar(odalar, "derslikler.xlsx")
    db.commit()
    c017 = db.execute(select(PhysicalFacility).where(
        PhysicalFacility.code == "C017")).scalar_one()
    assert c017.capacity == 85            # fiziksel koltuk
    assert c017.student_capacity == 83    # planlamada kullanılabilir


def test_kapasitesi_olmayan_oda_sifirlanmaz(db: Session, odalar) -> None:
    a = part3.DerslikAktarimi(db)
    a.aktar(odalar, "derslikler.xlsx")
    db.commit()
    l002 = db.execute(select(PhysicalFacility).where(
        PhysicalFacility.code == "L002")).scalar_one()
    assert l002.capacity is None          # 0 DEĞİL
    assert l002.student_capacity is None
    assert l002.room_label == "Film/stüd."


def test_kullanim_olculmemis_none_kalir(db: Session, odalar) -> None:
    """Envanterde doluluk yoktur; 0 yazmak "boş derslik" demek olurdu."""
    a = part3.DerslikAktarimi(db)
    a.aktar(odalar, "derslikler.xlsx")
    db.commit()
    for f in db.execute(select(PhysicalFacility)).scalars():
        assert f.occupied is None
        assert f.occupancy_percent is None


def test_kat_bilgisi_korunur(db: Session, odalar) -> None:
    a = part3.DerslikAktarimi(db)
    a.aktar(odalar, "derslikler.xlsx")
    db.commit()
    katlar = {f.code: f.floor for f in
              db.execute(select(PhysicalFacility)).scalars()}
    assert katlar["C017"] == 0 and katlar["L121"] == 1 and katlar["C214"] == 2


# ==========================================================================
# 3. Kapasite servisi — kapsam ve ölçülmemiş değer
# ==========================================================================


def test_kapasite_ozeti_olculmemis_dolulugu_uydurmaz(db: Session, odalar) -> None:
    part3.DerslikAktarimi(db).aktar(odalar, "d.xlsx")
    db.commit()
    o = fiziksel.capacity_overview(db, resolve(db))
    assert o["total_facilities"] == 6
    assert o["total_capacity"] == 85 + 88 + 35 + 30 + 30
    assert o["total_student_capacity"] == 83 + 76 + 33 + 30 + 30
    # Doluluk ÖLÇÜLMEDİ → None, 0 değil.
    assert o["total_occupied"] is None
    assert o["overall_occupancy_percent"] is None
    assert o["underutilized_count"] is None


def test_fakulte_kapsami_yalnizca_kendi_mekanlari(db: Session, odalar) -> None:
    part3.DerslikAktarimi(db).aktar(odalar, "d.xlsx")
    db.commit()
    muh = db.execute(select(Faculty).where(Faculty.code == "MUHMIM")).scalar_one()
    o = fiziksel.capacity_overview(db, resolve(db, faculty_id=muh.id))
    assert o["total_facilities"] == 2          # C017 + L121
    assert o["total_capacity"] == 85 + 30


def test_fakulte_mekani_bolum_kapsamina_inmez(db: Session, odalar) -> None:
    """Fakültenin dersliği, o fakültedeki HER bölümün dersliği değildir."""
    from fastapi import HTTPException

    part3.DerslikAktarimi(db).aktar(odalar, "d.xlsx")
    db.commit()
    bil = db.execute(
        select(Department).where(Department.code == "BILMUH")).scalar_one()
    with pytest.raises(HTTPException):
        fiziksel.capacity_overview(db, resolve(db, department_id=bil.id))


# ==========================================================================
# 4. Ücret eşleştirme
# ==========================================================================


def test_program_anahtari_ekleri_ve_tireyi_sadelestirir():
    assert part3.program_anahtari("BİLGİSAYAR MÜHENDİSLİĞİ PR.") \
        == part3.program_anahtari("Bilgisayar Mühendisliği")
    # Kaynak tiresiz yazıyor, katalog tireli.
    assert part3.program_anahtari("Elektrik Elektronik Mühendisliği") \
        == part3.program_anahtari("ELEKTRİK-ELEKTRONİK MÜHENDİSLİĞİ PR.")


def test_dil_yalnizca_parantezden_okunur():
    """"İngilizce Mütercim ve Tercümanlık" bir program ADIDIR."""
    ad, dil = part3.dil_ayikla("Bilgisayar Mühendisliği (İngilizce)")
    assert ad == "Bilgisayar Mühendisliği" and dil == "İngilizce"
    ad, dil = part3.dil_ayikla("İngilizce Mütercim ve Tercümanlık")
    assert ad == "İngilizce Mütercim ve Tercümanlık" and dil is None


def test_ucret_turu_yazim_varyantlarini_birlestirir():
    assert part3.ucret_turu("%50 Burslu") == FEE_HALF_SCHOLARSHIP
    assert part3.ucret_turu("%50 İndirimli") == FEE_HALF_SCHOLARSHIP
    assert part3.ucret_turu("Ücretli") == FEE_FULL


def test_ucret_programa_baglanir(db: Session) -> None:
    a = part3.UcretAktarimi(db)
    a.aktar([_ucret("2025-2026", "Mühendislik ve Mimarlık Fakültesi",
                    "Bilgisayar Mühendisliği", "Türkçe", "Ücretli", 928000)],
            "u.xlsx", "s1")
    db.commit()
    f = db.execute(select(ProgramTuitionFee)).scalar_one()
    prog = db.execute(select(AcademicProgram).where(
        AcademicProgram.code == "BILMUH")).scalar_one()
    assert f.academic_program_id == prog.id
    assert f.department_id == prog.department_id
    assert f.faculty_id is not None
    assert a.programsiz == []


def test_kisaltma_takma_adi_cozulur(db: Session) -> None:
    """İHA = İnsansız Hava Aracı — kurumun kendi iki yazımı."""
    a = part3.UcretAktarimi(db)
    a.aktar([_ucret("2026-2027", "Meslek Yüksekokulu",
                    "İHA Teknolojisi ve Operatörlüğü", None,
                    "%50 İndirimli", 350000)], "u.xlsx", "s1")
    db.commit()
    f = db.execute(select(ProgramTuitionFee)).scalar_one()
    assert f.academic_program_id is not None
    assert a.programsiz == []


def test_eslesmeyen_ucret_satiri_silinmez(db: Session) -> None:
    a = part3.UcretAktarimi(db)
    a.aktar([_ucret("2026-2027", "Havacılık ve Uzay Bilimleri Fakültesi",
                    "Pilotaj", None, "Ücretli", 1280000)], "u.xlsx", "s1")
    db.commit()
    f = db.execute(select(ProgramTuitionFee)).scalar_one()
    assert f.academic_program_id is None
    assert f.source_program_name == "Pilotaj"     # ham ad KORUNDU
    assert f.annual_fee == Decimal("1280000")
    assert len(a.programsiz) == 1


def test_program_baska_fakultede_aranmaz(db: Session) -> None:
    """Kapsam sızıntısı: MMF ücreti İTBF programına yazılamaz."""
    a = part3.UcretAktarimi(db)
    a.aktar([_ucret("2026-2027", "Mühendislik ve Mimarlık Fakültesi",
                    "Psikoloji", None, "Ücretli", 640000)], "u.xlsx", "s1")
    db.commit()
    f = db.execute(select(ProgramTuitionFee)).scalar_one()
    assert f.academic_program_id is None       # yanlış programa BAĞLANMADI


def test_ayni_ucretin_iki_sunumu_tek_satira_iner(db: Session) -> None:
    """Dil sütunlu sayfa önce; dilsiz sunum ikinci kez YAZILMAZ."""
    a = part3.UcretAktarimi(db)
    a.aktar([_ucret("2025-2026", "Mühendislik ve Mimarlık Fakültesi",
                    "Bilgisayar Mühendisliği", "Türkçe", "Ücretli", 928000)],
            "u.xlsx", "2025-2026 Ücretleri")
    a.aktar([_ucret("2025-2026", "Mühendislik ve Mimarlık Fakültesi",
                    "Bilgisayar Mühendisliği", None, "Ücretli", 928000)],
            "u.xlsx", "2025-2026 Eğitim Ücretleri")
    db.commit()
    assert db.execute(
        select(func.count()).select_from(ProgramTuitionFee)).scalar_one() == 1
    assert a.dil_zaten_var == 1


def test_part3_yetkili_cakisan_ucret_yazilir(db: Session) -> None:
    a = part3.UcretAktarimi(db)
    a.aktar([_ucret("2025-2026", "Mühendislik ve Mimarlık Fakültesi",
                    "Bilgisayar Mühendisliği", "Türkçe", "Ücretli", 900000)],
            "u.xlsx", "s1")
    db.commit()
    b = part3.UcretAktarimi(db)
    b.aktar([_ucret("2025-2026", "Mühendislik ve Mimarlık Fakültesi",
                    "Bilgisayar Mühendisliği", "Türkçe", "Ücretli", 928000)],
            "u.xlsx", "s2")
    part3._cakismalari_yaz(db, b.cakismalar, dry_run=False)
    db.commit()
    f = db.execute(select(ProgramTuitionFee)).scalar_one()
    assert f.annual_fee == Decimal("928000")      # PART3 KAZANDI
    c = db.execute(select(DataSourceConflict)).scalar_one()
    assert c.resolution == "applied_incoming"
    assert c.field_name == "annual_fee"


# ==========================================================================
# 5. Ücret servisi — kapsam
# ==========================================================================


@pytest.fixture()
def ucretli(db: Session) -> Session:
    a = part3.UcretAktarimi(db)
    a.aktar([
        _ucret("2026-2027", "Mühendislik ve Mimarlık Fakültesi",
               "Bilgisayar Mühendisliği", "Türkçe", "%50 İndirimli", 640000),
        _ucret("2026-2027", "Mühendislik ve Mimarlık Fakültesi",
               "Elektrik-Elektronik Mühendisliği", "İngilizce",
               "%50 İndirimli", 560000),
        _ucret("2026-2027", "İnsan ve Toplum Bilimleri Fakültesi",
               "Psikoloji", "Türkçe", "%50 İndirimli", 600000),
        _ucret("2025-2026", "Mühendislik ve Mimarlık Fakültesi",
               "Bilgisayar Mühendisliği", "Türkçe", "%50 İndirimli", 464000),
    ], "u.xlsx", "s1")
    db.commit()
    return db


def test_ucret_kapsami_hiyerarsiyi_izler(ucretli: Session) -> None:
    muh = ucretli.execute(
        select(Faculty).where(Faculty.code == "MUHMIM")).scalar_one()
    bil = ucretli.execute(
        select(Department).where(Department.code == "BILMUH")).scalar_one()
    prog = ucretli.execute(
        select(AcademicProgram).where(AcademicProgram.code == "BILMUH")).scalar_one()

    assert ucret.program_fees(ucretli, resolve(ucretli))["row_count"] == 3
    assert ucret.program_fees(
        ucretli, resolve(ucretli, faculty_id=muh.id))["row_count"] == 2
    assert ucret.program_fees(
        ucretli, resolve(ucretli, department_id=bil.id))["row_count"] == 1
    o = ucret.program_fees(ucretli, resolve(ucretli,
                                            academic_program_id=prog.id))
    assert o["row_count"] == 1
    assert o["rows"][0]["annual_fee"] == 640000.0


def test_ucret_kapsami_kardese_sizmaz(ucretli: Session) -> None:
    bil = ucretli.execute(
        select(Department).where(Department.code == "BILMUH")).scalar_one()
    o = ucret.program_fees(ucretli, resolve(ucretli, department_id=bil.id))
    adlar = {r["source_program_name"] for r in o["rows"]}
    assert "Elektrik-Elektronik Mühendisliği" not in adlar
    assert "Psikoloji" not in adlar


def test_ucret_trendi_tek_ucret_turunden(ucretli: Session) -> None:
    bil = ucretli.execute(
        select(Department).where(Department.code == "BILMUH")).scalar_one()
    t = ucret.fee_trend(ucretli, resolve(ucretli, department_id=bil.id))
    assert [y["academic_year"] for y in t["years"]] == ["2025-2026", "2026-2027"]
    assert t["years"][1]["change_percent"] == round(
        (640000 - 464000) / 464000 * 100, 2)


# ==========================================================================
# 6. Rakip ücretleri
# ==========================================================================


def _rakip(uni, yil, prog, etiket, ucret_metni, kategori="Standart Indirim (~%50)",
           seviye=LEVEL_BACHELOR):
    return {"university_name": uni, "academic_year": yil, "level": seviye,
            "unit_name": "Mühendislik Fakültesi", "program_name": prog,
            "fee_label": etiket, "fee_type": part3.ucret_turu(etiket),
            "price_category": kategori,
            "annual_fee": part3._para(ucret_metni), "fee_text": ucret_metni,
            "note": None}


def test_rakip_kurumu_kisaltmadan_cozulur(db: Session) -> None:
    a = part3.RakipUcretAktarimi(db)
    a.aktar([_rakip("TOBB ETU", "2026-2027", "Bilgisayar Müh.",
                    "%50 İndirimli", "500000")], "r.xlsx")
    db.commit()
    f = db.execute(select(CompetitorTuitionFee)).scalar_one()
    assert f.benchmark_institution_id is not None
    assert a.kurumsuz == []


def test_aralik_metni_sayiya_cevrilmez(db: Session) -> None:
    """"386.000 TL - 410.000 TL" uydurma bir orta noktaya indirgenmez."""
    a = part3.RakipUcretAktarimi(db)
    a.aktar([_rakip("TOBB ETU", "2026-2027", "Matematik",
                    "%50 İndirimli", "386.000 TL - 410.000 TL")], "r.xlsx")
    db.commit()
    f = db.execute(select(CompetitorTuitionFee)).scalar_one()
    assert f.annual_fee is None
    assert f.fee_text == "386.000 TL - 410.000 TL"   # ham metin KORUNDU
    assert a.aralik_metni == 1


def test_rakip_kiyasi_aralik_satirini_hesaba_katmaz(db: Session) -> None:
    a = part3.RakipUcretAktarimi(db)
    a.aktar([
        _rakip("TOBB ETU", "2026-2027", "A", "%50 İndirimli", "500000"),
        _rakip("TOBB ETU", "2026-2027", "B", "%50 İndirimli", "600000"),
        _rakip("TOBB ETU", "2026-2027", "C", "%50 İndirimli",
               "386.000 TL - 410.000 TL"),
    ], "r.xlsx")
    part3.UcretAktarimi(db).aktar(
        [_ucret("2026-2027", "Mühendislik ve Mimarlık Fakültesi",
                "Bilgisayar Mühendisliği", "Türkçe", "%50 İndirimli", 640000)],
        "u.xlsx", "s1")
    db.commit()
    o = ucret.competitor_fee_comparison(db, "2026-2027")
    tobb = next(r for r in o["universities"] if r["university_name"] == "TOBB ETU")
    assert tobb["measured_count"] == 2
    assert tobb["text_only_count"] == 1
    assert tobb["median_fee"] == 550000.0
    assert o["home"]["median_fee"] == 640000.0
    assert o["home"]["rank"] == 1


# ==========================================================================
# 7. İdempotans
# ==========================================================================


def test_derslik_ikinci_calistirmada_degismez(db: Session, odalar) -> None:
    a = part3.DerslikAktarimi(db)
    a.aktar(odalar, "d.xlsx")
    db.commit()
    ilk = db.execute(select(func.count()).select_from(PhysicalFacility)).scalar_one()

    b = part3.DerslikAktarimi(db)
    b.aktar(odalar, "d.xlsx")
    db.commit()
    assert db.execute(
        select(func.count()).select_from(PhysicalFacility)).scalar_one() == ilk
    assert b.eklendi == 0 and b.guncellendi == 0 and b.degismedi == ilk


def test_ucret_ikinci_calistirmada_degismez(ucretli: Session) -> None:
    ilk = ucretli.execute(
        select(func.count()).select_from(ProgramTuitionFee)).scalar_one()
    a = part3.UcretAktarimi(ucretli)
    a.aktar([_ucret("2026-2027", "Mühendislik ve Mimarlık Fakültesi",
                    "Bilgisayar Mühendisliği", "Türkçe", "%50 İndirimli",
                    640000)], "u.xlsx", "s1")
    ucretli.commit()
    assert ucretli.execute(
        select(func.count()).select_from(ProgramTuitionFee)).scalar_one() == ilk
    assert a.eklendi == 0 and a.degismedi == 1


def test_rakip_ikinci_calistirmada_degismez(db: Session) -> None:
    satir = [_rakip("TOBB ETU", "2026-2027", "A", "%50 İndirimli", "500000")]
    part3.RakipUcretAktarimi(db).aktar(satir, "r.xlsx")
    db.commit()
    b = part3.RakipUcretAktarimi(db)
    b.aktar(satir, "r.xlsx")
    db.commit()
    assert db.execute(
        select(func.count()).select_from(CompetitorTuitionFee)).scalar_one() == 1
    assert b.eklendi == 0 and b.degismedi == 1


def test_dry_run_yazmaz(db: Session, odalar) -> None:
    part3.DerslikAktarimi(db, dry_run=True).aktar(odalar, "d.xlsx")
    part3.UcretAktarimi(db, dry_run=True).aktar(
        [_ucret("2026-2027", "Mühendislik ve Mimarlık Fakültesi",
                "Bilgisayar Mühendisliği", None, "Ücretli", 1)], "u.xlsx", "s")
    assert db.execute(
        select(func.count()).select_from(PhysicalFacility)).scalar_one() == 0
    assert db.execute(
        select(func.count()).select_from(ProgramTuitionFee)).scalar_one() == 0


# ==========================================================================
# 8. MUTABAKAT — hiçbir kaynak satırı sessizce düşmez
# ==========================================================================


class _SahteSayfa:
    """openpyxl sayfasının okuyucular için gereken en küçük yüzeyi."""

    def __init__(self, satirlar, title="sayfa"):
        self._s = satirlar
        self.title = title
        self.max_row = len(satirlar)
        self.max_column = max(len(r) for r in satirlar)

    def cell(self, r, c):
        satir = self._s[r - 1]
        deger = satir[c - 1] if c <= len(satir) else None
        return type("H", (), {"value": deger})()


_BASLIK = ["Akademik Yıl", "Fakülte / Yüksekokul", "Bölüm / Program",
           "İndirim / Kontenjan Türü", "Normal Ücret (TL)",
           "İlk 5 Tercih İndirimli (TL)", "Peşin Ödeme İndirimli (TL)",
           "Ek Ücret (Uçuş vb.)"]


def test_okunamayan_ucret_sessizce_dusmez() -> None:
    """Ücreti sayıya çevrilemeyen satır GERİ BİLDİRİLİR.

    Eskiden `continue` ile sessizce atlanıyordu; kaynakta böyle bir satır
    olsaydı hiçbir sayaç bunu göstermezdi.
    """
    ws = _SahteSayfa([
        _BASLIK,
        ["2026-2027", "Hukuk Fakültesi", "Hukuk", "Ücretli", "640000",
         "-", "-", "-"],
        # Aralık metni: sayıya çevrilemez.
        ["2026-2027", "Hukuk Fakültesi", "Hukuk (İngilizce)", "Ücretli",
         "386.000 TL - 410.000 TL", "-", "-", "-"],
    ], title="2026-2027 Eğitim Ücretleri")

    atlanan = []
    satirlar = part3.ucret_sayfasi_oku(ws, atlanan)
    assert len(satirlar) == 1
    assert len(atlanan) == 1
    assert "satır 3" in atlanan[0]
    assert "386.000 TL - 410.000 TL" in atlanan[0]


def test_dilli_okuyucu_da_bildirir() -> None:
    ws = _SahteSayfa([
        ["Akademik Yıl", "Fakülte / Birim", "Bölüm / Program", "Eğitim Dili",
         "Ücret Türü", "Yıllık Ücret (TL)"],
        ["2025-2026", "Hukuk Fakültesi", "Hukuk", "Türkçe", "Ücretli", ""],
    ], title="2025-2026 Ücretleri")
    atlanan = []
    assert part3.ucret_sayfasi_oku_dilli(ws, atlanan) == []
    assert len(atlanan) == 1


def test_mutabakat_kimligi_tutar(db: Session) -> None:
    """veri satırı = eklendi + güncellendi + birleşen + dil + okunamadı.

    Aynı ücret üç kez sunulursa: 1 eklenir, 2 birleşir. Toplam yine 3.
    """
    a = part3.UcretAktarimi(db)
    satir = _ucret("2026-2027", "Mühendislik ve Mimarlık Fakültesi",
                   "Bilgisayar Mühendisliği", "Türkçe", "Ücretli", 928000)
    a.aktar([satir], "u.xlsx", "s1")
    a.aktar([satir], "u.xlsx", "s2")
    a.aktar([satir], "u.xlsx", "s3")
    db.commit()

    assert a.okunan_satir == 3
    hesap = (a.eklendi + a.guncellendi + a.birlesen + a.dil_zaten_var
             + len(a.atlanan))
    assert hesap == a.okunan_satir
    assert a.eklendi == 1 and a.birlesen == 2
    assert db.execute(
        select(func.count()).select_from(ProgramTuitionFee)).scalar_one() == 1


def test_birlesen_satir_ayni_degeri_tasir(db: Session) -> None:
    """"Birleşti" yalnızca DEĞER AYNIYSA sayılır.

    Farklı bir ücret gelseydi bu bir çakışmadır: part3 yetkisiyle yazılır
    ve kayıt altına alınır — sessizce "aynı" sayılmaz.
    """
    a = part3.UcretAktarimi(db)
    a.aktar([_ucret("2026-2027", "Mühendislik ve Mimarlık Fakültesi",
                    "Bilgisayar Mühendisliği", "Türkçe", "Ücretli", 928000)],
            "u.xlsx", "s1")
    b = part3.UcretAktarimi(db)
    b.aktar([_ucret("2026-2027", "Mühendislik ve Mimarlık Fakültesi",
                    "Bilgisayar Mühendisliği", "Türkçe", "Ücretli", 999000)],
            "u.xlsx", "s2")
    part3._cakismalari_yaz(db, b.cakismalar, dry_run=False)
    db.commit()

    assert b.birlesen == 0            # AYNI sayılmadı
    assert b.guncellendi == 1
    assert db.execute(select(ProgramTuitionFee)).scalar_one().annual_fee \
        == Decimal("999000")
    assert db.execute(
        select(func.count()).select_from(DataSourceConflict)).scalar_one() == 1


def test_dil_birlesmesi_yalnizca_ayni_ucrette(db: Session) -> None:
    """Dilsiz sunum, FARKLI ücret taşıyorsa ayrı kayıt olarak durur."""
    a = part3.UcretAktarimi(db)
    a.aktar([_ucret("2025-2026", "Mühendislik ve Mimarlık Fakültesi",
                    "Bilgisayar Mühendisliği", "Türkçe", "Ücretli", 928000)],
            "u.xlsx", "zengin")
    # Aynı program/tür, dil YOK, ücret FARKLI → birleştirilemez.
    a.aktar([_ucret("2025-2026", "Mühendislik ve Mimarlık Fakültesi",
                    "Bilgisayar Mühendisliği", None, "Ücretli", 850000)],
            "u.xlsx", "fakir")
    db.commit()
    assert a.dil_zaten_var == 0
    assert db.execute(
        select(func.count()).select_from(ProgramTuitionFee)).scalar_one() == 2


def test_her_kaynak_satiri_bir_kovaya_duser(db: Session) -> None:
    """Karışık bir küme: her satır TAM OLARAK bir kovaya düşer."""
    a = part3.UcretAktarimi(db)
    a.aktar([
        _ucret("2026-2027", "Mühendislik ve Mimarlık Fakültesi",
               "Bilgisayar Mühendisliği", "Türkçe", "Ücretli", 928000),
        _ucret("2026-2027", "Mühendislik ve Mimarlık Fakültesi",
               "Bilgisayar Mühendisliği", "Türkçe", "%50 İndirimli", 464000),
        # eşleşmeyen program — yine de saklanır
        _ucret("2026-2027", "Havacılık ve Uzay Bilimleri Fakültesi",
               "Pilotaj", None, "Ücretli", 1280000),
    ], "u.xlsx", "s1")
    # aynı ücretin ikinci sunumu (dilsiz)
    a.aktar([_ucret("2026-2027", "Mühendislik ve Mimarlık Fakültesi",
                    "Bilgisayar Mühendisliği", None, "Ücretli", 928000)],
            "u.xlsx", "s2")
    db.commit()

    assert a.okunan_satir == 4
    assert a.eklendi == 3 and a.dil_zaten_var == 1
    assert (a.eklendi + a.guncellendi + a.birlesen + a.dil_zaten_var
            + len(a.atlanan)) == a.okunan_satir
    assert db.execute(
        select(func.count()).select_from(ProgramTuitionFee)).scalar_one() == 3
