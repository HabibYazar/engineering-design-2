from module_04_academic_staff.models.staff import Staff
from module_05_physical_resources.models.classroom import Classroom
from module_14_user_authorization.models.user import User

staffs = [
    Staff(1, "Dr. Ayşe", 12, 30),
    Staff(2, "Dr. Mehmet", 8, 25),
    Staff(3, "Dr. Fatma", 15, 50),
    Staff(4, "Dr. Ali", 5, 12),
]

classrooms = [
    Classroom("A101", 40, 35),
    Classroom("B205", 60, 48),
    Classroom("C301", 30, 25),
    Classroom("D110", 50, 22),
]

users = [
    User("admin", "1234", "Admin"),
    User("eda", "1234", "Department Head"),
]