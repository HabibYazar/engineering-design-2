"""Modül 3 — Öğrenci Analitiği endpoint testleri.

Sayısal beklentiler seed_data.py'nin sabit tohumuyla (RANDOM_SEED) üretilen
demo veri kümesinin bilinen çıktısıdır (bkz. begüm/README.md demo akışı).
"""

ACADEMIC_YEAR = "2026-2027"


def test_academic_years_lists_three_years(client):
    resp = client.get("/api/student-analytics/academic-years")
    assert resp.status_code == 200
    assert resp.json() == ["2024-2025", "2025-2026", "2026-2027"]


def test_overview_matches_known_demo_totals(client):
    resp = client.get(f"/api/student-analytics/overview?academic_year={ACADEMIC_YEAR}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["program_count"] == 8
    assert body["total_students"] == 3124
    assert body["total_quota"] == 530
    assert body["total_enrolled_student_count"] == 356
    assert body["overall_occupancy_rate"] == 67.17
    assert body["employment_rate"] == 81.71
    assert body["employed_graduate_count"] == 670


def test_employment_rate_only_counts_graduates(client):
    """Yalnızca mezunlar paydadır; hâlâ okuyan/terk eden öğrenciler dışarıda kalır."""
    resp = client.get(f"/api/student-analytics/overview?academic_year={ACADEMIC_YEAR}")
    body = resp.json()
    graduates = body["graduated_student_count_total"]
    assert body["employed_graduate_count"] <= graduates
    expected_rate = round(body["employed_graduate_count"] / graduates * 100, 2)
    assert body["employment_rate"] == expected_rate


def test_full_scholarship_admission_score_has_fixed_bonus_over_base_score(client):
    """seed_data.py: tam burslu taban puanı = taban puan + 15 (FULL_SCHOLARSHIP_SCORE_BONUS)."""
    resp = client.get(f"/api/student-analytics/admission-scores?academic_year={ACADEMIC_YEAR}")
    rows = resp.json()
    for r in rows:
        assert r["full_scholarship_minimum_admission_score"] == round(
            r["minimum_admission_score"] + 15.0, 2
        )


def test_overview_unknown_year_returns_404(client):
    resp = client.get("/api/student-analytics/overview?academic_year=1999-2000")
    assert resp.status_code == 404


def test_programs_sorted_ascending_by_occupancy(client):
    resp = client.get(f"/api/student-analytics/programs?academic_year={ACADEMIC_YEAR}")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 8

    rates = [r["occupancy_rate"] for r in rows]
    assert rates == sorted(rates)
    assert rows[0]["program_code"] == "MSE-BSC"
    assert rows[0]["occupancy_rate"] == 27.5
    assert rows[-1]["program_code"] == "SWE-BSC"
    assert rows[-1]["occupancy_rate"] == 98.82


def test_program_detail_unknown_code_returns_404(client):
    resp = client.get(
        f"/api/student-analytics/programs/DOES-NOT-EXIST?academic_year={ACADEMIC_YEAR}"
    )
    assert resp.status_code == 404


def test_admission_scores_sorted_descending(client):
    resp = client.get(f"/api/student-analytics/admission-scores?academic_year={ACADEMIC_YEAR}")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 8
    scores = [r["minimum_admission_score"] for r in rows]
    assert scores == sorted(scores, reverse=True)


def test_demand_trends_cover_all_programs_with_a_series(client):
    resp = client.get("/api/student-analytics/demand-trends")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 8
    assert all(len(r["series"]) == 3 for r in rows)  # 3 akademik yıl


def test_comparative_analysis_computes_gap_against_provided_benchmarks(client):
    payload = {
        "academic_year": ACADEMIC_YEAR,
        "comparators": {
            "CENG-BSC": [
                {
                    "university_name": "Bogazici",
                    "occupancy_rate": 100,
                    "minimum_admission_score": 512.8,
                },
                {
                    "university_name": "ITU",
                    "occupancy_rate": 98.57,
                    "minimum_admission_score": 495.6,
                },
            ]
        },
    }
    resp = client.post("/api/student-analytics/comparative", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1

    result = body[0]
    assert result["program_code"] == "CENG-BSC"
    assert result["own_occupancy_rate"] == 38.0
    assert result["average_comparator_occupancy_rate"] == 99.28
    assert result["occupancy_gap_vs_comparators"] == -61.28
    assert result["competitive_position"] == "kıyaslama grubunun altında"


def test_comparative_analysis_unknown_program_code_is_skipped(client):
    payload = {
        "academic_year": ACADEMIC_YEAR,
        "comparators": {"NO-SUCH-CODE": [{"university_name": "X"}]},
    }
    resp = client.post("/api/student-analytics/comparative", json=payload)
    assert resp.status_code == 200
    assert resp.json() == []
