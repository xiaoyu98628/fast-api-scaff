"""适配 HTTPX2 流式响应、异常分类和连接池诊断。"""

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
        """接管由流式请求上下文约束生命周期的响应对象。"""

        self._response = response

    @property
    def status_code(self) -> int:
        """返回已经建立响应的 HTTP 状态码。"""

        return self._response.status_code

    @property
    def headers(self) -> HttpHeaders:
        """返回保留重复响应头的不可变键值序列。"""

        return tuple(self._response.headers.multi_items())

    async def aread(self) -> bytes:
        """读取完整流，并把 HTTPX2 异常转换为公共错误。"""

        try:
            return await self._response.aread()
        except httpx2.TimeoutException as error:
            raise HttpTimeoutError("读取 HTTP 响应超时") from error
        except httpx2.RequestError as error:
            raise HttpTransportError("读取 HTTP 响应失败") from error

    async def aiter_bytes(self) -> AsyncIterator[bytes]:
        """逐块读取原始字节，同时保持取消异常不变。"""

        try:
            async for chunk in self._response.aiter_bytes():
                yield chunk
        except httpx2.TimeoutException as error:
            raise HttpTimeoutError("读取 HTTP 响应超时") from error
        except httpx2.RequestError as error:
            raise HttpTransportError("读取 HTTP 响应失败") from error

    async def aiter_text(self) -> AsyncIterator[str]:
        """按 HTTPX2 解析的响应编码逐块读取文本。"""

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
    """打开一次流式请求，统一池诊断、错误映射和可靠退出。"""

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
        # 把当前异常传回 HTTPX2 上下文，使其按真实退出原因清理连接。
        error_type, error, traceback = sys.exc_info()

        # 即使调用方取消任务，也必须先退出响应上下文并归还连接容量。
        with CancelScope(shield=True):
            try:
                if entered:
                    await stream_context.__aexit__(error_type, error, traceback)
            finally:
                runtime.release()
