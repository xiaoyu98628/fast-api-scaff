"""登录校验中间件：校验 Bearer token 的 JWT 有效性与 Redis 存在性。"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.api.public_paths import PUBLIC_AUTH_SKIP_PATHS
from app.core.errors import BizException
from app.enums.user_error_code import UserErrorCode
from app.utils.jwt import decode_access_token
from app.infrastructure.redis import AccessTokenStore


class AuthTokenMiddleware(BaseHTTPMiddleware):
    """为业务接口提供登录校验（登录/文档/健康检查路径放行）。"""

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
        return request.method == "OPTIONS" or request.url.path in PUBLIC_AUTH_SKIP_PATHS

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
