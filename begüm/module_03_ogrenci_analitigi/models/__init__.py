"""Modül 3 ORM modelleri.

Modeller burada tek noktadan dışa açılır; böylece servis ve router katmanları
`from module_03_ogrenci_analitigi.models import Student` gibi kısa import
kullanabilir.
"""

from .academic_program import AcademicProgram
from .program_enrollment_snapshot import ProgramEnrollmentSnapshot
from .student import Student
from .student_academic_record import StudentAcademicRecord

__all__ = [
    "AcademicProgram",
    "ProgramEnrollmentSnapshot",
    "Student",
    "StudentAcademicRecord",
]
