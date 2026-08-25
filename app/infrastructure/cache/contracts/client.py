from enum import Enum, auto
from typing import Protocol


class CacheExpiration(Enum):
    DEFAULT = auto()
    NEVER = auto()


DEFAULT_EXPIRATION = CacheExpiration.DEFAULT
NO_EXPIRATION = CacheExpiration.NEVER

type CacheTTL = int | CacheExpiration


class CacheClient(Protocol):
    """业务代码可依赖的最小异步缓存能力。"""

    async def get(self, key: str) -> bytes | None: ...

    async def set(self, key: str, value: bytes, *, ttl: CacheTTL = DEFAULT_EXPIRATION) -> None: ...

    async def delete(self, key: str) -> bool: ...

    async def exists(self, key: str) -> bool: ...
