from fastapi import APIRouter

from module_05_physical_resources.services.capacity_service import (
    get_facilities,
    get_classrooms,
    calculate_capacity,
    utilization_by_type,
    allocation_by_department,
    space_per_person,
    underutilized_facilities,
    overcrowded_facilities,
    forecast_capacity_need
)

router = APIRouter()


@router.get("/facilities")
def facilities():
    return get_facilities()


@router.get("/classrooms")
def classrooms():
    return get_classrooms()


@router.get("/capacity")
def capacity():
    return calculate_capacity()


@router.get("/capacity/by-type")
def by_type():
    return utilization_by_type()


@router.get("/capacity/by-department")
def by_department():
    return allocation_by_department()


@router.get("/capacity/per-person")
def per_person():
    return space_per_person()


@router.get("/capacity/underutilized")
def underutilized():
    return underutilized_facilities()


@router.get("/capacity/overcrowded")
def overcrowded():
    return overcrowded_facilities()


@router.get("/capacity/forecast")
def forecast(growth_percent: float = 10):
    return forecast_capacity_need(growth_percent)