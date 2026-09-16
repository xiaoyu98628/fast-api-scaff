"""在业务处理前执行 HTTP API 的客户端 IP 共享配额检查。"""

import logging
from ipaddress import IPv6Address, ip_address

from fastapi import Request
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.infrastructure.logging.record import log_extra, safe_exception_details
from app.infrastructure.rate_limit.contracts import RateLimitUnavailableError
from app.interfaces.http.shared.response.codes.error_code import ErrorCode
from app.interfaces.http.shared.response.factories.json import JsonResponseFactory
from app.runtime.container import ApplicationContainer

_LOGGER = logging.getLogger("app.interfaces.http.rate_limit")


class RateLimitMiddleware:
    """对所有 API 请求共享计数，保留非 HTTP 流量及预检请求。"""

    def __init__(self, app: ASGIApp, *, fail_open: bool = False) -> None:
        """保存下游应用和存储不可用时的策略，不创建连接。"""

        self.app = app
        self.fail_open = fail_open

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """执行准入检查；拒绝和依赖故障沿用统一响应与请求上下文。"""

        if not _should_limit(scope):
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        container: ApplicationContainer = request.app.state.container
        limiter = container.rate_limiter
        if limiter is None:
            raise RuntimeError("限流中间件启用但组件未装配")

        headers = {"Cache-Control": "no-store"}
        try:
            decision = await limiter.acquire(_client_identity(scope))
        except RateLimitUnavailableError as error:
            error_type, stacktrace = safe_exception_details(error)
            _LOGGER.warning(
                "HTTP rate limit storage unavailable",
                extra=log_extra(
                    "http.rate_limit.unavailable",
                    fail_open=self.fail_open,
                    error_type=error_type,
                    stacktrace=stacktrace,
                ),
            )
            if self.fail_open:
                await self.app(scope, receive, send)
                return
            code = ErrorCode.SERVICE_UNAVAILABLE
        else:
            if decision.allowed:
                await self.app(scope, receive, send)
                return
            code = ErrorCode.TOO_MANY_REQUESTS
            headers["Retry-After"] = str(decision.retry_after_seconds)

        factory: JsonResponseFactory = request.app.state.json_response_factory
        response = JSONResponse(
            status_code=code.status_code,
            content=factory.error(code).model_dump(mode="json"),
            headers=headers,
        )
        await response(scope, receive, send)


def _should_limit(scope: Scope) -> bool:
    """仅匹配 API 路径边界，并排除真正的 CORS 预检请求。"""

    if scope["type"] != "http":
        return False
    path = scope["path"]
    root_path = scope.get("root_path", "")
    # 与路由的挂载路径语义一致，避免部署前缀让 API 请求绕过限流。
    if root_path and path.startswith(root_path):
        relative_path = path[len(root_path) :]
        if not relative_path or relative_path.startswith("/"):
            path = relative_path
    if path != "/api" and not path.startswith("/api/"):
        return False
    headers = Headers(scope=scope)
    return not (scope["method"] == "OPTIONS" and "origin" in headers and "access-control-request-method" in headers)


def _client_identity(scope: Scope) -> str:
    """规范化服务器提供的客户端 IP，不直接信任任何转发头。"""

    client = scope.get("client")
    if client is None:
        return "ip:unknown"
    try:
        address = ip_address(client[0])
    except ValueError:
        # 非 IP 传输地址和缺失地址共享保守配额，避免任意标识形成独立桶。
        return "ip:unknown"
    if isinstance(address, IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return f"ip:{address.compressed}"
