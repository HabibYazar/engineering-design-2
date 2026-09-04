"""RAKİP ÜCRET KIYASI KAPSAMI TAKİP EDER — hedefli regresyon.

Düzeltilen hata: bölüm/program seçiliyken bile grafik KURUM GENELİ
medyanlarını gösteriyordu. Bu testler kıyasın kapsamla birlikte
daraldığını ve daralırken hiçbir yerde kurum ortalamasına geri
düşmediğini kanıtlar.

Veri, testin kendi kurduğu küçük bir kümedir; gerçek veritabanına
bağımlı değildir. Kurgu, gerçek kaynaktaki TUZAKLARI birebir taklit
eder: toplu satırlar ("Tüm Programlar"), yanıltıcı benzer adlar
("Arka-Yüz Yazılım Geliştirme"), dil ekleri ve aralık metinleri.
"""

from decimal import Decimal

import pytest

from app.models.academic_program import AcademicProgram
from app.models.department import Department
from app.models.faculty import Faculty
from app.models.tuition_fee import (
    FEE_FULL,
    FEE_HALF_SCHOLARSHIP,
    CompetitorTuitionFee,
    ProgramTuitionFee,
)
from app.models.university_headcount import HOME_UNIVERSITY
from app.services import program_equivalence as esdeger
from app.services import tuition_service as service
from app.services.scope import resolve

YIL = "2025-2026"
ONCEKI = "2024-2025"


# ---------------------------------------------------------------------------
# Kurgu
# ---------------------------------------------------------------------------


#: Bu modülün yazdığı HER satır bu damgayı taşır; sökme işlemi damgaya
#: bakar. `db_session` paylaşılan bir veritabanı verir ve testler arasında
#: geri alma YAPMAZ; kurgumuzu kendimiz temizlemezsek sonraki test
#: benzersizlik kısıtına takılır.
DAMGA = "test_rakip_ucret_kapsami"


