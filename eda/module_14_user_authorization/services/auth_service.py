import uuid
from seed_data import users

# Basit bellek-içi oturum deposu (gerçek sistemde Redis/DB olurdu)
active_sessions = {}

# Hangi rol hangi yetkilere sahip
ROLE_PERMISSIONS = {
    "Admin": ["view_all", "edit_all", "manage_users"],
    "Dekan": ["view_all", "edit_faculty"],
    "Bölüm Başkanı": ["view_department", "edit_department"],
    "Öğretim Üyesi": ["view_own"],
}


def login(username, password):
    for user in users:
        if user.username == username and user.password == password:
            if not user.active:
                return {"message": "Hesap devre dışı", "role": "", "token": None}

            token = str(uuid.uuid4())
            active_sessions[token] = {
                "user_id": user.id,
                "username": user.username,
                "role": user.role,
                "department": user.department
            }
            return {
                "message": "Login Successful",
                "role": user.role,
                "department": user.department,
                "token": token
            }
    return {"message": "Invalid username or password", "role": "", "token": None}


def logout(token):
    if token in active_sessions:
        del active_sessions[token]
        return {"message": "Logout successful"}
    return {"message": "Invalid session"}


def get_session(token):
    return active_sessions.get(token)


def has_permission(token, permission):
    session = get_session(token)
    if not session:
        return False
    role = session["role"]
    return permission in ROLE_PERMISSIONS.get(role, [])


def get_users():
    return [
        {"username": u.username, "role": u.role, "department": u.department, "active": u.active}
        for u in users
    ]


def create_user(username, password, role, department=None):
    new_id = max(u.id for u in users) + 1
    from module_14_user_authorization.models.user import User
    new_user = User(new_id, username, password, role, department, True)
    users.append(new_user)
    return {"message": "Kullanıcı oluşturuldu", "username": username}


def deactivate_user(username):
    for user in users:
        if user.username == username:
            user.active = False
            return {"message": f"{username} devre dışı bırakıldı"}
    return {"message": "Kullanıcı bulunamadı"}