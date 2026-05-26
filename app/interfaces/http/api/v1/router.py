from fastapi import APIRouter

from app.interfaces.http.api.v1.endpoints import user

api_v1_router = APIRouter(prefix="/v1")

api_v1_router.include_router(user.router)