@pytest.fixture()
def veri(db_session):
    """Bir fakülte, iki bölüm, iki program + rakip ücret satırları."""
    fak = Faculty(name="MÜHENDİSLİK VE MİMARLIK FAKÜLTESİ (test)",
                  code="TSTMUHMIM")
    db_session.add(fak)
    db_session.flush()

    b_yaz = Department(name="YAZILIM MÜHENDİSLİĞİ BÖLÜMÜ", code="TSTYAZ",
                       faculty_id=fak.id)
    b_bil = Department(name="BİLGİSAYAR MÜHENDİSLİĞİ BÖLÜMÜ", code="TSTBIL",
                       faculty_id=fak.id)
    db_session.add_all([b_yaz, b_bil])
    db_session.flush()

    p_yaz = AcademicProgram(name="YAZILIM MÜHENDİSLİĞİ PR.", code="TSTYAZP",
                            department_id=b_yaz.id, degree_level="LISANS")
    p_bil = AcademicProgram(name="BİLGİSAYAR MÜHENDİSLİĞİ PR.", code="TSTBILP",
                            department_id=b_bil.id, degree_level="LISANS")
    db_session.add_all([p_yaz, p_bil])
    db_session.flush()

    def bizim(program, dept, ad, tur, ucret, yil=YIL, dil="İngilizce"):
        return ProgramTuitionFee(
            academic_year=yil, academic_program_id=program.id,
            department_id=dept.id, faculty_id=fak.id,
            source_faculty_name=fak.name, source_program_name=ad,
            education_language=dil, fee_type=tur,
            annual_fee=Decimal(ucret), source_dataset=DAMGA,
            source_file="test.xlsx")

    db_session.add_all([
        bizim(p_yaz, b_yaz, "YAZILIM MÜHENDİSLİĞİ PR.", FEE_HALF_SCHOLARSHIP, 464000),
        bizim(p_yaz, b_yaz, "YAZILIM MÜHENDİSLİĞİ PR.", FEE_FULL, 928000),
        bizim(p_bil, b_bil, "BİLGİSAYAR MÜHENDİSLİĞİ PR.", FEE_HALF_SCHOLARSHIP, 400000),
        # Önceki yıl: yıl süzmesinin çalıştığını göstermek için.
        bizim(p_yaz, b_yaz, "YAZILIM MÜHENDİSLİĞİ PR.", FEE_HALF_SCHOLARSHIP,
              300000, yil=ONCEKI),
    ])

    def rakip(kurum, ad, tur, ucret, yil=YIL, seviye="LISANS", metin=None):
        return CompetitorTuitionFee(
            university_name=kurum, academic_year=yil, level=seviye,
            unit_name="Mühendislik Fakültesi", program_name=ad, fee_type=tur,
            annual_fee=None if ucret is None else Decimal(ucret),
            fee_text=metin or str(ucret), source_dataset=DAMGA,
            source_file="test.xlsx")

    db_session.add_all([
        # --- ALFA: her iki programı da var, aynı dilde ---
        rakip("Alfa Universitesi", "Yazılım Mühendisliği (İngilizce)",
              FEE_HALF_SCHOLARSHIP, 425000),
        rakip("Alfa Universitesi", "Bilgisayar Mühendisliği (İngilizce)",
              FEE_HALF_SCHOLARSHIP, 415000),
        # --- BETA: YALNIZCA Bilgisayar var; Yazılım kohortunda GÖRÜNMEMELİ ---
        rakip("Beta Universitesi", "Computer Engineering",
              FEE_HALF_SCHOLARSHIP, 500000),
        # --- GAMA: hiçbir eşdeğer program yok, yalnızca TOPLU satır ---
        #     Kurum medyanına geri düşülürse bu kurum listeye sızar.
        rakip("Gama Universitesi", "Tüm Programlar", FEE_HALF_SCHOLARSHIP, 700000),
        rakip("Gama Universitesi", "Mühendislik Fakültesi*",
              FEE_HALF_SCHOLARSHIP, 720000),
        # --- DELTA: ADI BENZEYEN AMA FARKLI programlar — eşleşmemeli ---
        rakip("Delta Universitesi", "Arka-Yüz Yazılım Geliştirme",
              FEE_HALF_SCHOLARSHIP, 240000, seviye="ONLISANS"),
        rakip("Delta Universitesi", "Yapay Zeka Mühendisliği",
              FEE_HALF_SCHOLARSHIP, 999000),
        rakip("Delta Universitesi", "Bilişim Sistemleri Mühendisliği (İngilizce)",
              FEE_HALF_SCHOLARSHIP, 888000),
        # --- EPSILON: doğru program ama YANLIŞ ÜCRET TÜRÜ ---
        rakip("Epsilon Universitesi", "Yazılım Mühendisliği (İngilizce)",
              FEE_FULL, 1020000),
        # --- ZETA: doğru program ama BAŞKA YIL ---
        rakip("Zeta Universitesi", "Yazılım Mühendisliği (İngilizce)",
              FEE_HALF_SCHOLARSHIP, 350000, yil=ONCEKI),
        # --- ETA: doğru program, ücret ARALIK METNİ (sayı yok) ---
        rakip("Eta Universitesi", "Yazılım Mühendisliği (İngilizce)",
              FEE_HALF_SCHOLARSHIP, None, metin="400.000 TL - 450.000 TL"),
    ])
    db_session.commit()
    yield {"faculty": fak, "yazilim": b_yaz, "bilgisayar": b_bil,
           "p_yaz": p_yaz, "p_bil": p_bil}

    # --- SÖKME: kurguyu damgasından bularak geri al ---
    db_session.query(ProgramTuitionFee).filter_by(source_dataset=DAMGA).delete()
    db_session.query(CompetitorTuitionFee).filter_by(source_dataset=DAMGA).delete()
    bolum_idleri = [b.id for b in
                    db_session.query(Department).filter_by(faculty_id=fak.id)]
    if bolum_idleri:
        db_session.query(AcademicProgram).filter(
            AcademicProgram.department_id.in_(bolum_idleri)).delete(
                synchronize_session=False)
    db_session.query(Department).filter_by(faculty_id=fak.id).delete()
    db_session.query(Faculty).filter_by(id=fak.id).delete()
    db_session.commit()


