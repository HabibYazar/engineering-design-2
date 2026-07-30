from module_05_physical_resources.models.classroom import Classroom

classrooms = [
    Classroom("A101", 40, 35),
    Classroom("B205", 60, 48),
    Classroom("C301", 30, 25),
]

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