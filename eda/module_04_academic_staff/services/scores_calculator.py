import json
import os
from seed_data import staffs


def load_weights():
    config_path = os.path.join(os.path.dirname(__file__), "..", "config", "weights.json")
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_staff():
    return staffs


def calculate_score():
    weights = load_weights()
    ranking = []
    for staff in staffs:
        score = (
            staff.publication * weights["publication"]
            + staff.citation * weights["citation"]
            + staff.teaching_load * weights["teaching_load"]
            + staff.advising_count * weights["advising_count"]
            + staff.project_count * weights["project_count"]
            + staff.patent_count * weights["patent_count"]
            + staff.community_engagement * weights["community_engagement"]
        )
        ranking.append({"name": staff.name, "department": staff.department, "score": round(score, 1)})
    return sorted(ranking, key=lambda x: x["score"], reverse=True)


def compare_by(field):
    """field: 'department', 'faculty', veya 'title' olabilir"""
    groups = {}
    for staff in staffs:
        key = getattr(staff, field)
        if key not in groups:
            groups[key] = {"count": 0, "total_publication": 0, "total_citation": 0}
        groups[key]["count"] += 1
        groups[key]["total_publication"] += staff.publication
        groups[key]["total_citation"] += staff.citation

    result = []
    for key, data in groups.items():
        result.append({
            field: key,
            "staff_count": data["count"],
            "avg_publication": round(data["total_publication"] / data["count"], 1),
            "avg_citation": round(data["total_citation"] / data["count"], 1),
        })
    return result


def trend_by_year():
    """Akademik yıla göre gruplanmış toplam yayın/atıf"""
    years = {}
    for staff in staffs:
        year = staff.academic_year
        if year not in years:
            years[year] = {"publication": 0, "citation": 0, "staff_count": 0}
        years[year]["publication"] += staff.publication
        years[year]["citation"] += staff.citation
        years[year]["staff_count"] += 1

    result = []
    for year, data in sorted(years.items()):
        result.append({"academic_year": year, **data})
    return result