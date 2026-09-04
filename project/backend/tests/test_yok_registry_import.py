"""YÖK KAYIT DEFTERİ + ÖĞRENCİ SAYILARI (part2) aktarımı.

İddialar:
  · çift sayma yapısal olarak imkânsız (TOPLAM satırı ve T sütunu yazılmaz)
  · öğrenim türü yazım varyantları tek kategoriye iner
  · zenginleştirme YALNIZCA NULL alanı doldurur, hiçbir şeyi ezmez
  · ad eşleşse bile ÜST BİRİM tutmuyorsa eşleşme sayılmaz
  · takma ad mevcut kaydı çözer; kopya/yeniden adlandırma/üst değişimi yok
  · eşleşmeyen birim/bölüm OLUŞTURULMAZ, raporlanır
  · YÖK sayısı ÜNİVERSİTE düzeyindedir; alt kapsama sızmaz
  · ÖSYM türevi `student_count` DEĞİŞMEZ
  · aktarım idempotenttir
"""

from datetime import date
from typing import Iterator

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import import_yok_registry as aktar
from app.database import Base
from app.models import (
    AcademicProgram,
    Department,
    Faculty,
    UniversityStudentHeadcount,
    YksPlacementRecord,
)
from app.models.university_headcount import HOME_UNIVERSITY
from app.services import student_count
from app.services import university_headcount_service as kayitli
from app.services.scope import resolve
from app.services.unit_types import ACADEMIC_UNIT_TYPES, FACULTY, classify_unit

ABU = HOME_UNIVERSITY
DIS = "BAŞKA ÜNİVERSİTE"


# --------------------------------------------------------------------------
# Sahte kaynak satırları — gerçek dosyanın YAPISINI birebir taklit eder
# --------------------------------------------------------------------------

BIRIM_BASLIK = ["Üniversite Adı", "Birim Adı", "Açılış Tarihi",
                "Üniversite Türü", "Birim İli", "Birim Durum"]
BOLUM_BASLIK = ["Üniversite Adı", "Birim Grubu", "Bölüm Adı", "Açılış Tarihi",
                "Üniversite Türü", "Bölüm İli", "Bölüm Durumu"]


def _sayim_satiri(uni, tur, ogrenim, onl=(0, 0), lis=(0, 0), yl=(0, 0),
                  dr=(0, 0)):
    """Kaynak biçimi: 4 başlık sütunu + her düzey için (E, K, T) + genel."""
    hucreler = ["", uni, tur, "ANKARA", ogrenim]
    genel_e = genel_k = 0
    for e, k in (onl, lis, yl, dr):
        hucreler += [str(e), str(k), str(e + k)]
        genel_e += e
        genel_k += k
    hucreler += [str(genel_e), str(genel_k), str(genel_e + genel_k)]
    return hucreler


def _sayim_dosyasi(satirlar):
    """Banner (4 satır) + ayrıntı + genel TOPLAM satırı."""
    bos = [""] * 20
    basliklar = [bos, bos, bos, bos]
    genel_e = sum(int(s[17]) for s in satirlar)
    genel_k = sum(int(s[18]) for s in satirlar)
    toplam = [""] * 20
    toplam[1] = "TOPLAM"
    toplam[17], toplam[18], toplam[19] = (str(genel_e), str(genel_k),
                                          str(genel_e + genel_k))
    return basliklar + satirlar + [toplam]


