"""Hesaplama doğruluğu ve veri tutarlılığı testleri.

Bu dosya, bulunan gerçek hesaplama hatalarını KANITLAYAN ve düzeltmelerin
kalıcı olduğunu garanti eden testleri içerir. Her testin başındaki açıklama,
hangi hatanın önlendiğini anlatır.
"""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AcademicStaff,
    AcademicSuccessRecord,
    FinancialEntry,
    FinancialPeriod,
    Student,
)

CURRENT_YEAR = "2025-2026"
MILLION = Decimal("1000000")


def D(value) -> Decimal:
    """API'den gelen metin Decimal'i sayıya çevirir."""
    return Decimal(str(value))


# ===========================================================================
# 1. Senaryo motoru — düzeltilen hatalar
# ===========================================================================


def test_unknown_input_field_is_rejected(client: TestClient) -> None:
    """HATA: Yanlış yazılmış alan adı sessizce yok sayılıyordu.

    Arayüz "staff_count_change" gönderiyor, backend "academic_staff_change"
    bekliyordu. Pydantic varsayılan olarak fazladan alanları yok saydığı için
    istek 200 dönüyor ama HİÇBİR parametre uygulanmıyordu. Kullanıcı değeri
    değiştirdiğini sanıp aynı sonucu görüyordu.
    """
    for bad_field in (
        "staff_count_change",
        "student_count_change_percent",
        "new_program_student_count",
        "tamamen_uydurma_alan",
    ):
        response = client.post("/api/scenarios/preview", json={bad_field: 50})
        assert response.status_code == 422, (
            f"'{bad_field}' alanı sessizce kabul edildi. Bu, parametrenin "
            "uygulanmadan yutulması demektir."
        )


def test_salary_increase_scenario_changes_personnel_expense(client: TestClient) -> None:
    """HATA: Maaş artışı senaryosu hiç yoktu.

    Personel gideri yalnızca kişi sayısıyla değişebiliyordu; "maaşlara %2 zam
    yapılırsa ne olur" sorusu sistemde cevaplanamıyordu.
    """
    baseline = client.post("/api/scenarios/preview", json={}).json()
    raised = client.post(
        "/api/scenarios/preview", json={"academic_salary_change_percent": 2}
    ).json()

    def personnel(payload):
        return next(
            m for m in payload["comparison"]["financial"] if m["key"] == "personnel_expense"
        )

    base_metric = personnel(baseline)
    new_metric = personnel(raised)

    # Personel gideri tam %2 artmalı.
    assert new_metric["percent_change"] is not None
    assert abs(D(new_metric["percent_change"]) - Decimal("2")) < Decimal("0.01")

    # Mutlak değişim = taban gider × 0,02
    expected = D(base_metric["projected_value"]) * Decimal("0.02")
    assert abs(D(new_metric["absolute_change"]) - expected) < Decimal("1")

    # Gider artışı kurum için OLUMSUZ işaretlenmeli.
    assert new_metric["is_favorable"] is False


def test_salary_increase_propagates_to_balance_and_cost_per_student(
    client: TestClient,
) -> None:
    """Bir parametre değişince ETKİLENEN TÜM sonuçlar yeniden hesaplanmalı.

    Maaş zammı yalnızca personel giderini değil; toplam gideri, bütçe dengesini
    ve öğrenci başına maliyeti de değiştirir.
    """
    result = client.post(
        "/api/scenarios/preview", json={"academic_salary_change_percent": 2}
    ).json()
    metrics = {m["key"]: m for m in result["comparison"]["financial"]}

    personnel_delta = D(metrics["personnel_expense"]["absolute_change"])
    expenditure_delta = D(metrics["total_expenditure"]["absolute_change"])
    balance_delta = D(metrics["balance"]["absolute_change"])

    # Toplam gider artışı personel gideri artışına eşit olmalı
    # (başka hiçbir parametre değişmedi).
    assert abs(expenditure_delta - personnel_delta) < Decimal("1")

    # Gelir değişmediği için denge tam gider kadar azalmalı.
    assert abs(balance_delta + personnel_delta) < Decimal("1")

    # Öğrenci başına maliyet artmalı.
    assert metrics["cost_per_student"]["direction"] == "up"
    assert metrics["cost_per_student"]["is_favorable"] is False


