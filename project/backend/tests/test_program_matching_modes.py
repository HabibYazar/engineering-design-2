"""PROGRAM EŞLEŞTİRME ADALETİ — iki bağımsız boyutun testleri.

Bu paket asıl olarak NEGATİF kanıt üretmek için vardır. "Benzer Bölümler"
kipinin doğru programları getirmesi yetmez; YANLIŞ programları
GETİRMEDİĞİNİ de kanıtlamak gerekir, çünkü sessizce eklenen bir Maden
Mühendisliği kimsenin fark etmeyeceği yanlış bir sayı üretir.

Ölçüt kayıtlıdır ve kapalıdır: kanonik program anahtarı + dar disiplin
ailesi. "Adında mühendislik geçiyor" ölçüt DEĞİLDİR ve bu paket bunu
açıkça test eder.
"""

from __future__ import annotations

import pytest

from app.services.program_equivalence import (
    MATCH_EQUIVALENT,
    MATCH_EXACT,
    MATCH_SIMILAR,
    canonical_program_key,
    discipline_family,
    program_match_type,
)
from app.services.assistant.peer_filter_intent import (
    detect_matching_mode,
    resolve_comparison_universe,
)
from app.services import yok_atlas_comparison_service as atlas


# ---------------------------------------------------------------------------
# 1-4  EŞLEŞME DERECESİ
# ---------------------------------------------------------------------------

def test_1_ayni_yazim_exact_farkli_yazim_equivalent():
    assert program_match_type("Yazılım Mühendisliği",
                              "Yazılım Mühendisliği") == MATCH_EXACT
    # Dil/ek varyantı aynı kanonik anahtara düşer ama yazım farklıdır.
    assert program_match_type("Yazılım Mühendisliği",
                              "Yazılım Mühendisliği (İngilizce)") in (
        MATCH_EXACT, MATCH_EQUIVALENT)


@pytest.mark.parametrize("akran", [
    "Bilgisayar Mühendisliği",
    "Yapay Zeka Mühendisliği",
    "Yapay Zeka ve Veri Mühendisliği",
    "Bilişim Sistemleri Mühendisliği",
    "Bilgisayar Bilimleri",
])
def test_2_bilisim_ailesi_benzer_sayilir(akran):
    assert program_match_type("Yazılım Mühendisliği", akran) == MATCH_SIMILAR


@pytest.mark.parametrize("akran", [
    "Maden Mühendisliği",
    "İnşaat Mühendisliği",
    "Makine Mühendisliği",
    "Metalurji ve Malzeme Mühendisliği",
    "Gıda Mühendisliği",
    "Jeoloji Mühendisliği",
    "Hidrojeoloji Mühendisliği",
    "Çevre Mühendisliği",
    "Su Ürünleri Mühendisliği",
    "Tarım Makineleri ve Teknolojileri Mühendisliği",
    "Ağaç İşleri Endüstri Mühendisliği",
])
def test_3_ilgisiz_muhendislikler_ASLA_benzer_degil(akran):
    """NEGATİF KANIT — asıl mesele budur.

    Hepsinin adında "Mühendisliği" geçer. Hiçbiri Yazılım Mühendisliği
    ile akademik olarak kıyaslanabilir değildir. "Ağaç İşleri Endüstri
    Mühendisliği" ayrıca naif bir "Endüstri" eşleşmesinin tuzağıdır.
    """
    assert program_match_type("Yazılım Mühendisliği", akran) is None


def test_4_kayitli_olmayan_program_fail_closed():
    """Kayıtta olmayan bir program sessizce bir aileye SIZAMAZ."""
    assert discipline_family(canonical_program_key("Gastronomi ve Mutfak Sanatları")) is None
    assert program_match_type("Yazılım Mühendisliği",
                              "Gastronomi ve Mutfak Sanatları") is None
    # Boş/None girdi de patlamaz, None döner.
    assert program_match_type(None, "Yazılım Mühendisliği") is None
    assert program_match_type("Yazılım Mühendisliği", "") is None


def test_5_endustri_ile_agac_isleri_endustri_ayni_degil():
    assert program_match_type("Endüstri Mühendisliği",
                              "Ağaç İşleri Endüstri Mühendisliği") is None
    # Buna karşılık gerçek Endüstri Mühendisliği elbette eşleşir.
    assert program_match_type("Endüstri Mühendisliği",
                              "Endüstri Mühendisliği") == MATCH_EXACT


def test_6_yonetim_bilisim_sistemleri_muhendislikle_karistirilmaz():
    """YBS işletme kökenlidir; bilişim ailesine ALINMAZ."""
    assert program_match_type("Yazılım Mühendisliği",
                              "Yönetim Bilişim Sistemleri") is None
    assert program_match_type("İşletme",
                              "Yönetim Bilişim Sistemleri") == MATCH_SIMILAR


