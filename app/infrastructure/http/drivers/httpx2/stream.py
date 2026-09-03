import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx2
from anyio import CancelScope, get_cancelled_exc_class

from app.infrastructure.http.contracts.request import HttpRequest
from app.infrastructure.http.contracts.response import HttpHeaders
from app.infrastructure.http.drivers.httpx2.pool import HttpPoolRuntime
from app.infrastructure.http.drivers.httpx2.request import build_httpx2_request_arguments
from app.infrastructure.http.errors import HttpPoolTimeoutError, HttpTimeoutError, HttpTransportError
from app.infrastructure.http.logging import HttpLogEvent, write_http_log


class Httpx2StreamResponse:
    """隐藏 HTTPX2 Response 的公共流式响应实现。"""

    def __init__(self, response: httpx2.Response) -> None:
        self._response = response

    @property
    def status_code(self) -> int:
        return self._response.status_code

    @property
    def headers(self) -> HttpHeaders:
        return tuple(self._response.headers.multi_items())

    async def aread(self) -> bytes:
        try:
            return await self._response.aread()
        except httpx2.TimeoutException as error:
            raise HttpTimeoutError("读取 HTTP 响应超时") from error
        except httpx2.RequestError as error:
            raise HttpTransportError("读取 HTTP 响应失败") from error

    async def aiter_bytes(self) -> AsyncIterator[bytes]:
        try:
            async for chunk in self._response.aiter_bytes():
                yield chunk
        except httpx2.TimeoutException as error:
            raise HttpTimeoutError("读取 HTTP 响应超时") from error
        except httpx2.RequestError as error:
            raise HttpTransportError("读取 HTTP 响应失败") from error

    async def aiter_text(self) -> AsyncIterator[str]:
        try:
            async for chunk in self._response.aiter_text():
                yield chunk
        except httpx2.TimeoutException as error:
            raise HttpTimeoutError("读取 HTTP 响应超时") from error
        except httpx2.RequestError as error:
            raise HttpTransportError("读取 HTTP 响应失败") from error


@asynccontextmanager
async def open_httpx2_stream(
    client: httpx2.AsyncClient,
    request: HttpRequest,
    runtime: HttpPoolRuntime,
) -> AsyncIterator[Httpx2StreamResponse]:
    stream_context = client.stream(**build_httpx2_request_arguments(request))
    if runtime.acquire():
        write_http_log(
            logging.WARNING,
            HttpLogEvent.POOL_PRESSURE,
            "Outbound HTTP connection pool is under pressure",
            request,
            **runtime.log_details(),
        )
    entered = False

    try:
        response = await stream_context.__aenter__()
        entered = True
        yield Httpx2StreamResponse(response)
    except get_cancelled_exc_class():
        runtime.cancelled += 1
        raise
    except httpx2.PoolTimeout as error:
        runtime.pool_timeout += 1
        write_http_log(
            logging.WARNING,
            HttpLogEvent.POOL_TIMEOUT,
            "Outbound HTTP connection pool timed out",
            request,
            client_id=f"{id(client):#x}",
            **runtime.log_details(),
        )
        raise HttpPoolTimeoutError("等待 HTTP 连接池容量超时") from error
    except httpx2.TimeoutException as error:
        raise HttpTimeoutError("建立 HTTP 响应超时") from error
    except httpx2.RequestError as error:
        raise HttpTransportError("建立 HTTP 响应失败") from error
    finally:
        error_type, error, traceback = sys.exc_info()

        with CancelScope(shield=True):
            try:
                if entered:
                    await stream_context.__aexit__(error_type, error, traceback)
            finally:
                runtime.release()
