from fastapi import APIRouter

from module_05_physical_resources.services.capacity_service import (
    calculate_capacity
)

router = APIRouter()


@router.get("/capacity")
def capacity():
    return calculate_capacity()