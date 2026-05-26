from fastapi import APIRouter

from app.interfaces.http.api.v1.router import api_v1_router

api_router = APIRouter(prefix="/api")

api_router.include_router(api_v1_router)
