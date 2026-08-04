"""Modül 14 — Kimlik doğrulama, oturum ve yetki servisi.

Entegrasyon notu: Eda'nın `auth_service.py` dosyasındaki akış (login → token →
session → permission) korundu. İki nokta güçlendirildi:

1) Parolalar düz metin karşılaştırılıyordu. Artık PBKDF2-HMAC-SHA256 ile
   saltlanmış özet karşılaştırılıyor ve karşılaştırma `compare_digest` ile
   sabit sürede yapılıyor.
2) Kullanıcı adı bulunamadığında ve parola yanlış olduğunda aynı mesaj dönüyor;
   farklı mesaj vermek hangi kullanıcı adlarının var olduğunu ele verir.

UYARI (bilerek yapılan sadeleştirme): Oturumlar süreç belleğinde tutulur.
Sunucu yeniden başlatıldığında tüm oturumlar düşer ve birden fazla worker ile
çalıştırıldığında oturumlar paylaşılmaz. Bu, demo kapsamı için kabul edilmiş bir
sınırlamadır ve docs/KNOWN_LIMITATIONS.md dosyasında da belirtilmiştir.
"""

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Department, Faculty, SystemUser
from app.models.system_user import ROLE_PERMISSIONS
from app.schemas.system_users import SystemUserCreate, SystemUserUpdate

# PBKDF2 tur sayısı. Yüksek tutmak parola kırmayı yavaşlatır; demo başlangıç
# süresini gözle görülür biçimde uzatmayacak bir değer seçildi.
PBKDF2_ITERATIONS = 120_000

# Süreç içi oturum deposu: token -> oturum bilgisi.
_active_sessions: Dict[str, dict] = {}

# Rol açıklamaları; arayüzde rol seçiminde gösteriliyor.
ROLE_DESCRIPTIONS = {
    "Admin": "Tüm kurum verilerini görür ve kullanıcı yönetimi yapar.",
    "Dekan": "Bağlı olduğu fakültenin tüm verilerini görür ve düzenler.",
    "Bölüm Başkanı": "Bağlı olduğu bölümün verilerini görür ve düzenler.",
    "Öğretim Üyesi": "Yalnızca kendi kayıtlarını görüntüler.",
}


# ----------------------------------------------------------------------------
# Parola işlemleri
# ----------------------------------------------------------------------------


def hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    """Parolayı saltlayarak özetler; (salt, hash) döner."""
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), PBKDF2_ITERATIONS
    )
    return salt, digest.hex()


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    """Parolayı sabit sürede karşılaştırır (zamanlama saldırısına karşı)."""
    _, candidate = hash_password(password, salt)
    return hmac.compare_digest(candidate, expected_hash)


# ----------------------------------------------------------------------------
# Yardımcılar
# ----------------------------------------------------------------------------


def _scope_names(db: Session, user: SystemUser) -> tuple[Optional[str], Optional[str]]:
    """Kullanıcının fakülte ve bölüm adlarını çözer."""
    faculty_name = None
    department_name = None
    if user.faculty_id:
        faculty = db.get(Faculty, user.faculty_id)
        faculty_name = faculty.name if faculty else None
    if user.department_id:
        department = db.get(Department, user.department_id)
        department_name = department.name if department else None
        # Bölüm verildiyse fakülte adı bölümden de türetilebilir; kullanıcıda
        # ayrıca fakülte yazılmamışsa boş bırakmak yerine bölümün fakültesi alınır.
        if faculty_name is None and department and department.faculty:
            faculty_name = department.faculty.name
    return faculty_name, department_name


def to_response_dict(db: Session, user: SystemUser) -> dict:
    """Kullanıcıyı API cevabına çevirir; parola alanları dışarıda bırakılır."""
    faculty_name, department_name = _scope_names(db, user)
    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "role": user.role,
        "faculty_id": user.faculty_id,
        "faculty_name": faculty_name,
        "department_id": user.department_id,
        "department_name": department_name,
        "permissions": user.permissions,
        "is_active": user.is_active,
        "last_login_at": user.last_login_at,
    }


def _validate_role(role: str) -> None:
    if role not in ROLE_PERMISSIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"'{role}' tanımlı bir rol değil. "
                f"Kullanılabilir roller: {', '.join(ROLE_PERMISSIONS)}."
            ),
        )


# ----------------------------------------------------------------------------
# Oturum akışı
# ----------------------------------------------------------------------------


