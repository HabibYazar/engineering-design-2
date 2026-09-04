"""Modül 14 — Kimlik doğrulama, oturum ve kullanıcı yönetimi endpoint'leri."""

from typing import List

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.system_users import (
    LoginRequest,
    LoginResponse,
    PermissionCheckResponse,
    RolePermissionItem,
    SessionResponse,
    SystemUserCreate,
    SystemUserResponse,
    SystemUserUpdate,
    TokenRequest,
)
from app.services import auth_service as service

router = APIRouter(prefix="/api/auth", tags=["Modül 14 — Kullanıcı ve Yetkilendirme"])


@router.post("/login", response_model=LoginResponse, summary="Sisteme giriş")
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    """Kullanıcı adı/parola doğrulanır ve oturum jetonu üretilir.

    Kullanıcı bulunamadığında da parola hatalı olduğunda da aynı 401 mesajı
    döner; farklı mesaj vermek mevcut kullanıcı adlarını ele verirdi.
    """
    return LoginResponse(**service.login(db, payload.username, payload.password))


@router.post("/logout", summary="Oturumu kapat")
def logout(payload: TokenRequest) -> dict:
    """Jetonu oturum deposundan siler."""
    return service.logout(payload.token)


@router.post("/session", response_model=SessionResponse, summary="Oturum doğrula")
def check_session(payload: TokenRequest) -> SessionResponse:
    """Jetonun geçerli olup olmadığını ve sahibinin yetkilerini döndürür."""
    return SessionResponse(**service.describe_session(payload.token))


@router.post(
    "/permissions/check",
    response_model=PermissionCheckResponse,
    summary="Belirli bir yetkiyi kontrol et",
)
def check_permission(
    payload: TokenRequest,
    permission: str = Query(examples=["manage_users"]),
) -> PermissionCheckResponse:
    """Arayüzün menü/buton gizlemesi için kullanılır."""
    return PermissionCheckResponse(**service.check_permission(payload.token, permission))


@router.get(
    "/roles",
    response_model=List[RolePermissionItem],
    summary="Tanımlı roller ve yetkileri",
)
def list_roles() -> List[RolePermissionItem]:
    """Rol seçim ekranlarının beslendiği liste."""
    return [RolePermissionItem(**row) for row in service.list_roles()]


@router.get(
    "/users",
    response_model=List[SystemUserResponse],
    summary="Kullanıcı listesi",
)
def list_users(
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> List[SystemUserResponse]:
    """Parola alanları hiçbir cevapta yer almaz."""
    return [
        SystemUserResponse(**service.to_response_dict(db, user))
        for user in service.list_users(db, include_inactive)
    ]


@router.post(
    "/users",
    response_model=SystemUserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Yeni kullanıcı oluştur",
)
def create_user(payload: SystemUserCreate, db: Session = Depends(get_db)) -> SystemUserResponse:
    """Kullanıcı adı tekrar ederse 409, rol tanımsızsa 422 döner."""
    user = service.create_user(db, payload)
    return SystemUserResponse(**service.to_response_dict(db, user))


@router.get(
    "/users/{user_id}",
    response_model=SystemUserResponse,
    summary="Tek kullanıcı bilgisi",
)
def get_user(user_id: int, db: Session = Depends(get_db)) -> SystemUserResponse:
    """Kullanıcı bulunamazsa 404 döner."""
    return SystemUserResponse(**service.to_response_dict(db, service.get_user(db, user_id)))


@router.patch(
    "/users/{user_id}",
    response_model=SystemUserResponse,
    summary="Kullanıcı bilgilerini güncelle",
)
def update_user(
    user_id: int, payload: SystemUserUpdate, db: Session = Depends(get_db)
) -> SystemUserResponse:
    """Parola bu endpoint ile değiştirilmez."""
    user = service.update_user(db, user_id, payload)
    return SystemUserResponse(**service.to_response_dict(db, user))


@router.delete(
    "/users/{user_id}",
    response_model=SystemUserResponse,
    summary="Kullanıcıyı devre dışı bırak",
)
def deactivate_user(user_id: int, db: Session = Depends(get_db)) -> SystemUserResponse:
    """Kayıt silinmez; ayrıca kullanıcının açık oturumları da düşürülür."""
    user = service.deactivate_user(db, user_id)
    return SystemUserResponse(**service.to_response_dict(db, user))
