import logging
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from time import perf_counter

from anyio import get_cancelled_exc_class

from app.infrastructure.http.contracts.driver import HttpDriver
from app.infrastructure.http.contracts.request import HttpRequest
from app.infrastructure.http.contracts.response import HttpResponse
from app.infrastructure.http.contracts.stream import HttpStreamResponse
from app.infrastructure.http.errors import HttpError
from app.infrastructure.http.logging import HttpLogEvent, write_http_log


class ManagedHttpClient:
    """统一驱动调用、耗时和结构化日志的公共 HTTP 客户端。"""

    def __init__(self, driver: HttpDriver) -> None:
        self._driver = driver

    async def request(self, request: HttpRequest) -> HttpResponse:
        started_at = perf_counter()

        try:
            response = await self._driver.request(request)
        except get_cancelled_exc_class():
            write_http_log(
                logging.INFO,
                HttpLogEvent.REQUEST_CANCELLED,
                "Outbound HTTP request cancelled",
                request,
                duration_ms=_duration_ms(started_at),
            )
            raise
        except Exception as error:
            write_http_log(
                logging.ERROR,
                HttpLogEvent.REQUEST_FAILED,
                "Outbound HTTP request failed",
                request,
                duration_ms=_duration_ms(started_at),
                error_type=type(error).__name__,
            )
            raise

        write_http_log(
            logging.INFO,
            HttpLogEvent.REQUEST_COMPLETED,
            "Outbound HTTP request completed",
            request,
            status_code=response.status_code,
            duration_ms=_duration_ms(started_at),
            response_size=len(response.content),
        )
        return response

    def stream(self, request: HttpRequest) -> AbstractAsyncContextManager[HttpStreamResponse]:
        return self._stream(request)

    @asynccontextmanager
    async def _stream(self, request: HttpRequest) -> AsyncIterator[HttpStreamResponse]:
        started_at = perf_counter()
        status_code: int | None = None
        caller_failed = False

        try:
            async with self._driver.stream(request) as response:
                status_code = response.status_code
                write_http_log(
                    logging.INFO,
                    HttpLogEvent.STREAM_CONNECTED,
                    "Outbound HTTP stream connected",
                    request,
                    status_code=status_code,
                )
                try:
                    yield response
                except Exception as error:
                    caller_failed = not isinstance(error, HttpError)
                    raise
        except get_cancelled_exc_class():
            write_http_log(
                logging.INFO,
                HttpLogEvent.STREAM_CANCELLED,
                "Outbound HTTP stream cancelled",
                request,
                status_code=status_code,
                duration_ms=_duration_ms(started_at),
            )
            raise
        except Exception as error:
            if not caller_failed:
                write_http_log(
                    logging.ERROR,
                    HttpLogEvent.STREAM_FAILED,
                    "Outbound HTTP stream failed",
                    request,
                    status_code=status_code,
                    duration_ms=_duration_ms(started_at),
                    error_type=type(error).__name__,
                )
            raise

        write_http_log(
            logging.INFO,
            HttpLogEvent.STREAM_COMPLETED,
            "Outbound HTTP stream completed",
            request,
            status_code=status_code,
            duration_ms=_duration_ms(started_at),
        )


def _duration_ms(started_at: float) -> float:
    return round((perf_counter() - started_at) * 1000, 3)
