"""ÜNİVERSİTE SEVİYESİ RAKİP ANALİZİ.

İddialar:
  · HER GÖSTERGENİN KENDİ KOHORTU vardır; eksik kurum kohorttan düşer,
    gösterge kapanmaz ve ekran boşalmaz
  · eksik değer 0'a çevrilmez, kohorta girmez
  · iki ayrı "gösterilemez" sebebi ayrı raporlanır:
    yetersiz kohort (insufficient_cohort) / karşılaştırılamaz (not_comparable)
  · süzgeç kipleri gerçek veriden süzer; kendi kurumumuz daima içeride
  · varsayılan kip tüm Ankara listesi DEĞİLDİR
  · Ankara sıralaması süzgeçten ETKİLENMEZ
  · ölçek YÖK kayıtlı öğrenci sayısından gelir; ÖSYM türevi karışmaz
  · fakülte/bölüm/program karşılaştırması bu servisten ETKİLENMEZ
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
    Department,
    Faculty,
    UniversityProfile,
    UniversityStudentHeadcount,
    YksPlacementRecord,
)
from app.models.university_headcount import HOME_UNIVERSITY
from app.services import peer_comparison_service as kiyas
from app.services import student_count
from app.services import university_competitor_service as rakip
from app.services.scope import resolve
from app.services.unit_types import FACULTY

YIL_ILK, YIL_SON = "2022-2023", "2025-2026"


def _sayim(s, uni, yil, duzey, e, k, tur="VAKIF"):
    for cinsiyet, deger in (("E", e), ("K", k)):
        s.add(UniversityStudentHeadcount(
            university_name=uni, university_type=tur, city="ANKARA",
            academic_year=yil, education_mode="BİRİNCİ", degree_level=duzey,
            gender=cinsiyet, student_count=deger,
            source_dataset="t", source_file="f"))


@pytest.fixture()
def db() -> Iterator[Session]:
    """Kendi kurumumuz + 4 dış kurum.

    Kurumlar bilinçli olarak farklı: biri ölçek olarak çok büyük
    (benzer kümesine girmemeli), biri devlet, biri kadrosu bilinmeyen.
    """
    motor = create_engine(
        "sqlite://", future=True,
        connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(motor)
    s = sessionmaker(bind=motor, future=True)()

    # --- kendi hiyerarşimiz: alt seviye karşılaştırması bozulmasın diye ---
    muh = Faculty(name="MÜHENDİSLİK FAKÜLTESİ", code="MUH",
                  unit_type=FACULTY, is_active=True)
    fen = Faculty(name="FEN FAKÜLTESİ", code="FEN",
                  unit_type=FACULTY, is_active=True)
    s.add_all([muh, fen])
    s.flush()
    yaz = Department(name="YAZILIM MÜHENDİSLİĞİ BÖLÜMÜ", code="YAZMUH",
                     faculty_id=muh.id, is_active=True)
    bil = Department(name="BİLGİSAYAR MÜHENDİSLİĞİ BÖLÜMÜ", code="BILMUH",
                     faculty_id=muh.id, is_active=True)
    mat = Department(name="MATEMATİK BÖLÜMÜ", code="MAT",
                     faculty_id=fen.id, is_active=True)
    s.add_all([yaz, bil, mat])
    s.flush()
    prog = AcademicProgram(name="Yazılım Müh.", code="YAZ-PR",
                           department_id=yaz.id, degree_level="Lisans",
                           is_active=True)
    s.add(prog)
    s.flush()
    s.add(YksPlacementRecord(
        academic_program_id=prog.id, placement_year=2025,
        academic_year="2025-2026", placement_program_name="YAZ",
        score_type="SAY", scholarship_type="Burslu",
        quota=60, placed_students=45, source_dataset="t", source_file="f"))
    s.add(AcademicStaff(staff_number="Y1", first_name="A", last_name="B",
                        title="PROFESÖR", department_id=yaz.id,
                        academic_year="2025-2026", is_active=True,
                        publication_count=3, teaching_load_hours=10))

    # --- üniversite düzeyi kayıtlı öğrenci sayıları ---
    #  kurum            ilk yıl   son yıl   büyüme
    #  ABÜ (vakıf)        1000      2000    +100 %
    #  RAKİP A (vakıf)    1800      2400    +33.33 %
    #  RAKİP B (vakıf)    3000      2700    -10 %
    #  DEV C (devlet)     4000      5000    +25 %
    #  DEV D (devlet)    20000     22000    +10 %   (ölçek çok büyük)
    kurumlar = [
        (HOME_UNIVERSITY, "VAKIF", 1000, 2000),
        ("RAKİP A ÜNİVERSİTESİ", "VAKIF", 1800, 2400),
        ("RAKİP B ÜNİVERSİTESİ", "VAKIF", 3000, 2700),
        ("DEVLET C ÜNİVERSİTESİ", "DEVLET", 4000, 5000),
        ("DEVLET D ÜNİVERSİTESİ", "DEVLET", 20000, 22000),
    ]
    for ad, tur, ilk, son in kurumlar:
        # Lisans + önlisans ayrımı: öğrenci gövdesi bileşimi için.
        _sayim(s, ad, YIL_ILK, "LISANS", ilk // 2, ilk - ilk // 2, tur)
        _sayim(s, ad, YIL_SON, "LISANS", (son * 8 // 10) // 2,
               (son * 8 // 10) - (son * 8 // 10) // 2, tur)
        _sayim(s, ad, YIL_SON, "ONLISANS", (son * 2 // 10) // 2,
               (son * 2 // 10) - (son * 2 // 10) // 2, tur)

    # --- profiller ---
    # Yayın YALNIZCA kendi kurumumuzda: kapsama kuralı devreye girmeli.
    # "DEVLET D" kadrosu BİLİNMİYOR: kadro göstergesi de kapanmalı.
    profiller = [
        (HOME_UNIVERSITY, "VAKIF", 100, 250, 40, 6, 20),
        ("RAKİP A ÜNİVERSİTESİ", "VAKIF", 200, None, None, 8, 30),
        ("RAKİP B ÜNİVERSİTESİ", "VAKIF", 150, None, None, 5, 18),
        ("DEVLET C ÜNİVERSİTESİ", "DEVLET", 400, None, None, 12, 44),
        ("DEVLET D ÜNİVERSİTESİ", "DEVLET", None, None, None, 30, 120),
    ]
    for ad, tur, kadro, yayin, kisi, birim, bolum in profiller:
        s.add(UniversityProfile(
            university_name=ad, university_type=tur, city="ANKARA",
            academic_staff_count=kadro, total_publications=yayin,
            academics_with_publications=kisi,
            academic_unit_count=birim, department_count=bolum))
    s.commit()
    try:
        yield s
    finally:
        s.close()
        motor.dispose()


def _bul(o, ad):
    return next(r for r in o["universities"] if r["university_name"] == ad)


# ==========================================================================
# 1. Kapsama kuralı
# ==========================================================================


def test_tum_kurumlarda_olculen_gosterge_acilir(db: Session) -> None:
    o = rakip.competitor_analysis(db, rakip.FILTER_FOUNDATION)
    for anahtar in ("student_count", "growth_percent_period",
                    "academic_staff_count", "students_per_academic",
                    "academic_unit_count", "department_count"):
        assert o["metrics"][anahtar]["available"] is True, anahtar
        assert anahtar in o["available_metrics"]


def test_karsilastirilamayan_gosterge_kapatilir(db: Session) -> None:
    """Yayın: hem kohort küçük hem yöntemsel olarak karşılaştırılamaz."""
    o = rakip.competitor_analysis(db, rakip.FILTER_FOUNDATION)
    m = o["metrics"]["publications_per_academic"]
    assert m["available"] is False
    assert m["measured_count"] == 1
    assert m["total_count"] == len(o["universities"])
    assert "publications_per_academic" not in o["available_metrics"]
    assert any(u["key"] == "publications_per_academic"
               for u in o["unavailable_metrics"])


def test_kapali_gosterge_icin_sifir_uydurulmaz(db: Session) -> None:
    o = rakip.competitor_analysis(db, rakip.FILTER_FOUNDATION)
    a = _bul(o, "RAKİP A ÜNİVERSİTESİ")
    assert a["total_publications"] is None          # 0 DEĞİL
    assert a["publications_per_academic"] is None


def test_kapali_gosterge_icin_siralama_uretilmez(db: Session) -> None:
    o = rakip.competitor_analysis(db, rakip.FILTER_FOUNDATION)
    for r in o["universities"]:
        assert "publications_per_academic" not in r["ranks"]
        assert "student_count" in r["ranks"]
    assert o["metrics"]["publications_per_academic"]["cohort"] == []


def test_bir_kurumun_eksigi_gostergeyi_KAPATMAZ(db: Session) -> None:
    """DEVLET D'nin kadrosu yok. Gösterge KAPANMAZ; kohorttan düşer.

    Eski politika bu durumda göstergeyi tamamen gizliyordu ve tek bir
    kurumun tek bir eksik alanı ekranı boşaltabiliyordu.
    """
    hepsi = rakip.competitor_analysis(db, rakip.FILTER_ALL)
    m = hepsi["metrics"]["academic_staff_count"]
    assert m["available"] is True                 # gösterge AÇIK
    assert m["measured_count"] == 4               # 5 kurumun 4'ü ölçülü
    assert m["total_count"] == 5
    assert m["coverage_note"] == "4 / 5 kurumda veri"
    # Ölçülmeyen kurum kohortun DIŞINDA; 0 ile temsil edilmiyor.
    adlar = {c["university_name"] for c in m["cohort"]}
    assert "DEVLET D ÜNİVERSİTESİ" not in adlar
    assert len(m["cohort"]) == 4


def test_kohort_yalnizca_olculen_kurumlardan_olusur(db: Session) -> None:
    """Kohortta 0'a çevrilmiş değer BULUNAMAZ; eksik kurum yoktur."""
    for kip in (rakip.FILTER_SIMILAR, rakip.FILTER_ALL,
                rakip.FILTER_FOUNDATION, rakip.FILTER_STATE):
        o = rakip.competitor_analysis(db, kip)
        for anahtar in o["available_metrics"]:
            m = o["metrics"][anahtar]
            assert len(m["cohort"]) == m["measured_count"], f"{kip}/{anahtar}"
            assert all(c["value"] is not None for c in m["cohort"])
            # Kohorttaki her kurum satırda da GERÇEKTEN ölçülü.
            olculu = {r["university_name"] for r in o["universities"]
                      if r[anahtar] is not None}
            assert {c["university_name"] for c in m["cohort"]} == olculu