def test_student_increase_affects_revenue_expense_and_capacity(
    client: TestClient,
) -> None:
    """Öğrenci artışı gelir, gider ve kapasiteyi birlikte etkilemeli."""
    result = client.post(
        "/api/scenarios/preview", json={"student_change_percent": 10}
    ).json()

    academic = {m["key"]: m for m in result["comparison"]["academic"]}
    financial = {m["key"]: m for m in result["comparison"]["financial"]}
    capacity = {m["key"]: m for m in result["comparison"]["capacity"]}

    assert academic["student_count"]["direction"] == "up"
    assert financial["total_revenue"]["direction"] == "up"
    # Eğitim gideri öğrenciyle birlikte arttığı için toplam gider de artmalı.
    assert financial["total_expenditure"]["direction"] == "up"
    # Eş zamanlı derslik talebi de artmalı.
    assert capacity["classroom_demand"]["direction"] == "up"
    # Öğrenci başına öğretim üyesi oranı kötüleşmeli (personel sabit).
    assert academic["student_staff_ratio"]["direction"] == "up"
    assert academic["student_staff_ratio"]["is_favorable"] is False


def test_scholarship_change_reduces_revenue(client: TestClient) -> None:
    """Burs oranı artışı net öğrenim geliri düşürmeli."""
    result = client.post(
        "/api/scenarios/preview", json={"scholarship_change_percent": 5}
    ).json()
    financial = {m["key"]: m for m in result["comparison"]["financial"]}
    academic = {m["key"]: m for m in result["comparison"]["academic"]}

    assert financial["total_revenue"]["direction"] == "down"
    # Efektif burs oranı tam 5 puan artmalı.
    assert abs(D(academic["scholarship_rate"]["absolute_change"]) - Decimal("5")) < Decimal("0.01")


def test_scholarship_rate_cannot_exceed_100_percent(client: TestClient) -> None:
    """Burs oranı %100'ü aşamaz; aşan istek reddedilmeli."""
    response = client.post(
        "/api/scenarios/preview", json={"scholarship_change_percent": 90}
    )
    assert response.status_code == 422
    assert "burs" in str(response.json()).lower()


def test_capacity_uses_simultaneous_use_factor(client: TestClient) -> None:
    """HATA: Tüm öğrencilerin aynı anda derslikte olduğu varsayılıyordu.

    Katsayısız karşılaştırma her kurumu "kapasitesi yetersiz" gösteriyordu ve
    uyarı anlamını yitiriyordu.
    """
    result = client.post("/api/scenarios/preview", json={}).json()
    metrics = result["result"]
    capacity = {m["key"]: m for m in result["comparison"]["capacity"]}

    demand = D(capacity["classroom_demand"]["projected_value"])
    students = Decimal(metrics["projected_student_count"])

    # Eş zamanlı talep öğrenci sayısından KÜÇÜK olmalı.
    assert demand < students
    # %35 katsayısı uygulanmış olmalı.
    assert abs(demand - students * Decimal("0.35")) <= Decimal("1")


def test_quota_change_uses_fill_elasticity(client: TestClient) -> None:
    """Kontenjan artışının tamamı öğrenciye dönüşmemeli.

    Boş kontenjan gelir üretmez; doluluk esnekliği (0,85) uygulanır.
    """
    baseline = client.post("/api/scenarios/preview", json={}).json()
    scenario = client.post(
        "/api/scenarios/preview", json={"quota_change_percent": 100}
    ).json()

    base_students = baseline["result"]["projected_student_count"]
    new_students = scenario["result"]["projected_student_count"]

    growth = (new_students - base_students) / base_students * 100
    # %100 kontenjan artışı %85 öğrenci artışı üretmeli, %100 değil.
    assert 84 <= growth <= 86, f"Beklenen ~%85 artış, gerçekleşen %{growth:.1f}"