def _kiyas(db, **kapsam):
    return service.scoped_competitor_comparison(
        db, resolve(db, **kapsam), YIL, FEE_HALF_SCHOLARSHIP)


def _kurumlar(o):
    return {u["university_name"] for u in o["universities"]}


def _rakipler(o):
    return {u["university_name"] for u in o["universities"]
            if not u["is_home_institution"]}


# ---------------------------------------------------------------------------
# 1. Normalizasyon ve eşanlam kuralları (veritabanı gerekmez)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ad,beklenen", [
    ("Yazılım Mühendisliği", "SOFTWARE_ENG"),
    ("Yazılım Mühendisliği (İngilizce)", "SOFTWARE_ENG"),
    ("Yazılım Mühendisliği (Türkçe)", "SOFTWARE_ENG"),
    ("YAZILIM MÜHENDİSLİĞİ PR.", "SOFTWARE_ENG"),
    ("Software Engineering", "SOFTWARE_ENG"),
    ("Bilgisayar Mühendisliği (İngilizce)", "COMPUTER_ENG"),
    ("Computer Engineering", "COMPUTER_ENG"),
    ("BİLGİSAYAR MÜHENDİSLİĞİ PR.", "COMPUTER_ENG"),
])
def test_esanlamlar_ayni_anahtara_iner(ad, beklenen):
    assert esdeger.canonical_program_key(ad) == beklenen


@pytest.mark.parametrize("ad", [
    "Arka-Yüz Yazılım Geliştirme",       # "Yazılım" geçiyor ama başka program
    "Yapay Zeka Mühendisliği",
    "Bilişim Sistemleri Mühendisliği",
    "Bilgisayar Programcılığı",          # ön lisans, "Bilgisayar" geçiyor
])
def test_benzer_adlar_yazilim_ya_da_bilgisayara_karismaz(ad):
    k = esdeger.canonical_program_key(ad)
    assert k not in ("SOFTWARE_ENG", "COMPUTER_ENG")


@pytest.mark.parametrize("ad", [
    "Tüm Programlar", "Diğer Tüm Programlar", "Lisans Programları (Genel)",
    "Önlisans Programları", "Mühendislik Programları", "Mühendislik Fakültesi*",
    "İktisadi ve İdari Bilimler Programları",
    "Dil ve Konuşma Terapisi, Hemşirelik",
    "Mühendislik Programları (Bilgisayar, EE, Endüstri, İnşaat, Makine, Yazılım)",
])
def test_toplu_satirlar_program_kiyasina_giremez(ad):
    assert esdeger.is_aggregate_label(ad) is True
    assert esdeger.canonical_program_key(ad) is None


def test_dil_yalnizca_yaziliysa_okunur():
    assert esdeger.program_language("Yazılım Mühendisliği (İngilizce)") == "İngilizce"
    assert esdeger.program_language("Yazılım Mühendisliği (Türkçe)") == "Türkçe"
    assert esdeger.program_language("Yazılım Mühendisliği") is None


def test_gosterim_adi_kuyrugu_temizler():
    assert esdeger.display_program_name("YAZILIM MÜHENDİSLİĞİ PR.") == "Yazılım Mühendisliği"
    assert esdeger.display_program_name("YAZILIM MÜHENDİSLİĞİ BÖLÜMÜ") == "Yazılım Mühendisliği"
    # Zaten düzgün yazılmış ad bozulmaz.
    assert (esdeger.display_program_name("Bilişim Sistemleri Mühendisliği")
            == "Bilişim Sistemleri Mühendisliği")


# ---------------------------------------------------------------------------
# 2. Üniversite kapsamı — eski davranış korunur
# ---------------------------------------------------------------------------


def test_universite_kapsaminda_kurum_kiyasi_surer(db_session, veri):
    o = _kiyas(db_session)
    assert o["mode"] == "university"
    # Toplu satır yayımlayan kurum ÜNİVERSİTE kıyasında meşrudur.
    assert "Gama Universitesi" in _kurumlar(o)
    assert "kurum medyanları" in o["subtitle"]


