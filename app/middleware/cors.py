"""跨域处理。"""

import re
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse, Response

from config.config import get_config


class CorsMiddleware(BaseHTTPMiddleware):
    """跨域处理。"""

    def __init__(self, app):
        super().__init__(app)
        self.cors_settings = get_config().cors

    async def dispatch(self, request, call_next):
        origin = request.headers.get("origin")
        allow_origin = self._get_allow_origin(origin)

        if request.method == "OPTIONS":
            response = PlainTextResponse("OK", status_code=200)
        else:
            response: Response = await call_next(request)

        if allow_origin:
            response.headers["Access-Control-Allow-Origin"] = allow_origin
            response.headers["Vary"] = "Origin"

        response.headers["Access-Control-Allow-Methods"] = ",".join(self.cors_settings.allow_methods)
        response.headers["Access-Control-Allow-Headers"] = ",".join(self.cors_settings.allow_headers)
        response.headers["Access-Control-Max-Age"] = str(self.cors_settings.max_age)

        if self.cors_settings.allow_credentials:
            response.headers["Access-Control-Allow-Credentials"] = "true"

        if self.cors_settings.exposed_headers:
            response.headers["Access-Control-Expose-Headers"] = ",".join(self.cors_settings.exposed_headers)

        return response

    def _get_allow_origin(self, origin: Optional[str]) -> Optional[str]:
        if not origin:
            return None

        if "*" in self.cors_settings.allow_origins:
            return origin

        if origin in self.cors_settings.allow_origins:
            return origin

        for pattern in self.cors_settings.allowed_origins_patterns:
            if re.match(pattern, origin):
                return origin

        return None