def test_comparison_report_has_all_required_fields(client: TestClient) -> None:
    """Karşılaştırma her metrik için önceki/yeni/mutlak/yüzde döndürmeli."""
    result = client.post(
        "/api/scenarios/preview", json={"academic_salary_change_percent": 2}
    ).json()
    comparison = result["comparison"]

    assert comparison["currency"] == "USD"
    assert comparison["financial"] and comparison["academic"] and comparison["capacity"]

    for metric in comparison["financial"] + comparison["academic"] + comparison["capacity"]:
        for field in (
            "label", "unit", "baseline_value", "projected_value",
            "absolute_change", "direction", "group", "description",
        ):
            assert field in metric, f"{metric.get('key')} içinde {field} yok"
        # Mutlak değişim = yeni − önceki (arayüz kendi hesabını yapmasın diye).
        expected = D(metric["projected_value"]) - D(metric["baseline_value"])
        assert abs(D(metric["absolute_change"]) - expected) < Decimal("0.02")


def test_scenario_baseline_matches_financial_module(client: TestClient) -> None:
    """HATA: Senaryo tabanı ile mali analiz aynı kurumun gelirini farklı söylüyordu.

    Bir karar destek sisteminde bu, verilen kararı doğrudan yanlış yapar.
    """
    finance = client.get(f"/api/finance/{CURRENT_YEAR}/summary").json()
    scenario = client.post(
        f"/api/scenarios/preview?financial_period={CURRENT_YEAR}", json={}
    ).json()

    gross_revenue = D(finance["total_revenue"]) * MILLION
    scholarship = next(
        D(e["amount"]) * MILLION
        for e in finance["expenditure_breakdown"]
        if "Burs" in e["category"]
    )
    # Senaryo motoru net (burs sonrası) gelirle çalışır.
    expected_net = gross_revenue - scholarship
    actual = D(scenario["result"]["baseline_revenue"])

    assert abs(expected_net - actual) < Decimal("1000"), (
        f"Mali modül {expected_net} diyor, senaryo {actual} diyor. "
        "İki modül aynı kurumun gelirini farklı söylüyor."
    )


def test_financial_period_selection_changes_baseline(client: TestClient) -> None:
    """Farklı mali dönem seçilince taban da değişmeli."""
    periods = client.get("/api/scenarios/financial-periods").json()["periods"]
    assert len(periods) >= 5, "En az 5 mali dönem olmalı"

    first = client.post(
        f"/api/scenarios/preview?financial_period={periods[0]}", json={}
    ).json()
    last = client.post(
        f"/api/scenarios/preview?financial_period={periods[-1]}", json={}
    ).json()

    assert first["result"]["baseline_revenue"] != last["result"]["baseline_revenue"]
    assert first["result"]["baseline_student_count"] < last["result"]["baseline_student_count"]


def test_scenario_catalog_field_names_match_schema(client: TestClient) -> None:
    """Katalogdaki alan adları şemada GERÇEKTEN olmalı.

    Bu test, arayüz–backend alan adı uyuşmazlığının bir daha oluşmasını önler.
    """
    from app.schemas.scenarios import ScenarioInputCreate

    valid_fields = set(ScenarioInputCreate.model_fields)
    catalog = client.get("/api/scenarios/catalog").json()
    assert catalog, "Senaryo kataloğu boş"

    for scenario in catalog:
        for field in scenario["fields"]:
            assert field["name"] in valid_fields, (
                f"'{scenario['key']}' senaryosundaki '{field['name']}' alanı "
                f"ScenarioInputCreate şemasında yok. Arayüz bu alanı gönderirse "
                "istek 422 ile reddedilir."
            )