def test_kismi_kapsam_diger_gostergeleri_etkilemez(db: Session) -> None:
    """Bir göstergenin eksikliği ekranı boşaltmaz."""
    o = rakip.competitor_analysis(db, rakip.FILTER_ALL)
    # Yayın kapalı (karşılaştırılamaz) ama diğerleri açık.
    assert o["metrics"]["publications_per_academic"]["available"] is False
    assert len(o["available_metrics"]) >= 8
    assert o["metrics"]["student_count"]["available"] is True


def test_siralama_kohort_icinde_yeniden_numaralanir(db: Session) -> None:
    """Kohorttan düşen kurum, sıraları kaydırmaz — 1..n kesintisiz."""
    o = rakip.competitor_analysis(db, rakip.FILTER_ALL)
    m = o["metrics"]["academic_staff_count"]
    assert [c["rank"] for c in m["cohort"]] == list(range(1, len(m["cohort"]) + 1))


def test_medyan_ve_ceyrek_kohorttan_hesaplanir(db: Session) -> None:
    o = rakip.competitor_analysis(db, rakip.FILTER_FOUNDATION)
    m = o["metrics"]["student_count"]
    # Vakıf kümesi: 2000, 2400, 2700 → medyan 2400
    assert m["median"] == 2400
    assert m["home_value"] == 2000
    assert m["home_vs_median"] == -400
    assert m["cohort_size"] == 3


