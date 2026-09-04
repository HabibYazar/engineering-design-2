"""YÖK Akademik toplayıcı aktarımının doğruluk garantileri.

Bu testler ÜRETİM veritabanına değil, testin kendi kurduğu küçük ve sahte
bir TOPLAYICI veritabanına bakar. Amaç, aktarım kurallarının davranışını
sabitlemek:

  * kaynakta olmayan alan UYDURULMAZ (NULL kalır)
  * ders yükü yalnızca EN GÜNCEL dönemden alınır
  * hedef kurum karşılaştırma kurumu listesine girmez
  * betik idempotenttir
  * fakültesiz kayıtlar sessizce kaybolmaz, raporlanır

Sahte toplayıcı verisi kullanmak, gerçek veriyi taklit etmek değildir;
kural motorunu izole biçimde sınamaktır. Gerçek veriyle uçtan uca doğrulama
`import_yok_collector.py` çalıştırılarak yapılır.
"""

import sqlite3
from decimal import Decimal
from typing import Iterator

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import import_yok_collector as ay
from app.database import Base
from app.models import (
    AcademicProgram,
    AcademicStaff,
    BenchmarkInstitution,
    Department,
    Faculty,
)

HEDEF = "TEST ÜNİVERSİTESİ"


@pytest.fixture()
def bos_db() -> Iterator[Session]:
    """Aktarıma özel, TAMAMEN BOŞ veritabanı.

    Paketin ortak `db_session` fixture'ı demo verisiyle doldurulmuş
    veritabanını verir. Aktarım testleri "kaç fakülte oluştu" gibi sayımlar
    yaptığı için önceden var olan kayıtlar sonucu kirletirdi.
    """
    # Bellek içi veritabanı — bkz. test_ekdata_import.py'daki aynı gerekçe.
    motor = create_engine(
        "sqlite://", future=True,
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(motor)
    oturum = sessionmaker(bind=motor, future=True)()
    try:
        yield oturum
    finally:
        oturum.close()
        motor.dispose()


def _sahte_toplayici() -> sqlite3.Connection:
    """Gerçek şemanın aktarımda kullanılan sütunlarını taşıyan mini kaynak."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(
        """
        CREATE TABLE universities (
            name TEXT, city TEXT, type TEXT, source_url TEXT,
            academic_count_discovered INTEGER,
            first_seen_at TEXT, last_seen_at TEXT
        );
        CREATE TABLE academics (
            author_id TEXT, full_name TEXT, title TEXT, university_name TEXT,
            faculty TEXT, department TEXT, program TEXT, profile_url TEXT,
            email TEXT, orcid TEXT, basic_field TEXT, specialty TEXT,
            section_counts_json TEXT, last_scraped_at TEXT,
            discovered_at TEXT, last_seen_at TEXT
        );
        CREATE TABLE publications (author_id TEXT);
        CREATE TABLE theses (author_id TEXT);
        -- Gerçek şemada `courses` kaynak bağlantısını da taşır;
        -- ders geçmişi aktarımı bu sütunu okur.
        CREATE TABLE courses (author_id TEXT, data_json TEXT, source_url TEXT);
        """
    )
    c.executemany(
        "INSERT INTO universities VALUES (?,?,?,?,?,?,?)",
        [
            (HEDEF, "Ankara", "VAKIF", "http://x/1", 3, "2025-01-01", "2025-06-01"),
            ("RAKİP VAKIF ÜNİVERSİTESİ", "Ankara", "VAKIF", "http://x/2", 900,
             "2025-01-01", "2025-06-01"),
            ("DEVLET ÜNİVERSİTESİ", "Ankara", "DEVLET", "http://x/3", 2500,
             "2025-01-01", "2025-06-01"),
        ],
    )
    c.executemany(
        "INSERT INTO academics VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            # REKTÖRLÜK: idari birim. Aktarım bunu FAKÜLTE saymamalı.
            ("A0", "İDARİ KİŞİ", "Öğr. Gör.", HEDEF,
             "REKTÖRLÜK", None, None, "http://p/0", None, None, None, None,
             None, None, "2025-01-01", "2025-06-01"),
            ("A1", "AYŞE YILMAZ", "Prof. Dr. (Unvan:Profesör)", HEDEF,
             "MÜHENDİSLİK FAKÜLTESİ", "BİLGİSAYAR MÜHENDİSLİĞİ BÖLÜMÜ",
             "BİLGİSAYAR MÜHENDİSLİĞİ PR.", "http://p/1", None, None, None, None,
             None, None, "2025-01-01", "2025-06-01"),
            ("A2", "MEHMET CAN ÖZTÜRK", "Dr. Öğr. Üyesi", HEDEF,
             "MÜHENDİSLİK FAKÜLTESİ", None, None, "http://p/2", None, None,
             None, None, None, None, "2025-01-01", "2025-06-01"),
            # Fakültesi olmayan kayıt: aktarılmamalı ama raporlanmalı.
            ("A3", "BOŞ KAYIT", "Öğr. Gör.", HEDEF, None, None, None,
             "http://p/3", None, None, None, None, None, None,
             "2025-01-01", "2025-06-01"),
            # Başka kurumun akademisyeni: hiç görünmemeli.
            ("B1", "YABANCI KİŞİ", "Prof. Dr.", "RAKİP VAKIF ÜNİVERSİTESİ",
             "X FAKÜLTESİ", "X BÖLÜMÜ", None, "http://p/4", None, None, None,
             None, None, None, "2025-01-01", "2025-06-01"),
        ],
    )
    c.executemany("INSERT INTO publications VALUES (?)", [("A1",), ("A1",), ("A2",)])
    c.executemany("INSERT INTO theses VALUES (?)", [("A1",)])
    c.executemany(
        "INSERT INTO courses VALUES (?,?,?)",
        [
            ("A1", '{"Dönem": "2023-2024", "Ders Adı": "Eski Ders",'
                   ' "Dili": "Türkçe", "Saat": "9"}', "http://c/1"),
            ("A1", '{"Dönem": "2025-2026", "Ders Adı": "Algoritmalar",'
                   ' "Dili": "Türkçe", "Saat": "3"}', "http://c/2"),
            ("A1", '{"Dönem": "2025-2026", "Ders Adı": "Veri Yapıları",'
                   ' "Dili": "İngilizce", "Saat": "2"}', "http://c/3"),
            ("A2", '{"Dönem": "2025-2026", "Ders Adı": "Fizik",'
                   ' "Dili": "Türkçe", "Saat": "4"}', "http://c/4"),
        ],
    )
    c.commit()
    return c


@pytest.fixture()
def aktarim(bos_db) -> Iterator[ay.Aktarim]:
    kaynak = _sahte_toplayici()
    a = ay.Aktarim(kaynak, bos_db, HEDEF)
    a.kurumlari_aktar()
    a.yapi_ve_personel_aktar()
    bos_db.commit()
    yield a
    kaynak.close()


# --------------------------------------------------------------------------
# 1. Uydurma değer yok
# --------------------------------------------------------------------------


def test_kaynakta_olmayan_kontenjan_ve_sure_null_kalir(aktarim, bos_db) -> None:
    """Toplayıcı kontenjan/süre yayımlamaz → 0 değil NULL yazılır.

    0 yazmak "kontenjan sıfır" demektir ve doluluk oranını bozar.
    """
    programlar = bos_db.execute(
        select(AcademicProgram).where(
            AcademicProgram.description.like("Kaynak: YÖK%")
        )
    ).scalars().all()
    assert programlar, "en az bir program aktarılmış olmalı"
    for p in programlar:
        assert p.quota is None
        assert p.duration_years is None


def test_bilinmeyen_sayisal_alanlar_raporda_acikca_listelenir() -> None:
    """Sıfır bırakılan alanlar sessizce geçilmez; boşluk listesinde durur."""
    alanlar = {a for a, _ in ay.BOS_KALAN_ALANLAR}
    for beklenen in (
        "academic_staff.citation_count",
        "academic_staff.patent_count",
        "academic_staff.annual_salary_usd",
        "academic_programs.quota",
        "academic_programs.duration_years",
    ):
        assert beklenen in alanlar


def test_maas_ve_atif_sifir_ama_gercek_veri_gibi_sunulmuyor(aktarim, bos_db) -> None:
    """Kaynakta olmayan sayısal alanlar 0'dır ve bu bilinçli bir boşluktur."""
    kisi = bos_db.execute(
        select(AcademicStaff).where(AcademicStaff.staff_number == "A1")
    ).scalar_one()
    assert kisi.annual_salary_usd == Decimal("0.00")
    assert kisi.citation_count == 0
    assert kisi.patent_count == 0


# --------------------------------------------------------------------------
# 2. Sayımlar ve ders yükü
# --------------------------------------------------------------------------


def test_ders_yuku_yalnizca_en_guncel_donemden_alinir(aktarim, bos_db) -> None:
    """A1'in 2023-2024'te 9, 2025-2026'da 3+2=5 saati var → 5 olmalı.

    Bütün dönemleri toplamak (14 saat) yılların yükünü tek yıla yazmak olurdu.
    """
    kisi = bos_db.execute(
        select(AcademicStaff).where(AcademicStaff.staff_number == "A1")
    ).scalar_one()
    assert kisi.teaching_load_hours == 5
    assert kisi.academic_year == "2025-2026"


def test_yayin_ve_tez_sayilari_kisi_bazinda_dogru(aktarim, bos_db) -> None:
    kisiler = {
        s.staff_number: s
        for s in bos_db.execute(select(AcademicStaff)).scalars().all()
    }
    assert kisiler["A1"].publication_count == 2
    assert kisiler["A1"].advising_count == 1
    assert kisiler["A2"].publication_count == 1
    assert kisiler["A2"].advising_count == 0


# --------------------------------------------------------------------------
# 3. Kapsam ve yapı
# --------------------------------------------------------------------------


def test_hedef_kurum_kendi_rakibi_olarak_yazilmaz(aktarim, bos_db) -> None:
    adlar = {
        b.name for b in bos_db.execute(select(BenchmarkInstitution)).scalars().all()
    }
    assert HEDEF not in adlar
    assert "RAKİP VAKIF ÜNİVERSİTESİ" in adlar


def test_vakif_rakip_devlet_benzer_olarak_siniflanir(aktarim, bos_db) -> None:
    kurumlar = {
        b.name: b for b in bos_db.execute(select(BenchmarkInstitution)).scalars().all()
    }
    assert kurumlar["RAKİP VAKIF ÜNİVERSİTESİ"].is_competitor is True
    assert kurumlar["DEVLET ÜNİVERSİTESİ"].is_competitor is False


def test_baska_kurumun_akademisyeni_kadroya_girmez(aktarim, bos_db) -> None:
    numaralar = {
        s.staff_number
        for s in bos_db.execute(select(AcademicStaff)).scalars().all()
    }
    assert "B1" not in numaralar


def test_bolumsuz_personel_idari_birime_baglanir(aktarim, bos_db) -> None:
    """A2'nin bölümü yok; kaybolmamalı, uydurma bölüm de üretilmemeli."""
    kisi = bos_db.execute(
        select(AcademicStaff).where(AcademicStaff.staff_number == "A2")
    ).scalar_one()
    bolum = bos_db.get(Department, kisi.department_id)
    assert bolum.name == "MÜHENDİSLİK FAKÜLTESİ"
    # İki kişi bölümsüz: A2 (fakülte altında) ve A0 (Rektörlük altında).
    # Her ikisi için de üst birim adıyla bir "idari birim" bölümü açılır.
    assert aktarim.sayac["idari_birim_eklendi"] == 2


def test_fakultesiz_kayit_sessizce_kaybolmaz(aktarim) -> None:
    assert any("fakülte bilgisi yok" in n for n in aktarim.bosluklar)


def test_kaynak_izlenebilirligi_korunur(aktarim, bos_db) -> None:
    kurum = bos_db.execute(
        select(BenchmarkInstitution).where(
            BenchmarkInstitution.name == "RAKİP VAKIF ÜNİVERSİTESİ"
        )
    ).scalar_one()
    assert "http://x/2" in kurum.notes
    assert "2025-06-01" in kurum.notes


# --------------------------------------------------------------------------
# 4. Ad normalizasyonu ve idempotency
# --------------------------------------------------------------------------


def test_unvan_parantezli_ekten_arindirilir(aktarim, bos_db) -> None:
    kisi = bos_db.execute(
        select(AcademicStaff).where(AcademicStaff.staff_number == "A1")
    ).scalar_one()
    assert kisi.title == "Prof. Dr."


def test_cok_adli_kisilerde_soyad_sondaki_sozcuktur(aktarim, bos_db) -> None:
    kisi = bos_db.execute(
        select(AcademicStaff).where(AcademicStaff.staff_number == "A2")
    ).scalar_one()
    assert kisi.first_name == "MEHMET CAN"
    assert kisi.last_name == "ÖZTÜRK"


def test_ikinci_calistirma_kayit_cogaltmaz(bos_db) -> None:
    kaynak = _sahte_toplayici()
    try:
        for _ in range(2):
            a = ay.Aktarim(kaynak, bos_db, HEDEF)
            a.kurumlari_aktar()
            a.yapi_ve_personel_aktar()
            bos_db.commit()
        # MÜHENDİSLİK FAKÜLTESİ + REKTÖRLÜK (idari) = 2 üst birim.
        assert len(bos_db.execute(select(Faculty)).scalars().all()) == 2
        assert len(bos_db.execute(select(AcademicStaff)).scalars().all()) == 3
        assert a.sayac["fakulte_eklendi"] == 0
        assert a.sayac["personel_guncellendi"] == 3
    finally:
        kaynak.close()


# --------------------------------------------------------------------------
# 5. Birim türü — Rektörlük fakülte değildir
# --------------------------------------------------------------------------


def test_rektorluk_idari_birim_olarak_aktarilir(aktarim, bos_db) -> None:
    """Toplayıcı "REKTÖRLÜK"ü de fakülte alanında verir; aktarım tür ayırır."""
    from app.services.unit_types import ADMINISTRATIVE, FACULTY

    birimler = {
        f.name: f for f in bos_db.execute(select(Faculty)).scalars().all()
    }
    assert birimler["REKTÖRLÜK"].unit_type == ADMINISTRATIVE
    assert birimler["MÜHENDİSLİK FAKÜLTESİ"].unit_type == FACULTY


def test_akademik_birim_listesinde_rektorluk_yok(aktarim, bos_db) -> None:
    from app.services.scope import academic_faculty_ids

    akademik = set(academic_faculty_ids(bos_db))
    rektorluk = bos_db.execute(
        select(Faculty).where(Faculty.name == "REKTÖRLÜK")
    ).scalar_one()
    assert rektorluk.id not in akademik


def test_idari_birim_fakulte_sayisina_dahil_edilmez(aktarim) -> None:
    """Sayaçta idari üst birim ayrı raporlanır; "2 fakülte" denmez."""
    assert aktarim.sayac["fakulte_eklendi"] == 1
    assert aktarim.sayac["idari_ust_birim_eklendi"] == 1


def test_tur_sinifllandirmasi_mevcut_kayitta_da_duzeltilir(bos_db) -> None:
    """Eskiden FACULTY yazılmış bir Rektörlük kaydı ikinci aktarımda düzelir."""
    from app.services.unit_types import ADMINISTRATIVE, FACULTY

    bos_db.add(Faculty(name="REKTÖRLÜK", code="ESKI", unit_type=FACULTY,
                       is_active=True))
    bos_db.commit()

    kaynak = _sahte_toplayici()
    try:
        a = ay.Aktarim(kaynak, bos_db, HEDEF)
        a.kurumlari_aktar()
        a.yapi_ve_personel_aktar()
        bos_db.commit()
    finally:
        kaynak.close()

    kayit = bos_db.execute(
        select(Faculty).where(Faculty.code == "ESKI")
    ).scalar_one()
    assert kayit.unit_type == ADMINISTRATIVE
    assert a.sayac["fakulte_turu_duzeltildi"] == 1


# --------------------------------------------------------------------------
# 6. Akademisyenin ders geçmişi (yıl bazında)
# --------------------------------------------------------------------------


def test_ders_gecmisi_yil_bazinda_aktarilir(aktarim, bos_db) -> None:
    """`teaching_load_hours` tek sayıdır; ham satırlar ayrı tabloda durur."""
    from app.models import AcademicStaffCourse

    dersler = bos_db.execute(select(AcademicStaffCourse)).scalars().all()
    assert len(dersler) == 4
    assert {d.academic_year for d in dersler} == {"2023-2024", "2025-2026"}


def test_ders_adi_ve_dili_korunur(aktarim, bos_db) -> None:
    from app.models import AcademicStaffCourse

    ders = bos_db.execute(
        select(AcademicStaffCourse).where(
            AcademicStaffCourse.course_name == "Veri Yapıları"
        )
    ).scalar_one()
    assert ders.language == "İngilizce"
    assert ders.weekly_hours == 2
    assert ders.source_url == "http://c/3"


def test_ders_gecmisi_ikinci_calistirmada_cogalmaz(bos_db) -> None:
    from app.models import AcademicStaffCourse

    kaynak = _sahte_toplayici()
    try:
        for _ in range(2):
            a = ay.Aktarim(kaynak, bos_db, HEDEF)
            a.kurumlari_aktar()
            a.yapi_ve_personel_aktar()
            bos_db.commit()
        assert len(bos_db.execute(select(AcademicStaffCourse)).scalars().all()) == 4
    finally:
        kaynak.close()
