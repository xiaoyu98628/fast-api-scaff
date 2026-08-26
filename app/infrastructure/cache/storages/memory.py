from app.infrastructure.cache.connections.memory import MemoryCacheConnection


class MemoryCacheStorage:
    """基于单进程内存资源实现字节级 KV 存储。"""

    def __init__(self, connection: MemoryCacheConnection) -> None:
        self._connection = connection

    async def get(self, key: str) -> bytes | None:
        item = self._connection.values.get(key)
        if item is None:
            return None

        value, expires_at = item
        if expires_at is not None and expires_at <= self._connection.now():
            del self._connection.values[key]
            return None

        return value

    async def set(self, key: str, value: bytes, ttl: int | None) -> bool:
        expires_at = self._connection.now() + ttl if ttl is not None else None
        self._connection.values[key] = (value, expires_at)
        return True

    async def delete(self, key: str) -> bool:
        if await self.get(key) is None:
            return False

        del self._connection.values[key]
        return True

    async def exists(self, key: str) -> bool:
        return await self.get(key) is not None
