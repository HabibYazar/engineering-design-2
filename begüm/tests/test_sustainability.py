"""Modül 7 — Program Sürdürülebilirliği endpoint testleri."""

ACADEMIC_YEAR = "2026-2027"


def test_weights_sum_to_100_and_cover_11_criteria(client):
    resp = client.get("/api/program-sustainability/weights")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_weight"] == 100
    assert len(body["weights"]) == 11
    assert set(body["computed_criteria"]) == {
        "student_demand",
        "occupancy_rate",
        "graduation_rate",
    }


def test_scores_sorted_ascending_with_partial_completeness(client):
    resp = client.get(f"/api/program-sustainability/scores?academic_year={ACADEMIC_YEAR}")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 8

    scores = [r["sustainability_score"] for r in rows]
    assert scores == sorted(scores)
    # Yalnızca 3/11 kriter (ağırlık toplamı 40) Modül 3'ten hesaplanabiliyor.
    assert all(r["data_completeness_percent"] == 40.0 for r in rows)


def test_post_scores_with_external_inputs_raises_score_and_completeness(client):
    payload = {
        "academic_year": ACADEMIC_YEAR,
        "external_inputs": {
            "CENG-BSC": {
                "research_performance": 78,
                "academic_staff_quality": 82,
                "strategic_contribution": 85,
                "revenue_expenditure_balance": 55,
                "graduate_employability": 74,
            }
        },
    }
    resp = client.post("/api/program-sustainability/scores", json=payload)
    assert resp.status_code == 200

    ceng = next(r for r in resp.json() if r["program_code"] == "CENG-BSC")
    assert ceng["data_completeness_percent"] == 87.0
    assert ceng["sustainability_score"] == 55.31
    assert ceng["category"] == "Stratejik kurumsal destek gerektiren program"


def test_categories_cover_all_programs_exactly_once(client):
    resp = client.get(f"/api/program-sustainability/categories?academic_year={ACADEMIC_YEAR}")
    assert resp.status_code == 200
    rows = resp.json()
    assert sum(r["program_count"] for r in rows) == 8
    all_codes = [code for r in rows for code in r["program_codes"]]
    assert len(all_codes) == len(set(all_codes))  # her program tam olarak bir kategoride


def test_simplified_category_maps_every_program_to_one_of_four_abu_categories(client):
    """ABU PDF'inin yeni, 4 kategorili basit sınıflandırması (Bölüm 6 formatı)."""
    resp = client.get(f"/api/program-sustainability/scores?academic_year={ACADEMIC_YEAR}")
    rows = resp.json()
    allowed = {
        "Güçlendirilmesi gereken program",
        "Büyütülebilecek program",
        "Yeniden yapılandırılması gereken program",
        "Birleştirilmesi değerlendirilebilecek program",
    }
    for r in rows:
        assert r["simplified_category"] in allowed
        assert r["simplified_category_reason"]


def test_program_score_unknown_code_returns_404(client):
    resp = client.get(
        f"/api/program-sustainability/scores/DOES-NOT-EXIST?academic_year={ACADEMIC_YEAR}"
    )
    assert resp.status_code == 404
