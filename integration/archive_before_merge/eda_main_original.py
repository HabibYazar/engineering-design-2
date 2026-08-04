from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from module_05_physical_resources.routes.classroom_routes import router as classroom_router
from module_05_physical_resources.routes.capacity_routes import router as capacity_router
from module_04_academic_staff.routes.staff_routes import router as staff_router
from module_14_user_authorization.routes.auth_routes import router as auth_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(staff_router)
app.include_router(classroom_router)
app.include_router(capacity_router)