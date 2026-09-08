"""定义公共 HTTP 客户端与具体传输实现之间的驱动契约。"""

from contextlib import AbstractAsyncContextManager
from typing import Protocol

from app.infrastructure.http.contracts.request import HttpRequest
from app.infrastructure.http.contracts.response import HttpResponse
from app.infrastructure.http.contracts.stream import HttpStreamResponse


class HttpDriver(Protocol):
    """公共客户端依赖的底层 HTTP 驱动契约。"""

    async def request(self, request: HttpRequest) -> HttpResponse:
        """通过具体传输库执行一次完整缓冲请求。"""

        ...

    def stream(self, request: HttpRequest) -> AbstractAsyncContextManager[HttpStreamResponse]:
        """打开流式请求上下文，并在退出时归还连接资源。"""

        ...

    async def aclose(self) -> None:
        """关闭驱动持有的客户端和连接池。"""

        ...
