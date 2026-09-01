from contextlib import AbstractAsyncContextManager

import httpx
from anyio import CancelScope

from app.infrastructure.http.contracts.request import HttpRequest
from app.infrastructure.http.contracts.response import HttpResponse
from app.infrastructure.http.contracts.stream import HttpStreamResponse
from app.infrastructure.http.drivers.httpx.pool import HttpPoolRuntime, HttpxPoolCompatibility
from app.infrastructure.http.drivers.httpx.stream import HttpxStreamResponse, open_httpx_stream
from app.infrastructure.http.errors import HttpResponseTooLargeError
from app.infrastructure.http.logging import HTTP_LOGGER, HttpLogEvent
from app.infrastructure.logging.record import log_extra


class HttpxResource:
    """持有普通与流式 HTTPX 客户端的驱动资源。"""

    def __init__(
        self,
        standard_client: httpx.AsyncClient,
        stream_client: httpx.AsyncClient,
        max_response_bytes: int = 10 * 1024 * 1024,
    ) -> None:
        self._standard_client = standard_client
        self._stream_client = stream_client
        self._max_response_bytes = max_response_bytes
        self._standard_runtime = HttpPoolRuntime()
        self._stream_runtime = HttpPoolRuntime()
        self._pool_compatibility = HttpxPoolCompatibility()

    @property
    def standard_runtime(self) -> HttpPoolRuntime:
        return self._standard_runtime

    @property
    def stream_runtime(self) -> HttpPoolRuntime:
        return self._stream_runtime

    async def request(self, request: HttpRequest) -> HttpResponse:
        async with open_httpx_stream(
            self._standard_client,
            request,
            self._pool_compatibility,
            self._standard_runtime,
            pool_name="standard",
        ) as response:
            content = await self._read_limited(response)
            return HttpResponse(
                status_code=response.status_code,
                headers=response.headers,
                content=content,
            )

    def stream(self, request: HttpRequest) -> AbstractAsyncContextManager[HttpStreamResponse]:
        return open_httpx_stream(
            self._stream_client,
            request,
            self._pool_compatibility,
            self._stream_runtime,
            pool_name="stream",
        )

    async def aclose(self) -> None:
        errors: list[BaseException] = []

        with CancelScope(shield=True):
            try:
                await self._pool_compatibility.wait_for_cleanup()
            except BaseException as error:
                errors.append(error)

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

    async def _read_limited(self, response: HttpxStreamResponse) -> bytes:
        content = bytearray()

        async for chunk in response.aiter_bytes():
            if len(content) + len(chunk) > self._max_response_bytes:
                raise HttpResponseTooLargeError(self._max_response_bytes)

            content.extend(chunk)

        return bytes(content)
