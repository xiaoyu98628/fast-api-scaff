from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from app.config.http import HttpSettings
from app.infrastructure.http.clients.managed import ManagedHttpClient
from app.infrastructure.http.contracts.client import HttpClient
from app.infrastructure.http.contracts.request import HttpRequest
from app.infrastructure.http.contracts.response import HttpResponse
from app.infrastructure.http.contracts.stream import HttpStreamResponse
from app.infrastructure.http.drivers.httpx.factory import create_httpx_resource
from app.infrastructure.http.resource import ManagedHttpResource
from app.infrastructure.resources.lazy import AsyncLazy


class HttpClientManager:
    """管理全局、不具名的 HTTP 出站客户端及其生命周期。"""

    def __init__(self, settings: HttpSettings) -> None:
        self._settings = settings
        self._resource = AsyncLazy(
            factory=self._create,
            closer=ManagedHttpResource.aclose,
        )

    @property
    def is_initialized(self) -> bool:
        return self._resource.initialized

    async def get(self) -> HttpClient:
        return (await self._resource.get()).client

    async def request(self, request: HttpRequest) -> HttpResponse:
        return await (await self.get()).request(request)

    def stream(self, request: HttpRequest) -> AbstractAsyncContextManager[HttpStreamResponse]:
        return self._stream(request)

    @asynccontextmanager
    async def _stream(self, request: HttpRequest) -> AsyncIterator[HttpStreamResponse]:
        async with (await self.get()).stream(request) as response:
            yield response

    async def aclose(self) -> None:
        await self._resource.aclose()

    async def _create(self) -> ManagedHttpResource:
        driver = create_httpx_resource(self._settings)
        return ManagedHttpResource(
            driver=driver,
            client=ManagedHttpClient(driver),
        )