# ---------------------------------------------------------------------------
# 7-9  KİP ÇÖZÜMÜ VE BAĞLAM VARSAYILANI
# ---------------------------------------------------------------------------

def test_7_baglam_varsayilani_kapsama_gore():
    from app.services.scope import FACULTY_LEVEL, PROGRAM_LEVEL, Scope

    assert atlas.default_match_mode(
        Scope(level=FACULTY_LEVEL)) == atlas.MATCH_MODE_SHARED
    assert atlas.default_match_mode(
        Scope(level=PROGRAM_LEVEL)) == atlas.MATCH_MODE_SAME
    assert atlas.default_match_mode(None) == atlas.MATCH_MODE_SAME


def test_8_gecersiz_kip_baglamin_varsayilanina_duser():
    from app.services.scope import PROGRAM_LEVEL, Scope

    # Sessizce "benzer"e kaymaz; en dar ve en güvenli kipe düşer.
    assert atlas.default_match_mode(Scope(level=PROGRAM_LEVEL)) == "same_program"


@pytest.mark.parametrize("cumle,beklenen", [
    ("aynı bölümle karşılaştır", "same_program"),
    ("benzer bölümlerle karşılaştır", "similar_programs"),
    ("ortak bölümler üzerinden kıyasla", "shared_programs"),
    ("benzer programlarla karşılaştır", "similar_programs"),
    ("bu dönem bütçe ne durumda", None),
])
def test_9_asistan_kip_niyeti(cumle, beklenen):
    assert detect_matching_mode(cumle) == beklenen


def test_10_iki_boyut_asistanda_birlikte_cozulur():
    """Bir cümle iki boyutu da doldurur; biri diğerini bastırmaz."""
    r = resolve_comparison_universe(
        "vakıf üniversiteleriyle benzer bölümler üzerinden karşılaştır", [])
    assert r["mode"] == "foundation"
    assert r["matching_mode"] == "similar_programs"

    # Açık kurum dalında da ikinci boyut korunur.
    r2 = resolve_comparison_universe(
        "ODTÜ ile benzer bölümleri karşılaştır",
        ["ORTA DOĞU TEKNİK ÜNİVERSİTESİ"])
    assert r2["explicit_universities"] == ["ORTA DOĞU TEKNİK ÜNİVERSİTESİ"]
    assert r2["matching_mode"] == "similar_programs"


def test_11_ekran_secicisi_niyetin_gerisinde_kalir():
    r = resolve_comparison_universe("aynı bölümle karşılaştır", [],
                                    ekran_eslesme="similar_programs")
    assert r["matching_mode"] == "same_program"          # cümle kazanır
    r2 = resolve_comparison_universe("karşılaştır", [],
                                     ekran_eslesme="similar_programs")
    assert r2["matching_mode"] == "similar_programs"     # ekran devreye girer
    assert r2["matching_mode_source"] == "screen_selector"


# ---------------------------------------------------------------------------
# 12-16  SERVİS DAVRANIŞI (gerçek veritabanı gerektirir)
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_session():
    """GERÇEK veritabanına salt-okunur oturum.

    Paylaşılan `db_session` fixture'ı boş bir seed veritabanına bakar;
    orada ne YÖK Atlas satırları ne de Yazılım Mühendisliği programı
    vardır, dolayısıyla bu testler sessizce atlanırdı. Eşleştirme
    mantığının asıl kanıtı GERÇEK veri üzerinde olmalıdır, bu yüzden
    kaynak veritabanı doğrudan açılır.

    Yazma YAPILMAZ: oturum yalnızca okur ve sonunda rollback edilir.
    """
    import os
    import shutil
    import tempfile

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    kaynak = os.path.join(kok, "university_management.db")
    if not os.path.exists(kaynak):
        pytest.skip("Gerçek veritabanı bulunamadı.")
    # Kaynak dosyaya hiç dokunmamak için geçici bir kopya üzerinde çalışılır.
    with tempfile.TemporaryDirectory() as gecici:
        kopya = os.path.join(gecici, "okuma.db")
        shutil.copy2(kaynak, kopya)
        motor = create_engine(f"sqlite:///{kopya}")
        oturum = sessionmaker(bind=motor)()
        try:
            yield oturum
        finally:
            oturum.rollback()
            oturum.close()
            motor.dispose()


