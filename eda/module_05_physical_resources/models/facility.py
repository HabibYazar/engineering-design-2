class Facility:
    def __init__(self, id, name, type, department, capacity, occupied):
        self.id = id
        self.name = name           # "A101", "Lab-3", "Kütüphane Ana Salon" gibi
        self.type = type           # "classroom", "laboratory", "office", "library"
        self.department = department  # hangi bölüme/birime ait
        self.capacity = capacity
        self.occupied = occupied