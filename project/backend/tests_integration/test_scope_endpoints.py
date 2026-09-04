"""Kapsam kurallarının HTTP KATMANINDA da geçerli olduğunu doğrular.

NEDEN AYRI BİR DOSYA
--------------------
Asıl hata servis katmanında değil, SORGU PARAMETRESİ katmanındaydı:
arayüz `?faculty=MUHMIM&program=YAZMUH` gönderiyordu, uçlar
`faculty_id / academic_program_id` bekliyordu ve FastAPI tanımadığı
parametreyi SESSİZCE ATIYORDU. Servis testleri bunu yakalayamaz — çünkü
servise doğrudan kapsam nesnesi verilir.

Bu dosya gerçek HTTP isteği atar ve şunu kanıtlar:
  * doğru parametre adları kabul ediliyor,
  * kapsam gerçekten daraltıyor,
  * yanlış/tutarsız kapsam sessizce yok sayılmıyor (400/422).

Ortak demo veritabanı kullanılır (tests_integration/conftest.py), yani
uçtan uca gerçek uygulama yapılandırmasıyla.
"""

from typing import Dict, List

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AcademicProgram, Department, Faculty
from app.services.unit_types import ACADEMIC_UNIT_TYPES


# --------------------------------------------------------------------------
# Yardımcılar
# --------------------------------------------------------------------------


@pytest.fixture()
def hiyerarsi(db_session: Session) -> Dict:
    """En çok programı olan fakülteyi ve içindeki bir programı seçer.

    Kod sabitlemek yerine veriden seçiyoruz: demo veri seti değişse bile
    test anlamını korur ve "kardeş var mı?" koşulu garanti altında olur.
    """
    fakulteler = db_session.execute(
        select(Faculty).where(Faculty.unit_type.in_(ACADEMIC_UNIT_TYPES))
    ).scalars().all()

    en_iyi = None
    for f in fakulteler:
        bolumler = db_session.execute(
            select(Department).where(Department.faculty_id == f.id)
        ).scalars().all()
        programlar = db_session.execute(
            select(AcademicProgram).where(
                AcademicProgram.department_id.in_([b.id for b in bolumler] or [-1])
            )
        ).scalars().all()
        if len(programlar) >= 2 and (en_iyi is None or len(programlar) > len(en_iyi["programlar"])):
            en_iyi = {"fakulte": f, "bolumler": bolumler, "programlar": programlar}

    if en_iyi is None:
        pytest.skip("Testin gerektirdiği çok programlı fakülte demo veride yok.")

    program = en_iyi["programlar"][0]
    bolum = db_session.get(Department, program.department_id)
    return {
        "faculty_id": en_iyi["fakulte"].id,
        "department_id": bolum.id,
        "program_id": program.id,
        "program_code": program.code,
        "faculty_program_codes": {p.code for p in en_iyi["programlar"]},
        "tum_program_sayisi": len(
            db_session.execute(select(AcademicProgram)).scalars().all()
        ),
    }


def _kodlar(satirlar: List[dict], anahtar: str = "program_code") -> set:
    return {r[anahtar] for r in satirlar}


# ==========================================================================
# 1. Rektörlük / idari birim ayrımı — HTTP
# ==========================================================================


def test_fakulte_ucu_birim_turunu_yayinlar(client: TestClient) -> None:
    """Arayüz türü tahmin etmesin diye sunucu açıkça söyler."""
    cevap = client.get("/api/faculties")
    assert cevap.status_code == 200
    satirlar = cevap.json()
    assert satirlar, "demo veride fakülte olmalı"
    for satir in satirlar:
        assert satir["unit_type"] in {
            "FACULTY", "VOCATIONAL_SCHOOL", "INSTITUTE", "ADMINISTRATIVE"
        }
        assert "unit_type_label" in satir
        assert "is_academic" in satir