def test_universite_kapsaminda_baslikta_program_adi_yok(db_session, veri):
    o = _kiyas(db_session)
    assert "Yazılım" not in o["title"]


# ---------------------------------------------------------------------------
# 3. Bölüm kapsamı — yalnızca eşdeğer programlar
# ---------------------------------------------------------------------------


def test_yazilim_kapsami_yalnizca_yazilim_esdegerlerini_getirir(db_session, veri):
    o = _kiyas(db_session, department_id=veri["yazilim"].id)
    assert o["mode"] == "program"
    assert o["program_keys"] == ["SOFTWARE_ENG"]
    assert _rakipler(o) == {"Alfa Universitesi", "Eta Universitesi"}
    for u in o["universities"]:
        if u["is_home_institution"]:
            continue
        for m in u["matched_programs"]:
            assert m["canonical_key"] == "SOFTWARE_ENG"


def test_bilgisayar_kapsami_yalnizca_bilgisayar_esdegerlerini_getirir(db_session, veri):
    o = _kiyas(db_session, department_id=veri["bilgisayar"].id)
    assert o["program_keys"] == ["COMPUTER_ENG"]
    # Beta yalnızca İngilizce adla ("Computer Engineering") yayımlıyor.
    assert _rakipler(o) == {"Alfa Universitesi", "Beta Universitesi"}


def test_bolum_degisince_kohort_gercekten_degisir(db_session, veri):
    yaz = _kiyas(db_session, department_id=veri["yazilim"].id)
    bil = _kiyas(db_session, department_id=veri["bilgisayar"].id)
    assert _rakipler(yaz) != _rakipler(bil)
    assert yaz["program_keys"] != bil["program_keys"]


def test_alakasiz_programlar_disarida_kalir(db_session, veri):
    o = _kiyas(db_session, department_id=veri["yazilim"].id)
    # Delta'nın üç programı da Yazılım Mühendisliği DEĞİL.
    assert "Delta Universitesi" not in _kurumlar(o)


def test_esdegeri_olmayan_kurum_genel_medyanla_ikame_edilmez(db_session, veri):
    """Gama yalnızca toplu satır yayımlıyor: listeye HİÇ girmemeli."""
    for bolum in (veri["yazilim"], veri["bilgisayar"]):
        o = _kiyas(db_session, department_id=bolum.id)
        assert "Gama Universitesi" not in _kurumlar(o)
        assert all(720000 not in (u["median_fee"], u["max_fee"])
                   for u in o["universities"])


# ---------------------------------------------------------------------------
# 4. Ücret türü ve akademik yıl
# ---------------------------------------------------------------------------


def test_ucret_turu_karistirilmaz(db_session, veri):
    o = _kiyas(db_session, department_id=veri["yazilim"].id)
    assert o["fee_type"] == FEE_HALF_SCHOLARSHIP
    # Epsilon aynı programı ama TAM ÜCRET olarak yayımlıyor.
    assert "Epsilon Universitesi" not in _kurumlar(o)


def test_tam_ucret_secilince_kohort_da_tam_ucret_olur(db_session, veri):
    o = service.scoped_competitor_comparison(
        db_session, resolve(db_session, department_id=veri["yazilim"].id),
        YIL, FEE_FULL)
    assert "Epsilon Universitesi" in _kurumlar(o)
    assert "Alfa Universitesi" not in _kurumlar(o)   # Alfa yalnızca %50 yayımlıyor
    assert o["fee_type_label"] == "Tam ücret"


def test_akademik_yil_karistirilmaz(db_session, veri):
    o = _kiyas(db_session, department_id=veri["yazilim"].id)
    assert o["academic_year"] == YIL
    # Zeta yalnızca ÖNCEKİ yılda yayımlıyor.
    assert "Zeta Universitesi" not in _kurumlar(o)


def test_secili_yilda_veri_yoksa_baska_yila_dusulmez(db_session, veri):
    o = service.scoped_competitor_comparison(
        db_session, resolve(db_session, department_id=veri["bilgisayar"].id),
        ONCEKI, FEE_HALF_SCHOLARSHIP)
    assert o["available"] is False
    assert o["academic_year"] == ONCEKI
    assert o["universities"] == []
    assert o["unavailable_reason"]