def test_kohort_cok_kucukse_gosterge_kapanir(db: Session) -> None:
    """İki kurumluk "sıralama" karar üretmez."""
    from app.models import UniversityProfile as UP

    for ad in ("RAKİP A ÜNİVERSİTESİ", "RAKİP B ÜNİVERSİTESİ"):
        p = db.execute(select(UP).where(UP.university_name == ad)).scalar_one()
        p.academic_staff_count = None
    db.flush()
    o = rakip.competitor_analysis(db, rakip.FILTER_FOUNDATION)
    m = o["metrics"]["academic_staff_count"]
    assert m["measured_count"] == 1
    assert m["available"] is False
    assert m["unavailable_reason"] == "insufficient_cohort"
    # Diğer göstergeler ETKİLENMEDİ.
    assert o["metrics"]["student_count"]["available"] is True


def test_yayin_kapsam_degil_karsilastirilabilirlik_nedeniyle_kapali(
        db: Session) -> None:
    """İki farklı "gösterilemez" sebebi ayrı ayrı raporlanır."""
    o = rakip.competitor_analysis(db, rakip.FILTER_ALL)
    m = o["metrics"]["total_publications"]
    assert m["comparable"] is False
    assert m["available"] is False
    assert m["unavailable_reason"] == "not_comparable"
    assert "farklı derinlikte" in m["note"]


