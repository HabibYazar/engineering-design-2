from fastapi import APIRouter

from module_14_user_authorization.schemas.user_schema import LoginRequest
from module_14_user_authorization.services.auth_service import (
    login,
    get_users
)

router = APIRouter()


@router.post("/login")
def login_user(request: LoginRequest):

    return login(request.username, request.password)

@router.get("/users")
def users():

    return get_users()

@router.get("/health")
def health():

    return {
        "status":"running",
        "message":"System is running successfully"
    }