from fastapi import FastAPI

from app.config.settings import Settings
from app.interfaces.http.response.json import ApiResponseFactory
from app.interfaces.http.routes.register import register_routes


def configure_http_app(app: FastAPI, settings: Settings) -> None:
    """装配 FastAPI 创建后需要注册的 HTTP 组件。"""
    responses = ApiResponseFactory.from_service_code(settings.app.service_code)
    register_routes(app, responses)
