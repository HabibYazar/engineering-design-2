"""RESMÎ ÖĞRENCİ SAYISI regresyon testleri.

KURAL
-----
    student_count = Σ placed_students   (son ≤ 4 yerleştirme yılı)

Bu dosya kuralın kendisini ve hiyerarşiye uygulanışını sabitler:

  * varyantlar (Burslu / %50 / Ücretli · TR / EN) TOPLANIR, çift sayılmaz
  * 4'ten fazla yıl varsa YALNIZCA en güncel 4'ü alınır
  * 4'ten az yıl varsa olanlar toplanır — eksik yıl SIFIR SAYILMAZ
  * NULL yerleşen sıfır sayılmaz
  * kapsam: program / bölüm / fakülte / üniversite
  * sahte öğrenci kaydı ÜRETİLMEZ
  * kullanıcıya "tahmini/yaklaşık" ibaresi GÖSTERİLMEZ
"""

from typing import Iterator

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import (
    AcademicProgram,
    Department,
    Faculty,
    ProgramEnrollmentSnapshot,
    Student,
    YksPlacementRecord,
)
from app.services import education_analytics_service as egitim
from app.services import student_analytics_service as ogrenci
from app.services import student_count
from app.services.scope import resolve
from app.services.unit_types import ADMINISTRATIVE, FACULTY

YIL = "2025-2026"


# --------------------------------------------------------------------------
# Fixture
# --------------------------------------------------------------------------


