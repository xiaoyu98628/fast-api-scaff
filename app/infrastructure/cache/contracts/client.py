"""定义业务可依赖的缓存客户端和 TTL 公共语义。"""

from enum import Enum, auto
from typing import Protocol


class CacheExpiration(Enum):
    """区分使用全局默认 TTL 与显式永不过期。"""

    DEFAULT = auto()
    NEVER = auto()


DEFAULT_EXPIRATION = CacheExpiration.DEFAULT
NO_EXPIRATION = CacheExpiration.NEVER

type CacheTTL = int | CacheExpiration


class CacheClient(Protocol):
    """业务代码可依赖的最小异步缓存能力。"""

    async def get(self, key: str) -> bytes | None:
        """读取字节值；未命中或已过期时返回 None。"""

        ...

    async def set(self, key: str, value: bytes, *, ttl: CacheTTL = DEFAULT_EXPIRATION) -> None:
        """写入值，并选择全局默认、显式秒数或永不过期策略。"""

        ...

    async def delete(self, key: str) -> bool:
        """删除 key，并返回此前是否存在有效值。"""

        ...

    async def exists(self, key: str) -> bool:
        """判断 key 当前是否存在有效值。"""

        ...
