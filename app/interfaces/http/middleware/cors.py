"""跨域处理。"""

import re

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

from config.config import config
from config.cors import CorsConfig


class CorsMiddleware(BaseHTTPMiddleware):
    """为响应附加 CORS 头；OPTIONS 预检直接返回 200。"""

    async def dispatch(self, request: Request, call_next) -> Response:
        cors_settings = config().cors
        origin = request.headers.get("origin")
        allow_origin = _resolve_allow_origin(origin, cors_settings)

        if request.method == "OPTIONS":
            response: Response = PlainTextResponse("OK", status_code=200)
        else:
            response = await call_next(request)

        if allow_origin:
            response.headers["Access-Control-Allow-Origin"] = allow_origin
            response.headers["Vary"] = "Origin"

        response.headers["Access-Control-Allow-Methods"] = ",".join(cors_settings.allow_methods)
        response.headers["Access-Control-Allow-Headers"] = ",".join(cors_settings.allow_headers)
        response.headers["Access-Control-Max-Age"] = str(cors_settings.max_age)

        if cors_settings.allow_credentials:
            response.headers["Access-Control-Allow-Credentials"] = "true"

        if cors_settings.exposed_headers:
            response.headers["Access-Control-Expose-Headers"] = ",".join(cors_settings.exposed_headers)

        return response


def _resolve_allow_origin(origin: str | None, cors_settings: CorsConfig) -> str | None:
    if not origin:
        return None

    if "*" in cors_settings.allow_origins:
        return origin

    if origin in cors_settings.allow_origins:
        return origin

    for pattern in cors_settings.allowed_origins_patterns:
        if re.match(pattern, origin):
            return origin

    return None
