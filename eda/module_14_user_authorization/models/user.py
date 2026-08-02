class User:
    def __init__(self, id, username, password, role, department=None, active=True):
        self.id = id
        self.username = username
        self.password = password
        self.role = role            # "Admin", "Dekan", "Bölüm Başkanı", "Öğretim Üyesi"
        self.department = department
        self.active = active