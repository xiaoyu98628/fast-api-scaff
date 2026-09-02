from collections.abc import AsyncIterator
from typing import Protocol

from app.infrastructure.http.contracts.response import HttpHeaders


class HttpStreamResponse(Protocol):
    """仅在所属异步上下文中有效的流式响应。"""

    @property
    def status_code(self) -> int: ...

    @property
    def headers(self) -> HttpHeaders: ...

    async def aread(self) -> bytes: ...

    def aiter_bytes(self) -> AsyncIterator[bytes]: ...

    def aiter_text(self) -> AsyncIterator[str]: ...
