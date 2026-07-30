from seed_data import classrooms


def get_classrooms():
    return classrooms


def calculate_capacity():
    result = []
    for classroom in classrooms:
        occupancy = round((classroom.occupied / classroom.capacity) * 100, 2)
        result.append({
            "room": classroom.room,
            "capacity": classroom.capacity,
            "occupied": classroom.occupied,
            "occupancy": f"{occupancy}%"
        })
    return result