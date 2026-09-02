from contextlib import AbstractAsyncContextManager
from typing import Protocol

from app.infrastructure.http.contracts.request import HttpRequest
from app.infrastructure.http.contracts.response import HttpResponse
from app.infrastructure.http.contracts.stream import HttpStreamResponse


class HttpDriver(Protocol):
    """公共客户端依赖的底层 HTTP 驱动契约。"""

    async def request(self, request: HttpRequest) -> HttpResponse: ...

    def stream(self, request: HttpRequest) -> AbstractAsyncContextManager[HttpStreamResponse]: ...

    async def aclose(self) -> None: ...
