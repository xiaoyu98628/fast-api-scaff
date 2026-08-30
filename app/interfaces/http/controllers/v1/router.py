from fastapi import APIRouter

from app.interfaces.http.controllers.v1.users.router import router as users_router

api_v1_router = APIRouter(prefix="/v1")

api_v1_router.include_router(users_router)