def test_her_gosterge_kapsam_notu_tasir(db: Session) -> None:
    o = rakip.competitor_analysis(db, rakip.FILTER_ALL)
    for anahtar, m in o["metrics"].items():
        assert m["coverage_note"].endswith("kurumda veri"), anahtar
        assert str(m["measured_count"]) in m["coverage_note"]


def test_benzer_kip_kurali_aciklanir(db: Session) -> None:
    o = rakip.competitor_analysis(db, rakip.FILTER_SIMILAR)
    k = o["similar_rule"]
    assert k["lower_multiplier"] == rakip.SIMILAR_LOWER
    assert k["upper_multiplier"] == rakip.SIMILAR_UPPER
    assert k["reference_student_count"] == 2000
    assert "vakıf" in k["explanation"].lower()


def test_gecmis_donem_guncel_profili_ve_gelecek_yili_sizdirmaz(
        db: Session) -> None:
    """Tarihsel öğrenci sayısı güncel kadro/birim verisiyle karışmaz."""
    o = rakip.competitor_analysis(db, rakip.FILTER_FOUNDATION, YIL_ILK)
    bizim = _bul(o, HOME_UNIVERSITY)

    assert o["academic_year"] == YIL_ILK
    assert o["year_count"] == 1
    assert bizim["yearly_totals"] == {YIL_ILK: 1000}
    assert bizim["academic_staff_count"] is None
    assert bizim["students_per_academic"] is None
    assert bizim["department_count"] is None
    assert o["profile_note"]


# ==========================================================================
# 2. Hesaplamalar
# ==========================================================================


def test_buyume_dogru_hesaplanir(db: Session) -> None:
    o = rakip.competitor_analysis(db, rakip.FILTER_FOUNDATION)
    biz = _bul(o, HOME_UNIVERSITY)
    assert biz["first_student_count"] == 1000
    assert biz["student_count"] == 2000
    assert biz["growth_percent_period"] == 100.0
    b = _bul(o, "RAKİP B ÜNİVERSİTESİ")
    assert b["growth_percent_period"] == -10.0     # küçülme gizlenmez


def test_kapasite_oranlari(db: Session) -> None:
    o = rakip.competitor_analysis(db, rakip.FILTER_FOUNDATION)
    biz = _bul(o, HOME_UNIVERSITY)
    assert biz["academic_staff_count"] == 100
    assert biz["students_per_academic"] == 20.0
    assert biz["academics_per_100_students"] == 5.0


def test_kurumsal_yapi_gostergeleri(db: Session) -> None:
    o = rakip.competitor_analysis(db, rakip.FILTER_FOUNDATION)
    biz = _bul(o, HOME_UNIVERSITY)
    assert biz["academic_unit_count"] == 6
    assert biz["department_count"] == 20
    assert biz["students_per_department"] == 100.0


def test_ogrenci_govdesi_duzeye_gore_doner(db: Session) -> None:
    o = rakip.competitor_analysis(db, rakip.FILTER_FOUNDATION)
    d = _bul(o, HOME_UNIVERSITY)["by_degree_level"]
    assert d["Lisans"] == 1600
    assert d["Önlisans"] == 400
    assert sum(d.values()) == 2000


def test_siralama_yon_duyarlidir(db: Session) -> None:
    """Öğrenci/akademisyen oranında KÜÇÜK olan 1. sıradadır."""
    o = rakip.competitor_analysis(db, rakip.FILTER_FOUNDATION)
    en_iyi = min(o["universities"], key=lambda r: r["students_per_academic"])
    assert en_iyi["ranks"]["students_per_academic"] == 1
    en_buyuk = max(o["universities"], key=lambda r: r["student_count"])
    assert en_buyuk["ranks"]["student_count"] == 1