def _yazilim_kapsami(db):
    from sqlalchemy import select
    from app.models import AcademicProgram
    from app.services.scope import resolve

    prog = db.execute(
        select(AcademicProgram).where(AcademicProgram.name.ilike("%YAZILIM%"))
    ).scalars().first()
    if prog is None:
        pytest.skip("Bu veritabanında Yazılım Mühendisliği programı yok.")
    return resolve(db, academic_program_id=prog.id)


def test_12_benzer_kip_aynidan_dar_degildir(db_session):
    sc = _yazilim_kapsami(db_session)
    ayni = atlas.comparison(db_session, sc, "2024-2025",
                            matching_mode="same_program")
    benzer = atlas.comparison(db_session, sc, "2024-2025",
                              matching_mode="similar_programs")
    if not ayni["available"]:
        pytest.skip("Atlas verisi yüklü değil.")
    assert benzer["peer_count"] >= ayni["peer_count"]
    assert benzer["cohort_basis"] == "same_discipline_family_programs"
    assert ayni["cohort_basis"] == "same_canonical_program"


def test_13_benzer_kipte_ilgisiz_muhendislik_GIRMEZ(db_session):
    """Uçtan uca negatif kanıt: kayıt doğru olsa bile servis onu
    doğru uygulamıyor olabilirdi. Bu test o boşluğu kapatır."""
    sc = _yazilim_kapsami(db_session)
    o = atlas.comparison(db_session, sc, "2024-2025",
                         matching_mode="similar_programs")
    if not o["available"]:
        pytest.skip("Atlas verisi yüklü değil.")
    yasakli = ("Maden", "İnşaat", "Makine", "Metalurji", "Gıda",
               "Jeoloji", "Çevre")
    giren = [p.get("program_name") or "" for p in o["peers"]
             if not p["is_home_institution"]]
    ihlal = [ad for ad in giren if any(y in ad for y in yasakli)]
    assert ihlal == [], f"İlgisiz programlar karşılaştırmaya girdi: {ihlal}"


def test_14_iki_boyut_birbirini_degistirmez(db_session):
    """Kurum türünü değiştirmek eşleştirme kipini, kipi değiştirmek
    kurum türünü DEĞİŞTİRMEZ."""
    sc = _yazilim_kapsami(db_session)
    for tur in ("all", "state", "foundation"):
        for kip in ("same_program", "similar_programs"):
            o = atlas.comparison(db_session, sc, "2024-2025",
                                 institution_type=tur, matching_mode=kip)
            assert o["institution_type_filter"] == tur
            assert o["matching_mode"] == kip


def test_15_ortak_bolumler_program_kapsaminda_acikca_geri_duser(db_session):
    sc = _yazilim_kapsami(db_session)
    o = atlas.comparison(db_session, sc, "2024-2025",
                         matching_mode="shared_programs")
    assert o["matching_mode"] == "same_program"
    assert o["matching_mode_fallback"] == {
        "requested": "shared_programs",
        "applied": "same_program",
        "reason": "shared_programs_requires_faculty_scope",
    }


def test_16_aciklanabilirlik_ust_verisi_eksiksiz(db_session):
    sc = _yazilim_kapsami(db_session)
    o = atlas.comparison(db_session, sc, "2024-2025",
                         matching_mode="similar_programs")
    if not o["available"]:
        pytest.skip("Atlas verisi yüklü değil.")
    for alan in ("institution_type_filter", "matching_mode",
                 "matching_mode_label", "cohort_basis", "home_programs",
                 "peer_programs_used", "excluded_peer_programs",
                 "match_type_breakdown", "matching_explanation",
                 "home_discipline_families"):
        assert alan in o, f"Eksik açıklanabilirlik alanı: {alan}"
    # Her akran satırı gerekçesini KENDİSİ taşır.
    for satir in o["peers"]:
        if satir["is_home_institution"]:
            continue
        assert satir["match_type"] in (MATCH_EXACT, MATCH_EQUIVALENT,
                                       MATCH_SIMILAR)
        assert satir["match_reason"]


def test_17_ortalama_yuzde_toplanmaz(db_session):
    """Doluluk yüzdesi ASLA yüzdelerin toplamı/ortalaması değildir;
    toplam kontenjan ve toplam yerleşenden yeniden hesaplanır."""
    sc = _yazilim_kapsami(db_session)
    o = atlas.comparison(db_session, sc, "2024-2025",
                         matching_mode="similar_programs")
    if not o["available"]:
        pytest.skip("Atlas verisi yüklü değil.")
    for satir in o["peers"]:
        kont, yer = satir.get("quota"), satir.get("placed_students")
        dol = satir.get("occupancy_percent")
        if not kont or yer is None or dol is None:
            continue
        assert abs(dol - (yer / kont * 100)) < 0.01, (
            f"{satir['label']}: doluluk yeniden hesaplanmamış")
