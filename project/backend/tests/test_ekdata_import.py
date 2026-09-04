"""`data/ekdata` aktarımının doğruluk garantileri.

Testler kendi küçük kaynak dosyalarını üretir ve kendi BOŞ veritabanına
yazar. Amaç, gerçek dosyaları taklit etmek değil, aktarımın KURALLARINI
sabitlemek:

  * kaynakta olmayan alan UYDURULMAZ → NULL
  * yıl granülerliği KORUNUR
  * köken (dosya, kaynak türü) KORUNUR
  * seviye/yazım farkı yüzünden KOPYA BİRİM açılmaz
  * aynı verinin CSV ve JSON kopyası İKİ KEZ aktarılmaz
  * çakışan gerçek değer SESSİZCE EZİLMEZ
  * idari birime akademik veri bağlanmaz
  * aktarım idempotenttir
"""

import csv
import json
from decimal import Decimal
from typing import Iterator

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import import_ekdata as ek
from app.database import Base
from app.models import (
    AcademicProgram,
    CurriculumCourse,
    DataSourceConflict,
    Department,
    Faculty,
    ProgramEnrollmentSnapshot,
    YksPlacementRecord,
)
from app.services.unit_matching import UnitIndex, normalize_unit_name
from app.services.unit_types import ADMINISTRATIVE, FACULTY, VOCATIONAL_SCHOOL

MUH = "Mühendislik ve Mimarlık Fakültesi"
MYO = "Meslek Yüksekokulu"


# --------------------------------------------------------------------------
# Fixture — YÖK aktarımının kurduğu omurgayı taklit eden küçük ağaç
# --------------------------------------------------------------------------