def test_catalog_covers_all_required_scenario_types(client: TestClient) -> None:
    """İstenen dokuz senaryo türünün tamamı desteklenmeli."""
    catalog = {s["key"] for s in client.get("/api/scenarios/catalog").json()}
    required = {
        "academic-staffing",            # 1. maaş yüzde değişimi
        "academic-staffing-headcount",  # 2. personel sayısı
        "student-enrollment",           # 3. öğrenci sayısı
        "scholarship-policy",           # 4. burs oranı
        "tuition-scholarship",          # 5. öğrenim ücreti
        "quota-change",                 # 6. kontenjan
        "investment",                   # 7. derslik/laboratuvar kapasitesi
        "revenue-item",                 # 9a. gelir kalemi
        "expense-item",                 # 9b. gider kalemi
    }
    missing = required - catalog
    assert not missing, f"Desteklenmeyen senaryo türleri: {missing}"


# ===========================================================================
# 2. Mali veri — 5 yıllık toplamlar ve türetme kuralları
# ===========================================================================


def test_five_financial_periods_exist_with_data(client: TestClient) -> None:
    """En az 5 gerçekleşmiş mali dönem bulunmalı."""
    trend = client.get("/api/finance/trend").json()
    with_data = [r for r in trend if D(r["total_revenue"]) > 0]
    assert len(with_data) >= 5, f"Yalnızca {len(with_data)} dönem verisi var"


def test_financial_totals_equal_sum_of_line_items(client: TestClient) -> None:
    """Dönem toplamı, kalem toplamına birebir eşit olmalı."""
    for period in client.get("/api/finance/periods").json():
        year = period["academic_year"]
        summary = client.get(f"/api/finance/{year}/summary").json()

        revenue_sum = sum(D(e["amount"]) for e in summary["revenue_breakdown"])
        expense_sum = sum(D(e["amount"]) for e in summary["expenditure_breakdown"])

        assert D(summary["total_revenue"]) == revenue_sum, f"{year} gelir toplamı tutmuyor"
        assert D(summary["total_expenditure"]) == expense_sum, f"{year} gider toplamı tutmuyor"
        assert D(summary["balance"]) == revenue_sum - expense_sum


def test_personnel_expense_equals_headcount_times_salary(db_session: Session) -> None:
    """Personel gideri = personel sayısı × ortalama maaş eşitliği doğrulanabilmeli.

    Bu eşitlik, maaş senaryosunun doğru çalışabilmesinin ön koşuludur.
    """
    periods = db_session.execute(
        select(FinancialPeriod).where(FinancialPeriod.total_students > 0)
    ).scalars().all()
    assert periods, "Gerçekleşmiş mali dönem yok"

    for period in periods:
        entry = db_session.execute(
            select(FinancialEntry).where(
                FinancialEntry.financial_period_id == period.id,
                FinancialEntry.category == "Akademik personel giderleri",
            )
        ).scalars().first()
        assert entry is not None, f"{period.academic_year} akademik personel gideri yok"

        expected = (
            Decimal(period.academic_staff_count)
            * period.average_academic_salary_usd
            / MILLION
        )
        # Milyon USD'ye yuvarlama farkı 0,01'i geçmemeli.
        assert abs(entry.amount - expected) < Decimal("0.01"), (
            f"{period.academic_year}: kalem {entry.amount}M, "
            f"{period.academic_staff_count} × ${period.average_academic_salary_usd} "
            f"= {expected}M"
        )


