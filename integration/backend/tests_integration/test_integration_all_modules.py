"""Entegrasyon testleri — birleştirilmiş ürünün uçtan uca doğrulaması.

Bu dosya tek tek modüllerin iç mantığını test etmez (onlar kendi test
dosyalarında). Buradaki testler, birleştirme sırasında bozulabilecek şeyleri
kontrol eder:

* Tüm modüllerin router'ları aynı uygulamada çakışmadan yaşıyor mu?
* Ortak veri seti bütün modüllerde tutarlı sonuç üretiyor mu?
* Modüller arası bağlantılar (bölüm -> bütçe, fakülte -> KPI) çalışıyor mu?
* Yapılan söz tutuluyor mu: LLM bağlı değil, parola sızmıyor, eksik veri
  sıfır olarak gösterilmiyor?
"""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AcademicStaff,
    Department,
    Faculty,
    FinancialPeriod,
    PhysicalFacility,
    StrategicKpi,
    SystemUser,
)

CURRENT_YEAR = "2025-2026"


# ---------------------------------------------------------------------------
# 1) Router birleştirmesi
# ---------------------------------------------------------------------------


def test_all_module_prefixes_registered(client: TestClient) -> None:
    """13 modülün de endpoint'leri aynı uygulamada kayıtlı olmalı."""
    paths = set(client.get("/openapi.json").json()["paths"])

    expected_prefixes = {
        "Modül 1 - Üniversite yapısı": "/api/faculties",
        "Modül 2 - Öğrenci analitiği": "/api/student-analytics",
        "Modül 3 - Öğrenci analitiği (Begüm)": "/api/education-analytics",
        "Modül 4 - Akademik personel": "/api/academic-staff",
        "Modül 5 - Fiziksel kaynaklar": "/api/physical-resources",
        "Modül 6 - Finansal analiz": "/api/finance",
        "Modül 7 - Sürdürülebilirlik": "/api/program-sustainability",
        "Modül 8 - Performans yönetimi": "/api/kpi",
        "Modül 9 - Senaryo analizi": "/api/scenarios",
        "Modül 10 - Değerlendirme": "/api/ranking-evaluations",
        "Modül 11 - Erken uyarı": "/api/early-warning",
        "Modül 13 - Veri entegrasyonu": "/api/data-integration",
        "Modül 14 - Kullanıcı yönetimi": "/api/auth",
    }

    missing = {
        label: prefix
        for label, prefix in expected_prefixes.items()
        if not any(p.startswith(prefix) for p in paths)
    }
    assert not missing, f"Bu modüllerin endpoint'leri kayıtlı değil: {missing}"


def test_no_duplicate_path_method_pairs(client: TestClient) -> None:
    """Aynı (yol, metot) ikilisi iki kez kayıtlı olmamalı.

    İki router aynı yolu paylaşırsa ikincisi sessizce gölgede kalır ve
    hangisinin çalıştığı belirsizleşir. Modül 2 ile Modül 3'ün prefix çakışması
    entegrasyonda tam olarak bu yüzden ayrıştırıldı.
    """
    from main import app

    seen: set = set()
    duplicates: list = []
    for route in app.routes:
        for method in getattr(route, "methods", None) or []:
            key = (getattr(route, "path", None), method)
            if key in seen:
                duplicates.append(key)
            seen.add(key)
    assert not duplicates, f"Çakışan yol/metot ikilileri: {duplicates}"


def test_module2_and_module3_do_not_collide(client: TestClient) -> None:
    """İki öğrenci analitiği modülü ayrı prefix'lerde ve ikisi de yanıt vermeli."""
    m2 = client.get("/api/student-analytics/overview")
    m3 = client.get("/api/education-analytics/overview", params={"academic_year": CURRENT_YEAR})

    assert m2.status_code == 200
    # Modül 3 için veri o yılda yoksa 404 kabul edilebilir; ama 200 ise
    # Modül 2'den farklı bir şema döndürmeli (aynı olsaydı biri diğerini
    # gölgeliyor demektir).
    if m3.status_code == 200:
        assert set(m2.json()) != set(m3.json()), (
            "Modül 2 ve Modül 3 aynı şemayı döndürüyor; router'lardan biri "
            "diğerini gölgeliyor olabilir."
        )


