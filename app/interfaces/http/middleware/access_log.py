import logging
from time import perf_counter

from starlette.middleware import Middleware
from starlette.routing import BaseRoute
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.interfaces.http.logging import HttpLogEvent

_ACCESS_LOGGER = logging.getLogger("app.interfaces.http.access")


class AccessLogMiddleware:
    """为每个进入请求上下文的 HTTP 请求记录一条访问日志。"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started_at = perf_counter()
        status_code: int | None = None
        failed = False

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code

            if message["type"] == "http.response.start":
                status_code = message["status"]

            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except BaseException:
            failed = True
            raise
        finally:
            effective_status = status_code if status_code is not None else 500
            details: dict[str, object] = {
                "method": scope["method"],
                "path": scope["path"],
                "route": _get_route_path(scope),
                "status_code": effective_status,
                "duration_ms": round((perf_counter() - started_at) * 1000, 3),
                "client_ip": _get_client_ip(scope),
            }

            if failed:
                details["failed"] = True

            _ACCESS_LOGGER.log(
                _get_log_level(effective_status, failed=failed),
                "HTTP request completed",
                extra={
                    "event": HttpLogEvent.REQUEST_COMPLETED,
                    "details": details,
                },
            )


def build_access_log_middleware() -> Middleware:
    return Middleware(AccessLogMiddleware)


def _get_route_path(scope: Scope) -> str | None:
    route = scope.get("route")
    if not isinstance(route, BaseRoute):
        return None

    path = getattr(route, "path", None)
    return path if isinstance(path, str) else None


def _get_client_ip(scope: Scope) -> str | None:
    client = scope.get("client")
    if client is None:
        return None

    host, _port = client
    return host


def _get_log_level(status_code: int, *, failed: bool) -> int:
    if failed or status_code >= 500:
        return logging.ERROR

    if status_code >= 400:
        return logging.WARNING

    return logging.INFO
