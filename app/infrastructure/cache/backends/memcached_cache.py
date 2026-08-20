from memcachio import Client

from app.infrastructure.cache.backends.base import BaseCache


class MemcachedCache(BaseCache):
    def __init__(self, client: Client[bytes], key_prefix: str = "") -> None:
        super().__init__(key_prefix)
        self._client = client

    async def get(self, key: str) -> bytes | None:
        cache_key = self._key(key)
        items = await self._client.get(cache_key)
        item = items.get(cache_key)
        return item.value if item is not None else None

    async def set(self, key: str, value: bytes, ttl: int | None = None) -> bool:
        self._validate_ttl(ttl)
        result = await self._client.set(self._key(key), value, expiry=ttl or 0)
        return result is True

    async def delete(self, key: str) -> bool:
        result = await self._client.delete(self._key(key))
        return result is True

    async def exists(self, key: str) -> bool:
        return await self.get(key) is not None

    async def ping(self) -> bool:
        return bool(await self._client.version())

    async def aclose(self) -> None:
        self._client.connection_pool.close()

    def _key(self, key: str) -> bytes:
        return self._prefixed_key(key).encode()