# ---------------------------------------------------------------------------
# 2) Model birleştirmesi
# ---------------------------------------------------------------------------


def test_begum_extra_columns_exist_on_canonical_models() -> None:
    """Begüm'ün servislerinin ihtiyaç duyduğu kolonlar kanonik modelde olmalı."""
    from app.models import ProgramEnrollmentSnapshot, Student

    assert hasattr(Student, "status_change_year")
    assert hasattr(Student, "is_employed")
    assert hasattr(
        ProgramEnrollmentSnapshot, "full_scholarship_minimum_admission_score"
    )


def test_no_duplicate_tables_for_same_concept() -> None:
    """Aynı kavram için iki tablo bırakılmamalı."""
    from app.database import Base

    tables = set(Base.metadata.tables)

    # Birleştirme sırasında ayrı tablo olarak kalması muhtemel adlar.
    forbidden = {
        "staff",  # Modül 4 -> academic_staff altında birleşti
        "classrooms",  # Modül 5 -> physical_facilities altında birleşti
        "facilities",
        "users",  # Modül 14 -> system_users
        "students_m3",  # Modül 3 kendi öğrenci tablosunu açmamalı
    }
    collisions = tables & forbidden
    assert not collisions, f"Çift tablo tespit edildi: {collisions}"


def test_all_departments_belong_to_a_faculty(db_session: Session) -> None:
    """Bölüm -> fakülte bağı kopmuş olmamalı."""
    faculty_ids = {f.id for f in db_session.execute(select(Faculty)).scalars()}
    orphans = [
        d.code
        for d in db_session.execute(select(Department)).scalars()
        if d.faculty_id not in faculty_ids
    ]
    assert not orphans, f"Fakültesi bulunmayan bölümler: {orphans}"


# ---------------------------------------------------------------------------
# 3) Modüller arası bağlantılar
# ---------------------------------------------------------------------------


def test_staff_resolves_faculty_through_department(client: TestClient) -> None:
    """Modül 4 personeli, Modül 1'deki fakülte adını çözebilmeli."""
    rows = client.get("/api/academic-staff", params={"limit": 5}).json()
    if not rows:
        pytest.skip("Akademik personel verisi yok.")
    assert all(r["faculty_name"] not in (None, "", "Bilinmiyor") for r in rows), (
        "Personel kayıtları fakülte adını çözemiyor; bölüm bağlantısı kopuk."
    )


def test_capacity_per_person_uses_real_counts(client: TestClient, db_session: Session) -> None:
    """Modül 5, öğrenci/personel sayısını sabit değil veritabanından almalı.

    Orijinal kodda TOTAL_STUDENTS = 3200 ve TOTAL_STAFF = 180 sabitleri vardı.
    """
    response = client.get("/api/physical-resources/capacity/per-person")
    if response.status_code == 404:
        pytest.skip("Fiziksel mekân verisi yok.")

    data = response.json()
    real_staff = db_session.execute(
        select(AcademicStaff).where(AcademicStaff.is_active.is_(True))
    ).scalars().all()

    assert data["active_staff_count"] == len(real_staff), (
        "Personel sayısı veritabanıyla uyuşmuyor; sabit değer kullanılıyor olabilir."
    )
    assert data["active_student_count"] != 3200 or len(real_staff) == 3200


def test_department_budget_links_to_module1_department(client: TestClient) -> None:
    """Modül 6 bütçeleri Modül 1'deki bölümlere bağlı olmalı."""
    response = client.get(f"/api/finance/{CURRENT_YEAR}/departments")
    if response.status_code == 404:
        pytest.skip("Mali dönem verisi yok.")
    rows = response.json()
    if not rows:
        pytest.skip("Bölüm bütçesi girilmemiş.")

    department_ids = {d["id"] for d in client.get("/api/departments", params={"limit": 200}).json()}
    assert all(r["department_id"] in department_ids for r in rows), (
        "Bütçe kayıtları var olmayan bölümlere bağlı."
    )
    assert all(r["department_name"] != "Bilinmiyor" for r in rows)


