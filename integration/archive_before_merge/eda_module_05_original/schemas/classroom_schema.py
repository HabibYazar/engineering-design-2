from pydantic import BaseModel

class ClassroomResponse(BaseModel):
    room: str
    capacity: int
    occupied: int