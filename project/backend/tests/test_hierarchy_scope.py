"""HİYERARŞİ ve KAPSAM regresyon testleri.

İKİ HATA SABİTLENİYOR
---------------------
1. **Rektörlük fakülte değildir.** `faculties` tablosu üniversitenin bütün
   üst düzey birimlerini tutuyor; hepsini "fakülte" diye göstermek fakülte
   sayısını yanlış çıkarıyor ve akademik karşılaştırmalara idari birim
   sokuyordu.

2. **Kapsam sızıntısı.** Bir programa inildiğinde grafikler ve tablolar
   kardeş programların verisini göstermeye devam ediyordu. Kök sebep:
   arayüz `?faculty=KOD` gönderiyordu, uçlar `faculty_id` bekliyordu ve
   FastAPI tanımadığı parametreyi sessizce atıyordu.

Bu dosya KENDİ veritabanını kurar. Ortak demo fixture'ı kullanılsaydı
"kaç satır döndü" gibi sayımlar başka modüllerin verisiyle kirlenirdi.
Kurulan ağaç kasten GERÇEK veriye benzetildi (YAZMUH, REKTÖRLÜK, MYO).
"""

from decimal import Decimal
from typing import Iterator

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import (
    AcademicProgram,
    AcademicStaff,
    AcademicSuccessRecord,
    Department,
    DepartmentBudget,
    Faculty,
    FinancialPeriod,
    PhysicalFacility,
    ProgramEnrollmentSnapshot,
    Student,
)
from app.services import (
    academic_staff_service,
    decision_analytics_service,
    physical_resources_service,
)
from app.services import academic_success_service as basari
from app.services import education_analytics_service as egitim
from app.services import finance_service
from app.services import student_analytics_service as ogrenci
from app.services.scope import academic_faculty_ids, resolve
from app.services.unit_types import (
    ADMINISTRATIVE,
    FACULTY,
    VOCATIONAL_SCHOOL,
    classify_unit,
)

YIL = "2025-2026"


# --------------------------------------------------------------------------
# Fixture — gerçek yapıya benzeyen küçük bir üniversite
# --------------------------------------------------------------------------


