from seed_data import staffs  


def get_staff():
    return staffs


def calculate_score():
    ranking = []
    for staff in staffs:
        score = staff.publication * 5 + staff.citation * 2
        ranking.append({
            "name": staff.name,
            "score": score
        })
    return ranking