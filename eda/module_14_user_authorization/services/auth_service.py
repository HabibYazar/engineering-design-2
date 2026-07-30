from module_14_user_authorization.seed_data import users


def login(username, password):
    for user in users:
        if user.username == username and user.password == password:
            return {
                "message": "Login Successful",
                "role": user.role
            }
    return {
        "message": "Invalid username or password",
        "role": ""
    }


def get_users():
    return [
        {"username": user.username, "role": user.role}
        for user in users
    ]