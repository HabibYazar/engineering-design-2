"""YABANCI ÖĞRENCİ VERİ KÜMESİ — aktarım, kapsam, dönem ve oran kuralı.

Kaynak: `data/ekdata/ankara_bilim_yabanci_ogrenci_2025_2026.xlsx`
    15 program satırı · toplam 233
    Mühendislik ve Mimarlık 98 · İnsan ve Toplum 79
    Güzel Sanatlar 31 · Meslek Yüksekokulu 25

Testlerin koruduğu kurallar:
  · kaynak toplamı = yazılan toplam (sessiz kayıp yok)
  · eşleşmeyen satır DÜŞMEZ, fakülte düzeyinde saklanır
  · yeni fakülte/bölüm/program OLUŞTURULMAZ
  · aktarım idempotenttir
  · oran YALNIZCA aynı kapsam + aynı yıl + uyumlu nüfus tanımı varsa
  · veri kümesinin yılı dışında bir dönem seçilirse değer TEKRARLANMAZ
  · kapsam izolasyonu: kardeş fakülte sızmaz
"""

from pathlib import Path
from typing import Iterator

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import import_foreign_students as aktar
from app.database import Base
from app.models import AcademicProgram, Department, Faculty, UniversityStudentHeadcount
from app.models.student_demographic import (
    DIMENSION_FOREIGN,
    RESOLUTION_FACULTY,
    RESOLUTION_PROGRAM,
    StudentDemographicCount,
)
from app.models.university_headcount import HOME_UNIVERSITY
from app.services import foreign_student_service as yabanci
from app.services.scope import resolve
from app.services.unit_types import FACULTY

KAYNAK = (Path(__file__).resolve().parents[2] / "data" / "ekdata"
          / "ankara_bilim_yabanci_ogrenci_2025_2026.xlsx")
DAMGA = "Kaynak: YÖK Akademik toplayıcısı"

#: Kaynağın beyan ettiği fakülte toplamları — testin çapası.
BEKLENEN_FAKULTE = {
    "Mühendislik ve Mimarlık Fakültesi": 98,
    "İnsan ve Toplum Bilimleri Fakültesi": 79,
    "Güzel Sanatlar ve Tasarım Fakültesi": 31,
    "Meslek Yüksekokulu / Önlisans": 25,
}
BEKLENEN_TOPLAM = 233


@pytest.fixture()
def db() -> Iterator[Session]:
    """Kurumun GERÇEK hiyerarşisinin ilgili parçası."""
    motor = create_engine("sqlite://", future=True,
                          connect_args={"check_same_thread": False},
                          poolclass=StaticPool)
    Base.metadata.create_all(motor)
    s = sessionmaker(bind=motor, future=True)()

    fakulteler = {}
    for ad, kod in (("MÜHENDİSLİK VE MİMARLIK FAKÜLTESİ", "MUHMIM"),
                    ("İNSAN VE TOPLUM BİLİMLERİ FAKÜLTESİ", "INSTOPBIL"),
                    ("GÜZEL SANATLAR VE TASARIM FAKÜLTESİ", "GUZSANTAS"),
                    ("MESLEK YÜKSEKOKULU", "MESLEK"),
                    ("HUKUK FAKÜLTESİ", "HUKUK")):
        f = Faculty(name=ad, code=kod, unit_type=FACULTY,
                    description=DAMGA, is_active=True)
        s.add(f)
        fakulteler[kod] = f
    s.flush()

    # Kaynakla eşleşecek programlar + kasıtlı olarak BAŞKA fakültede
    # duran "İç Mimarlık" (gerçek hiyerarşideki durum).
    tanim = [
        ("YAZILIM MÜHENDİSLİĞİ BÖLÜMÜ", "YAZILIM MÜHENDİSLİĞİ PR.", "MUHMIM"),
        ("BİLGİSAYAR MÜHENDİSLİĞİ BÖLÜMÜ", "BİLGİSAYAR MÜHENDİSLİĞİ PR.", "MUHMIM"),
        ("ENDÜSTRİ MÜHENDİSLİĞİ BÖLÜMÜ", "ENDÜSTRİ MÜHENDİSLİĞİ PR.", "MUHMIM"),
        ("YÖNETİM BİLİŞİM SİSTEMLERİ BÖLÜMÜ", "YÖNETİM BİLİŞİM SİSTEMLERİ PR.", "INSTOPBIL"),
        ("PSİKOLOJİ BÖLÜMÜ", "PSİKOLOJİ PR.", "INSTOPBIL"),
        ("İŞLETME BÖLÜMÜ", "İŞLETME PR.", "INSTOPBIL"),
        ("SİYASET BİLİMİ VE KAMU YÖNETİMİ BÖLÜMÜ",
         "SİYASET BİLİMİ VE KAMU YÖNETİMİ PR.", "INSTOPBIL"),
        ("MÜTERCİM VE TERCÜMANLIK BÖLÜMÜ", "İNGİLİZCE MÜTERCİM VE TERCÜMANLIK", "INSTOPBIL"),
        ("BİLGİSAYAR TEKNOLOJİLERİ BÖLÜMÜ", "BİLGİSAYAR PROGRAMCILIĞI", "MESLEK"),
        ("ELEKTRONİK VE OTOMASYON BÖLÜMÜ",
         "İNSANSIZ HAVA ARACI TEKNOLOJİSİ VE OPERATÖRLÜĞÜ PR.", "MESLEK"),
        # ÇELİŞKİ: kaynak bunu Mühendislik altında veriyor.
        ("İÇ MİMARLIK VE ÇEVRE TASARIMI BÖLÜMÜ",
         "İÇ MİMARLIK VE ÇEVRE TASARIMI PR.", "GUZSANTAS"),
    ]
    for bolum_ad, program_ad, fkod in tanim:
        b = Department(name=bolum_ad, code=bolum_ad[:12],
                       faculty_id=fakulteler[fkod].id,
                       description=DAMGA, is_active=True)
        s.add(b)
        s.flush()
        s.add(AcademicProgram(name=program_ad, code=program_ad[:12],
                              department_id=b.id, degree_level="Lisans",
                              description=DAMGA, is_active=True))

    # Oranın paydası: YÖK kayıtlı öğrenci sayısı (aynı yıl).
    for yil, sayi in (("2024-2025", 3135), ("2025-2026", 3626)):
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


