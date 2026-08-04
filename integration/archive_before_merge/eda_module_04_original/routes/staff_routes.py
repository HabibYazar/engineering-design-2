from fastapi import APIRouter

from module_04_academic_staff.services.scores_calculator import (
    get_staff,
    calculate_score,
    compare_by,
    trend_by_year
)

router = APIRouter()


@router.get("/staff")
def staff():
    return get_staff()


@router.get("/ranking")
def ranking():
    return calculate_score()


@router.get("/staff/compare/department")
def compare_department():
    return compare_by("department")


@router.get("/staff/compare/faculty")
def compare_faculty():
    return compare_by("faculty")


@router.get("/staff/compare/title")
def compare_title():
    return compare_by("title")


@router.get("/staff/trend")
def trend():
    return trend_by_year()