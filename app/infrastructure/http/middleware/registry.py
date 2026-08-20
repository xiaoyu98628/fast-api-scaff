from starlette.middleware import Middleware

from app.config.settings import Settings
from app.infrastructure.http.middleware.cors import build_cors_middleware
from app.infrastructure.http.middleware.request_id import build_request_id_middleware


def build_http_middlewares(settings: Settings) -> list[Middleware]:
    """按从外到内的顺序构建应用 HTTP 中间件。"""
    return [
        build_request_id_middleware(),
        build_cors_middleware(settings.cors),
    ]
