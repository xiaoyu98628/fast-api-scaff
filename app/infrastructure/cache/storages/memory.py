"""使用进程内字典实现带惰性过期的字节级 KV Storage。"""

from app.infrastructure.cache.connections.memory import MemoryCacheConnection


class MemoryCacheStorage:
    """基于单进程资源实现 KV；不提供跨进程一致性或显式并发锁。"""

    def __init__(self, connection: MemoryCacheConnection) -> None:
        """绑定保存值和单调时钟的进程内连接。"""

        self._connection = connection

    async def get(self, key: str) -> bytes | None:
        """读取有效值，并在命中过期项时就地清理。"""

        item = self._connection.values.get(key)
        if item is None:
            return None

        value, expires_at = item
        # 没有后台清理任务，过期项在下一次读取或存在性检查时删除。
        if expires_at is not None and expires_at <= self._connection.now():
            del self._connection.values[key]
            return None

        return value

    async def set(self, key: str, value: bytes, ttl: int | None) -> bool:
        """用单调时间计算进程内绝对过期时刻。"""

        expires_at = self._connection.now() + ttl if ttl is not None else None
        self._connection.values[key] = (value, expires_at)
        return True

    async def delete(self, key: str) -> bool:
        """清理过期项或删除有效值，并返回是否删除成功。"""

        if await self.get(key) is None:
            return False

        del self._connection.values[key]
        return True

    async def exists(self, key: str) -> bool:
        """复用读取逻辑判断存在性，同时触发惰性过期清理。"""

        return await self.get(key) is not None