def test_kpi_faculty_values_link_to_module1_faculty(client: TestClient) -> None:
    """Modül 8 fakülte kırılımı Modül 1'deki fakültelere bağlı olmalı."""
    kpis = client.get("/api/kpi", params={"academic_year": CURRENT_YEAR}).json()
    if not kpis:
        pytest.skip("KPI verisi yok.")

    faculty_ids = {f["id"] for f in client.get("/api/faculties", params={"limit": 200}).json()}
    for kpi in kpis:
        for value in kpi["faculty_values"]:
            assert value["faculty_id"] in faculty_ids
            assert value["faculty_name"], "Fakülte adı çözülemedi."


# ---------------------------------------------------------------------------
# 4) Veri dürüstlüğü sözleri
# ---------------------------------------------------------------------------


def test_assistant_has_no_llm_connected(client: TestClient) -> None:
    """Asistan hiçbir dil modeline bağlı olmamalı ve bunu açıkça söylemeli."""
    status = client.get("/api/assistant/status").json()

    assert status["enabled"] is False
    assert status["provider"] in (None, "")
    assert status["model"] in (None, "")
    assert status["api_key_configured"] is False
    assert "dil modeli" in status["message"].lower()


def test_assistant_never_generates_an_answer(client: TestClient) -> None:
    """Cevap üreten bir endpoint bulunmamalı; bağlam cevabı uyarı içermeli."""
    paths = set(client.get("/openapi.json").json()["paths"])
    answer_endpoints = [
        p for p in paths if p.startswith("/api/assistant") and
        any(word in p for word in ("ask", "answer", "chat", "complete", "generate"))
    ]
    assert not answer_endpoints, (
        f"Dil modeli bağlı olmadan cevap üreten endpoint var: {answer_endpoints}"
    )

    context = client.post(
        "/api/assistant/prepare-context",
        json={"question": "Hangi programların doluluk oranı düşüyor?"},
    ).json()
    assert "DEĞİLDİR" in context["notice"], "Cevap olmadığı uyarısı kaldırılmış."
    assert context["context_items"], "Bağlam boş; veri erişimi çalışmıyor."


def test_no_api_key_in_source_code() -> None:
    """Kaynak kodda gerçek API anahtarı bulunmamalı."""
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parent.parent
    # Yaygın anahtar biçimleri.
    patterns = [
        re.compile(r"sk-[A-Za-z0-9]{20,}"),
        re.compile(r"AIza[A-Za-z0-9_\-]{30,}"),
        re.compile(r"(?i)api[_-]?key\s*=\s*['\"][A-Za-z0-9_\-]{16,}['\"]"),
    ]
    findings = []
    for path in root.rglob("*.py"):
        if ".venv" in str(path):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in patterns:
            if pattern.search(text):
                findings.append(str(path.relative_to(root)))
                break
    assert not findings, f"Kaynak kodda API anahtarı benzeri metin: {findings}"


def test_passwords_are_hashed_and_never_returned(client: TestClient, db_session: Session) -> None:
    """Parolalar özetlenmiş saklanmalı ve API cevaplarında yer almamalı."""
    users = db_session.execute(select(SystemUser)).scalars().all()
    if not users:
        pytest.skip("Kullanıcı verisi yok.")

    for user in users:
        assert user.password_hash != "demo1234"
        assert len(user.password_hash) == 64, "PBKDF2-SHA256 özeti 64 karakter olmalı."
        assert len(user.password_salt) == 32

    body = client.get("/api/auth/users").text
    for forbidden in ("password", "hash", "salt", "demo1234"):
        assert forbidden not in body.lower(), (
            f"Kullanıcı cevabında '{forbidden}' geçiyor; parola bilgisi sızıyor."
        )


