from typing import Protocol


class CacheConnection(Protocol):
    """缓存原生连接资源需要实现的生命周期能力。"""

    async def ping(self) -> bool: ...

    async def aclose(self) -> None: ...