# ==========================================================================
# 3. Süzgeç kipleri
# ==========================================================================


def test_varsayilan_kip_tum_evren(db: Session) -> None:
    """VARSAYILAN ARTIK "TÜMÜ".

    ESKİ BEKLENTİ: varsayılan `FILTER_SIMILAR`, küme `FILTER_ALL`'dan küçük.
    YENİ BEKLENTİ: varsayılan `FILTER_ALL`.

    NEDEN DEĞİŞTİ: "benzer" tanımı AYNI TÜR koşulu içeriyordu. ABÜ bir
    vakıf kurumu olduğu için varsayılan karşılaştırma sessizce "yalnızca
    vakıf üniversiteleri" hâline geliyor, ODTÜ/Hacettepe/Gazi/Ankara Ü.
    hiç görünmüyordu. Karşılaştırma evrenini daraltmak bir ANALİZ
    TERCİHİDİR; varsayılan olarak dayatılamaz. Daraltma artık
    kullanıcının açık seçimidir (Devlet / Vakıf / Benzer Ölçek).
    """
    o = rakip.competitor_analysis(db)
    assert o["filter_mode"] == rakip.FILTER_ALL
    hepsi = rakip.competitor_analysis(db, rakip.FILTER_ALL)
    assert o["university_count"] == hepsi["university_count"]


def test_benzer_kip_olcek_bandi_uygular(db: Session) -> None:
    """"Benzer" YALNIZCA ölçektir; kurum türü ölçüt DEĞİLDİR.

    ABÜ 2000 öğrenci; 22.000 öğrencili kurum banda girmediği için
    dışarıdadır — VAKIF olmadığı için değil. Bant içindeki bir DEVLET
    kurumu artık meşru bir "benzer" akrandır.
    """
    o = rakip.competitor_analysis(db, rakip.FILTER_SIMILAR)
    adlar = {r["university_name"] for r in o["universities"]}
    # Ölçek dışında kaldığı için yok (tür yüzünden değil):
    assert "DEVLET D ÜNİVERSİTESİ" not in adlar
    assert "RAKİP A ÜNİVERSİTESİ" in adlar
    assert HOME_UNIVERSITY in adlar
    # Bant içindeki her kurum, TÜRÜNE BAKILMAKSIZIN içeride olmalı.
    hepsi = rakip.competitor_analysis(db, rakip.FILTER_ALL)["universities"]
    biz = next(r for r in hepsi if r["is_home_institution"])
    alt = biz["student_count"] * rakip.SIMILAR_LOWER
    ust = biz["student_count"] * rakip.SIMILAR_UPPER
    bantta = {r["university_name"] for r in hepsi
              if r["student_count"] is not None
              and alt <= r["student_count"] <= ust}
    assert bantta <= adlar, "ölçek bandındaki bir kurum türü yüzünden elenmiş"


def test_vakif_ve_devlet_kipleri(db: Session) -> None:
    v = rakip.competitor_analysis(db, rakip.FILTER_FOUNDATION)
    assert all(r["university_type"] == "VAKIF" for r in v["universities"])
    d = rakip.competitor_analysis(db, rakip.FILTER_STATE)
    # Kendi kurumumuz karşılaştırma referansı olarak DAİMA listededir.
    assert all(r["university_type"] == "DEVLET" or r["is_home_institution"]
               for r in d["universities"])


def test_kendi_kurumumuz_her_kipte_listede(db: Session) -> None:
    for kip in (rakip.FILTER_SIMILAR, rakip.FILTER_ALL,
                rakip.FILTER_FOUNDATION, rakip.FILTER_STATE):
        o = rakip.competitor_analysis(db, kip)
        assert any(r["is_home_institution"] for r in o["universities"]), kip
        assert o["home"] is not None


def test_gecersiz_kip_varsayilana_duser(db: Session) -> None:
    """ESKİ: geçersiz kip -> FILTER_SIMILAR. YENİ: -> FILTER_ALL.
    Sebep: varsayılan artık evreni daraltmıyor (bkz. üstteki test)."""
    o = rakip.competitor_analysis(db, "olmayan-kip")
    assert o["filter_mode"] == rakip.FILTER_ALL


