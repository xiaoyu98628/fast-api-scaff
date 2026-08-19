from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware import Middleware

from app.config.cors import CorsSettings


def build_cors_middleware(settings: CorsSettings) -> Middleware:
    """根据配置构建官方 CORS 中间件。"""
    return Middleware(
        CORSMiddleware,
        allow_origins=settings.allow_origins,
        allow_methods=settings.allow_methods,
        allow_headers=settings.allow_headers,
        allow_credentials=settings.allow_credentials,
        expose_headers=settings.expose_headers,
        max_age=settings.max_age,
    )