@pytest.fixture()
def db() -> Iterator[Session]:
    motor = create_engine(
        "sqlite://", future=True,
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(motor)
    s = sessionmaker(bind=motor, future=True)()

    muh = Faculty(name="MÜHENDİSLİK VE MİMARLIK FAKÜLTESİ", code="MUHMIM",
                  unit_type=FACULTY, is_active=True)
    huk = Faculty(name="HUKUK FAKÜLTESİ", code="HUKUK",
                  unit_type=FACULTY, is_active=True)
    myo = Faculty(name="MESLEK YÜKSEKOKULU", code="MESLEK",
                  unit_type="VOCATIONAL_SCHOOL", is_active=True)
    s.add_all([muh, huk, myo])
    s.flush()

    bil = Department(name="BİLGİSAYAR MÜHENDİSLİĞİ BÖLÜMÜ", code="BILMUH",
                     faculty_id=muh.id, is_active=True)
    # part-1 müfredat aktarımından gelen, YÖK'ün farklı yazdığı bölüm.
    bilsis = Department(name="Bilişim Sistemleri Mühendisliği",
                        code="BILSISMUH", faculty_id=muh.id, is_active=True)
    # Adı MYO'daki "HUKUK BÖLÜMÜ" ile karışabilecek AYRI bölüm.
    hukuk_bol = Department(name="Hukuk", code="HUKUKB",
                           faculty_id=huk.id, is_active=True)
    s.add_all([bil, bilsis, hukuk_bol])
    s.flush()

    program = AcademicProgram(name="Bilgisayar Mühendisliği", code="BIL-PR",
                              department_id=bil.id, degree_level="Lisans",
                              is_active=True)
    s.add(program)
    s.flush()
    for yil, yerlesen in ((2024, 40), (2025, 30)):
        s.add(YksPlacementRecord(
            academic_program_id=program.id, placement_year=yil,
            academic_year=f"{yil}-{yil + 1}", placement_program_name="BIL",
            score_type="SAY", scholarship_type="Burslu",
            quota=50, placed_students=yerlesen,
            source_dataset="t", source_file="f"))
    s.commit()
    try:
        yield s
    finally:
        s.close()
        motor.dispose()


@pytest.fixture()
def birim_satirlari():
    return [BIRIM_BASLIK] + [
        [ABU, "MÜHENDİSLİK VE MİMARLIK FAKÜLTESİ", "17.04.2020",
         "VAKIF", "ANKARA", "AKTİF"],
        [ABU, "HUKUK FAKÜLTESİ", "06.02.2021", "VAKIF", "ANKARA", "AKTİF"],
        [ABU, "MESLEK YÜKSEKOKULU", "01.06.2022", "VAKIF", "ANKARA", "AKTİF"],
        [ABU, "LİSANSÜSTÜ EĞİTİM ENSTİTÜSÜ", "06.02.2021",
         "VAKIF", "ANKARA", "AKTİF"],
        [ABU, "SÜREKLİ EĞİTİM UYGULAMA VE ARAŞTIRMA MERKEZİ", "04.11.2020",
         "VAKIF", "ANKARA", "AKTİF"],
        # BAŞKA üniversitenin birimi — hiç okunmamalı.
        [DIS, "MÜHENDİSLİK FAKÜLTESİ", "01.01.2000", "DEVLET", "ANKARA", "AKTİF"],
    ]


@pytest.fixture()
def bolum_satirlari():
    return [BOLUM_BASLIK] + [
        [ABU, "MÜHENDİSLİK VE MİMARLIK FAKÜLTESİ",
         "BİLGİSAYAR MÜHENDİSLİĞİ BÖLÜMÜ", "06.05.2020",
         "VAKIF", "ANKARA", "AKTİF"],
        [ABU, "MÜHENDİSLİK VE MİMARLIK FAKÜLTESİ",
         "BİLİŞİM SİSTEMLERİ MÜHENDİSLİĞİ BÖLÜMÜ", "26.04.2022",
         "VAKIF", "ANKARA", "AKTİF"],
        # MYO'daki HUKUK BÖLÜMÜ — Hukuk Fakültesi'ndeki "Hukuk" DEĞİLDİR.
        [ABU, "MESLEK YÜKSEKOKULU", "HUKUK BÖLÜMÜ", "26.11.2025",
         "VAKIF", "ANKARA", "AKTİF"],
        [ABU, "MESLEK YÜKSEKOKULU", "TASARIM BÖLÜMÜ", "27.05.2025",
         "VAKIF", "ANKARA", "AKTİF"],
        [DIS, "MÜHENDİSLİK FAKÜLTESİ", "BİLGİSAYAR MÜHENDİSLİĞİ BÖLÜMÜ",
         "01.01.2000", "DEVLET", "ANKARA", "AKTİF"],
    ]


@pytest.fixture()
def sayim_2025():
    return _sayim_dosyasi([
        _sayim_satiri(ABU, "VAKIF", "BİRİNCİ Ö.", onl=(464, 255),
                      lis=(1225, 1558), yl=(91, 33)),
        _sayim_satiri(ABU, "VAKIF", "TOPLAM", onl=(464, 255),
                      lis=(1225, 1558), yl=(91, 33)),
        _sayim_satiri(DIS, "DEVLET", "BİRİNCİ Ö.", lis=(100, 100)),
        _sayim_satiri(DIS, "DEVLET", "TOPLAM", lis=(100, 100)),
    ])


def _calistir(db, birim=None, bolum=None, sayimlar=(), dry_run=False):
    a = aktar.YokKayitDefteriAktarimi(db, dry_run=dry_run)
    if birim:
        a.birimleri_zenginlestir(birim, "birimler.xls")
    if bolum:
        a.bolumleri_zenginlestir(bolum, "bolumler.xls")
    for satirlar, yil, ad in sayimlar:
        a.sayimlari_aktar(satirlar, ad, yil)
    a.cakismalari_yaz()
    db.flush()
    return a


# ==========================================================================
# 1. Çift sayma korumaları
# ==========================================================================


def test_toplam_satiri_yazilmaz(db, sayim_2025):
    _calistir(db, sayimlar=[(sayim_2025, "2025-2026", "s.xls")])
    toplam = db.execute(
        select(func.sum(UniversityStudentHeadcount.student_count))
        .where(UniversityStudentHeadcount.university_name == ABU)
    ).scalar_one()
    # TOPLAM satırı da yazılsaydı 3626 yerine 7252 çıkardı.
    assert toplam == 3626


def test_t_sutunu_yazilmaz_yalnizca_e_ve_k(db, sayim_2025):
    _calistir(db, sayimlar=[(sayim_2025, "2025-2026", "s.xls")])
    cinsiyetler = {
        c for (c,) in db.execute(
            select(UniversityStudentHeadcount.gender).distinct())
    }
    assert cinsiyetler == {"E", "K"}


def test_kirilim_korunur(db, sayim_2025):
    _calistir(db, sayimlar=[(sayim_2025, "2025-2026", "s.xls")])
    satir = db.execute(
        select(UniversityStudentHeadcount).where(
            UniversityStudentHeadcount.university_name == ABU,
            UniversityStudentHeadcount.degree_level == "LISANS",
            UniversityStudentHeadcount.gender == "K",
        )
    ).scalar_one()
    assert satir.education_mode == "BİRİNCİ"
    assert satir.academic_year == "2025-2026"
    assert satir.student_count == 1558


def test_ogrenim_turu_yazim_varyantlari_tek_kategoriye_iner():
    """Dosya (2) Türkçe harfsiz yazıyor; iki kategori oluşamaz."""
    assert aktar.ogrenim_turu("BİRİNCİ Ö.") == "BİRİNCİ"
    assert aktar.ogrenim_turu("BIRINCI Ö.") == "BİRİNCİ"
    assert aktar.ogrenim_turu("İKİNCİ Ö.") == "İKİNCİ"
    assert aktar.ogrenim_turu("IKINCI Ö.") == "İKİNCİ"
    assert aktar.ogrenim_turu("TOPLAM") is None


def test_harfsiz_varyant_ayni_satira_yazilir(db):
    """Aynı yıl iki yazımla gelirse İKİ kategori oluşmamalı.

    Ham metni anahtar yapsaydık "BİRİNCİ Ö." ve "BIRINCI Ö." iki ayrı
    öğrenim türü olur, toplamlar ikiye katlanırdı.
    """
    a = _sayim_dosyasi([_sayim_satiri(ABU, "VAKIF", "BİRİNCİ Ö.", lis=(10, 20))])
    b = _sayim_dosyasi([_sayim_satiri(ABU, "VAKIF", "BIRINCI Ö.", lis=(10, 20))])
    _calistir(db, sayimlar=[(a, "2025-2026", "a.xls"), (b, "2025-2026", "b.xls")])
    turler = {t for (t,) in db.execute(
        select(UniversityStudentHeadcount.education_mode).distinct())}
    assert turler == {"BİRİNCİ"}
    assert db.execute(
        select(func.sum(UniversityStudentHeadcount.student_count))
    ).scalar_one() == 30       # 60 olsaydı çift sayardık


def test_e_arti_k_toplami_tutmayan_satir_yazilmaz(db):
    """Doğrulama DÜZEY bazındadır: yalnızca bozuk düzey atlanır.

    Bütün satırı atmak, sağlam düzeylerin gerçek sayılarını da
    kaybettirirdi; tutarsız olan tek düzeydir.
    """
    bozuk = _sayim_dosyasi([_sayim_satiri(ABU, "VAKIF", "BİRİNCİ Ö.",
                                          lis=(10, 20), yl=(3, 4))])
    bozuk[4][10] = "999"      # LİSANS T sütununu boz
    a = _calistir(db, sayimlar=[(bozuk, "2025-2026", "bozuk.xls")])
    assert a.tutarsizliklar and "LISANS" in a.tutarsizliklar[0]
    yazilan = {(r.degree_level, r.gender): r.student_count
               for r in db.execute(select(UniversityStudentHeadcount)).scalars()}
    assert ("LISANS", "E") not in yazilan       # bozuk düzey YAZILMADI
    assert ("LISANS", "K") not in yazilan
    assert yazilan[("YUKSEKLISANS", "E")] == 3  # sağlam düzey korundu
    assert yazilan[("YUKSEKLISANS", "K")] == 4


# ==========================================================================
# 2. Zenginleştirme — yalnızca NULL doldurur
# ==========================================================================


def test_birim_alanlari_doldurulur(db, birim_satirlari):
    a = _calistir(db, birim=birim_satirlari)
    muh = db.execute(
        select(Faculty).where(Faculty.code == "MUHMIM")).scalar_one()
    assert muh.established_on == date(2020, 4, 17)
    assert muh.yok_status == "AKTİF"
    assert len(a.birim_zengin) == 3


def test_dolu_alan_ezilmez_cakisma_kaydedilir(db, birim_satirlari):
    muh = db.execute(
        select(Faculty).where(Faculty.code == "MUHMIM")).scalar_one()
    muh.established_on = date(1999, 1, 1)
    db.flush()
    a = _calistir(db, birim=birim_satirlari)
    assert muh.established_on == date(1999, 1, 1)      # KORUNDU
    assert any(c["field_name"] == "established_on" for c in a.cakismalar)


def test_is_active_bayragina_dokunulmaz(db, birim_satirlari, bolum_satirlari):
    """`yok_status` dış kaynağın beyanı, `is_active` bizim bayrağımız."""
    muh = db.execute(
        select(Faculty).where(Faculty.code == "MUHMIM")).scalar_one()
    muh.is_active = False
    db.flush()
    _calistir(db, birim=birim_satirlari, bolum=bolum_satirlari)
    assert muh.is_active is False
    assert muh.yok_status == "AKTİF"


def test_baska_universitenin_birimi_okunmaz(db, birim_satirlari):
    a = _calistir(db, birim=birim_satirlari)
    assert not any("MÜHENDİSLİK FAKÜLTESİ" == x for x in a.birim_eslesmedi)
    assert db.execute(select(func.count()).select_from(Faculty)).scalar_one() == 3


def test_ayristirilamayan_tarih_none_kalir(db):
    satirlar = [BIRIM_BASLIK, [ABU, "HUKUK FAKÜLTESİ", "", "VAKIF",
                               "ANKARA", "AKTİF"]]
    _calistir(db, birim=satirlar)
    huk = db.execute(
        select(Faculty).where(Faculty.code == "HUKUK")).scalar_one()
    assert huk.established_on is None       # uydurulmadı
    assert huk.yok_status == "AKTİF"


# ==========================================================================
# 3. Bölüm eşleştirme — üst birim doğrulanır
# ==========================================================================


def test_takma_ad_mevcut_bolumu_cozer(db, bolum_satirlari):
    a = _calistir(db, bolum=bolum_satirlari)
    bilsis = db.execute(
        select(Department).where(Department.code == "BILSISMUH")).scalar_one()
    assert bilsis.established_on == date(2022, 4, 26)
    assert a.takma_ad_cozuldu and "BILSISMUH" not in a.takma_ad_cozuldu[0]
    assert len(a.takma_ad_cozuldu) == 1


def test_takma_ad_kopya_uretmez_yeniden_adlandirmaz(db, bolum_satirlari):
    onceki = db.execute(select(func.count()).select_from(Department)).scalar_one()
    _calistir(db, bolum=bolum_satirlari)
    bilsis = db.get(Department, 2)
    assert db.execute(
        select(func.count()).select_from(Department)).scalar_one() == onceki
    assert bilsis.name == "Bilişim Sistemleri Mühendisliği"   # AYNI
    assert bilsis.faculty_id == 1                              # AYNI üst


def test_ayni_adli_farkli_ustteki_bolum_birlestirilmez(db, bolum_satirlari):
    """MYO'daki "HUKUK BÖLÜMÜ", Hukuk Fakültesi'ndeki "Hukuk" değildir."""
    a = _calistir(db, bolum=bolum_satirlari)
    hukuk = db.execute(
        select(Department).where(Department.code == "HUKUKB")).scalar_one()
    assert hukuk.faculty_id == 2            # üst DEĞİŞMEDİ
    assert hukuk.established_on is None     # MYO tarihi ona yazılmadı
    assert any("HUKUK BÖLÜMÜ" in x for x in a.bolum_eslesmedi)


def test_eslesmeyen_bolum_olusturulmaz(db, bolum_satirlari):
    onceki = db.execute(select(func.count()).select_from(Department)).scalar_one()
    a = _calistir(db, bolum=bolum_satirlari)
    assert db.execute(
        select(func.count()).select_from(Department)).scalar_one() == onceki
    assert any("TASARIM BÖLÜMÜ" in x for x in a.bolum_eslesmedi)


def test_eslesmeyen_birim_olusturulmaz_ve_raporlanir(db, birim_satirlari):
    a = _calistir(db, birim=birim_satirlari)
    assert db.execute(select(func.count()).select_from(Faculty)).scalar_one() == 3
    rapor = " | ".join(a.birim_eslesmedi)
    assert "LİSANSÜSTÜ EĞİTİM ENSTİTÜSÜ" in rapor
    assert "SÜREKLİ EĞİTİM UYGULAMA VE ARAŞTIRMA MERKEZİ" in rapor


def test_arastirma_merkezi_akademik_birim_degil():
    """Merkez oluşturulsa bile fakülte karşılaştırmasına GİREMEZ."""
    tur = classify_unit("SÜREKLİ EĞİTİM UYGULAMA VE ARAŞTIRMA MERKEZİ")
    assert tur not in ACADEMIC_UNIT_TYPES
    # Mevcut birimlerin sınıflandırması DEĞİŞMEDİ.
    assert classify_unit("MÜHENDİSLİK VE MİMARLIK FAKÜLTESİ") == FACULTY
    assert classify_unit("MESLEK YÜKSEKOKULU") == "VOCATIONAL_SCHOOL"


# ==========================================================================
# 4. Mevcut veriye dokunulmadı
# ==========================================================================


def test_yks_kayitlari_degismez(db, sayim_2025, birim_satirlari, bolum_satirlari):
    onceki = [(r.academic_program_id, r.placement_year, r.placed_students)
              for r in db.execute(select(YksPlacementRecord)).scalars()]
    _calistir(db, birim=birim_satirlari, bolum=bolum_satirlari,
              sayimlar=[(sayim_2025, "2025-2026", "s.xls")])
    sonraki = [(r.academic_program_id, r.placement_year, r.placed_students)
               for r in db.execute(select(YksPlacementRecord)).scalars()]
    assert onceki == sonraki


def test_osym_turevi_ogrenci_sayisi_degismez(db, sayim_2025):
    """YÖK sayımı içeri alınınca ÖSYM türevi toplam DEĞİŞMEZ.

    İki ölçüm birbirinin yerine geçmez: ÖSYM türevi program bazlı
    yerleştirmeden gelir, YÖK sayısı kurumun bildirdiği kayıtlı
    öğrencidir. Aktarım, program bazlı zinciri asla yeniden yazmamalıdır.
    """
    onceki = student_count._yks_turevi_toplam(db)
    _calistir(db, sayimlar=[(sayim_2025, "2025-2026", "s.xls")])
    assert student_count._yks_turevi_toplam(db) == onceki == 70


def test_universite_kapsaminda_yok_sayisi_yetkilidir(db, sayim_2025):
    """Aktarımdan SONRA üniversite kapsamının yetkili sayısı YÖK olur.

    Bu, `total_for_scope` üzerinde BİLİNÇLİ bir davranış değişikliğidir:
    daha önce yalnızca gezinme ağacında (frontend) yapılan düzeltme
    servise alındı. Amaç, aynı soruya iki farklı sayı veren uçları
    (`/staffing` 3.348 · kayıtlı öğrenci ucu 3.626) tek kaynağa
    bağlamaktır. Alt kapsamlarda ÖSYM türevi korunur — YÖK verisinin
    fakülte/bölüm kırılımı yoktur ve uydurulamaz.
    """
    from app.services import university_headcount_service as kayitli

    osym = student_count._yks_turevi_toplam(db)
    _calistir(db, sayimlar=[(sayim_2025, "2025-2026", "s.xls")])

    ozet = kayitli.enrolled_headcount(db)
    assert ozet["available"]

    sayi, kaynak = student_count.total_for_scope_detailed(db)
    assert kaynak == "yok_kayitli"
    assert sayi == ozet["student_count"]   # tek kaynak, tek sayı
    assert sayi != osym                    # iki ölçüm gerçekten farklıdır


# ==========================================================================
# 5. Trend servisi ve kapsam sınırı
# ==========================================================================


@pytest.fixture()
def dolu(db):
    _calistir(db, sayimlar=[
        (_sayim_dosyasi([_sayim_satiri(ABU, "VAKIF", "BİRİNCİ Ö.",
                                       lis=(573, 649), yl=(134, 37))]),
         "2022-2023", "a.xls"),
        (_sayim_dosyasi([_sayim_satiri(ABU, "VAKIF", "BİRİNCİ Ö.",
                                       onl=(464, 255), lis=(1225, 1558),
                                       yl=(91, 33))]),
         "2025-2026", "b.xls"),
    ])
    db.commit()
    return db


def test_universite_trendi_yillari_siralar(dolu):
    o = kayitli.enrolled_headcount(dolu, resolve(dolu))
    assert o["available"] is True
    assert [y["academic_year"] for y in o["years"]] == ["2022-2023", "2025-2026"]
    assert o["student_count"] == 3626
    assert o["first_student_count"] == 1393


def test_gecmis_donem_trendi_secili_yilda_biter(dolu):
    o = kayitli.enrolled_headcount(
        dolu, resolve(dolu), donem="2022-2023")
    assert [y["academic_year"] for y in o["years"]] == ["2022-2023"]
    assert o["year_count"] == 1
    assert o["latest_academic_year"] == "2022-2023"


def test_buyume_hesaplanir_ilk_yil_none(dolu):
    o = kayitli.enrolled_headcount(dolu, resolve(dolu))
    assert o["years"][0]["change_percent"] is None       # önceki yıl yok
    assert o["years"][1]["change_percent"] == round(
        (3626 - 1393) / 1393 * 100, 2)
    assert o["period_growth_absolute"] == 2233


def test_duzey_kirilimi_donuyor(dolu):
    o = kayitli.enrolled_headcount(dolu, resolve(dolu))
    assert o["by_degree_level"]["Lisans"] == 2783
    assert o["by_degree_level"]["Önlisans"] == 719
    assert o["by_degree_level"]["Yüksek Lisans"] == 124


def test_alt_kapsamda_universite_sayisi_sizmaz(dolu):
    """Üniversite toplamını fakülteye/bölüme yazmak uydurma olurdu."""
    for kw in ({"faculty_id": 1}, {"department_id": 1},
               {"academic_program_id": 1}):
        o = kayitli.enrolled_headcount(dolu, resolve(dolu, **kw))
        assert o["available"] is False
        assert "student_count" not in o
        assert o["measured_at_level"] == "university"


def test_veri_yokken_available_false(db):
    o = kayitli.enrolled_headcount(db, resolve(db))
    assert o["available"] is False


def test_kiyas_listesi_sirali_ve_kurumu_isaretler(dolu):
    satirlar = kayitli.peer_headcounts(dolu)
    assert satirlar
    assert satirlar[0]["rank"] == 1
    assert any(r["is_home_institution"] for r in satirlar)


# ==========================================================================
# 6. İdempotans
# ==========================================================================


def test_ikinci_calistirma_satir_eklemez(db, sayim_2025, birim_satirlari,
                                         bolum_satirlari):
    _calistir(db, birim=birim_satirlari, bolum=bolum_satirlari,
              sayimlar=[(sayim_2025, "2025-2026", "s.xls")])
    db.commit()
    ilk = db.execute(
        select(func.count()).select_from(UniversityStudentHeadcount)).scalar_one()

    a = _calistir(db, birim=birim_satirlari, bolum=bolum_satirlari,
                  sayimlar=[(sayim_2025, "2025-2026", "s.xls")])
    db.commit()
    assert db.execute(
        select(func.count()).select_from(UniversityStudentHeadcount)
    ).scalar_one() == ilk
    assert a.sayim_yazildi == 0
    assert a.sayim_degismedi == ilk
    assert a.birim_zengin == [] and a.bolum_zengin == []


def test_kaynak_guncellenirse_sayi_yazilir_ve_cakisma_kaydedilir(db, sayim_2025):
    _calistir(db, sayimlar=[(sayim_2025, "2025-2026", "s.xls")])
    db.commit()
    duzeltilmis = _sayim_dosyasi([
        _sayim_satiri(ABU, "VAKIF", "BİRİNCİ Ö.", onl=(464, 255),
                      lis=(1225, 1560), yl=(91, 33)),
    ])
    a = _calistir(db, sayimlar=[(duzeltilmis, "2025-2026", "s2.xls")])
    satir = db.execute(
        select(UniversityStudentHeadcount).where(
            UniversityStudentHeadcount.degree_level == "LISANS",
            UniversityStudentHeadcount.gender == "K",
            UniversityStudentHeadcount.university_name == ABU,
        )
    ).scalar_one()
    assert satir.student_count == 1560
    assert any(c["field_name"] == "student_count" for c in a.cakismalar)


def test_dry_run_yazmaz(db, sayim_2025, birim_satirlari):
    _calistir(db, birim=birim_satirlari,
              sayimlar=[(sayim_2025, "2025-2026", "s.xls")], dry_run=True)
    assert db.execute(
        select(func.count()).select_from(UniversityStudentHeadcount)
    ).scalar_one() == 0
    muh = db.execute(
        select(Faculty).where(Faculty.code == "MUHMIM")).scalar_one()
    assert muh.established_on is None