def test_academic_only_filtresi_idari_birimleri_disarida_birakir(
    client: TestClient, db_session: Session
) -> None:
    hepsi = client.get("/api/faculties", params={"limit": 500}).json()
    akademik = client.get(
        "/api/faculties", params={"limit": 500, "academic_only": True}
    ).json()

    assert all(f["is_academic"] for f in akademik)
    idari = [f for f in hepsi if not f["is_academic"]]
    assert len(akademik) == len(hepsi) - len(idari)


def test_gecersiz_birim_turu_sessizce_yok_sayilmaz(client: TestClient) -> None:
    cevap = client.get("/api/faculties", params={"unit_type": "REKTORLUK"})
    assert cevap.status_code == 422


# ==========================================================================
# 2. Kapsam parametreleri GERÇEKTEN uygulanıyor
# ==========================================================================


def test_program_kapsami_tek_satir_dondurur(client: TestClient, hiyerarsi) -> None:
    """ASIL HATA BUYDU: program seçiliyken kardeşler de geliyordu."""
    cevap = client.get(
        "/api/student-analytics/by-program",
        params={"academic_program_id": hiyerarsi["program_id"]},
    )
    assert cevap.status_code == 200
    assert _kodlar(cevap.json()) == {hiyerarsi["program_code"]}


def test_fakulte_kapsami_yalnizca_kendi_programlarini_dondurur(
    client: TestClient, hiyerarsi
) -> None:
    cevap = client.get(
        "/api/student-analytics/by-program",
        params={"faculty_id": hiyerarsi["faculty_id"]},
    )
    assert cevap.status_code == 200
    kodlar = _kodlar(cevap.json())
    assert kodlar == hiyerarsi["faculty_program_codes"]
    assert len(kodlar) < hiyerarsi["tum_program_sayisi"], "kapsam daraltmadı"


def test_universite_kapsami_tum_programlari_dondurur(
    client: TestClient, hiyerarsi
) -> None:
    """Daraltma çalışıyor diye genişlik bozulmamalı."""
    cevap = client.get("/api/student-analytics/by-program")
    assert cevap.status_code == 200
    assert len(cevap.json()) == hiyerarsi["tum_program_sayisi"]


def test_bolum_kirilimi_program_kapsaminda_tek_bolum(
    client: TestClient, hiyerarsi
) -> None:
    cevap = client.get(
        "/api/student-analytics/by-department",
        params={"academic_program_id": hiyerarsi["program_id"]},
    )
    assert cevap.status_code == 200
    assert len(cevap.json()) == 1


def test_ogrenci_ozeti_kapsamla_daralir(client: TestClient, hiyerarsi) -> None:
    genel = client.get("/api/student-analytics/overview").json()
    dar = client.get(
        "/api/student-analytics/overview",
        params={"academic_program_id": hiyerarsi["program_id"]},
    ).json()

    assert dar["total_students"] <= genel["total_students"]
    assert dar["applied_filters"]["academic_program_id"] == hiyerarsi["program_id"]


def test_tutarsiz_kapsam_400_doner(client: TestClient, db_session: Session) -> None:
    """Başka fakültenin programı istenirse istek REDDEDİLİR.

    Sessizce "en yakın" kapsama düşmek, yanlış veriyi doğru başlıkla
    göstermek olurdu.
    """
    program = db_session.execute(select(AcademicProgram)).scalars().first()
    bolum = db_session.get(Department, program.department_id)
    baska_fakulte = db_session.execute(
        select(Faculty).where(Faculty.id != bolum.faculty_id)
    ).scalars().first()
    if baska_fakulte is None:
        pytest.skip("Tek fakülte var; tutarsızlık kurulamıyor.")

    cevap = client.get(
        "/api/student-analytics/by-program",
        params={
            "faculty_id": baska_fakulte.id,
            "academic_program_id": program.id,
        },
    )
    assert cevap.status_code == 400
    assert "Tutarsız kapsam" in cevap.json()["detail"]