def test_scholarship_expense_matches_tuition_and_rate(db_session: Session) -> None:
    """Burs gideri = brüt öğrenim ücreti geliri × burs oranı."""
    periods = db_session.execute(
        select(FinancialPeriod).where(FinancialPeriod.total_students > 0)
    ).scalars().all()

    for period in periods:
        gross = db_session.execute(
            select(FinancialEntry).where(
                FinancialEntry.financial_period_id == period.id,
                FinancialEntry.category == "Öğrenim ücretleri (brüt)",
            )
        ).scalars().first()
        scholarship = db_session.execute(
            select(FinancialEntry).where(
                FinancialEntry.financial_period_id == period.id,
                FinancialEntry.category == "Burs giderleri",
            )
        ).scalars().first()
        assert gross and scholarship

        expected = gross.amount * period.average_scholarship_rate_percent / Decimal("100")
        assert abs(scholarship.amount - expected) < Decimal("0.02"), (
            f"{period.academic_year}: burs {scholarship.amount}M, beklenen {expected}M"
        )


def test_gross_tuition_matches_students_times_list_price(db_session: Session) -> None:
    """Brüt öğrenim geliri = öğrenci sayısı × liste ücreti."""
    for period in db_session.execute(
        select(FinancialPeriod).where(FinancialPeriod.total_students > 0)
    ).scalars():
        gross = db_session.execute(
            select(FinancialEntry).where(
                FinancialEntry.financial_period_id == period.id,
                FinancialEntry.category == "Öğrenim ücretleri (brüt)",
            )
        ).scalars().first()
        expected = (
            Decimal(period.total_students)
            * period.list_tuition_per_student_usd
            / MILLION
        )
        assert abs(gross.amount - expected) < Decimal("0.01")


def test_cost_per_student_matches_manual_calculation(client: TestClient) -> None:
    """Öğrenci başına maliyet = toplam gider / öğrenci sayısı."""
    summary = client.get(f"/api/finance/{CURRENT_YEAR}/summary").json()
    expected = (
        D(summary["total_expenditure"]) * MILLION / Decimal(summary["total_students"])
    )
    # Tam USD alanı yuvarlama kaybı olmadan karşılaştırılabilir.
    assert abs(D(summary["cost_per_student_usd"]) - expected) < Decimal("0.01")

    # Bin USD alanı özet kartlar için iki ondalığa yuvarlanır; bu yüzden
    # 10 USD'ye kadar sapma beklenen davranıştır.
    rounded = D(summary["cost_per_student_thousand_usd"]) * Decimal("1000")
    assert abs(rounded - expected) <= Decimal("10")


def test_year_over_year_change_is_correct(client: TestClient) -> None:
    """Yıllık değişim yüzdesi doğru hesaplanmalı."""
    trend = [r for r in client.get("/api/finance/trend").json() if D(r["total_revenue"]) > 0]
    for previous, current in zip(trend, trend[1:]):
        expected = (
            (D(current["total_revenue"]) - D(previous["total_revenue"]))
            / D(previous["total_revenue"]) * Decimal("100")
        )
        assert abs(D(current["revenue_change_percent"]) - expected) < Decimal("0.02")

    # İlk yılda karşılaştırma tabanı olmadığı için değişim null olmalı.
    assert trend[0]["revenue_change_percent"] is None


def test_all_amounts_are_usd(client: TestClient) -> None:
    """Sistemde tek para birimi USD olmalı; TL kalıntısı bulunmamalı."""
    summary = client.get(f"/api/finance/{CURRENT_YEAR}/summary").text
    for forbidden in ("₺", "TRY", " TL"):
        assert forbidden not in summary, f"Mali cevapta '{forbidden}' geçiyor"

    comparison = client.post("/api/scenarios/preview", json={}).json()["comparison"]
    assert comparison["currency"] == "USD"


# ===========================================================================
# 3. Akademik başarı — sınır ve tutarlılık kontrolleri
# ===========================================================================