def test_missing_data_is_not_reported_as_zero(client: TestClient) -> None:
    """Ölçüm girilmemiş alanlar sıfır değil, boş (null) dönmeli."""
    # Bütçesi olmayan bir bölüm için gerçekleşme oranı hesaplanmamalı.
    response = client.get(f"/api/finance/{CURRENT_YEAR}/departments")
    if response.status_code == 200:
        for row in response.json():
            if Decimal(row["allocated_budget"]) == 0:
                assert row["budget_realization_percent"] is None, (
                    "Bütçesi tanımsız bölüm için oran uydurulmuş."
                )
                assert row["budget_status"] == "bütçe tanımsız"

    # Metrekare ölçümü olmayan grup için 0 değil null dönmeli.
    alloc = client.get("/api/physical-resources/capacity/by-department")
    if alloc.status_code == 200:
        for row in alloc.json():
            area = row["total_area_square_meters"]
            assert area is None or area > 0, "Ölçüm yokken 0 m² yazılmış."


def test_module10_does_not_claim_real_rankings(client: TestClient) -> None:
    """Modül 10 gerçek THE/QS/YÖK sıralaması ürettiğini iddia etmemeli."""
    spec = client.get("/openapi.json").json()
    ranking_paths = {
        p: v for p, v in spec["paths"].items() if p.startswith("/api/ranking-evaluations")
    }
    assert ranking_paths, "Modül 10 endpoint'leri bulunamadı."

    frameworks = client.get("/api/ranking-evaluations/frameworks").json()
    for framework in frameworks:
        # Şemada "world rank" gibi bir alan olmamalı.
        assert "world_rank" not in framework
        assert "global_position" not in framework


# ---------------------------------------------------------------------------
# 5) Arayüz servisi
# ---------------------------------------------------------------------------


def test_frontend_is_served_at_root(client: TestClient) -> None:
    """Arayüz backend ile aynı sunucudan servis edilmeli."""
    response = client.get("/")
    assert response.status_code == 200
    assert "<!DOCTYPE html" in response.text
    assert "assets/api.js" in response.text


def test_frontend_assets_are_reachable(client: TestClient) -> None:
    """Arayüzün ihtiyaç duyduğu dosyaların hepsi erişilebilir olmalı."""
    for asset in (
        "/assets/api.js",
        "/assets/app.js",
        "/assets/style.css",
        "/assets/integration.css",
        "/assets/views-overview.js",
        "/assets/views-analytics.js",
        "/assets/views-planning.js",
        "/assets/views-system.js",
    ):
        assert client.get(asset).status_code == 200, f"{asset} servis edilmiyor."


def test_api_and_docs_still_work_behind_frontend_mount(client: TestClient) -> None:
    """Arayüz kök yola bağlandıktan sonra API ve dokümantasyon çalışmaya devam etmeli."""
    assert client.get("/docs").status_code == 200
    assert client.get("/health").status_code == 200
    assert client.get("/api").json()["message"].startswith("Backend")
    assert client.get("/api/faculties").status_code == 200


def test_frontend_contains_no_mock_data_markers() -> None:
    """Arayüz dosyalarında sahte veri kalıntısı olmamalı."""
    import pathlib
    import re

    frontend = pathlib.Path(__file__).resolve().parent.parent.parent / "frontend"
    if not frontend.is_dir():
        pytest.skip("Arayüz klasörü yok.")

    # "mock" kelimesi ve Halil'in orijinal sabit veri dizileri.
    forbidden = re.compile(r"\bmock\b|ASSISTANT_ANSWERS|const DRILL\s*=", re.IGNORECASE)
    findings = [
        str(path.name)
        for path in frontend.rglob("*.js")
        if forbidden.search(path.read_text(encoding="utf-8", errors="ignore"))
    ]
    assert not findings, f"Arayüzde sahte veri kalıntısı: {findings}"
