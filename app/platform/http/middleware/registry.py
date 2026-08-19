from starlette.middleware import Middleware

from app.config.settings import Settings
from app.platform.http.middleware.cors import build_cors_middleware


def build_http_middlewares(settings: Settings) -> list[Middleware]:
    """按从外到内的顺序构建应用 HTTP 中间件。"""
    middlewares: list[Middleware] = []

    if settings.cors.enabled:
        middlewares.append(build_cors_middleware(settings.cors))

    return middlewares