def test_success_rates_are_within_bounds(client: TestClient) -> None:
    """Tüm oranlar 0-100 aralığında olmalı."""
    for level in ("by-faculty", "by-department", "by-program"):
        rows = client.get(
            f"/api/academic-success/{level}", params={"academic_year": CURRENT_YEAR}
        ).json()
        assert rows, f"{level} boş döndü"
        for row in rows:
            for field in (
                "course_pass_rate", "course_fail_rate",
                "average_success_score", "dropout_rate", "graduation_rate",
            ):
                value = row[field]
                if value is None:
                    continue
                assert Decimal("0") <= D(value) <= Decimal("100"), (
                    f"{level} · {field} = {value} — 0-100 aralığı dışında"
                )


def test_pass_and_fail_rates_sum_to_100(client: TestClient) -> None:
    """Ders geçme + ders kalma oranı tam 100 etmeli."""
    for level in ("by-faculty", "by-department", "by-program"):
        for row in client.get(
            f"/api/academic-success/{level}", params={"academic_year": CURRENT_YEAR}
        ).json():
            total = D(row["course_pass_rate"]) + D(row["course_fail_rate"])
            assert abs(total - Decimal("100")) < Decimal("0.01"), (
                f"{level}: geçme + kalma = {total}, 100 olmalıydı"
            )


def test_faculty_department_program_totals_are_consistent(client: TestClient) -> None:
    """Fakülte, bölüm ve program toplamları birbirine eşit olmalı.

    Aynı yıl için farklı ekranlarda farklı toplam gösterilmesi bir karar
    destek sisteminde kabul edilemez.
    """
    overview = client.get(
        "/api/academic-success/overview", params={"academic_year": CURRENT_YEAR}
    ).json()
    faculties = client.get(
        "/api/academic-success/by-faculty", params={"academic_year": CURRENT_YEAR}
    ).json()
    departments = client.get(
        "/api/academic-success/by-department", params={"academic_year": CURRENT_YEAR}
    ).json()
    programs = client.get(
        "/api/academic-success/by-program", params={"academic_year": CURRENT_YEAR}
    ).json()

    university_total = overview["measured_student_count"]
    faculty_total = sum(r["measured_student_count"] for r in faculties)
    department_total = sum(r["measured_student_count"] for r in departments)
    program_total = sum(r["measured_student_count"] for r in programs)

    assert university_total == faculty_total == department_total == program_total, (
        f"Toplamlar tutmuyor — üniversite {university_total}, fakülte {faculty_total}, "
        f"bölüm {department_total}, program {program_total}"
    )


def test_faculty_rate_is_weighted_not_simple_average(client: TestClient) -> None:
    """Fakülte oranı, program satırlarının AĞIRLIKLI ortalaması olmalı.

    Basit ortalama, 40 öğrencili programı 600 öğrencili programla aynı
    ağırlıkta sayar ve fakülte performansını yanlış gösterir.
    """
    faculties = client.get(
        "/api/academic-success/by-faculty", params={"academic_year": CURRENT_YEAR}
    ).json()
    # Ağırlık farkının görülebilmesi için birden fazla programı olan bir
    # fakülte seçilir; tek programlı fakültede ağırlıklı ve basit ortalama
    # zaten aynı çıkar ve test bir şey kanıtlamaz.
    target = max(faculties, key=lambda f: f["program_count"])
    assert target["program_count"] >= 2, "Çok programlı fakülte bulunamadı"

    programs = client.get(
        "/api/academic-success/by-program",
        params={"academic_year": CURRENT_YEAR, "faculty_id": target["faculty_id"]},
    ).json()

    weight_total = sum(p["measured_student_count"] for p in programs)
    weighted = sum(
        D(p["course_pass_rate"]) * p["measured_student_count"] for p in programs
    ) / weight_total
    simple = sum(D(p["course_pass_rate"]) for p in programs) / len(programs)

    assert abs(D(target["course_pass_rate"]) - weighted) < Decimal("0.02")
    # Ağırlıklı ile basit ortalama farklı olmalı; aksi halde test ağırlığın
    # gerçekten uygulandığını kanıtlamıyor demektir.
    assert abs(weighted - simple) > Decimal("0.01"), (
        "Ağırlıklı ve basit ortalama aynı çıktı; ağırlık uygulanmıyor olabilir."
    )


