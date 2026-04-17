"""登录校验中间件：校验 Bearer token 的 JWT 有效性与 Redis 存在性。"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.application.user.errors import UserErrorCode
from app.common.errors import BizException
from app.common.utils.jwt import decode_access_token
from app.infrastructure.redis.token_store import AccessTokenStore


class AuthTokenMiddleware(BaseHTTPMiddleware):
    """为业务接口提供登录校验（登录/文档/健康检查路径放行）。"""

    _public_paths = {
        "/docs",
        "/openapi.json",
        "/redoc",
        "/api/v1/auth/login",
        "/api/v1/test/health",
        "/api/v1/test/db-health",
        "/api/v1/test/redis-health",
    }

    def __init__(self, app):
        super().__init__(app)
        self._token_store = AccessTokenStore()

    @staticmethod
    def _extract_bearer_token(request: Request) -> str:
        authorization = request.headers.get("Authorization", "")
        if not authorization:
            raise BizException(UserErrorCode.TOKEN_MISSING)
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise BizException(UserErrorCode.TOKEN_INVALID)
        return token.strip()

    def _should_skip(self, request: Request) -> bool:
        return request.url.path in self._public_paths

    async def dispatch(self, request: Request, call_next):
        if self._should_skip(request):
            return await call_next(request)

        token = self._extract_bearer_token(request)
        try:
            payload = decode_access_token(token)
        except Exception as exc:
            raise BizException(UserErrorCode.TOKEN_INVALID) from exc

        if not await self._token_store.exists(token):
            raise BizException(UserErrorCode.TOKEN_INVALID)

        request.state.user_id = payload.get("sub")
        request.state.username = payload.get("username")
        return await call_next(request)
