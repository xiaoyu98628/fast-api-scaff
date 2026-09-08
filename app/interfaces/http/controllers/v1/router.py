"""汇总第一版 API 的各业务控制器。"""

from fastapi import APIRouter

from app.interfaces.http.controllers.v1.auth.router import router as auth_router
from app.interfaces.http.controllers.v1.users.router import router as users_router

api_v1_router = APIRouter(prefix="/v1")

# 各限界上下文维护自己的前缀、标签和 OpenAPI 响应声明。
api_v1_router.include_router(users_router)
api_v1_router.include_router(auth_router)
