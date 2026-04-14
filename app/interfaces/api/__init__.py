"""HTTP API：按版本聚合路由，路径形如 ``/api/v1/...``。"""
from fastapi import FastAPI

from app.interfaces.api.router import api_router

def register_api_router(app: FastAPI) -> None:
    """注册 API 路由。"""

    app.include_router(api_router)

    @app.get(path="/health", summary="健康检测")
    async def health():
        return {"message": "Hello World"}