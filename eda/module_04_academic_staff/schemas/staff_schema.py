from pydantic import BaseModel


class StaffResponse(BaseModel):

    id: int
    name: str
    publication: int
    citation: int