def test_ankara_siralamasi_sizgecten_etkilenmez(db: Session) -> None:
    """"Ankara'da kaçıncıyım" sorusunun cevabı süzgeçle değişemez."""
    siralar = {kip: rakip.competitor_analysis(db, kip)["home"]["ankara_rank"]
               for kip in (rakip.FILTER_SIMILAR, rakip.FILTER_ALL,
                           rakip.FILTER_FOUNDATION, rakip.FILTER_STATE)}
    assert len(set(siralar.values())) == 1
    # 2000 öğrenci: 22000, 5000, 2700, 2400'ün ardından 5.
    assert set(siralar.values()) == {5}


# ==========================================================================
# 4. İki öğrenci sayısı karışmaz
# ==========================================================================


def test_olcek_yok_kayitli_ogrenciden_gelir(db: Session) -> None:
    """Rakip ölçeği YÖK kayıtlı sayıdan gelir, ÖSYM türevinden değil.

    ÖSYM türevi (program bazlı, son ≤4 kohort) burada 45'tir; kurumun
    kayıtlı öğrenci sayısı 2000'dir. Karşılaştırma tablosu 2000'i
    kullanmalıdır — 45 ile kıyaslamak kurumu 40 kat küçük gösterirdi.
    """
    assert student_count._yks_turevi_toplam(db) == 45
    o = rakip.competitor_analysis(db, rakip.FILTER_FOUNDATION)
    assert _bul(o, HOME_UNIVERSITY)["student_count"] == 2000


def test_yetkili_sayi_ve_osym_turevi_ayri_kalir(db: Session) -> None:
    """İki ölçüm birbirini EZMEZ; ikisi de ayrı ayrı okunabilir.

    `total_for_scope` üniversite kapsamında artık YÖK sayısını döner
    (böylece `/staffing` ile kayıtlı öğrenci ucu aynı sayıyı söyler),
    ama program bazlı ÖSYM zinciri olduğu gibi durur.
    """
    sayi, kaynak = student_count.total_for_scope_detailed(db)
    assert (sayi, kaynak) == (2000, "yok_kayitli")
    assert student_count._yks_turevi_toplam(db) == 45


def test_rakip_analizi_osym_sayisini_degistirmez(db: Session) -> None:
    onceki = student_count._yks_turevi_toplam(db)
    rakip.competitor_analysis(db, rakip.FILTER_ALL)
    assert student_count._yks_turevi_toplam(db) == onceki


# ==========================================================================
# 5. Alt seviye karşılaştırması ETKİLENMEDİ
# ==========================================================================


def test_fakulte_kapsami_hala_kardes_fakultelerle(db: Session) -> None:
    fid = db.execute(select(Faculty.id).where(Faculty.code == "MUH")).scalar_one()
    o = kiyas.peer_comparison(db, resolve(db, faculty_id=fid))
    assert o["basis"] == "sibling_faculties"
    assert o["external_institutions"] == []
    assert {r["name"] for r in o["peers"]} == {"MÜHENDİSLİK FAKÜLTESİ",
                                              "FEN FAKÜLTESİ"}


def test_bolum_kapsami_hala_ayni_fakultedeki_bolumlerle(db: Session) -> None:
    bid = db.execute(
        select(Department.id).where(Department.code == "BILMUH")).scalar_one()
    o = kiyas.peer_comparison(db, resolve(db, department_id=bid))
    assert o["basis"] == "sibling_departments"
    adlar = {r["name"] for r in o["peers"]}
    assert "MATEMATİK BÖLÜMÜ" not in adlar        # başka fakülte
    assert o["external_institutions"] == []


def test_universite_kapsami_hala_dis_kurumlari_bildirir(db: Session) -> None:
    """`peer_comparison` davranışı DEĞİŞMEDİ; rakip panosu ayrı uçtur."""
    o = kiyas.peer_comparison(db, resolve(db))
    assert o["basis"] == "external_institutions"
    assert o["peers"] == []


# ==========================================================================
# 6. Veri yokken
# ==========================================================================


def test_veri_yokken_available_false() -> None:
    motor = create_engine("sqlite://", future=True,
                          connect_args={"check_same_thread": False},
                          poolclass=StaticPool)
    Base.metadata.create_all(motor)
    s = sessionmaker(bind=motor, future=True)()
    o = rakip.competitor_analysis(s)
    assert o["available"] is False
    assert o["universities"] == []
    s.close()
    motor.dispose()
