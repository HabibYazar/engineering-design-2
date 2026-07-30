from module_04_academic_staff.models.staff import Staff


staffs = [

    Staff(1, "Dr. Ayşe", 12, 30),

    Staff(2, "Dr. Mehmet", 8, 25),

    Staff(3, "Dr. Fatma", 15, 50)

]


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