# ==========================================================================
# 3. Kapsam parametreleri BÜTÜN modüllerde tanımlı
# ==========================================================================

#: Kapsam kabul etmesi ZORUNLU uçlar. Yeni bir analiz ucu eklendiğinde
#: buraya da eklenmeli; aksi hâlde sessizce kapsamsız kalır.
KAPSAM_BEKLENEN_UCLAR = [
    "/api/student-analytics/overview",
    "/api/student-analytics/by-program",
    "/api/student-analytics/by-department",
    "/api/student-analytics/by-faculty",
    "/api/academic-success/overview",
    "/api/academic-success/by-faculty",
    "/api/academic-success/by-department",
    "/api/academic-success/by-program",
    "/api/academic-success/rankings",
    "/api/academic-success/correlations",
    "/api/academic-staff/overview",
    "/api/academic-staff/ranking",
    "/api/academic-staff",
    "/api/education-analytics/overview",
    "/api/education-analytics/programs",
    "/api/education-analytics/admission-scores",
    "/api/education-analytics/demand-trends",
    "/api/education-analytics/performance-trends",
    "/api/early-warning/alerts",
    "/api/early-warning/summary",
    "/api/program-sustainability/scores",
    "/api/program-sustainability/categories",
    "/api/physical-resources/capacity/overview",
    "/api/physical-resources/capacity/by-type",
    "/api/physical-resources/capacity/by-department",
    "/api/physical-resources/capacity/per-person",
    "/api/physical-resources/capacity/forecast",
    "/api/physical-resources/capacity/underutilized",
    "/api/physical-resources/capacity/overcrowded",
    "/api/kpi",
    "/api/kpi/scorecard",
    "/api/kpi/faculty-comparison",
    "/api/kpi/attention",
    "/api/kpi/missing-data",
    "/api/engagement/industry-collaboration",
    "/api/engagement/regional-contribution",
]


@pytest.mark.parametrize("yol", KAPSAM_BEKLENEN_UCLAR)
def test_ucun_kapsam_parametreleri_tanimli(client: TestClient, yol: str) -> None:
    """OpenAPI şemasında kapsam parametreleri GÖRÜNMELİ.

    Bu testin varlık sebebi: parametre adı yanlış yazılırsa FastAPI onu
    sessizce atar ve filtre hiç uygulanmaz. Şemada varlığını kontrol
    etmek, o sessiz hatayı yapısal olarak imkânsız kılar.
    """
    şema = client.get("/openapi.json").json()
    parametreler = {
        p["name"] for p in şema["paths"][yol]["get"].get("parameters", [])
    }
    assert "faculty_id" in parametreler, f"{yol}: faculty_id yok"
    assert "department_id" in parametreler, f"{yol}: department_id yok"
    assert "academic_program_id" in parametreler, f"{yol}: academic_program_id yok"


def test_finans_uclari_kapsam_kabul_eder(client: TestClient) -> None:
    """Finans yolları parametreli olduğu için ayrı kontrol ediliyor."""
    şema = client.get("/openapi.json").json()
    for yol in (
        "/api/finance/{academic_year}/summary",
        "/api/finance/{academic_year}/departments",
    ):
        parametreler = {
            p["name"] for p in şema["paths"][yol]["get"].get("parameters", [])
        }
        assert {"faculty_id", "department_id", "academic_program_id"} <= parametreler


def test_asistan_kapsami_yapisal_olarak_tasiniyor(client: TestClient) -> None:
    """Sohbet isteği birim adını METİNDE değil, `scope` alanında taşır."""
    şema = client.get("/openapi.json").json()
    istek = şema["components"]["schemas"]["ChatRequest"]
    assert "scope" in istek["properties"]

    secim = şema["components"]["schemas"]["ScopeSelection"]["properties"]
    assert {"faculty_id", "department_id", "academic_program_id"} <= set(secim)
