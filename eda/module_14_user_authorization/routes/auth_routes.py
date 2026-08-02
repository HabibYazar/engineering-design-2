from fastapi import APIRouter

from module_14_user_authorization.schemas.user_schema import (
    LoginRequest, CreateUserRequest, TokenRequest
)
from module_14_user_authorization.services.auth_service import (
    login, logout, get_session, has_permission,
    get_users, create_user, deactivate_user
)

router = APIRouter()


@router.post("/login")
def login_user(request: LoginRequest):
    return login(request.username, request.password)


@router.post("/logout")
def logout_user(request: TokenRequest):
    return logout(request.token)


@router.post("/session")
def check_session(request: TokenRequest):
    session = get_session(request.token)
    if session:
        return {"valid": True, **session}
    return {"valid": False}


@router.get("/users")
def users():
    return get_users()


@router.post("/users")
def add_user(request: CreateUserRequest):
    return create_user(request.username, request.password, request.role, request.department)


@router.post("/users/{username}/deactivate")
def remove_user(username: str):
    return deactivate_user(username)


@router.get("/health")
def health():
    return {"status": "running", "message": "System is running successfully"}