def test_department_drilldown_filters_correctly(client: TestClient) -> None:
    """Fakülte seçilince yalnızca o fakültenin bölümleri dönmeli."""
    faculties = client.get(
        "/api/academic-success/by-faculty", params={"academic_year": CURRENT_YEAR}
    ).json()
    target = faculties[0]

    filtered = client.get(
        "/api/academic-success/by-department",
        params={"academic_year": CURRENT_YEAR, "faculty_id": target["faculty_id"]},
    ).json()
    assert filtered
    assert all(r["faculty_id"] == target["faculty_id"] for r in filtered)


def test_success_trend_covers_five_years(client: TestClient) -> None:
    """Başarı trendi en az 5 dönem içermeli."""
    trend = client.get("/api/academic-success/trend").json()
    assert len(trend) >= 5, f"Yalnızca {len(trend)} dönem var"
    for point in trend:
        assert Decimal("0") <= D(point["course_pass_rate"]) <= Decimal("100")


def test_rankings_exclude_tiny_units(client: TestClient) -> None:
    """Küçük birimler sıralamayı yanıltmamalı."""
    rankings = client.get(
        "/api/academic-success/rankings",
        params={"academic_year": CURRENT_YEAR, "level": "program"},
    ).json()
    threshold = rankings["minimum_student_threshold"]
    for entry in rankings["top"] + rankings["bottom"]:
        assert entry["measured_student_count"] >= threshold


# ===========================================================================
# 4. KPI künyeleri ve türetilmiş göstergeler
# ===========================================================================


def test_every_kpi_has_complete_metadata(client: TestClient) -> None:
    """Her göstergenin açıklaması, formülü, kaynağı ve yönü olmalı.

    Bu alanlar olmadan ekrandaki "52.2" neyi ölçtüğü belirsiz bir sayı kalır.
    """
    kpis = client.get("/api/kpi", params={"academic_year": CURRENT_YEAR}).json()
    assert kpis

    incomplete = []
    for kpi in kpis:
        missing = [
            field
            for field in ("description", "formula", "data_source")
            if not kpi.get(field)
        ]
        if missing:
            incomplete.append((kpi["name"], missing))
        assert isinstance(kpi["higher_is_better"], bool)
        assert kpi["direction_label"], f"{kpi['name']} için yön yorumu yok"

    assert not incomplete, f"Künyesi eksik göstergeler: {incomplete}"


def test_cost_kpis_are_marked_lower_is_better(client: TestClient) -> None:
    """Maliyet göstergelerinde düşmek iyi olmalı.

    Bu bayrak olmadan arayüz maliyet artışını yeşil (olumlu) gösterirdi.
    """
    kpis = {k["name"]: k for k in client.get("/api/kpi", params={"academic_year": CURRENT_YEAR}).json()}
    for name in ("Öğrenci başına eğitim gideri (bin USD)", "Öğrenci / öğretim üyesi oranı"):
        assert name in kpis, f"{name} göstergesi yok"
        assert kpis[name]["higher_is_better"] is False, f"{name} yanlış işaretlenmiş"


def test_industry_collaboration_index_is_computed_from_components(
    client: TestClient,
) -> None:
    """Sanayi iş birliği endeksi bileşenlerden formülle hesaplanmalı."""
    data = client.get(
        "/api/engagement/industry-collaboration", params={"academic_year": CURRENT_YEAR}
    ).json()

    assert len(data["components"]) == 5
    # Ağırlıklar toplamı 1,00 olmalı.
    assert abs(D(data["weight_total"]) - Decimal("1")) < Decimal("0.001")
    assert data["weight_warning"] is None

    # Endeks = Σ katkılar
    contributions = sum(D(c["contribution_to_index"]) for c in data["components"])
    assert abs(D(data["index_value"]) - contributions) < Decimal("0.02")

    # Her bileşenin katkısı = hedefe ulaşma × ağırlık
    for component in data["components"]:
        expected = D(component["achievement_percent"]) * D(component["weight"])
        assert abs(D(component["contribution_to_index"]) - expected) < Decimal("0.02")


