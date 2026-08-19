from fastapi import FastAPI

from app.bootstrap.routes import register_routes
from app.config.settings import Settings


def configure_http_app(app: FastAPI, settings: Settings) -> None:
    """装配 FastAPI 创建后需要注册的 HTTP 组件。"""
    register_routes(app)
