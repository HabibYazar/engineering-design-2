from fastapi import APIRouter

from module_04_academic_staff.services.scores_calculator import (
    get_staff,
    calculate_score
)

router = APIRouter()


@router.get("/staff")
def staff():

    return get_staff()


@router.get("/ranking")
def ranking():

    return calculate_score()