@pytest.fixture()
def yuklu(db: Session) -> Session:
    aktar.YabanciOgrenciAktarimi(db, KAYNAK).aktar()
    return db


# ==========================================================================
# 1. AKTARIM
# ==========================================================================


def test_kaynak_dosyasi_var(db: Session) -> None:
    assert KAYNAK.exists(), f"Kaynak dosya yok: {KAYNAK}"


def test_kaynak_toplami_233_ve_hicbir_satir_kaybolmuyor(yuklu: Session) -> None:
    toplam = yuklu.execute(
        select(func.sum(StudentDemographicCount.student_count))
        .where(StudentDemographicCount.dimension == DIMENSION_FOREIGN)
    ).scalar_one()
    satir = yuklu.execute(
        select(func.count()).select_from(StudentDemographicCount)).scalar_one()
    assert toplam == BEKLENEN_TOPLAM
    assert satir == 15, "kaynak 15 program satırı taşıyor; hiçbiri düşmemeli"


def test_fakulte_toplamlari_kaynakla_birebir(yuklu: Session) -> None:
    """Fakülte atıfı KAYNAĞINDIR — hiyerarşi farklı dese bile."""
    satirlar = yuklu.execute(
        select(StudentDemographicCount.source_faculty_label,
               func.sum(StudentDemographicCount.student_count))
        .group_by(StudentDemographicCount.source_faculty_label)).all()
    assert {ad: int(n) for ad, n in satirlar} == BEKLENEN_FAKULTE


def test_yeni_hiyerarsi_varligi_OLUSTURULMAZ(db: Session) -> None:
    """"(İngilizce)" eki veya MYO adlandırması yüzünden kopya açılmaz."""
    once = tuple(db.execute(select(func.count()).select_from(m)).scalar_one()
                 for m in (Faculty, Department, AcademicProgram))
    aktar.YabanciOgrenciAktarimi(db, KAYNAK).aktar()
    sonra = tuple(db.execute(select(func.count()).select_from(m)).scalar_one()
                  for m in (Faculty, Department, AcademicProgram))
    assert once == sonra


def test_aktarim_idempotent(db: Session) -> None:
    a1 = aktar.YabanciOgrenciAktarimi(db, KAYNAK)
    a1.aktar()
    a2 = aktar.YabanciOgrenciAktarimi(db, KAYNAK)
    a2.aktar()
    assert a2.sayac["eklendi"] == 0
    assert a2.sayac["guncellendi"] == 0
    assert a2.sayac["degismedi"] == 15
    assert db.execute(
        select(func.sum(StudentDemographicCount.student_count))
    ).scalar_one() == BEKLENEN_TOPLAM


def test_fakulte_celiskisi_kayda_gecer_program_baglanmaz(yuklu: Session) -> None:
    """İç Mimarlık: kaynak Mühendislik der, hiyerarşi Güzel Sanatlar.

    Satır KAYNAĞIN fakültesinde kalır (98 toplamı korunur), program
    kimliği bağlanmaz ve çelişki `resolution_note` içinde saklanır.
    Programı sessizce taşımak da toplamı bozmak da uydurma olurdu.
    """
    r = yuklu.execute(
        select(StudentDemographicCount).where(
            StudentDemographicCount.source_program_label.like("İç Mimarlık%"))
    ).scalar_one()
    muh = yuklu.execute(
        select(Faculty).where(Faculty.code == "MUHMIM")).scalar_one()
    assert r.faculty_id == muh.id
    assert r.academic_program_id is None
    assert r.resolution == RESOLUTION_FACULTY
    assert "hiyerarşide" in (r.resolution_note or "")


