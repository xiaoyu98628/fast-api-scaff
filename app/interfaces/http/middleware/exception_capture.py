import logging

from fastapi import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.infrastructure.logging.record import log_extra
from app.interfaces.http.exceptions.handlers import render_exception
from app.interfaces.http.logging import HttpLogEvent

_EXCEPTION_LOGGER = logging.getLogger("app.interfaces.http.exception")


class ExceptionCaptureMiddleware:
    """在请求上下文退出前转换中间件和请求处理异常。"""

    def __init__(self, app: ASGIApp, *, debug: bool = False) -> None:
        self.app = app
        self.debug = debug

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal response_started

            if message["type"] == "http.response.start":
                response_started = True

            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exception:
            if self.debug:
                raise

            _EXCEPTION_LOGGER.exception(
                "Unhandled HTTP request exception",
                extra=log_extra(
                    HttpLogEvent.UNHANDLED_EXCEPTION,
                    method=scope["method"],
                    response_started=response_started,
                ),
            )

            if response_started:
                raise

            response: Response = await render_exception(Request(scope), exception)
            await response(scope, receive, send_wrapper)
