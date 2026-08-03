"""Modül 11 — Risk ve Erken Uyarı endpoint testleri."""

ACADEMIC_YEAR = "2026-2027"


def test_alerts_are_sorted_by_severity(client):
    resp = client.get(f"/api/early-warning/alerts?academic_year={ACADEMIC_YEAR}")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 27

    order = {"kritik": 0, "yuksek": 1, "orta": 2, "dusuk": 3}
    ranks = [order[r["severity"]] for r in rows]
    assert ranks == sorted(ranks)


def test_alerts_can_be_filtered_by_severity_and_program(client):
    resp = client.get(
        f"/api/early-warning/alerts?academic_year={ACADEMIC_YEAR}&severity=kritik"
    )
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 11
    assert all(r["severity"] == "kritik" for r in rows)

    resp = client.get(
        f"/api/early-warning/alerts?academic_year={ACADEMIC_YEAR}&program_code=ceng-bsc"
    )
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) > 0
    assert all(r["scope_code"] == "CENG-BSC" for r in rows)


def test_summary_matches_known_demo_totals(client):
    resp = client.get(f"/api/early-warning/summary?academic_year={ACADEMIC_YEAR}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_alerts"] == 27
    assert body["by_severity"] == {"kritik": 11, "yuksek": 11, "orta": 5}
    assert body["most_at_risk"][0]["scope_code"] == "ME-BSC"
    assert body["most_at_risk"][0]["alert_count"] == 7


def test_rule_catalog_has_15_rules_8_implemented(client):
    resp = client.get("/api/early-warning/rules")
    assert resp.status_code == 200
    rules = resp.json()
    assert len(rules) == 15
    assert sum(1 for r in rules if r["implemented"]) == 8


def test_pending_rules_are_exactly_the_unimplemented_ones(client):
    resp = client.get("/api/early-warning/rules")
    all_rules = resp.json()
    expected_pending = {r["key"] for r in all_rules if not r["implemented"]}

    resp = client.get("/api/early-warning/rules/pending")
    assert resp.status_code == 200
    pending = resp.json()
    assert {r["key"] for r in pending} == expected_pending
    assert all(not r["implemented"] for r in pending)


def test_every_alert_pdf_condition_references_a_real_pdf_bullet_or_says_so(client):
    """PDF traceability: pdf_condition ya gerçek bir PDF alıntısıyla başlar ya da
    türetilmiş/bileşik gösterge olduğunu açıkça belirtir (bkz. rules.json düzeltmesi)."""
    resp = client.get("/api/early-warning/rules")
    rules = resp.json()
    for rule in rules:
        condition = rule["pdf_condition"]
        assert condition.startswith(
            (
                "Program enrollment rates fall below a critical threshold",
                "Student attrition rates increase",
                "A budget deficit emerges",
                "Expenditures of an organizational unit exceed its allocated budget",
                "The need for additional academic staff increases",
                "Classroom or laboratory capacity becomes insufficient",
                "Academic performance indicators decline",
                "Strategic objectives are delayed",
                "Accreditation renewal or expiration dates are approaching",
                "Research revenues or student-related revenues decrease",
                "Turetilmis bilesik gosterge",
            )
        ), f"{rule['key']} beklenmeyen pdf_condition: {condition}"
