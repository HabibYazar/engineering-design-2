from module_04_academic_staff.models.staff import Staff
from module_05_physical_resources.models.facility import Facility
from module_05_physical_resources.models.classroom import Classroom
from module_14_user_authorization.models.user import User

staffs = [
    Staff(1, "Dr. Ayşe", "Bilgisayar Mühendisliği", "Mühendislik Fakültesi", "Dr. Öğr. Üyesi", "2023-2024",
          12, 30, 8, 3, 2, 0, True, False, 6),
    Staff(2, "Dr. Mehmet", "Elektrik Mühendisliği", "Mühendislik Fakültesi", "Doç. Dr.", "2023-2024",
          8, 25, 10, 5, 1, 1, False, True, 4),
    Staff(3, "Prof. Dr. Fatma", "Makine Mühendisliği", "Mühendislik Fakültesi", "Prof. Dr.", "2023-2024",
          20, 65, 6, 8, 3, 2, True, True, 8),
    Staff(4, "Dr. Ali", "Bilgisayar Mühendisliği", "Mühendislik Fakültesi", "Dr. Öğr. Üyesi", "2022-2023",
          5, 12, 12, 1, 1, 0, False, False, 2),
    Staff(5, "Dr. Zeynep", "Mimarlık", "Mimarlık Fakültesi", "Doç. Dr.", "2023-2024",
          14, 40, 9, 4, 2, 0, False, True, 5),
]

facilities = [
    Facility(1, "A101", "classroom", "Bilgisayar Mühendisliği", 40, 35),
    Facility(2, "B205", "classroom", "Elektrik Mühendisliği", 60, 48),
    Facility(3, "C301", "classroom", "Makine Mühendisliği", 30, 25),
    Facility(4, "D110", "classroom", "Mimarlık", 50, 22),
    Facility(5, "Lab-1", "laboratory", "Bilgisayar Mühendisliği", 25, 24),
    Facility(6, "Lab-2", "laboratory", "Elektrik Mühendisliği", 20, 12),
    Facility(7, "Ofis-Blok-A", "office", "Bilgisayar Mühendisliği", 15, 15),
    Facility(8, "Ofis-Blok-B", "office", "Elektrik Mühendisliği", 12, 8),
    Facility(9, "Kütüphane Ana Salon", "library", "Ortak", 200, 140),
]

classrooms = [
    Classroom("A101", 40, 35),
    Classroom("B205", 60, 48),
    Classroom("C301", 30, 25),
    Classroom("D110", 50, 22),
]

users = [
    User(1, "admin", "1234", "Admin", None, True),
    User(2, "eda", "1234", "Bölüm Başkanı", "Bilgisayar Mühendisliği", True),
    User(3, "dekan1", "1234", "Dekan", "Mühendislik Fakültesi", True),
    User(4, "ogretim1", "1234", "Öğretim Üyesi", "Elektrik Mühendisliği", True),
    User(5, "eskikullanici", "1234", "Öğretim Üyesi", "Makine Mühendisliği", False),
]