@pytest.fixture()
def db() -> Iterator[Session]:
    """İki fakülte, üç program; her programın yıl deseni FARKLI.

    Desenler bilerek ayrıştırıldı ki bir hata sayıları karıştırdığında
    test hangi kuralın bozulduğunu göstersin.
    """
    motor = create_engine(
        "sqlite://", future=True,
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(motor)
    s = sessionmaker(bind=motor, future=True)()

    muh = Faculty(name="MÜHENDİSLİK FAKÜLTESİ", code="MUH",
                  unit_type=FACULTY, is_active=True)
    hukuk = Faculty(name="HUKUK FAKÜLTESİ", code="HUK",
                    unit_type=FACULTY, is_active=True)
    rekt = Faculty(name="REKTÖRLÜK", code="REKTORLUK",
                   unit_type=ADMINISTRATIVE, is_active=True)
    s.add_all([muh, hukuk, rekt])
    s.flush()

    yazmuh = Department(name="YAZILIM MÜHENDİSLİĞİ BÖLÜMÜ", code="YAZMUH",
                        faculty_id=muh.id, is_active=True)
    bilmuh = Department(name="BİLGİSAYAR MÜHENDİSLİĞİ BÖLÜMÜ", code="BILMUH",
                        faculty_id=muh.id, is_active=True)
    kamhuk = Department(name="KAMU HUKUKU BÖLÜMÜ", code="KAMHUK",
                        faculty_id=hukuk.id, is_active=True)
    s.add_all([yazmuh, bilmuh, kamhuk])
    s.flush()

    for kod, ad, bolum in (
        ("YAZ-PR", "Yazılım Mühendisliği", yazmuh),
        ("BIL-PR", "Bilgisayar Mühendisliği", bilmuh),
        ("HUK-PR", "Hukuk", kamhuk),
        # ÖSYM kaydı HİÇ olmayan program: sayısı NULL kalmalı.
        ("YOK-PR", "Kayıtsız Program", kamhuk),
    ):
        s.add(AcademicProgram(
            name=ad, code=kod, department_id=bolum.id, degree_level="Lisans",
            duration_years=4, quota=None, is_active=True,
        ))
    s.flush()
    s.commit()
    try:
        yield s
    finally:
        s.close()
        motor.dispose()


def _pid(db: Session, kod: str) -> int:
    return db.execute(
        select(AcademicProgram.id).where(AcademicProgram.code == kod)
    ).scalar_one()


def _yks(db: Session, kod: str, yil: int, yerlesen, burs="Burslu",
         program_adi=None) -> None:
    """Tek bir ÖSYM yerleştirme satırı ekler."""
    db.add(YksPlacementRecord(
        academic_program_id=_pid(db, kod),
        placement_year=yil,
        academic_year=f"{yil}-{yil + 1}",
        placement_program_name=program_adi or f"{kod} {burs} {yil}",
        score_type="SAY",
        scholarship_type=burs,
        quota=10,
        placed_students=yerlesen,
        source_dataset="test",
        source_file="test.csv",
    ))


# ==========================================================================
# 1. Formülün kendisi
# ==========================================================================


def test_tek_yil_tek_varyant(db: Session) -> None:
    _yks(db, "YAZ-PR", 2025, 30)
    db.commit()
    assert student_count.program_count(db, _pid(db, "YAZ-PR")) == 30


def test_burs_ve_dil_varyantlari_toplanir(db: Session) -> None:
    """Burslu / %50 / Ücretli FARKLI kişilerdir; toplanır.

    Bunlar aynı kişinin tekrarı değildir — çift sayma riski, aynı
    satırın iki kez yazılmasıdır ve buna tekillik kısıtı izin vermez.
    """
    _yks(db, "YAZ-PR", 2025, 8, burs="Burslu", program_adi="Yaz (İng) (Burslu)")
    _yks(db, "YAZ-PR", 2025, 5, burs="Burslu", program_adi="Yaz (Burslu)")
    _yks(db, "YAZ-PR", 2025, 20, burs="%50 İndirimli", program_adi="Yaz (%50)")
    _yks(db, "YAZ-PR", 2025, 2, burs="Ücretli", program_adi="Yaz (Ücretli)")
    db.commit()
    assert student_count.program_count(db, _pid(db, "YAZ-PR")) == 35


def test_dort_yil_toplanir(db: Session) -> None:
    for yil, adet in ((2022, 10), (2023, 20), (2024, 30), (2025, 40)):
        _yks(db, "YAZ-PR", yil, adet)
    db.commit()
    assert student_count.program_count(db, _pid(db, "YAZ-PR")) == 100


def test_dortten_fazla_yilda_yalnizca_son_dort_alinir(db: Session) -> None:
    """2021 kohortu mezun olmuştur; öğrenci gövdesine dahil değildir."""
    for yil, adet in ((2020, 999), (2021, 500), (2022, 10), (2023, 20),
                      (2024, 30), (2025, 40)):
        _yks(db, "YAZ-PR", yil, adet)
    db.commit()
    assert student_count.program_count(db, _pid(db, "YAZ-PR")) == 100


def test_dortten_az_yil_varsa_olanlar_toplanir(db: Session) -> None:
    """Program 2024'te açılmışsa 2022-2023 satırı YOKTUR."""
    for yil, adet in ((2024, 25), (2025, 35)):
        _yks(db, "YAZ-PR", yil, adet)
    db.commit()
    assert student_count.program_count(db, _pid(db, "YAZ-PR")) == 60


def test_eksik_yil_sifir_sayilmaz(db: Session) -> None:
    """Aradaki boşluk yıl ORTALAMAYI düşürmez; toplam etkilenmez.

    2023 verisi yoksa toplam 2022+2024+2025'tir; 2023'ü 0 yazıp dört yıl
    varmış gibi davranmak programı olduğundan küçük gösterirdi.
    """
    for yil, adet in ((2022, 10), (2024, 30), (2025, 40)):
        _yks(db, "YAZ-PR", yil, adet)
    db.commit()
    kayit = student_count.program_counts(db)[_pid(db, "YAZ-PR")]
    assert kayit.student_count == 80
    assert kayit.years == (2022, 2024, 2025)
    assert kayit.year_span == "2022-2025"


def test_null_yerlesen_sifir_sayilmaz(db: Session) -> None:
    """ÖSYM yerleşen sayısını açıklamamışsa o satır toplamın dışındadır."""
    _yks(db, "YAZ-PR", 2025, 30, burs="Burslu", program_adi="A")
    _yks(db, "YAZ-PR", 2025, None, burs="Ücretli", program_adi="B")
    db.commit()
    assert student_count.program_count(db, _pid(db, "YAZ-PR")) == 30


def test_hic_kaydi_olmayan_program_none_dondurur(db: Session) -> None:
    """NULL = "veri yok". 0 yazmak "öğrencisi yok" demek olurdu."""
    assert student_count.program_count(db, _pid(db, "YOK-PR")) is None
    assert _pid(db, "YOK-PR") not in student_count.program_counts(db)


# ==========================================================================
# 2. Sahte öğrenci kaydı üretilmiyor
# ==========================================================================


def test_sahte_ogrenci_satiri_uretilmez(db: Session) -> None:
    """Sayı türetilir; `students` tablosuna tek satır bile yazılmaz."""
    for yil, adet in ((2022, 10), (2023, 20), (2024, 30), (2025, 40)):
        _yks(db, "YAZ-PR", yil, adet)
    db.commit()
    student_count.refresh_stored_counts(db)
    db.commit()

    assert student_count.program_count(db, _pid(db, "YAZ-PR")) == 100
    assert db.execute(select(Student)).scalars().all() == []


def test_gercek_ogrenci_satiri_varsa_o_sayilir(db: Session) -> None:
    """ÖSYM kaydı olmayan programda gerçek öğrenci satırları kullanılır.

    Demo veri kümesi ve ileride yüklenecek öğrenci bilgi sistemi bu
    yoldan çalışır; davranışları değişmez.
    """
    pid = _pid(db, "YOK-PR")
    for i in range(7):
        db.add(Student(
            student_number=f"S{i}", first_name="A", last_name="B",
            enrollment_year=2023, academic_program_id=pid,
            current_status="active",
        ))
    db.commit()
    kayit = student_count.program_counts(db)[pid]
    assert kayit.student_count == 7
    assert kayit.source_method == student_count.STUDENT_RECORD_SOURCE_METHOD


def test_yks_verisi_ogrenci_satirlarindan_onceliklidir(db: Session) -> None:
    """İkisi de varsa ÖSYM RESMÎDİR; öğrenci satırları onu ezmez."""
    pid = _pid(db, "YAZ-PR")
    _yks(db, "YAZ-PR", 2025, 30)
    db.add(Student(student_number="X1", first_name="A", last_name="B",
                   enrollment_year=2023, academic_program_id=pid,
                   current_status="active"))
    db.commit()
    kayit = student_count.program_counts(db)[pid]
    assert kayit.student_count == 30
    assert kayit.source_method == student_count.OFFICIAL_SOURCE_METHOD


# ==========================================================================
# 3. HİYERARŞİ — program / bölüm / fakülte / üniversite
# ==========================================================================


@pytest.fixture()
def dolu(db: Session) -> Session:
    """YAZ=100, BIL=60, HUK=25 → MUH=160, üniversite=185."""
    for yil, adet in ((2022, 10), (2023, 20), (2024, 30), (2025, 40)):
        _yks(db, "YAZ-PR", yil, adet)
    for yil, adet in ((2024, 25), (2025, 35)):
        _yks(db, "BIL-PR", yil, adet)
    _yks(db, "HUK-PR", 2025, 25)
    db.commit()
    return db


def test_program_kapsami_yalnizca_kendi_sayisi(dolu: Session) -> None:
    kapsam = resolve(dolu, academic_program_id=_pid(dolu, "YAZ-PR"))
    assert student_count.total_for_scope(dolu, kapsam) == 100


def test_bolum_kapsami_kendi_programlarini_toplar(dolu: Session) -> None:
    bolum_id = dolu.execute(
        select(Department.id).where(Department.code == "YAZMUH")
    ).scalar_one()
    assert student_count.total_for_scope(
        dolu, resolve(dolu, department_id=bolum_id)) == 100


def test_fakulte_kapsami_torun_programlari_toplar(dolu: Session) -> None:
    """MÜHENDİSLİK = YAZ(100) + BIL(60) = 160. HUKUK karışmamalı."""
    fak_id = dolu.execute(
        select(Faculty.id).where(Faculty.code == "MUH")
    ).scalar_one()
    assert student_count.total_for_scope(
        dolu, resolve(dolu, faculty_id=fak_id)) == 160


def test_universite_kapsami_tum_akademik_programlari_toplar(
    dolu: Session
) -> None:
    assert student_count.total_for_scope(dolu, resolve(dolu)) == 185


def test_fakulte_toplami_programlarin_toplamina_esittir(dolu: Session) -> None:
    """Toplama TEK yerde yapılır; üst düzeyde ayrı bir sayı tutulmaz."""
    fak_id = dolu.execute(
        select(Faculty.id).where(Faculty.code == "MUH")
    ).scalar_one()
    kapsam = resolve(dolu, faculty_id=fak_id)
    parcalar = sum(
        k.student_count for k in student_count.program_counts(dolu, kapsam).values()
        if k.student_count is not None
    )
    assert student_count.total_for_scope(dolu, kapsam) == parcalar


def test_veri_hic_yoksa_toplam_none(db: Session) -> None:
    """Hiç veri yokken 0 döndürmek, veri yokluğunu gizlemek olurdu."""
    assert student_count.total_for_scope(db, resolve(db)) is None


# ==========================================================================
# 4. Analitik ve API yüzeyleri bu sayıyı kullanıyor
# ==========================================================================


def test_program_analitigi_resmi_sayiyi_gosterir(dolu: Session) -> None:
    satirlar = ogrenci.build_program_analytics(
        dolu, scope=resolve(dolu, academic_program_id=_pid(dolu, "YAZ-PR"))
    )
    assert [r.total_students for r in satirlar] == [100]


def test_genel_ozet_universite_toplamini_gosterir(dolu: Session) -> None:
    assert ogrenci.build_overview(dolu, scope=resolve(dolu)).total_students == 185


def test_genel_ozet_fakulte_kapsaminda_daralir(dolu: Session) -> None:
    fak_id = dolu.execute(
        select(Faculty.id).where(Faculty.code == "MUH")
    ).scalar_one()
    ozet = ogrenci.build_overview(dolu, scope=resolve(dolu, faculty_id=fak_id))
    assert ozet.total_students == 160


def test_egitim_analitigi_program_metriginde_kullanilir(dolu: Session) -> None:
    """`education-analytics` snapshot ister; snapshot da ÖSYM'den gelir."""
    dolu.add(ProgramEnrollmentSnapshot(
        academic_program_id=_pid(dolu, "YAZ-PR"), academic_year=YIL,
        quota=40, enrolled_student_count=40,
    ))
    dolu.commit()
    metrikler = egitim.get_program_metrics(dolu, YIL)
    yaz = [m for m in metrikler if m["program_code"] == "YAZ-PR"]
    assert yaz and yaz[0]["total_students"] == 100


# ==========================================================================
# 5. Saklanan sütun ve izlenebilirlik
# ==========================================================================


def test_saklanan_sutun_hesapla_ayni(dolu: Session) -> None:
    student_count.refresh_stored_counts(dolu)
    dolu.commit()
    p = dolu.execute(
        select(AcademicProgram).where(AcademicProgram.code == "YAZ-PR")
    ).scalar_one()
    assert p.student_count == 100
    assert p.student_count_source_method == "yks_recent_4_cohorts"
    assert p.student_count_year_span == "2022-2025"


def test_kaynak_yontemi_sabittir(dolu: Session) -> None:
    """Etiket iç izlenebilirlik içindir; değeri sözleşmedir."""
    assert student_count.OFFICIAL_SOURCE_METHOD == "yks_recent_4_cohorts"
    assert student_count.RECENT_COHORT_YEARS == 4


def test_veri_olmayan_programin_sutunu_null_kalir(dolu: Session) -> None:
    student_count.refresh_stored_counts(dolu)
    dolu.commit()
    p = dolu.execute(
        select(AcademicProgram).where(AcademicProgram.code == "YOK-PR")
    ).scalar_one()
    assert p.student_count is None
    assert p.student_count_source_method is None


def test_yeniden_hesaplama_idempotenttir(dolu: Session) -> None:
    student_count.refresh_stored_counts(dolu)
    dolu.commit()
    ikinci = student_count.refresh_stored_counts(dolu)
    dolu.commit()
    assert ikinci["guncellendi"] == 0
    assert ikinci["degismedi"] == 3


def test_ham_yks_satirlari_korunur(dolu: Session) -> None:
    """Özet üretmek ham veriyi tüketmez."""
    student_count.refresh_stored_counts(dolu)
    dolu.commit()
    assert len(dolu.execute(select(YksPlacementRecord)).scalars().all()) == 7


# ==========================================================================
# 6. Kullanıcıya "tahmini" denmez
# ==========================================================================


def test_kullaniciya_donen_alanlarda_tahmin_ibaresi_yok(dolu: Session) -> None:
    """Sayı kurumun kabul ettiği resmî sayıdır; çekince ibaresi taşımaz."""
    from app.schemas.academic_program import AcademicProgramResponse

    student_count.refresh_stored_counts(dolu)
    dolu.commit()
    p = dolu.execute(
        select(AcademicProgram).where(AcademicProgram.code == "YAZ-PR")
    ).scalar_one()
    cikti = AcademicProgramResponse.model_validate(p).model_dump()

    assert cikti["student_count"] == 100
    metin = " ".join(str(v) for v in cikti.values()).lower()
    for yasak in ("tahmin", "yaklaşık", "estimate", "approx", "öngörü"):
        assert yasak not in metin


def test_izlenebilirlik_alanlari_ayri_durur(dolu: Session) -> None:
    """Kaynak bilgisi VARDIR ama `student_count` alanına karışmaz."""
    from app.schemas.academic_program import AcademicProgramResponse

    student_count.refresh_stored_counts(dolu)
    dolu.commit()
    p = dolu.execute(
        select(AcademicProgram).where(AcademicProgram.code == "YAZ-PR")
    ).scalar_one()
    cikti = AcademicProgramResponse.model_validate(p).model_dump()
    assert cikti["student_count_source_method"] == "yks_recent_4_cohorts"
    assert isinstance(cikti["student_count"], int)
