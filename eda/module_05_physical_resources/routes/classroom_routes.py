from fastapi import APIRouter

from module_05_physical_resources.services.capacity_service import (
    get_classrooms,
    calculate_capacity
)

router = APIRouter()


@router.get("/classrooms")
def classrooms():

    return get_classrooms()