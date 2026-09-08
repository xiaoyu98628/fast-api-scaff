"""定义各缓存驱动都必须实现的字节级 KV 语义。"""

from typing import Protocol


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
