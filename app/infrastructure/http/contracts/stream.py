"""定义仅在异步上下文内有效的流式 HTTP 响应契约。"""

from collections.abc import AsyncIterator
from typing import Protocol

from app.infrastructure.http.contracts.response import HttpHeaders


class HttpStreamResponse(Protocol):
    """仅在所属异步上下文中有效的流式响应。"""

    @property
    def status_code(self) -> int:
        """返回已经建立响应的 HTTP 状态码。"""

        ...

    @property
    def headers(self) -> HttpHeaders:
        """返回保留重复项的不可变响应头序列。"""

        ...

    async def aread(self) -> bytes:
        """读取并返回完整响应体字节。"""

        ...

    def aiter_bytes(self) -> AsyncIterator[bytes]:
        """按传输驱动提供的分块异步迭代响应字节。"""

        ...

    def aiter_text(self) -> AsyncIterator[str]:
        """按响应编码异步迭代文本块。"""

        ...