def test_eslesmeyen_satir_DUSMEZ(yuklu: Session) -> None:
    """Hiyerarşide karşılığı olmayan program fakülte düzeyinde saklanır."""
    r = yuklu.execute(
        select(StudentDemographicCount).where(
            StudentDemographicCount.source_program_label.like("Dijital Oyun%"))
    ).scalar_one()
    assert r.student_count == 14
    assert r.academic_program_id is None
    assert r.faculty_id is not None
    assert r.resolution == RESOLUTION_FACULTY


def test_ingilizce_eki_program_eslestirmesini_bozmaz(yuklu: Session) -> None:
    r = yuklu.execute(
        select(StudentDemographicCount).where(
            StudentDemographicCount.source_program_label.like("Yazılım%"))
    ).scalar_one()
    assert r.resolution == RESOLUTION_PROGRAM
    assert r.academic_program_id is not None
    assert r.student_count == 38


# ==========================================================================
# 2. ORAN KURALI
# ==========================================================================


def test_universite_orani_iki_kaynaktan_HESAPLANIR(yuklu: Session) -> None:
    """233 / 3.626 → %6,43. Oran koda gömülü DEĞİL, türetilir."""
    o = yabanci.foreign_students(yuklu, None, "2025-2026")
    assert o["available"] is True
    assert o["student_count"] == 233
    assert o["denominator"] == 3626
    assert o["denominator_source"] == "yok_kayitli"
    assert o["ratio_percent"] == round(233 / 3626 * 100, 2) == 6.43


def test_fakulte_kapsaminda_ORAN_HESAPLANMAZ(yuklu: Session) -> None:
    """Uyumlu payda yoksa sayı gösterilir, oran iddia edilmez.

    Alt kapsamdaki tek payda adayı ÖSYM türevi 4 yıllık kohort
    toplamıdır: farklı nüfus tanımı, farklı zaman aralığı.
    """
    muh = yuklu.execute(
        select(Faculty.id).where(Faculty.code == "MUHMIM")).scalar_one()
    o = yabanci.foreign_students(yuklu, resolve(yuklu, faculty_id=muh), "2025-2026")
    assert o["available"] is True
    assert o["student_count"] == 98
    assert o["ratio_available"] is False
    assert o["ratio_percent"] is None
    assert "ÖSYM" in o["ratio_note"]


# ==========================================================================
# 3. KAPSAM İZOLASYONU
# ==========================================================================


@pytest.mark.parametrize("kod,beklenen", [
    ("MUHMIM", 98), ("INSTOPBIL", 79), ("GUZSANTAS", 31), ("MESLEK", 25),
])
def test_fakulte_kapsami_kendi_sayisini_verir(yuklu: Session, kod, beklenen) -> None:
    fid = yuklu.execute(select(Faculty.id).where(Faculty.code == kod)).scalar_one()
    o = yabanci.foreign_students(yuklu, resolve(yuklu, faculty_id=fid), "2025-2026")
    assert o["student_count"] == beklenen


def test_yabanci_ogrencisi_olmayan_fakulte_SIFIR_DEGIL_veri_yok(yuklu: Session) -> None:
    """Hukuk Fakültesi kaynakta hiç geçmiyor → 0 değil, "kayıt yok"."""
    fid = yuklu.execute(
        select(Faculty.id).where(Faculty.code == "HUKUK")).scalar_one()
    o = yabanci.foreign_students(yuklu, resolve(yuklu, faculty_id=fid), "2025-2026")
    assert o["available"] is False
    assert o["student_count"] is None


def test_fakulte_toplamlari_universiteyi_ASMAZ(yuklu: Session) -> None:
    uni = yabanci.foreign_students(yuklu, None, "2025-2026")["student_count"]
    toplam = 0
    for kod in ("MUHMIM", "INSTOPBIL", "GUZSANTAS", "MESLEK", "HUKUK"):
        fid = yuklu.execute(
            select(Faculty.id).where(Faculty.code == kod)).scalar_one()
        o = yabanci.foreign_students(yuklu, resolve(yuklu, faculty_id=fid),
                                     "2025-2026")
        toplam += o.get("student_count") or 0
    assert toplam == uni == 233


# ==========================================================================
# 4. DÖNEM DAVRANIŞI
# ==========================================================================


def test_baska_donem_2025_2026_degerini_TEKRARLAMAZ(yuklu: Session) -> None:
    for yil in ("2024-2025", "2023-2024", "2022-2023"):
        o = yabanci.foreign_students(yuklu, None, yil)
        assert o["available"] is False, yil
        assert o["student_count"] is None, yil
        assert o["ratio_percent"] is None, yil
        assert yil in o["note"]


def test_baska_donemde_fakulte_de_bos_doner(yuklu: Session) -> None:
    fid = yuklu.execute(
        select(Faculty.id).where(Faculty.code == "MUHMIM")).scalar_one()
    o = yabanci.foreign_students(yuklu, resolve(yuklu, faculty_id=fid), "2024-2025")
    assert o["available"] is False
    assert o["student_count"] is None


def test_fakulte_kirilimi_donem_disinda_bos(yuklu: Session) -> None:
    assert yabanci.faculty_breakdown(yuklu, "2025-2026")["total"] == 233
    assert yabanci.faculty_breakdown(yuklu, "2024-2025")["available"] is False
