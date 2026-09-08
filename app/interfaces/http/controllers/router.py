"""汇总应用全部版本化 API 路由。"""

from fastapi import APIRouter

from app.interfaces.http.controllers.v1.router import api_v1_router

api_router = APIRouter(prefix="/api")

# 版本前缀由下级 Router 负责，便于未来并列装配其他 API 版本。
api_router.include_router(api_v1_router)
