"""聚合 v1 下各业务模块的 router（endpoints 包）。"""

from fastapi import APIRouter

from app.interfaces.api.v1.endpoints import test

v1_router = APIRouter(prefix="/v1")

v1_router.include_router(test.router)
