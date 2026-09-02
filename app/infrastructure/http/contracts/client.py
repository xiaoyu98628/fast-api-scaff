from contextlib import AbstractAsyncContextManager
from typing import Protocol

from app.infrastructure.http.contracts.request import HttpRequest
from app.infrastructure.http.contracts.response import HttpResponse
from app.infrastructure.http.contracts.stream import HttpStreamResponse


class HttpClient(Protocol):
    """应用公共的 HTTP 出站客户端契约。"""

    async def request(self, request: HttpRequest) -> HttpResponse: ...

    def stream(self, request: HttpRequest) -> AbstractAsyncContextManager[HttpStreamResponse]: ...
