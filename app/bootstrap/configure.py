from fastapi import FastAPI

from app.config.settings import Settings
from app.interfaces.http.exceptions.register import register_exception_handlers
from app.interfaces.http.routes.register import register_routes
from app.interfaces.http.shared.response.codes.builder import ResponseCodeBuilder
from app.interfaces.http.shared.response.factory import JsonResponseFactory


def configure_http_app(app: FastAPI, settings: Settings) -> None:
    """装配 FastAPI 创建后需要注册的 HTTP 组件。"""
    app.state.json_response_factory = JsonResponseFactory(
        code_builder=ResponseCodeBuilder(settings.app.service_code),
    )
    register_exception_handlers(app)
    register_routes(app)