def test_onceki_yil_secilince_o_yilin_degeri_kullanilir(db_session, veri):
    o = service.scoped_competitor_comparison(
        db_session, resolve(db_session, department_id=veri["yazilim"].id),
        ONCEKI, FEE_HALF_SCHOLARSHIP)
    ev = next(u for u in o["universities"] if u["is_home_institution"])
    assert ev["median_fee"] == 300000        # 464.000 DEĞİL
    assert _rakipler(o) == {"Zeta Universitesi"}


# ---------------------------------------------------------------------------
# 5. Kendi değerimiz
# ---------------------------------------------------------------------------


def test_kendi_cubugumuz_secili_programin_ucretidir(db_session, veri):
    o = _kiyas(db_session, department_id=veri["yazilim"].id)
    ev = next(u for u in o["universities"] if u["is_home_institution"])
    assert ev["university_name"] == HOME_UNIVERSITY
    assert ev["median_fee"] == 464000

    o2 = _kiyas(db_session, department_id=veri["bilgisayar"].id)
    ev2 = next(u for u in o2["universities"] if u["is_home_institution"])
    assert ev2["median_fee"] == 400000
    assert ev["median_fee"] != ev2["median_fee"]


def test_kendi_cubugumuz_kurum_medyani_degildir(db_session, veri):
    kurum = _kiyas(db_session)
    kurum_evi = next(u for u in kurum["universities"] if u["is_home_institution"])
    program = _kiyas(db_session, department_id=veri["yazilim"].id)
    program_evi = next(u for u in program["universities"]
                       if u["is_home_institution"])
    # Kurum geneli iki programın medyanı (432.000); program kapsamı 464.000.
    assert kurum_evi["median_fee"] != program_evi["median_fee"]


# ---------------------------------------------------------------------------
# 6. Fakülte kapsamı
# ---------------------------------------------------------------------------


def test_fakulte_kapsami_fakultedeki_programlarin_esdegerlerini_kullanir(
        db_session, veri):
    o = _kiyas(db_session, faculty_id=veri["faculty"].id)
    assert set(o["program_keys"]) == {"SOFTWARE_ENG", "COMPUTER_ENG"}
    assert _rakipler(o) == {"Alfa Universitesi", "Beta Universitesi",
                            "Eta Universitesi"}
    assert "Gama Universitesi" not in _kurumlar(o)


def test_fakulte_kapsami_kurum_medyanina_dusmez(db_session, veri):
    o = _kiyas(db_session, faculty_id=veri["faculty"].id)
    assert o["mode"] == "program"
    assert "kurum medyanları" not in o["subtitle"]


# ---------------------------------------------------------------------------
# 7. Başlık / alt başlık ve üst veri
# ---------------------------------------------------------------------------


def test_baslik_kapsamla_degisir(db_session, veri):
    kurum = _kiyas(db_session)
    yaz = _kiyas(db_session, department_id=veri["yazilim"].id)
    bil = _kiyas(db_session, department_id=veri["bilgisayar"].id)
    assert yaz["title"] == ("Rakip Üniversitelerde Yazılım Mühendisliği "
                            "Ücret Karşılaştırması")
    assert bil["title"] == ("Rakip Üniversitelerde Bilgisayar Mühendisliği "
                            "Ücret Karşılaştırması")
    assert kurum["title"] != yaz["title"] != bil["title"]


def test_alt_baslik_yil_ve_ucret_turunu_soyler(db_session, veri):
    o = _kiyas(db_session, department_id=veri["yazilim"].id)
    assert YIL in o["subtitle"]
    assert "%50 burslu" in o["subtitle"]
    assert "eşdeğer" in o["subtitle"]


def test_program_kapsaminda_kurum_medyani_ifadesi_kullanilmaz(db_session, veri):
    for kapsam in ({"department_id": veri["yazilim"].id},
                   {"faculty_id": veri["faculty"].id}):
        o = _kiyas(db_session, **kapsam)
        assert "kurum medyanları" not in o["subtitle"]
        assert "medyan" not in o["title"].lower()


