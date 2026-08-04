"""Modül 14 — Kullanıcı, oturum ve yetki şemaları."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    """Giriş isteği."""

    username: str = Field(min_length=2, max_length=80, examples=["admin"])
    password: str = Field(min_length=4, max_length=200, examples=["demo1234"])


class TokenRequest(BaseModel):
    """Oturum jetonu ile yapılan istekler."""

    token: str = Field(min_length=8, examples=["3f2c9b8a-1d4e-4a77-9c2b-8e1f0a5d6c73"])


class LoginResponse(BaseModel):
    """Başarılı giriş cevabı.

    Parola veya özet bilgisi asla döndürülmez.
    """

    token: str = Field(examples=["3f2c9b8a-1d4e-4a77-9c2b-8e1f0a5d6c73"])
    username: str = Field(examples=["admin"])
    full_name: str = Field(examples=["Sistem Yöneticisi"])
    role: str = Field(examples=["Admin"])
    faculty_id: Optional[int] = Field(default=None, examples=[None])
    faculty_name: Optional[str] = Field(default=None, examples=[None])
    department_id: Optional[int] = Field(default=None, examples=[None])
    department_name: Optional[str] = Field(default=None, examples=[None])
    permissions: List[str] = Field(examples=[["view_all", "edit_all", "manage_users"]])
    message: str = Field(examples=["Giriş başarılı."])


class SessionResponse(BaseModel):
    """Oturum doğrulama cevabı."""

    is_valid: bool = Field(examples=[True])
    username: Optional[str] = Field(default=None, examples=["admin"])
    role: Optional[str] = Field(default=None, examples=["Admin"])
    permissions: List[str] = Field(default_factory=list)
    issued_at: Optional[datetime] = None


class PermissionCheckResponse(BaseModel):
    """Belirli bir yetkinin kontrol sonucu."""

    permission: str = Field(examples=["manage_users"])
    granted: bool = Field(examples=[True])
    role: Optional[str] = Field(default=None, examples=["Admin"])


class SystemUserCreate(BaseModel):
    """Yeni kullanıcı kaydı."""

    username: str = Field(min_length=2, max_length=80, examples=["dekan.muh"])
    full_name: str = Field(min_length=2, max_length=200, examples=["Mühendislik Dekanı"])
    password: str = Field(min_length=4, max_length=200, examples=["demo1234"])
    role: str = Field(examples=["Dekan"])
    faculty_id: Optional[int] = Field(default=None, ge=1, examples=[1])
    department_id: Optional[int] = Field(default=None, ge=1, examples=[None])


class SystemUserUpdate(BaseModel):
    """Kullanıcı güncelleme; parola ayrı endpoint ile değiştirilir."""

    full_name: Optional[str] = Field(default=None, min_length=2, max_length=200)
    role: Optional[str] = None
    faculty_id: Optional[int] = Field(default=None, ge=1)
    department_id: Optional[int] = Field(default=None, ge=1)


class SystemUserResponse(BaseModel):
    """Kullanıcı bilgisi; parola alanları hiçbir zaman yer almaz."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: str
    role: str
    faculty_id: Optional[int] = None
    faculty_name: Optional[str] = None
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    permissions: List[str]
    is_active: bool
    last_login_at: Optional[datetime] = None


class RolePermissionItem(BaseModel):
    """Rol tanımı ve yetkileri."""

    role: str = Field(examples=["Dekan"])
    permissions: List[str] = Field(examples=[["view_all", "edit_faculty"]])
    description: str = Field(examples=["Bağlı olduğu fakültenin tüm verilerini görür."])
