import logging
from asyncio import CancelledError
from time import perf_counter

from starlette.middleware import Middleware
from starlette.routing import BaseRoute
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.infrastructure.logging.record import log_extra
from app.interfaces.http.logging import HttpLogEvent

_ACCESS_LOGGER = logging.getLogger("app.interfaces.http.access")


class AccessLogMiddleware:
    """为每个进入请求上下文的 HTTP 请求记录一条访问日志。"""

    def __init__(self, app: ASGIApp, *, exclude_routes: frozenset[str] = frozenset()) -> None:
        self.app = app
        self._exclude_routes = exclude_routes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started_at = perf_counter()
        status_code: int | None = None
        failure_type: str | None = None
        cancelled = False
        completed = False

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code

            if message["type"] == "http.response.start":
                status_code = message["status"]

            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except CancelledError:
            failure_type = "CancelledError"
            cancelled = True
            raise
        except Exception as exception:
            failure_type = type(exception).__name__
            raise
        else:
            completed = True
        finally:
            self._write_log(
                scope,
                status_code=status_code,
                started_at=started_at,
                failure_type=failure_type,
                cancelled=cancelled,
                completed=completed,
            )

    def _write_log(
        self,
        scope: Scope,
        *,
        status_code: int | None,
        started_at: float,
        failure_type: str | None,
        cancelled: bool,
        completed: bool,
    ) -> None:
        route = _get_route_path(scope)
        failed = not completed
        effective_status = status_code if status_code is not None else (499 if cancelled else 500)

        if route in self._exclude_routes and effective_status < 400 and not failed:
            return

        details: dict[str, object] = {
            "method": scope["method"],
            "route": route,
            "status_code": effective_status,
            "duration_ms": round((perf_counter() - started_at) * 1000, 3),
            "client_ip": _get_client_ip(scope),
        }

        if failed:
            details["failed"] = True

        if failure_type is not None:
            details["failure_type"] = failure_type

        _ACCESS_LOGGER.log(
            _get_log_level(effective_status, failed=failed, cancelled=cancelled),
            "HTTP request completed",
            extra=log_extra(HttpLogEvent.REQUEST_COMPLETED, **details),
        )


def build_access_log_middleware(*, exclude_routes: frozenset[str]) -> Middleware:
    return Middleware(AccessLogMiddleware, exclude_routes=exclude_routes)


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


def _get_log_level(status_code: int, *, failed: bool, cancelled: bool) -> int:
    if cancelled:
        return logging.WARNING

    if failed or status_code >= 500:
        return logging.ERROR

    if status_code >= 400:
        return logging.WARNING

    return logging.INFO
