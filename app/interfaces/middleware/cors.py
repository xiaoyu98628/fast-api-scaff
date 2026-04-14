import re
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response, PlainTextResponse

from config.config import get_config


class CorsMiddleware(BaseHTTPMiddleware):
    """跨域处理"""

    def __init__(self, app):
        super().__init__(app)
        self.cors_settings = get_config().cors

    async def dispatch(self, request, call_next):
        origin = request.headers.get("origin")

        # 判断是否允许该 origin
        allow_origin = self._get_allow_origin(origin)

        # 处理预检请求
        if request.method == "OPTIONS":
            response = PlainTextResponse("OK", status_code=200)
        else:
            response: Response = await call_next(request)

        # ===== 设置 CORS 头 =====

        if allow_origin:
            response.headers["Access-Control-Allow-Origin"] = allow_origin
            response.headers["Vary"] = "Origin"

        # 允许方法
        response.headers["Access-Control-Allow-Methods"] = ",".join(
            self.cors_settings.allow_methods
        )

        # 允许请求头
        response.headers["Access-Control-Allow-Headers"] = ",".join(
            self.cors_settings.allow_headers
        )

        # 预检缓存
        response.headers["Access-Control-Max-Age"] = str(
            self.cors_settings.max_age
        )

        # 是否允许 cookie
        if self.cors_settings.allow_credentials:
            response.headers["Access-Control-Allow-Credentials"] = "true"

        # 允许前端读取的响应头
        if self.cors_settings.exposed_headers:
            response.headers["Access-Control-Expose-Headers"] = ",".join(
                self.cors_settings.exposed_headers
            )

        return response

    def _get_allow_origin(self, origin: Optional[str]) -> Optional[str]:
        """
        判断 origin 是否允许
        优先级：
        1. allow_origins
        2. allowed_origins_patterns
        """

        if not origin:
            return None


        # 1️⃣ 精确匹配
        if "*" in self.cors_settings.allow_origins:
            # ⚠️ 注意：不能直接返回 "*"（带 credentials 时会报错）
            return origin

        if origin in self.cors_settings.allow_origins:
            return origin

        # 2️⃣ 正则匹配
        for pattern in self.cors_settings.allowed_origins_patterns:
            if re.match(pattern, origin):
                return origin

        return None