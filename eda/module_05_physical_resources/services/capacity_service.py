from seed_data import facilities

# Not: gerçek entegrasyonda bu sayı Modül 4'ten (personel) ve
# öğrenci modülünden gelecek. Şimdilik demo amaçlı sabit değer.
TOTAL_STUDENTS = 3200
TOTAL_STAFF = 180


def get_facilities():
    return facilities


def get_classrooms():
    return [f for f in facilities if f.type == "classroom"]


def calculate_capacity():
    result = []
    for f in facilities:
        occupancy = round((f.occupied / f.capacity) * 100, 2)
        result.append({
            "name": f.name,
            "type": f.type,
            "department": f.department,
            "capacity": f.capacity,
            "occupied": f.occupied,
            "occupancy": f"{occupancy}%"
        })
    return result


def utilization_by_type():
    """Tesis türüne göre ortalama kullanım oranı"""
    groups = {}
    for f in facilities:
        if f.type not in groups:
            groups[f.type] = {"total_capacity": 0, "total_occupied": 0, "count": 0}
        groups[f.type]["total_capacity"] += f.capacity
        groups[f.type]["total_occupied"] += f.occupied
        groups[f.type]["count"] += 1

    result = []
    for ftype, data in groups.items():
        avg_util = round((data["total_occupied"] / data["total_capacity"]) * 100, 2)
        result.append({
            "type": ftype,
            "facility_count": data["count"],
            "total_capacity": data["total_capacity"],
            "average_utilization": f"{avg_util}%"
        })
    return result


def allocation_by_department():
    """Birim bazlı toplam alan (kapasite) dağılımı"""
    groups = {}
    for f in facilities:
        if f.department not in groups:
            groups[f.department] = 0
        groups[f.department] += f.capacity

    return [{"department": dept, "total_capacity": cap} for dept, cap in groups.items()]


def space_per_person():
    """Öğrenci ve personel başına düşen toplam kapasite"""
    total_capacity = sum(f.capacity for f in facilities)
    return {
        "total_capacity": total_capacity,
        "space_per_student": round(total_capacity / TOTAL_STUDENTS, 3),
        "space_per_staff": round(total_capacity / TOTAL_STAFF, 3)
    }


def underutilized_facilities(threshold=50):
    """Doluluk oranı eşik değerinin altında olan tesisler"""
    result = []
    for f in facilities:
        occupancy = (f.occupied / f.capacity) * 100
        if occupancy < threshold:
            result.append({"name": f.name, "type": f.type, "occupancy": f"{round(occupancy, 1)}%"})
    return result


def overcrowded_facilities(threshold=90):
    """Doluluk oranı eşik değerinin üstünde olan tesisler"""
    result = []
    for f in facilities:
        occupancy = (f.occupied / f.capacity) * 100
        if occupancy >= threshold:
            result.append({"name": f.name, "type": f.type, "occupancy": f"{round(occupancy, 1)}%"})
    return result


def forecast_capacity_need(expected_growth_percent):
    """Yeni program/öğrenci artışının kapasiteye etkisini tahmin eder"""
    total_capacity = sum(f.capacity for f in facilities)
    total_occupied = sum(f.occupied for f in facilities)
    projected_occupied = total_occupied * (1 + expected_growth_percent / 100)

    return {
        "current_capacity": total_capacity,
        "current_occupied": total_occupied,
        "expected_growth_percent": expected_growth_percent,
        "projected_occupied": round(projected_occupied, 1),
        "sufficient": projected_occupied <= total_capacity,
        "shortfall": max(0, round(projected_occupied - total_capacity, 1))
    }