def test_regional_contribution_index_is_computed_from_components(
    client: TestClient,
) -> None:
    """Bölgesel katkı endeksi altı bileşenden hesaplanmalı."""
    data = client.get(
        "/api/engagement/regional-contribution", params={"academic_year": CURRENT_YEAR}
    ).json()

    assert len(data["components"]) == 6
    assert abs(D(data["weight_total"]) - Decimal("1")) < Decimal("0.001")
    contributions = sum(D(c["contribution_to_index"]) for c in data["components"])
    assert abs(D(data["index_value"]) - contributions) < Decimal("0.02")


def test_regional_employment_share_is_plausible(client: TestClient) -> None:
    """Bölgesel istihdam oranı %100'ü aşmamalı.

    Önceki sürümde bir yılın istihdamı tüm yılların mezun havuzuna bölünüyor
    ve %160 gibi imkânsız bir oran üretiliyordu.
    """
    data = client.get(
        "/api/engagement/regional-contribution", params={"academic_year": CURRENT_YEAR}
    ).json()
    share = data["regional_employment_share_percent"]
    if share is not None:
        assert Decimal("0") <= D(share) <= Decimal("100"), f"Oran %{share} — imkânsız"
    assert data["regional_employment_note"]


def test_engagement_trend_covers_five_years(client: TestClient) -> None:
    """İki endeksin de 5 yıllık zaman serisi olmalı."""
    trend = client.get("/api/engagement/trend").json()
    assert len(trend) >= 5
    for point in trend:
        assert point["industry_collaboration_index"] is not None
        assert point["regional_contribution_index"] is not None


# ===========================================================================
# 5. Genel veri tutarlılığı
# ===========================================================================


def test_student_count_is_consistent_across_modules(client: TestClient) -> None:
    """Öğrenci sayısı tüm ekranlarda aynı olmalı."""
    analytics = client.get("/api/student-analytics/overview").json()["total_students"]
    success = client.get(
        "/api/academic-success/overview", params={"academic_year": CURRENT_YEAR}
    ).json()["measured_student_count"]
    capacity = client.get(
        "/api/physical-resources/capacity/per-person"
    ).json()["active_student_count"]

    assert analytics == success, (
        f"Öğrenci Analitiği {analytics}, Akademik Başarı {success} diyor"
    )
    # Kapasite ekranı yalnızca AKTİF öğrencileri sayar; toplamdan küçük olmalı.
    assert capacity <= analytics


def test_academic_staff_salaries_are_populated(db_session: Session) -> None:
    """Her personelin maaşı tanımlı olmalı; maaş senaryosu buna dayanır."""
    staff = db_session.execute(select(AcademicStaff)).scalars().all()
    assert staff
    assert all(s.annual_salary_usd > 0 for s in staff), "Maaşı sıfır olan personel var"


def test_seed_is_idempotent(db_session: Session) -> None:
    """Seed tekrar çalıştırıldığında kayıt çoğalmamalı."""
    def counts():
        return {
            "students": db_session.execute(select(func.count(Student.id))).scalar(),
            "staff": db_session.execute(select(func.count(AcademicStaff.id))).scalar(),
            "success": db_session.execute(
                select(func.count(AcademicSuccessRecord.id))
            ).scalar(),
            "entries": db_session.execute(select(func.count(FinancialEntry.id))).scalar(),
        }

    before = counts()

    import seed_all_demo_data

    seed_all_demo_data.main()
    db_session.expire_all()

    after = counts()
    assert before == after, f"Seed kayıt çoğalttı: {before} -> {after}"
