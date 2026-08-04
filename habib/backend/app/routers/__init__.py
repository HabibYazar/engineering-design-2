"""API endpoint'lerinin konularına göre ayrıldığı router paketi."""

# Router modüllerini burada topluyoruz; main.py tek satırla hepsine erişebiliyor.
from app.routers import (
    administrative_units,
    data_integration,
    departments,
    faculties,
    health,
    programs,
    ranking_evaluations,
    scenarios,
    student_analytics,
    students,
)

__all__ = [
    "health",
    "faculties",
    "departments",
    "programs",
    "administrative_units",
    "data_integration",
    "scenarios",
    "students",
    "student_analytics",
    "ranking_evaluations",
]
