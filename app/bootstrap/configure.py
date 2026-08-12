from fastapi import FastAPI

from app.bootstrap.routes import register_routes


def configure_app(app: FastAPI) -> None:
    """集中注册应用的 HTTP 入口组件。"""
    register_routes(app)
