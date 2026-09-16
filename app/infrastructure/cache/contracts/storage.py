"""定义各缓存驱动都必须实现的字节级 KV 语义。"""

from typing import Protocol, runtime_checkable


class KeyValueStorage(Protocol):
    """缓存驱动提供给公共客户端的内部字节级 KV 能力。"""

    async def get(self, key: str) -> bytes | None:
        """读取驱动 key；未命中或过期时返回 None。"""

        ...

    async def set(self, key: str, value: bytes, ttl: int | None) -> bool:
        """按秒级 TTL 写入字节值，None 表示不设置过期时间。"""

        ...

    async def delete(self, key: str) -> bool:
        """删除驱动 key，并返回是否删除了有效值。"""

        ...

    async def exists(self, key: str) -> bool:
        """判断驱动 key 是否存在有效值。"""

        ...


class RedisStringStorage(Protocol):
    """声明登录限制等适配器需要的 Redis String 原子操作。"""

    async def acquire_window(self, key: str, limit: int, window_ms: int) -> tuple[bool, int]:
        """原子消耗固定窗口配额；返回准入标识与拒绝时的剩余毫秒数。"""

        ...

    async def increment(self, key: str, ttl: int) -> int:
        """原子递增，并在首次创建时设置 TTL。"""

        ...

    async def expire(self, key: str, ttl: int) -> bool:
        """更新已有 key 的 TTL。"""

        ...

    async def ttl(self, key: str) -> int:
        """返回 Redis TTL 状态值。"""

        ...


@runtime_checkable
class RedisAtomicStorage(KeyValueStorage, Protocol):
    """在公共 KV 能力之外暴露受控 Redis String 原子能力。"""

    strings: RedisStringStorage
