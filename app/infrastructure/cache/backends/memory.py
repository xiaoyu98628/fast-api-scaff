import time
from collections.abc import Callable


class MemoryCacheBackend:
    """供测试和单进程本地开发使用的内存缓存。"""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._values: dict[str, tuple[bytes, float | None]] = {}

    async def get(self, key: str) -> bytes | None:
        item = self._values.get(key)
        if item is None:
            return None

        value, expires_at = item
        if expires_at is not None and expires_at <= self._clock():
            del self._values[key]
            return None

        return value

    async def set(self, key: str, value: bytes, ttl: int | None) -> bool:
        expires_at = self._clock() + ttl if ttl is not None else None
        self._values[key] = (value, expires_at)
        return True

    async def delete(self, key: str) -> bool:
        if await self.get(key) is None:
            return False

        del self._values[key]
        return True

    async def exists(self, key: str) -> bool:
        return await self.get(key) is not None

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        self._values.clear()
