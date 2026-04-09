"""挂载所有 API 版本子路由（当前仅 v1）。"""

from fastapi import APIRouter

from app.interfaces.api.v1.router import v1_router

api_router = APIRouter(prefix="/api")

api_router.include_router(v1_router)