from contextlib import AbstractAsyncContextManager

import httpx2
from anyio import CancelScope

from app.infrastructure.http.contracts.request import HttpRequest
from app.infrastructure.http.contracts.response import HttpResponse
from app.infrastructure.http.contracts.stream import HttpStreamResponse
from app.infrastructure.http.drivers.httpx2.pool import HttpPoolRuntime
from app.infrastructure.http.drivers.httpx2.stream import Httpx2StreamResponse, open_httpx2_stream
from app.infrastructure.http.errors import HttpResponseTooLargeError
from app.infrastructure.http.logging import HTTP_LOGGER, HttpLogEvent
from app.infrastructure.logging.record import log_extra


class Httpx2Resource:
    """持有普通与流式 HTTPX2 客户端的驱动资源。"""

    def __init__(
        self,
        standard_client: httpx2.AsyncClient,
        stream_client: httpx2.AsyncClient,
        standard_pool_limit: int = 100,
        stream_pool_limit: int = 100,
        pool_warning_ratio: float = 0.8,
        max_response_bytes: int = 10 * 1024 * 1024,
    ) -> None:
        self._standard_client = standard_client
        self._stream_client = stream_client
        self._max_response_bytes = max_response_bytes
        self._standard_runtime = HttpPoolRuntime(
            name="standard",
            limit=standard_pool_limit,
            warning_ratio=pool_warning_ratio,
        )
        self._stream_runtime = HttpPoolRuntime(
            name="stream",
            limit=stream_pool_limit,
            warning_ratio=pool_warning_ratio,
        )

    @property
    def standard_runtime(self) -> HttpPoolRuntime:
        return self._standard_runtime

    @property
    def stream_runtime(self) -> HttpPoolRuntime:
        return self._stream_runtime

    async def request(self, request: HttpRequest) -> HttpResponse:
        async with open_httpx2_stream(
            self._standard_client,
            request,
            self._standard_runtime,
        ) as response:
            content = await self._read_limited(response)
            return HttpResponse(
                status_code=response.status_code,
                headers=response.headers,
                content=content,
            )

    def stream(self, request: HttpRequest) -> AbstractAsyncContextManager[HttpStreamResponse]:
        return open_httpx2_stream(
            self._stream_client,
            request,
            self._stream_runtime,
        )

    async def aclose(self) -> None:
        errors: list[BaseException] = []

        with CancelScope(shield=True):
            for client in (self._stream_client, self._standard_client):
                try:
                    await client.aclose()
                except BaseException as error:
                    errors.append(error)

        if errors:
            raise BaseExceptionGroup("HTTP 客户端关闭失败", errors)

        HTTP_LOGGER.info(
            "Outbound HTTP resource closed",
            extra=log_extra(HttpLogEvent.RESOURCE_CLOSED),
        )

    async def _read_limited(self, response: Httpx2StreamResponse) -> bytes:
        content = bytearray()

        async for chunk in response.aiter_bytes():
            if len(content) + len(chunk) > self._max_response_bytes:
                raise HttpResponseTooLargeError(self._max_response_bytes)

            content.extend(chunk)

        return bytes(content)
