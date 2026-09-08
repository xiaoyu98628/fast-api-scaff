"""管理全局 HTTP 出站资源的延迟创建和关闭。"""

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from app.config.http import HttpSettings
from app.infrastructure.http.clients.managed import ManagedHttpClient
from app.infrastructure.http.contracts.client import HttpClient
from app.infrastructure.http.contracts.request import HttpRequest
from app.infrastructure.http.contracts.response import HttpResponse
from app.infrastructure.http.contracts.stream import HttpStreamResponse
from app.infrastructure.http.drivers.httpx2.factory import create_httpx2_resource
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
        """报告底层 HTTPX2 客户端是否已经创建。"""

        return self._resource.initialized

    async def get(self) -> HttpClient:
        """首次使用时创建并返回公共 HTTP 客户端。"""

        return (await self._resource.get()).client

    async def request(self, request: HttpRequest) -> HttpResponse:
        """通过公共客户端执行完整缓冲请求。"""

        return await (await self.get()).request(request)

    def stream(self, request: HttpRequest) -> AbstractAsyncContextManager[HttpStreamResponse]:
        """返回保持底层连接开放的流式响应上下文。"""

        return self._stream(request)

    @asynccontextmanager
    async def _stream(self, request: HttpRequest) -> AsyncIterator[HttpStreamResponse]:
        async with (await self.get()).stream(request) as response:
            yield response

    async def aclose(self) -> None:
        """关闭已经创建的普通和流式连接池。"""

        await self._resource.aclose()

    async def _create(self) -> ManagedHttpResource:
        """组合 HTTPX2 驱动资源与统一日志客户端。"""

        driver = create_httpx2_resource(self._settings)
        return ManagedHttpResource(
            driver=driver,
            client=ManagedHttpClient(driver),
        )