@pytest.fixture()
def db() -> Iterator[Session]:
    # BELLEK İÇİ veritabanı: 37 tablonun her testte diske yazılması
    # kurulumu test başına ~3 saniyeye çıkarıyordu. StaticPool, aynı
    # bellek veritabanının tek bağlantı üzerinden paylaşılmasını sağlar
    # (yoksa her bağlantı boş bir veritabanı açar).
    motor = create_engine(
        "sqlite://", future=True,
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(motor)
    s = sessionmaker(bind=motor, future=True)()

    muh = Faculty(name="MÜHENDİSLİK VE MİMARLIK FAKÜLTESİ", code="MUHMIM",
                  unit_type=FACULTY, is_active=True)
    myo = Faculty(name="MESLEK YÜKSEKOKULU", code="MESLEK",
                  unit_type=VOCATIONAL_SCHOOL, is_active=True)
    rekt = Faculty(name="REKTÖRLÜK", code="REKTORLUK",
                   unit_type=ADMINISTRATIVE, is_active=True)
    s.add_all([muh, myo, rekt])
    s.flush()

    yazmuh = Department(name="YAZILIM MÜHENDİSLİĞİ BÖLÜMÜ", code="YAZMUH",
                        faculty_id=muh.id, is_active=True)
    # MYO'da bir BÖLÜM, altında birden çok PROGRAM: ÖSYM'nin "department"
    # dediği şey burada PROGRAM seviyesindedir.
    bilteknoloji = Department(name="BİLGİSAYAR TEKNOLOJİLERİ BÖLÜMÜ",
                              code="BILTEK", faculty_id=myo.id, is_active=True)
    s.add_all([yazmuh, bilteknoloji])
    s.flush()

    s.add_all([
        AcademicProgram(name="YAZILIM MÜHENDİSLİĞİ PR.", code="YAZMUH-PR",
                        department_id=yazmuh.id, degree_level="Lisans",
                        duration_years=None, quota=None, is_active=True),
        AcademicProgram(name="BİLGİSAYAR PROGRAMCILIĞI PR.", code="BILPRG-PR",
                        department_id=bilteknoloji.id, degree_level="Ön Lisans",
                        duration_years=None, quota=None, is_active=True),
        AcademicProgram(name="WEB TASARIMI VE KODLAMA PR.", code="WEBTAS-PR",
                        department_id=bilteknoloji.id, degree_level="Ön Lisans",
                        duration_years=None, quota=None, is_active=True),
    ])
    s.commit()
    try:
        yield s
    finally:
        s.close()
        motor.dispose()


def _yks_satiri(**ustunden):
    temel = {
        "academic_year": "2025", "faculty": MUH,
        "department": "Yazılım Mühendisliği",
        "program_name": "Yazılım Mühendisliği (Burslu) (4 Yıllık)",
        "program_code": "", "score_type": "SAY", "scholarship_type": "Burslu",
        "quota": "7", "placed_students": "8", "vacant_quota": "",
        "occupancy_rate": "1.14", "base_score": "431.79005",
        "highest_score": "", "success_rank": "63592",
    }
    temel.update(ustunden)
    return temel


def _yaz_csv(yol, satirlar):
    with yol.open("w", encoding="utf-8", newline="") as f:
        y = csv.DictWriter(f, fieldnames=list(satirlar[0]))
        y.writeheader()
        y.writerows(satirlar)


# ==========================================================================
# 1. Dosya tanıma — ada değil İÇERİĞE bakar
# ==========================================================================


def test_dosya_turu_icerikten_taninir(tmp_path) -> None:
    yol = tmp_path / "adi-hicbir-sey-anlatmayan-dosya.csv"
    _yaz_csv(yol, [_yks_satiri()])
    tur, satirlar, _ = ek._tanı(yol)
    assert tur == "yks"
    assert len(satirlar) == 1


def test_tanınmayan_sema_sessizce_atlanmaz(tmp_path) -> None:
    yol = tmp_path / "alakasiz.csv"
    _yaz_csv(yol, [{"a": "1", "b": "2"}])
    tur, _, sutunlar = ek._tanı(yol)
    assert tur == "bilinmiyor"
    assert sutunlar == ["a", "b"]


def test_csv_ve_json_ikizi_ayni_parmak_izini_verir(tmp_path) -> None:
    """CSV metin, JSON yerel tür verir; ikisi AYNI veri sayılmalı."""
    satir = _yks_satiri()
    csv_gibi = [satir]
    json_gibi = [{
        **satir,
        "academic_year": 2025, "quota": 7, "placed_students": 8,
        "program_code": None, "vacant_quota": None, "highest_score": None,
        "occupancy_rate": 1.14, "base_score": 431.79005, "success_rank": 63592,
    }]
    assert ek._icerik_izi("yks", csv_gibi) == ek._icerik_izi("yks", json_gibi)


# ==========================================================================
# 2. Birim eşleştirme — seviye farkı kopya üretmez
# ==========================================================================


def test_osym_department_alani_programa_baglanir(db: Session) -> None:
    """ÖSYM'nin "Bilgisayar Programcılığı"sı bizim PROGRAMIMIZDIR.

    Yeni bir bölüm açmak, var olan tek birimi ikiye bölerdi.
    """
    dizin = UnitIndex(db)
    myo = dizin.find_faculty(MYO)
    eslesme = dizin.resolve("Bilgisayar Programcılığı", myo)
    assert eslesme.level == "program"
    assert eslesme.matched_name == "BİLGİSAYAR PROGRAMCILIĞI PR."


def test_ayni_ada_sahip_program_bolumden_once_gelir(db: Session) -> None:
    """"Yazılım Mühendisliği" hem bölüm hem program adıyla eşleşiyor.

    EN DAR eşleşme kazanır: ÖSYM verisi programa aittir, bölüme değil.
    Bölüme yazmak, aynı bölümdeki başka programların verisiyle
    karışmasına yol açardı. Bölüm bilgisi yine de döner.
    """
    dizin = UnitIndex(db)
    eslesme = dizin.resolve("Yazılım Mühendisliği", dizin.find_faculty(MUH))
    assert eslesme.level == "program"
    assert eslesme.matched_name == "YAZILIM MÜHENDİSLİĞİ PR."
    assert eslesme.department_id is not None


def test_yalnizca_bolum_olarak_var_olan_ad_boluma_baglanir(db: Session) -> None:
    """Program karşılığı olmayan bölüm adı BÖLÜM olarak çözülür."""
    dizin = UnitIndex(db)
    eslesme = dizin.resolve("Bilgisayar Teknolojileri", dizin.find_faculty(MYO))
    assert eslesme.level == "department"
    assert eslesme.matched_name == "BİLGİSAYAR TEKNOLOJİLERİ BÖLÜMÜ"


def test_idari_birim_akademik_kaynaktan_bulunamaz(db: Session) -> None:
    """Rektörlük akademik bir satırın fakültesi olamaz."""
    assert UnitIndex(db).find_faculty("Rektörlük") is None


def test_benzer_ama_farkli_birim_birlestirilmez(db: Session) -> None:
    """"Bilişim Sistemleri Mühendisliği" ≠ "Yazılım Mühendisliği".

    Bulanık eşleştirme iki gerçek bölümü sessizce birleştirirdi.
    """
    dizin = UnitIndex(db)
    assert not dizin.resolve("Bilişim Sistemleri Mühendisliği",
                             dizin.find_faculty(MUH)).found


def test_ogretim_dili_eki_ayni_birimi_isaret_eder() -> None:
    assert (normalize_unit_name("Bilgisayar Mühendisliği (İngilizce)")
            == normalize_unit_name("BİLGİSAYAR MÜHENDİSLİĞİ BÖLÜMÜ"))


# ==========================================================================
# 3. YKS aktarımı
# ==========================================================================


@pytest.fixture()
def yks_aktarildi(db: Session) -> ek.EkVeriAktarimi:
    a = ek.EkVeriAktarimi(db)
    a.yks_aktar([
        _yks_satiri(),
        _yks_satiri(scholarship_type="%50 İndirimli", quota="42",
                    placed_students="3", base_score="", success_rank="",
                    program_name="Yazılım Mühendisliği (%50 İndirimli) (4 Yıllık)"),
        _yks_satiri(academic_year="2024", quota="10", placed_students="11",
                    base_score="417.06405", success_rank="65660"),
    ], "test_yks.csv")
    db.commit()
    return a


def test_kaynak_granulerligi_korunur(db: Session, yks_aktarildi) -> None:
    """Her burs türü AYRI satır olarak kalır; snapshot'a sıkıştırılmaz."""
    kayitlar = db.execute(select(YksPlacementRecord)).scalars().all()
    assert len(kayitlar) == 3
    assert {k.scholarship_type for k in kayitlar} == {"Burslu", "%50 İndirimli"}


def test_yil_granulerligi_korunur(db: Session, yks_aktarildi) -> None:
    yillar = {k.placement_year for k in
              db.execute(select(YksPlacementRecord)).scalars()}
    assert yillar == {2024, 2025}


def test_takvim_yili_akademik_yila_cevrilir(db: Session, yks_aktarildi) -> None:
    kayit = db.execute(
        select(YksPlacementRecord).where(YksPlacementRecord.placement_year == 2025)
    ).scalars().first()
    assert kayit.academic_year == "2025-2026"


def test_bos_hucre_sifir_degil_null_olur(db: Session, yks_aktarildi) -> None:
    """Kaynakta 212/212 boş olan alanlar 0 değil NULL."""
    kayit = db.execute(
        select(YksPlacementRecord).where(
            YksPlacementRecord.scholarship_type == "%50 İndirimli"
        )
    ).scalar_one()
    assert kayit.base_score is None
    assert kayit.success_rank is None
    assert kayit.placement_program_code is None
    assert kayit.vacant_quota is None


def test_taban_puan_tam_hassasiyetle_saklanir(db: Session, yks_aktarildi) -> None:
    """5 ondalık kaynakta var; yerleştirme tablosunda kaybolmaz."""
    kayit = db.execute(
        select(YksPlacementRecord).where(
            YksPlacementRecord.placement_year == 2025,
            YksPlacementRecord.scholarship_type == "Burslu",
        )
    ).scalar_one()
    assert kayit.base_score == Decimal("431.79005")


def test_koken_korunur(db: Session, yks_aktarildi) -> None:
    kayit = db.execute(select(YksPlacementRecord)).scalars().first()
    assert kayit.source_file == "test_yks.csv"
    assert kayit.source_dataset == "ankara_bilim_yks_4year"
    assert kayit.source_row_key


def test_snapshot_varyantlari_toplar(db: Session, yks_aktarildi) -> None:
    """Burslu(7) + %50(42) = 49 kontenjan; yerleşen 8 + 3 = 11."""
    s = db.execute(
        select(ProgramEnrollmentSnapshot).where(
            ProgramEnrollmentSnapshot.academic_year == "2025-2026"
        )
    ).scalar_one()
    assert s.quota == 49
    assert s.enrolled_student_count == 11


def test_snapshot_taban_puani_en_dusuk_varyanttir(
    db: Session, yks_aktarildi
) -> None:
    """Programa giriş eşiği, varyantların en düşüğüdür."""
    s = db.execute(
        select(ProgramEnrollmentSnapshot).where(
            ProgramEnrollmentSnapshot.academic_year == "2025-2026"
        )
    ).scalar_one()
    assert s.minimum_admission_score == Decimal("431.79")
    assert s.full_scholarship_minimum_admission_score == Decimal("431.79")


def test_program_kontenjani_en_guncel_yildan_dolar(
    db: Session, yks_aktarildi
) -> None:
    """YÖK'te NULL bırakılan alan, ÖSYM verisiyle kapanır."""
    p = db.execute(
        select(AcademicProgram).where(AcademicProgram.code == "YAZMUH-PR")
    ).scalar_one()
    assert p.quota == 49  # 2025 toplamı, 2024'ünki değil


def test_kontenjani_olmayan_yil_icin_snapshot_uydurulmaz(db: Session) -> None:
    """quota NOT NULL; kaynakta yoksa kayıt AÇILMAZ."""
    a = ek.EkVeriAktarimi(db)
    a.yks_aktar([_yks_satiri(quota="", placed_students="")], "bos.csv")
    db.commit()
    assert db.execute(select(ProgramEnrollmentSnapshot)).scalars().all() == []
    assert a.sayac["snapshot_atlandi_kontenjan_yok"] == 1


def test_bulunamayan_gercek_birim_olusturulur(db: Session) -> None:
    a = ek.EkVeriAktarimi(db)
    a.yks_aktar([_yks_satiri(department="Bilişim Sistemleri Mühendisliği",
                             program_name="Bilişim Sistemleri Müh. (Burslu)")],
                "yeni.csv")
    db.commit()
    yeni = db.execute(
        select(Department).where(Department.name == "Bilişim Sistemleri Mühendisliği")
    ).scalar_one()
    assert yeni.faculty.code == "MUHMIM"
    assert "yeni.csv" in (yeni.description or "")


def test_ogretim_dili_eki_bolum_adina_yazilmaz(db: Session) -> None:
    """"(İngilizce)" programın özelliğidir; bölüm adına girerse aynı bölüm
    Türkçe programı geldiğinde ikinci kez açılırdı."""
    a = ek.EkVeriAktarimi(db)
    a.yks_aktar([_yks_satiri(department="Bilişim Sistemleri Mühendisliği (İngilizce)",
                             program_name="X (Burslu)")], "dil.csv")
    db.commit()
    adlar = {d.name for d in db.execute(select(Department)).scalars()}
    assert "Bilişim Sistemleri Mühendisliği" in adlar
    assert "Bilişim Sistemleri Mühendisliği (İngilizce)" not in adlar


def test_ayni_ad_farkli_dil_eki_ikinci_bolum_acmaz(db: Session) -> None:
    a = ek.EkVeriAktarimi(db)
    a.yks_aktar([
        _yks_satiri(department="Bilişim Sistemleri Mühendisliği (İngilizce)",
                    program_name="X (Burslu)"),
        _yks_satiri(department="Bilişim Sistemleri Mühendisliği",
                    program_name="X (Ücretli)", scholarship_type="Ücretli"),
    ], "dil2.csv")
    db.commit()
    assert sum(1 for d in db.execute(select(Department)).scalars()
               if "Bilişim" in d.name) == 1


# ==========================================================================
# 4. Müfredat
# ==========================================================================


def test_mufredat_dersi_bolume_baglanir(db: Session) -> None:
    a = ek.EkVeriAktarimi(db)
    a.mufredat_aktar([{
        "faculty": MUH, "department": "Yazılım Mühendisliği",
        "course_code": "SE 101", "course_name": "Yazılım Mühendisliğine Giriş",
        "source_type": "official_university_web_curriculum", "source": "web",
    }], "mufredat.xlsx")
    db.commit()
    ders = db.execute(select(CurriculumCourse)).scalar_one()
    assert ders.course_code == "SE 101"
    assert ders.name_is_reliable is True
    assert ders.source_type == "official_university_web_curriculum"
    assert ders.source_file == "mufredat.xlsx"


def test_birlesmis_pdf_metni_guvenilmez_isaretlenir(db: Session) -> None:
    """43 satırda bütün dönem tablosu tek hücreye yapışmış.

    Metin AYIKLANMAZ (uydurma olurdu), ham hâliyle saklanır ve
    işaretlenir; hiçbir analiz onu ders adı sanamaz.
    """
    bozuk = ("Occupational Health and Safety IİngilizceZ 1 0 1 1ENG 101 "
             "Academic English I İngilizceZ 2 0 2 2MATH 101Calculus I")
    a = ek.EkVeriAktarimi(db)
    a.mufredat_aktar([{
        "faculty": MUH, "department": "Yazılım Mühendisliği",
        "course_code": "OHS 101", "course_name": bozuk,
        "source_type": "uploaded", "source": None,
    }], "m.xlsx")
    db.commit()
    ders = db.execute(select(CurriculumCourse)).scalar_one()
    assert ders.name_is_reliable is False
    assert ders.course_name == bozuk       # ham metin korundu


def test_ayni_ders_kodu_farkli_kaynaktan_iki_kayit_olur(db: Session) -> None:
    """(bölüm, kod) TEKİL DEĞİL — 1205 satırda 151 tekrar var.

    Kodu tekil varsaymak gerçek satırları yutardı.
    """
    ortak = {
        "faculty": MUH, "department": "Yazılım Mühendisliği",
        "course_code": "TUR 101", "course_name": "Türk Dili I",
    }
    a = ek.EkVeriAktarimi(db)
    a.mufredat_aktar([
        {**ortak, "source_type": "web", "source": "web"},
        {**ortak, "source_type": "booklet", "source": "kitapcik.pdf"},
    ], "m.xlsx")
    db.commit()
    assert len(db.execute(select(CurriculumCourse)).scalars().all()) == 2


def test_mufredat_bos_ders_kodu_null_kalir(db: Session) -> None:
    a = ek.EkVeriAktarimi(db)
    a.mufredat_aktar([{
        "faculty": MUH, "department": "Yazılım Mühendisliği",
        "course_code": None, "course_name": "Seçmeli Ders",
        "source_type": "web", "source": "web",
    }], "m.xlsx")
    db.commit()
    assert db.execute(select(CurriculumCourse)).scalar_one().course_code is None


# ==========================================================================
# 5. Çakışma — sessizce ezme yok
# ==========================================================================


def test_farkli_kaynak_ayni_alani_ezmez(db: Session) -> None:
    a = ek.EkVeriAktarimi(db)
    a.yks_aktar([_yks_satiri()], "kaynak_a.csv")
    db.commit()

    b = ek.EkVeriAktarimi(db)
    b.yks_aktar([_yks_satiri(quota="999")], "kaynak_b.csv")
    b.cakismalari_yaz()
    db.commit()

    s = db.execute(select(ProgramEnrollmentSnapshot)).scalar_one()
    assert s.quota == 7, "mevcut gerçek değer korunmalıydı"

    cakisma = db.execute(
        select(DataSourceConflict).where(
            DataSourceConflict.field_name == "quota",
            DataSourceConflict.table_name == "program_enrollment_snapshots",
        )
    ).scalar_one()
    assert cakisma.existing_value == "7"
    assert cakisma.incoming_value == "999"
    assert "kaynak_b.csv" in cakisma.incoming_source
    assert cakisma.resolution == "kept_existing"


def test_bos_alani_doldurmak_cakisma_degildir(db: Session) -> None:
    """Farklı kaynaklar aynı varlığın FARKLI alanlarını doldurabilir."""
    a = ek.EkVeriAktarimi(db)
    a.yks_aktar([_yks_satiri(base_score="")], "a.csv")
    db.commit()

    b = ek.EkVeriAktarimi(db)
    b.yks_aktar([_yks_satiri(base_score="400.5")], "b.csv")
    b.cakismalari_yaz()
    db.commit()

    s = db.execute(select(ProgramEnrollmentSnapshot)).scalar_one()
    assert s.minimum_admission_score == Decimal("400.50")
    assert b.sayac["cakisma"] == 0


def test_sutun_hassasiyeti_sahte_cakisma_uretmez(db: Session) -> None:
    """Sütun 2 ondalık saklıyor; 431.79005 → 431.79 bir çakışma DEĞİLDİR."""
    a = ek.EkVeriAktarimi(db)
    a.yks_aktar([_yks_satiri()], "a.csv")
    db.commit()

    b = ek.EkVeriAktarimi(db)
    b.yks_aktar([_yks_satiri()], "b.csv")
    db.commit()
    assert b.sayac["cakisma"] == 0


# ==========================================================================
# 6. İdempotency
# ==========================================================================


def test_ikinci_calistirma_kayit_cogaltmaz(db: Session) -> None:
    satirlar = [_yks_satiri(), _yks_satiri(academic_year="2024")]
    ders = [{
        "faculty": MUH, "department": "Yazılım Mühendisliği",
        "course_code": "SE 101", "course_name": "Giriş",
        "source_type": "web", "source": "web",
    }]
    for _ in range(3):
        a = ek.EkVeriAktarimi(db)
        a.yks_aktar(satirlar, "y.csv")
        a.mufredat_aktar(ders, "m.xlsx")
        a.cakismalari_yaz()
        db.commit()

    assert len(db.execute(select(YksPlacementRecord)).scalars().all()) == 2
    assert len(db.execute(select(CurriculumCourse)).scalars().all()) == 1
    assert len(db.execute(select(ProgramEnrollmentSnapshot)).scalars().all()) == 2
    assert db.execute(select(DataSourceConflict)).scalars().all() == []


# ==========================================================================
# 7. Türetilmiş özet saklanmaz
# ==========================================================================


def test_tahmin_sutunu_veritabanina_yazilmaz(db: Session) -> None:
    """`estimated_*` adı gereği tahmindir; ölçülmüş gibi saklanamaz."""
    a = ek.EkVeriAktarimi(db)
    a.ozet_dogrula([{
        "faculty": MUH, "department": "Yazılım Mühendisliği",
        "program_name": "X", "observed_years": "2022|2023|2024|2025",
        "years_with_placed_data": "4",
        "estimated_4_cohort_placed_students": "43",
    }], "ozet.csv")
    db.commit()
    assert a.sayac["ozet_satir_okundu"] == 1
    assert any("TAHMİN" in n for n in a.notlar)
    # Hiçbir tabloya yazılmadı.
    assert db.execute(select(YksPlacementRecord)).scalars().all() == []
