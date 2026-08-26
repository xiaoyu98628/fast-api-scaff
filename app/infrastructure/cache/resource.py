from dataclasses import dataclass

from app.infrastructure.cache.contracts.client import CacheClient
from app.infrastructure.cache.contracts.connection import CacheConnection
from app.infrastructure.cache.contracts.storage import KeyValueStorage


@dataclass(frozen=True, slots=True)
class CacheResource:
    """一个已经创建的缓存连接及其字节级 KV Storage。"""

    connection: CacheConnection
    storage: KeyValueStorage


@dataclass(frozen=True, slots=True)
class ManagedCacheResource:
    """组合底层缓存资源和应用公共客户端。"""

    connection: CacheConnection
    storage: KeyValueStorage
    client: CacheClient

    async def ping(self) -> bool:
        return await self.connection.ping()

    async def aclose(self) -> None:
        await self.connection.aclose()