def login(db: Session, username: str, password: str) -> dict:
    """Kullanıcı adı ve parolayı doğrular, oturum jetonu üretir."""
    user = db.execute(
        select(SystemUser).where(SystemUser.username == username)
    ).scalars().first()

    # Kullanıcı yoksa da parola yanlışsa da aynı 401 mesajı dönüyor.
    if user is None or not verify_password(password, user.password_salt, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Kullanıcı adı veya parola hatalı.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu hesap devre dışı bırakılmış.",
        )

    token = str(uuid.uuid4())
    faculty_name, department_name = _scope_names(db, user)
    _active_sessions[token] = {
        "user_id": user.id,
        "username": user.username,
        "role": user.role,
        "faculty_id": user.faculty_id,
        "department_id": user.department_id,
        "issued_at": datetime.now(),
    }

    user.last_login_at = datetime.now()
    db.commit()

    return {
        "token": token,
        "username": user.username,
        "full_name": user.full_name,
        "role": user.role,
        "faculty_id": user.faculty_id,
        "faculty_name": faculty_name,
        "department_id": user.department_id,
        "department_name": department_name,
        "permissions": user.permissions,
        "message": "Giriş başarılı.",
    }


def logout(token: str) -> dict:
    """Oturumu kapatır. Geçersiz jeton için de 404 döner ki durum net olsun."""
    if token not in _active_sessions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bu jetona ait açık oturum bulunamadı.",
        )
    del _active_sessions[token]
    return {"message": "Oturum kapatıldı."}


def get_session(token: str) -> Optional[dict]:
    """Jetona ait oturumu döndürür; yoksa None."""
    return _active_sessions.get(token)


def describe_session(token: str) -> dict:
    """Oturum doğrulama cevabı üretir."""
    session = get_session(token)
    if session is None:
        return {"is_valid": False, "username": None, "role": None, "permissions": []}
    return {
        "is_valid": True,
        "username": session["username"],
        "role": session["role"],
        "permissions": ROLE_PERMISSIONS.get(session["role"], []),
        "issued_at": session["issued_at"],
    }


def check_permission(token: str, permission: str) -> dict:
    """Jetonun belirtilen yetkiye sahip olup olmadığını söyler."""
    session = get_session(token)
    if session is None:
        return {"permission": permission, "granted": False, "role": None}
    role = session["role"]
    return {
        "permission": permission,
        "granted": permission in ROLE_PERMISSIONS.get(role, []),
        "role": role,
    }


def active_session_count() -> int:
    """Açık oturum sayısı (izleme amaçlı)."""
    return len(_active_sessions)


# ----------------------------------------------------------------------------
# Kullanıcı yönetimi
# ----------------------------------------------------------------------------


def list_users(db: Session, include_inactive: bool = False) -> List[SystemUser]:
    """Kullanıcı listesi."""
    query = select(SystemUser)
    if not include_inactive:
        query = query.where(SystemUser.is_active.is_(True))
    return list(db.execute(query.order_by(SystemUser.username)).scalars())


def get_user(db: Session, user_id: int) -> SystemUser:
    """Tek kullanıcı; bulunamazsa 404."""
    user = db.get(SystemUser, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{user_id} numaralı kullanıcı bulunamadı.",
        )
    return user


def create_user(db: Session, payload: SystemUserCreate) -> SystemUser:
    """Yeni kullanıcı; kullanıcı adı tekrarında 409."""
    _validate_role(payload.role)

    existing = db.execute(
        select(SystemUser).where(SystemUser.username == payload.username)
    ).scalars().first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"'{payload.username}' kullanıcı adı zaten kayıtlı.",
        )

    if payload.faculty_id is not None and db.get(Faculty, payload.faculty_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{payload.faculty_id} numaralı fakülte bulunamadı.",
        )
    if payload.department_id is not None and db.get(Department, payload.department_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{payload.department_id} numaralı bölüm bulunamadı.",
        )

    salt, digest = hash_password(payload.password)
    user = SystemUser(
        username=payload.username,
        full_name=payload.full_name,
        password_salt=salt,
        password_hash=digest,
        role=payload.role,
        faculty_id=payload.faculty_id,
        department_id=payload.department_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_user(db: Session, user_id: int, payload: SystemUserUpdate) -> SystemUser:
    """Kullanıcı bilgilerini günceller."""
    user = get_user(db, user_id)
    data = payload.model_dump(exclude_unset=True)
    if "role" in data:
        _validate_role(data["role"])
    for field, value in data.items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user


def deactivate_user(db: Session, user_id: int) -> SystemUser:
    """Kullanıcıyı pasifleştirir ve açık oturumlarını düşürür.

    Oturum düşürülmezse devre dışı bırakılan kullanıcı elindeki jetonla
    çalışmaya devam ederdi.
    """
    user = get_user(db, user_id)
    user.is_active = False
    db.commit()
    db.refresh(user)

    for token, session in list(_active_sessions.items()):
        if session["user_id"] == user.id:
            del _active_sessions[token]
    return user


def list_roles() -> List[dict]:
    """Tanımlı roller ve yetkileri."""
    return [
        {
            "role": role,
            "permissions": permissions,
            "description": ROLE_DESCRIPTIONS.get(role, ""),
        }
        for role, permissions in ROLE_PERMISSIONS.items()
    ]
