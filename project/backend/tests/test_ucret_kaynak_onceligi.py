"""ÜCRET KAYNAK ÖNCELİĞİ VE TUTARLILIK — hedefli regresyon.

Düzeltilen sorun: ABÜ'nün ücreti ekranın iki yerinde iki AYRI kod yolunda
hesaplanıyordu (ana ücret paneli ve rakip kıyasındaki ★ çubuğu). Bugünkü
veride aynı sonucu veriyorlardı, ama bunu zorlayan hiçbir şey yoktu.

Bu testler üç şeyi kanıtlar:

  1. TEK YETKİLİ KAYNAK  ABÜ değeri daima `program_tuition_fees`'ten
     gelir; rakip dosyasına bir "Ankara Bilim" satırı düşse bile o satır
     akran havuzuna girmez ve ★ çubuğunu ETKİLEMEZ.
  2. TUTARLILIK          aynı kapsam + yıl + ücret türü için ana panel,
     kıyas çubuğu, detay satırları ve API yanıtı AYNI sayıyı verir.
  3. TOPLAMA KURALI      dil kopyaları medyanı bozmaz; ücret türü, yıl ve
     program yalıtımı korunur; dar kapsamda kurum medyanına düşülmez.

Sayılar testin kendi kurduğu veriden gelir; hiçbir yerde sabit
464.000 gibi bir değer BEKLENMEZ — beklenen değer daima yetkili
kaynaktan türetilir.
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
from app.services import tuition_provenance as prov
from app.services import tuition_service as service
from app.services.scope import resolve

YIL = "2025-2026"
ONCEKI = "2024-2025"
DAMGA = "test_ucret_kaynak_onceligi"

#: Yetkili ABÜ ücretleri (testin kurduğu gerçek). Beklentiler bu
#: değerlerden TÜRETİLİR, koda sabit yazılmaz.
PSIKOLOJI_HALF = 464000
PSIKOLOJI_FULL = 928000
#: Rakip dosyasına DÜŞMÜŞ sahte bir ABÜ satırı — asla kullanılmamalı.
SAHTE_ABU_HALF = 111111


@pytest.fixture()
def veri(db_session):
    fak = Faculty(name="İNSAN VE TOPLUM BİLİMLERİ FAKÜLTESİ (test)",
                  code="TSTITB")
    db_session.add(fak)
    db_session.flush()

    b_psi = Department(name="PSİKOLOJİ BÖLÜMÜ", code="TSTPSI", faculty_id=fak.id)
    b_isl = Department(name="İŞLETME BÖLÜMÜ", code="TSTISL", faculty_id=fak.id)
    db_session.add_all([b_psi, b_isl])
    db_session.flush()

    p_psi = AcademicProgram(name="PSİKOLOJİ PR.", code="TSTPSIP",
                            department_id=b_psi.id, degree_level="LISANS")
    p_isl = AcademicProgram(name="İŞLETME PR.", code="TSTISLP",
                            department_id=b_isl.id, degree_level="LISANS")
    db_session.add_all([p_psi, p_isl])
    db_session.flush()

    def bizim(program, dept, ad, tur, ucret, dil, yil=YIL):
        return ProgramTuitionFee(
            academic_year=yil, academic_program_id=program.id,
            department_id=dept.id, faculty_id=fak.id,
            source_faculty_name=fak.name, source_program_name=ad,
            education_language=dil, fee_type=tur, annual_fee=Decimal(ucret),
            source_dataset=DAMGA, source_file="abu_ucretler.xlsx")

    db_session.add_all([
        # Psikoloji: AYNI ücret, iki dil → dil kopyası (tek satır sayılmalı)
        bizim(p_psi, b_psi, "PSİKOLOJİ PR.", FEE_HALF_SCHOLARSHIP,
              PSIKOLOJI_HALF, "Türkçe"),
        bizim(p_psi, b_psi, "PSİKOLOJİ PR.", FEE_HALF_SCHOLARSHIP,
              PSIKOLOJI_HALF, "İngilizce"),
        bizim(p_psi, b_psi, "PSİKOLOJİ PR.", FEE_FULL, PSIKOLOJI_FULL, "Türkçe"),
        bizim(p_psi, b_psi, "PSİKOLOJİ PR.", FEE_FULL, PSIKOLOJI_FULL, "İngilizce"),
        # Önceki yıl — yıl yalıtımı için
        bizim(p_psi, b_psi, "PSİKOLOJİ PR.", FEE_HALF_SCHOLARSHIP,
              300000, "Türkçe", yil=ONCEKI),
        # Başka bir program — program yalıtımı ve kurum medyanı için
        bizim(p_isl, b_isl, "İŞLETME PR.", FEE_HALF_SCHOLARSHIP, 200000, "İngilizce"),
    ])

    def rakip(kurum, ad, tur, ucret, yil=YIL):
        return CompetitorTuitionFee(
            university_name=kurum, academic_year=yil, level="LISANS",
            unit_name="Fen Edebiyat", program_name=ad, fee_type=tur,
            annual_fee=Decimal(ucret), fee_text=str(ucret),
            source_dataset=DAMGA, source_file="rakipler.xlsx")

    db_session.add_all([
        rakip("Alfa Universitesi", "Psikoloji", FEE_HALF_SCHOLARSHIP, 650000),
        rakip("Beta Universitesi", "Psikoloji (İngilizce)",
              FEE_HALF_SCHOLARSHIP, 460000),
        # Beta aynı programı TÜRKÇE de yayımlıyor, ÜCRET AYNI → dil kopyası
        rakip("Beta Universitesi", "Psikoloji (Türkçe)",
              FEE_HALF_SCHOLARSHIP, 460000),
        # --- RAKİP DOSYASINA DÜŞMÜŞ ABÜ SATIRLARI ---
        #     Yetkili kaynağı EZMEMELİ, ikinci bir çubuk ÜRETMEMELİ.
        rakip("Ankara Bilim Universitesi", "Psikoloji",
              FEE_HALF_SCHOLARSHIP, SAHTE_ABU_HALF),
        rakip("ANKARA BİLİM ÜNİVERSİTESİ", "Psikoloji (İngilizce)",
              FEE_HALF_SCHOLARSHIP, SAHTE_ABU_HALF),
    ])
    db_session.commit()
    yield {"faculty": fak, "psikoloji": b_psi, "isletme": b_isl}

    db_session.query(ProgramTuitionFee).filter_by(source_dataset=DAMGA).delete()
    db_session.query(CompetitorTuitionFee).filter_by(source_dataset=DAMGA).delete()
    bolumler = [b.id for b in
                db_session.query(Department).filter_by(faculty_id=fak.id)]
    if bolumler:
        db_session.query(AcademicProgram).filter(
            AcademicProgram.department_id.in_(bolumler)).delete(
                synchronize_session=False)
    db_session.query(Department).filter_by(faculty_id=fak.id).delete()
    db_session.query(Faculty).filter_by(id=fak.id).delete()
    db_session.commit()


def _ana_panel(db, sc, yil=YIL, tur=FEE_HALF_SCHOLARSHIP):
    pf = service.program_fees(db, sc, yil)
    return next(x for x in pf["by_fee_type"] if x["fee_type"] == tur)


def _kiyas(db, sc, yil=YIL, tur=FEE_HALF_SCHOLARSHIP):
    return service.scoped_competitor_comparison(db, sc, yil, tur)


def _ev(o):
    return next((u for u in o["universities"] if u["is_home_institution"]), None)


# ---------------------------------------------------------------------------
# 1. Kaynak önceliği
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ad", [
    "Ankara Bilim Universitesi", "ANKARA BİLİM ÜNİVERSİTESİ",
    "Ankara Bilim Üniversitesi", "ABÜ", "ABU",
])
def test_kendi_kurumumuz_taninir(ad):
    assert prov.is_home_university(ad) is True


@pytest.mark.parametrize("ad", [
    "Ankara Medipol Universitesi", "Ankara Universitesi", "Atilim Universitesi",
    "Bilkent Universitesi", "", None,
])
def test_baska_kurum_ev_sayilmaz(ad):
    assert prov.is_home_university(ad) is False


def test_yetkili_abu_degeri_rakip_satirini_ezer(db_session, veri):
    o = _kiyas(db_session, resolve(db_session, department_id=veri["psikoloji"].id))
    ev = _ev(o)
    assert ev["median_fee"] == PSIKOLOJI_HALF
    assert ev["median_fee"] != SAHTE_ABU_HALF
    assert ev["source"] == prov.SOURCE_HOME
    assert ev["authoritative"] is True


def test_rakip_dosyasindaki_abu_satirlari_akran_olmaz(db_session, veri):
    o = _kiyas(db_session, resolve(db_session, department_id=veri["psikoloji"].id))
    akranlar = [u for u in o["universities"] if not u["is_home_institution"]]
    assert all(not prov.is_home_university(u["university_name"])
               for u in akranlar)
    # Sahte değer hiçbir çubukta görünmemeli.
    assert all(u["median_fee"] != SAHTE_ABU_HALF for u in o["universities"])


def test_elenen_abu_satirlari_sessizce_yutulmaz(db_session, veri):
    o = _kiyas(db_session, resolve(db_session, department_id=veri["psikoloji"].id))
    elenen = o["excluded_home_rows_from_peer_source"]
    assert len(elenen) == 2
    assert all(e["source"] == prov.SOURCE_COMPETITOR for e in elenen)
    assert all(e["reason"] for e in elenen)


def test_tek_bir_abu_cubugu_vardir(db_session, veri):
    o = _kiyas(db_session, resolve(db_session, department_id=veri["psikoloji"].id))
    ev_sayisi = sum(1 for u in o["universities"] if u["is_home_institution"])
    assert ev_sayisi == 1
    adlar = [u["university_name"] for u in o["universities"]]
    assert adlar.count(HOME_UNIVERSITY) == 1


def test_universite_kapsaminda_da_abu_satirlari_elenir(db_session, veri):
    o = service.scoped_competitor_comparison(
        db_session, resolve(db_session), YIL, FEE_HALF_SCHOLARSHIP)
    assert o["mode"] == "university"
    assert len(o["excluded_home_rows_from_peer_source"]) == 2
    assert sum(1 for u in o["universities"] if u["is_home_institution"]) == 1
    assert all(u["median_fee"] != SAHTE_ABU_HALF for u in o["universities"])


# ---------------------------------------------------------------------------
# 2. Ana panel ile kıyas çubuğu AYNI
# ---------------------------------------------------------------------------


def test_psikoloji_ana_panel_ve_kiyas_esittir(db_session, veri):
    sc = resolve(db_session, department_id=veri["psikoloji"].id)
    ana = _ana_panel(db_session, sc)
    ev = _ev(_kiyas(db_session, sc))
    assert ana["median_fee"] == ev["median_fee"] == PSIKOLOJI_HALF


def test_her_kapsamda_ana_panel_ve_kiyas_esittir(db_session, veri):
    """Tutarlılık tek bir bölümde değil, HER kapsamda geçerli olmalı."""
    kapsamlar = [
        resolve(db_session),
        resolve(db_session, faculty_id=veri["faculty"].id),
        resolve(db_session, department_id=veri["psikoloji"].id),
        resolve(db_session, department_id=veri["isletme"].id),
    ]
    for sc in kapsamlar:
        for tur in (FEE_HALF_SCHOLARSHIP, FEE_FULL):
            ana = _ana_panel(db_session, sc, tur=tur)
            ev = _ev(_kiyas(db_session, sc, tur=tur))
            if ev is None:
                assert ana["median_fee"] is None, sc.label
                continue
            assert ana["median_fee"] == ev["median_fee"], (sc.label, tur)


def test_yetkili_hesap_dogrudan_cagrilinca_da_ayni(db_session, veri):
    sc = resolve(db_session, department_id=veri["psikoloji"].id)
    y = service.home_scoped_fee(db_session, sc, YIL, FEE_HALF_SCHOLARSHIP)
    assert y["median_fee"] == _ana_panel(db_session, sc)["median_fee"]
    assert y["median_fee"] == _ev(_kiyas(db_session, sc))["median_fee"]
    assert y["source"] == prov.SOURCE_HOME


def test_detay_satirlari_cubukla_ayni_degeri_anlatir(db_session, veri):
    sc = resolve(db_session, department_id=veri["psikoloji"].id)
    ev = _ev(_kiyas(db_session, sc))
    ucretler = [r["annual_fee"] for r in ev["matched_programs"]
                if r["annual_fee"] is not None]
    assert prov.median(ucretler) == ev["median_fee"]


def test_api_yaniti_ile_ana_panel_esittir(client, db_session, veri):
    p = {"academic_year": YIL, "department_id": veri["psikoloji"].id}
    ucret = client.get("/api/tuition/program-fees", params=p).json()
    kiyas = client.get("/api/tuition/competitors",
                       params={**p, "fee_type": FEE_HALF_SCHOLARSHIP}).json()
    ana = next(x for x in ucret["by_fee_type"]
               if x["fee_type"] == FEE_HALF_SCHOLARSHIP)
    ev = next(u for u in kiyas["universities"] if u["is_home_institution"])
    assert ana["median_fee"] == ev["median_fee"]
    assert ev["source"] == prov.SOURCE_HOME


# ---------------------------------------------------------------------------
# 3. Toplama kuralı: dil kopyaları
# ---------------------------------------------------------------------------


def test_ayni_ucretli_dil_kopyasi_tek_kez_sayilir(db_session, veri):
    sc = resolve(db_session, department_id=veri["psikoloji"].id)
    y = service.home_scoped_fee(db_session, sc, YIL, FEE_HALF_SCHOLARSHIP)
    # İki satır girdi, bir satır medyana girdi.
    assert y["measured_count"] == 1
    assert len(y["collapsed_duplicate_rows"]) == 1
    assert y["median_fee"] == PSIKOLOJI_HALF
    kalan = y["source_rows"][0]
    assert sorted(kalan["languages"]) == ["Türkçe", "İngilizce"]


def test_akran_tarafinda_da_dil_kopyasi_birlesir(db_session, veri):
    o = _kiyas(db_session, resolve(db_session, department_id=veri["psikoloji"].id))
    beta = next(u for u in o["universities"]
                if u["university_name"] == "Beta Universitesi")
    assert beta["measured_count"] == 1
    assert len(beta["collapsed_duplicate_rows"]) == 1
    assert beta["median_fee"] == 460000


def test_farkli_ucretli_dil_satirlari_birlestirilmez():
    satirlar = [
        {"identity": 1, "annual_fee": 100.0, "education_language": "Türkçe"},
        {"identity": 1, "annual_fee": 200.0, "education_language": "İngilizce"},
    ]
    kalan, birlesen = prov.collapse_language_duplicates(satirlar)
    assert len(kalan) == 2 and birlesen == []


def test_dil_kopyasi_medyani_kaydirmaz():
    """Çift sayılan bir program medyanı kendine çeker; kural bunu keser."""
    ham = [
        {"identity": "A", "annual_fee": 100.0, "education_language": "Türkçe"},
        {"identity": "A", "annual_fee": 100.0, "education_language": "İngilizce"},
        {"identity": "B", "annual_fee": 300.0, "education_language": "Türkçe"},
    ]
    assert prov.median([r["annual_fee"] for r in ham]) == 100.0   # çarpık
    assert prov.aggregate(ham)["median_fee"] == 200.0             # düzeltilmiş


def test_toplama_kurali_yanitla_birlikte_bildirilir(db_session, veri):
    o = _kiyas(db_session, resolve(db_session, department_id=veri["psikoloji"].id))
    assert o["aggregation"] == prov.AGGREGATION_MEDIAN
    assert o["home_source"] == prov.SOURCE_HOME
    assert o["peer_source"] == prov.SOURCE_COMPETITOR
    for u in o["universities"]:
        assert u["aggregation"] == prov.AGGREGATION_MEDIAN


# ---------------------------------------------------------------------------
# 4. Yalıtım: ücret türü / yıl / program
# ---------------------------------------------------------------------------


def test_ucret_turu_yalitimi(db_session, veri):
    sc = resolve(db_session, department_id=veri["psikoloji"].id)
    yari = service.home_scoped_fee(db_session, sc, YIL, FEE_HALF_SCHOLARSHIP)
    tam = service.home_scoped_fee(db_session, sc, YIL, FEE_FULL)
    assert yari["median_fee"] == PSIKOLOJI_HALF
    assert tam["median_fee"] == PSIKOLOJI_FULL
    assert all(r["fee_type"] == FEE_HALF_SCHOLARSHIP
               for r in yari["source_rows"])


def test_akademik_yil_yalitimi(db_session, veri):
    sc = resolve(db_session, department_id=veri["psikoloji"].id)
    bu = service.home_scoped_fee(db_session, sc, YIL, FEE_HALF_SCHOLARSHIP)
    onceki = service.home_scoped_fee(db_session, sc, ONCEKI, FEE_HALF_SCHOLARSHIP)
    assert bu["median_fee"] == PSIKOLOJI_HALF
    assert onceki["median_fee"] == 300000
    assert all(r["academic_year"] == ONCEKI for r in onceki["source_rows"])


def test_program_yalitimi(db_session, veri):
    psi = service.home_scoped_fee(
        db_session, resolve(db_session, department_id=veri["psikoloji"].id),
        YIL, FEE_HALF_SCHOLARSHIP)
    isl = service.home_scoped_fee(
        db_session, resolve(db_session, department_id=veri["isletme"].id),
        YIL, FEE_HALF_SCHOLARSHIP)
    assert psi["median_fee"] == PSIKOLOJI_HALF
    assert isl["median_fee"] == 200000
    assert psi["median_fee"] != isl["median_fee"]


# ---------------------------------------------------------------------------
# 5. Sessiz geri düşme yok
# ---------------------------------------------------------------------------


def test_dar_kapsamda_kurum_medyanina_dusulmez(db_session, veri):
    """Bölüm kapsamındaki ★ değeri, üniversite geneli medyanla AYNI olamaz
    (test verisinde ikisi bilerek farklı kurulmuştur)."""
    kurum = service.home_scoped_fee(
        db_session, resolve(db_session), YIL, FEE_HALF_SCHOLARSHIP)
    psi = service.home_scoped_fee(
        db_session, resolve(db_session, department_id=veri["psikoloji"].id),
        YIL, FEE_HALF_SCHOLARSHIP)
    assert psi["median_fee"] != kurum["median_fee"]
    assert psi["scope_level"] == "department"
    assert kurum["scope_level"] == "university"


def test_veri_olmayan_yilda_baska_yila_dusulmez(db_session, veri):
    y = service.home_scoped_fee(
        db_session, resolve(db_session, department_id=veri["psikoloji"].id),
        "2019-2020", FEE_HALF_SCHOLARSHIP)
    assert y["median_fee"] is None
    assert y["measured_count"] == 0
    assert y["source_rows"] == []