@pytest.fixture()
def db() -> Iterator[Session]:
    """MUHMIM(2 bölüm) + HUKUK(1 bölüm) + MYO + REKTÖRLÜK.

    Her programın kendi öğrencisi, kontenjanı, başarı kaydı ve mekânı var;
    böylece "kardeş verisi sızdı mı?" sorusu SAYIYLA yanıtlanabiliyor.
    """
    # Bellek içi veritabanı — bkz. test_ekdata_import.py'daki aynı gerekçe.
    motor = create_engine(
        "sqlite://", future=True,
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(motor)
    s = sessionmaker(bind=motor, future=True)()

    # --- birimler ---
    muhmim = Faculty(name="MÜHENDİSLİK VE MİMARLIK FAKÜLTESİ", code="MUHMIM",
                     unit_type=FACULTY, is_active=True)
    hukuk = Faculty(name="HUKUK FAKÜLTESİ", code="HUKUK",
                    unit_type=FACULTY, is_active=True)
    myo = Faculty(name="MESLEK YÜKSEKOKULU", code="MESLEK",
                  unit_type=VOCATIONAL_SCHOOL, is_active=True)
    rektorluk = Faculty(name="REKTÖRLÜK", code="REKTORLUK",
                        unit_type=ADMINISTRATIVE, is_active=True)
    s.add_all([muhmim, hukuk, myo, rektorluk])
    s.flush()

    yazmuh = Department(name="YAZILIM MÜHENDİSLİĞİ BÖLÜMÜ", code="YAZMUH",
                        faculty_id=muhmim.id, is_active=True)
    bilmuh = Department(name="BİLGİSAYAR MÜHENDİSLİĞİ BÖLÜMÜ", code="BILMUH",
                        faculty_id=muhmim.id, is_active=True)
    kamhuk = Department(name="KAMU HUKUKU BÖLÜMÜ", code="KAMHUK",
                        faculty_id=hukuk.id, is_active=True)
    myobil = Department(name="BİLGİSAYAR TEKNOLOJİLERİ BÖLÜMÜ", code="BILTEK",
                        faculty_id=myo.id, is_active=True)
    idari = Department(name="REKTÖRLÜK", code="REKTORLUK-B",
                       faculty_id=rektorluk.id, is_active=True)
    s.add_all([yazmuh, bilmuh, kamhuk, myobil, idari])
    s.flush()

    # Program başına farklı sayılar: karışırsa test hemen yakalar.
    tanimlar = [
        ("YAZMUH-LIS", "Yazılım Mühendisliği", yazmuh, 100, 90, 9),
        ("BILMUH-LIS", "Bilgisayar Mühendisliği", bilmuh, 200, 150, 15),
        ("KAMHUK-LIS", "Kamu Hukuku", kamhuk, 300, 210, 21),
        ("BILTEK-ON", "Bilgisayar Teknolojileri", myobil, 400, 320, 32),
    ]
    programlar = {}
    for kod, ad, bolum, kontenjan, yerlesen, ogrenci_sayisi in tanimlar:
        p = AcademicProgram(
            name=ad, code=kod, department_id=bolum.id,
            degree_level="Lisans", duration_years=4, quota=kontenjan,
            is_active=True,
        )
        s.add(p)
        s.flush()
        programlar[kod] = p

        s.add(ProgramEnrollmentSnapshot(
            academic_program_id=p.id, academic_year=YIL,
            quota=kontenjan, enrolled_student_count=yerlesen,
        ))
        s.add(AcademicSuccessRecord(
            academic_program_id=p.id, academic_year=YIL,
            measured_student_count=ogrenci_sayisi,
            course_pass_rate=Decimal("80.00"),
            average_success_score=Decimal("70.00"),
            dropout_rate=Decimal("5.00"),
            graduation_rate=Decimal("75.00"),
        ))
        for i in range(ogrenci_sayisi):
            s.add(Student(
                student_number=f"{kod}-{i:04d}",
                first_name="Ad", last_name="Soyad",
                enrollment_year=2022, academic_program_id=p.id,
                current_status="active", expected_graduation_year=2026,
            ))

    # --- personel: bölüm başına farklı sayı ---
    for bolum, adet in ((yazmuh, 3), (bilmuh, 7), (kamhuk, 5), (idari, 4)):
        for i in range(adet):
            s.add(AcademicStaff(
                staff_number=f"{bolum.code}-P{i}", first_name="Ög", last_name="Üye",
                title="Dr. Öğr. Üyesi", department_id=bolum.id,
                academic_year=YIL, is_active=True,
            ))

    # --- mekânlar: bölüm başına farklı kapasite ---
    for bolum, kap in ((yazmuh, 50), (bilmuh, 120), (kamhuk, 200)):
        s.add(PhysicalFacility(
            code=f"{bolum.code}-D1", name=f"{bolum.code} Derslik",
            facility_type="classroom", capacity=kap, occupied=kap // 2,
            department_id=bolum.id, is_active=True,
        ))
    # Bölümü olmayan ORTAK alan: dar kapsamda görünmemeli.
    s.add(PhysicalFacility(
        code="ORTAK-1", name="Merkezi Amfi", facility_type="classroom",
        capacity=1000, occupied=500, department_id=None, is_active=True,
    ))

    # --- mali dönem ve bölüm bütçeleri ---
    donem = FinancialPeriod(academic_year=YIL, total_students=572,
                            total_graduates=100)
    s.add(donem)
    s.flush()
    for bolum, gelir in ((yazmuh, 1_000_000), (bilmuh, 2_000_000),
                         (kamhuk, 3_000_000)):
        s.add(DepartmentBudget(
            financial_period_id=donem.id, department_id=bolum.id,
            student_count=10, revenue=Decimal(gelir),
            expenditure=Decimal(gelir) / 2, allocated_budget=Decimal(gelir),
        ))

    s.commit()
    try:
        yield s
    finally:
        s.close()
        motor.dispose()


def _kimlik(db: Session, model, kod: str) -> int:
    return db.execute(select(model.id).where(model.code == kod)).scalar_one()


# ==========================================================================
# 1. REKTÖRLÜK FAKÜLTE DEĞİLDİR
# ==========================================================================


def test_rektorluk_idari_birim_olarak_siniflanir() -> None:
    """Sınıflandırma ada bakar ama sonuç sütuna YAZILIR; sonraki filtreler
    ad değil `unit_type` kullanır."""
    assert classify_unit("REKTÖRLÜK") == ADMINISTRATIVE
    assert classify_unit("Genel Sekreterlik") == ADMINISTRATIVE
    assert classify_unit("MESLEK YÜKSEKOKULU") == VOCATIONAL_SCHOOL
    assert classify_unit("LİSANSÜSTÜ EĞİTİM ENSTİTÜSÜ") == "INSTITUTE"
    assert classify_unit("MÜHENDİSLİK VE MİMARLIK FAKÜLTESİ") == FACULTY


def test_rektorluk_akademik_birim_listesinde_yok(db: Session) -> None:
    akademik = set(academic_faculty_ids(db))
    assert _kimlik(db, Faculty, "REKTORLUK") not in akademik
    # MYO akademiktir: idari değildir, yalnızca fakülte de değildir.
    assert _kimlik(db, Faculty, "MESLEK") in akademik
    assert _kimlik(db, Faculty, "MUHMIM") in akademik
    assert len(akademik) == 3


def test_fakulte_karsilastirmasinda_rektorluk_gorunmez(db: Session) -> None:
    """Üniversite seviyesindeki fakülte kırılımı idari birimi içermez.

    Rektörlük'ün programı ve öğrencisi yoktur; "fakülte" diye grafiğe
    girseydi %0 dolulukla listeyi yanıltırdı.
    """
    satirlar = ogrenci.build_faculty_analytics(db, scope=resolve(db))
    adlar = {r.faculty_name for r in satirlar}
    assert "REKTÖRLÜK" not in adlar
    assert "MÜHENDİSLİK VE MİMARLIK FAKÜLTESİ" in adlar


def test_idari_birimin_personeli_akademik_kadroya_karismaz(db: Session) -> None:
    """Rektörlük'e bağlı 4 kişi akademik fakülte kapsamlarında sayılmaz."""
    muhmim = resolve(db, faculty_id=_kimlik(db, Faculty, "MUHMIM"))
    kadro = academic_staff_service.list_staff(db, limit=1000, scope=muhmim)
    assert len(kadro) == 10  # 3 YAZMUH + 7 BILMUH, idari 4 kişi yok


# ==========================================================================
# 2. KAPSAM ÇÖZÜCÜ — kimlik tabanlı, tutarsızlığı reddeder
# ==========================================================================


def test_program_kapsami_yalnizca_kendi_kimligini_tasir(db: Session) -> None:
    yazmuh_lis = _kimlik(db, AcademicProgram, "YAZMUH-LIS")
    k = resolve(db, academic_program_id=yazmuh_lis)
    assert k.level == "program"
    assert k.program_ids == {yazmuh_lis}
    # Üst seviyeler TÜRETİLİR; istemcinin göndermesine gerek yok.
    assert k.department_id == _kimlik(db, Department, "YAZMUH")
    assert k.faculty_id == _kimlik(db, Faculty, "MUHMIM")


def test_fakulte_kapsami_tum_torunlari_kapsar(db: Session) -> None:
    k = resolve(db, faculty_id=_kimlik(db, Faculty, "MUHMIM"))
    assert k.department_ids == {
        _kimlik(db, Department, "YAZMUH"), _kimlik(db, Department, "BILMUH")
    }
    assert k.program_codes == {"YAZMUH-LIS", "BILMUH-LIS"}
    assert "KAMHUK-LIS" not in k.program_codes


def test_tutarsiz_kapsam_sessizce_duzeltilmez(db: Session) -> None:
    """YAZMUH programı HUKUK fakültesine aitmiş gibi sorulursa 400.

    "En yakın kapsama düşürmek" kullanıcıya yanlış veriyi doğru başlıkla
    gösterirdi; bu yüzden reddediliyor.
    """
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as hata:
        resolve(
            db,
            faculty_id=_kimlik(db, Faculty, "HUKUK"),
            academic_program_id=_kimlik(db, AcademicProgram, "YAZMUH-LIS"),
        )
    assert hata.value.status_code == 400


def test_universite_kapsami_filtre_uygulamaz(db: Session) -> None:
    k = resolve(db)
    assert k.is_university
    assert k.program_ids is None  # None = "filtre yok", boş küme değil


# ==========================================================================
# 3. YAZMUH SAYFASINDA YALNIZCA YAZMUH VERİSİ
# ==========================================================================


@pytest.fixture()
def yazmuh(db: Session):
    """YAZMUH programının kapsamı — testlerin ortak girdisi."""
    return resolve(db, academic_program_id=_kimlik(db, AcademicProgram, "YAZMUH-LIS"))


def test_ogrenci_analitigi_program_kapsaminda_tek_satir(db: Session, yazmuh) -> None:
    satirlar = ogrenci.build_program_analytics(db, scope=yazmuh)
    assert [r.program_code for r in satirlar] == ["YAZMUH-LIS"]


def test_ogrenci_ozeti_kardes_ogrencileri_saymaz(db: Session, yazmuh) -> None:
    """YAZMUH'un 9 öğrencisi var; toplam 77 öğrencinin hiçbiri sızmamalı."""
    ozet = ogrenci.build_overview(db, scope=yazmuh)
    assert ozet.total_students == 9


def test_bolum_kirilimi_kardes_bolumu_gostermez(db: Session, yazmuh) -> None:
    satirlar = ogrenci.build_department_analytics(db, scope=yazmuh)
    assert [r.department_name for r in satirlar] == ["YAZILIM MÜHENDİSLİĞİ BÖLÜMÜ"]


def test_egitim_analitigi_program_kapsaminda_tek_program(db: Session, yazmuh) -> None:
    metrikler = egitim.get_program_metrics(db, YIL, scope=yazmuh)
    assert [m["program_code"] for m in metrikler] == ["YAZMUH-LIS"]


def test_egitim_ozeti_yalnizca_secili_programin_kontenjani(db: Session, yazmuh) -> None:
    ozet = egitim.get_university_overview(db, YIL, scope=yazmuh)
    assert ozet["total_quota"] == 100  # BILMUH'un 200'ü karışmadı


def test_akademik_basari_program_kapsaminda_tek_satir(db: Session, yazmuh) -> None:
    satirlar = basari.by_program(db, YIL, scope=yazmuh)
    assert [r["program_code"] for r in satirlar] == ["YAZMUH-LIS"]


def test_akademik_basari_ozeti_kardesi_agirliklandirmaz(db: Session, yazmuh) -> None:
    ozet = basari.university_overview(db, YIL, scope=yazmuh)
    assert ozet["measured_student_count"] == 9


def test_personel_program_kapsaminda_tahsise_bakar(db: Session, yazmuh) -> None:
    """Program seviyesinde kadro tahsisi yoksa BOŞ döner.

    Bölümün 3 kişilik kadrosunu programın kadrosu gibi göstermek, üst
    birimin verisini alt birime taşımak olurdu.
    """
    kadro = academic_staff_service.list_staff(db, limit=1000, scope=yazmuh)
    assert kadro == []


def test_program_panelleri_bolum_kadrosuna_dusmez(db: Session, yazmuh) -> None:
    """Programda bölüm personeli ve ders geçmişi 0 gibi de sunulmaz."""
    kadro = decision_analytics_service.staffing_overview(db, yazmuh, YIL)
    assert kadro["available"] is False
    assert kadro["academic_staff_count"] is None
    # Fikstürde yalnız cari öğrenci satırları var; tarihsel YKS kaydı yok.
    # Açık 2025 seçimi cari satırlara geri düşmemeli.
    assert kadro["student_count"] is None

    assert decision_analytics_service.teaching_load_trend(
        db, yazmuh, YIL) == []
    yogunlasma = decision_analytics_service.course_concentration(
        db, yazmuh, YIL)
    assert yogunlasma["available"] is False
    assert "program" in yogunlasma["note"]
    program_kadrosu = decision_analytics_service.staffing_by_program(
        db, yazmuh, YIL)
    assert len(program_kadrosu) == 1
    assert program_kadrosu[0]["academic_staff_count"] is None
    assert program_kadrosu[0]["staff_scope"] == "unavailable"


def test_program_panelleri_bolum_mekanina_dusmez(db: Session, yazmuh) -> None:
    assert physical_resources_service.list_facilities(
        db, scope=yazmuh) == []


def test_kapasite_program_kapsaminda_ortak_alani_saymaz(db: Session, yazmuh) -> None:
    """Program tahsisi yoksa bölümün 50 kişilik dersliği devralınmamalı."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as hata:
        physical_resources_service.capacity_overview(db, scope=yazmuh)
    assert hata.value.status_code == 404


def test_finans_program_seviyesinde_veri_olmadigini_soyler(db: Session, yazmuh) -> None:
    """Mali veri program seviyesinde tutulmuyor → üniversite toplamı DEĞİL, 404."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as hata:
        finance_service.financial_summary(db, YIL, scope=yazmuh)
    assert hata.value.status_code == 404
    assert "program seviyesinde" in hata.value.detail


# ==========================================================================
# 4. FAKÜLTE SAYFASI YALNIZCA KENDİ TORUNLARINI GÖSTERİR
# ==========================================================================


@pytest.fixture()
def muhmim(db: Session):
    return resolve(db, faculty_id=_kimlik(db, Faculty, "MUHMIM"))


def test_fakulte_sayfasi_yalnizca_kendi_programlarini_listeler(
    db: Session, muhmim
) -> None:
    kodlar = {r.program_code for r in ogrenci.build_program_analytics(db, scope=muhmim)}
    assert kodlar == {"YAZMUH-LIS", "BILMUH-LIS"}


def test_fakulte_sayfasi_baska_fakultenin_bolumunu_gostermez(
    db: Session, muhmim
) -> None:
    adlar = {r.department_name
             for r in ogrenci.build_department_analytics(db, scope=muhmim)}
    assert adlar == {"YAZILIM MÜHENDİSLİĞİ BÖLÜMÜ", "BİLGİSAYAR MÜHENDİSLİĞİ BÖLÜMÜ"}


def test_fakulte_basari_ozeti_yalnizca_torunlardan_toplanir(
    db: Session, muhmim
) -> None:
    ozet = basari.university_overview(db, YIL, scope=muhmim)
    assert ozet["measured_student_count"] == 9 + 15


def test_fakulte_kapasitesi_kardes_fakultenin_dersligini_saymaz(
    db: Session, muhmim
) -> None:
    ozet = physical_resources_service.capacity_overview(db, scope=muhmim)
    assert ozet["total_capacity"] == 50 + 120  # KAMHUK'un 200'ü ve ortak alan yok


def test_fakulte_butcesi_yalnizca_kendi_bolumlerini_toplar(
    db: Session, muhmim
) -> None:
    butceler = finance_service.list_department_budgets(db, YIL, scope=muhmim)
    assert len(butceler) == 2
    ozet = finance_service.financial_summary(db, YIL, scope=muhmim)
    # 1.000.000 + 2.000.000 = 3 milyon USD; KAMHUK'un 3.000.000'u yok.
    assert ozet["total_revenue"] == Decimal("3.00")


def test_fakulte_personeli_kardes_fakulteden_kisi_almaz(
    db: Session, muhmim
) -> None:
    kadro = academic_staff_service.list_staff(db, limit=1000, scope=muhmim)
    assert {k.staff_number.split("-")[0] for k in kadro} == {"YAZMUH", "BILMUH"}


# ==========================================================================
# 5. BÖLÜM KAPSAMI
# ==========================================================================


def test_bolum_kapsami_yalnizca_kendi_programlarini_gosterir(db: Session) -> None:
    k = resolve(db, department_id=_kimlik(db, Department, "BILMUH"))
    kodlar = {r.program_code for r in ogrenci.build_program_analytics(db, scope=k)}
    assert kodlar == {"BILMUH-LIS"}


def test_bolum_kapsaminda_kadro_bolumden_okunur(db: Session) -> None:
    """Bölüm seviyesinde kadro TAHSİSE değil, bölüm bağlantısına bakar."""
    k = resolve(db, department_id=_kimlik(db, Department, "BILMUH"))
    assert len(academic_staff_service.list_staff(db, limit=1000, scope=k)) == 7


# ==========================================================================
# 6. ÜNİVERSİTE SEVİYESİ KARŞILAŞTIRMA HÂLÂ ÇALIŞIYOR
# ==========================================================================


def test_universite_seviyesinde_tum_akademik_programlar_gorunur(db: Session) -> None:
    kodlar = {r.program_code for r in ogrenci.build_program_analytics(db, scope=resolve(db))}
    assert kodlar == {"YAZMUH-LIS", "BILMUH-LIS", "KAMHUK-LIS", "BILTEK-ON"}


def test_universite_ozeti_tum_ogrencileri_toplar(db: Session) -> None:
    ozet = ogrenci.build_overview(db, scope=resolve(db))
    assert ozet.total_students == 9 + 15 + 21 + 32


def test_universite_kapasitesi_ortak_alani_da_icerir(db: Session) -> None:
    """Kapsam yokken merkezi amfi sayılır — dar kapsamda sayılmaz."""
    ozet = physical_resources_service.capacity_overview(db, scope=resolve(db))
    assert ozet["total_capacity"] == 50 + 120 + 200 + 1000


def test_universite_mali_ozeti_kurum_geneli_kalir(db: Session) -> None:
    ozet = finance_service.financial_summary(db, YIL, scope=resolve(db))
    # Üniversite özeti kalemlerden gelir; bölüm bütçelerinden değil.
    assert ozet["total_students"] == 572


def test_kapsam_verilmezse_davranis_degismez(db: Session) -> None:
    """Geriye dönük uyum: `scope=None` ile `scope=resolve(db)` aynı sonucu verir."""
    kapsamsiz = ogrenci.build_program_analytics(db)
    universite = ogrenci.build_program_analytics(db, scope=resolve(db))
    assert [r.program_code for r in kapsamsiz] == [r.program_code for r in universite]