# ---------------------------------------------------------------------------
# 8. Dil ve sayısal olmayan ücretler
# ---------------------------------------------------------------------------


def test_ayni_dil_tercih_edilir_ama_dil_uydurulmaz(db_session, veri):
    o = _kiyas(db_session, department_id=veri["yazilim"].id)
    alfa = next(u for u in o["universities"]
                if u["university_name"] == "Alfa Universitesi")
    assert alfa["language_match"] == "ayni"

    b = _kiyas(db_session, department_id=veri["bilgisayar"].id)
    beta = next(u for u in b["universities"]
                if u["university_name"] == "Beta Universitesi")
    # "Computer Engineering" adında dil yazmıyor: uydurulmaz, bildirilir.
    assert beta["language_match"] == "belirtilmemis"


def test_aralik_metni_olan_ucret_sayiya_cevrilmez(db_session, veri):
    o = _kiyas(db_session, department_id=veri["yazilim"].id)
    eta = next(u for u in o["universities"]
               if u["university_name"] == "Eta Universitesi")
    assert eta["median_fee"] is None
    assert eta["measured_count"] == 0
    assert eta["text_only_count"] == 1


# ---------------------------------------------------------------------------
# 9. Uç durum: hiç eşdeğer yok
# ---------------------------------------------------------------------------


def test_hic_esdeger_yoksa_veri_yok_denir(db_session, veri):
    """Rakiplerde karşılığı olmayan bir program: sessizce genel ücrete
    düşülmez, açıkça 'veri yok' denir."""
    b_yeni = Department(name="DENİZCİLİK BÖLÜMÜ", code="TSTDEN",
                        faculty_id=veri["faculty"].id)
    db_session.add(b_yeni)
    db_session.flush()
    p_yeni = AcademicProgram(name="DENİZCİLİK PR.", code="TSTDENP",
                             department_id=b_yeni.id, degree_level="LISANS")
    db_session.add(p_yeni)
    db_session.flush()
    db_session.add(ProgramTuitionFee(
        academic_year=YIL, academic_program_id=p_yeni.id,
        department_id=b_yeni.id, faculty_id=veri["faculty"].id,
        source_faculty_name="F", source_program_name="DENİZCİLİK PR.",
        education_language="Türkçe", fee_type=FEE_HALF_SCHOLARSHIP,
        annual_fee=Decimal(111000), source_dataset=DAMGA,
        source_file="test.xlsx"))
    db_session.commit()

    o = _kiyas(db_session, department_id=b_yeni.id)
    assert o["available"] is False
    assert o["competitor_count"] == 0
    assert o["unavailable_reason"]
    # Kendi değerimiz yine gerçek program ücretidir, kurum medyanı değil.
    ev = next(u for u in o["universities"] if u["is_home_institution"])
    assert ev["median_fee"] == 111000


# ---------------------------------------------------------------------------
# 10. Uç nokta: kapsam parametreleri GERÇEKTEN taşınıyor mu?
# ---------------------------------------------------------------------------


def test_endpoint_kapsam_parametresini_kabul_eder(client, db_session, veri):
    """Hatanın bir ayağı da buydu: uç nokta kapsam parametresi ALMIYORDU."""
    kurum = client.get("/api/tuition/competitors",
                       params={"academic_year": YIL}).json()
    bolum = client.get("/api/tuition/competitors",
                       params={"academic_year": YIL,
                               "department_id": veri["yazilim"].id}).json()
    assert kurum["mode"] == "university"
    assert bolum["mode"] == "program"
    assert bolum["title"] != kurum["title"]
    assert "Gama Universitesi" not in {u["university_name"]
                                       for u in bolum["universities"]}


def test_endpoint_akademik_yili_dikkate_alir(client, db_session, veri):
    o = client.get("/api/tuition/competitors",
                   params={"academic_year": ONCEKI,
                           "department_id": veri["yazilim"].id}).json()
    assert o["academic_year"] == ONCEKI
    ev = next(u for u in o["universities"] if u["is_home_institution"])
    assert ev["median_fee"] == 300000
