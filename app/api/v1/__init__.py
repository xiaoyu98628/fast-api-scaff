"""路由注册。"""

from fastapi import APIRouter

from app.api.v1 import test

api_router = APIRouter(prefix='/api/v1')

api_router.include_router(test.router)
