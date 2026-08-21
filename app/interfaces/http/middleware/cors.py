from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware import Middleware
from starlette_context.header_keys import HeaderKeys

from app.config.cors import CorsSettings


def build_cors_middleware(settings: CorsSettings) -> Middleware:
    """根据配置构建官方 CORS 中间件。"""
    request_id_header = HeaderKeys.request_id.value
    expose_headers = [
        request_id_header,
        *(header for header in settings.expose_headers if header.lower() != request_id_header.lower()),
    ]

    return Middleware(
        CORSMiddleware,
        allow_origins=settings.allow_origins,
        allow_methods=settings.allow_methods,
        allow_headers=settings.allow_headers,
        allow_credentials=settings.allow_credentials,
        expose_headers=expose_headers,
        max_age=settings.max_age,
    )
