from redis.asyncio import Redis

from config.config import get_config

_redis_client: Redis | None = None


def get_redis_client() -> Redis:
    global _redis_client
    if _redis_client is None:
        redis_config = get_config().redis
        _redis_client = Redis.from_url(
            redis_config.url,
            decode_responses=redis_config.decode_responses,
        )
    return _redis_client


async def ping_redis() -> bool:
    redis = get_redis_client()
    return bool(await redis.ping())


async def close_redis() -> None:
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
    _redis_client = None


class AccessTokenStore:
    """Redis token 存储，key 设计为 ``auth:access_token:{token}``。"""

    key_prefix = "auth:access_token:"

    @staticmethod
    def _build_key(token: str) -> str:
        return f"{AccessTokenStore.key_prefix}{token}"

    async def save(self, token: str, ttl_seconds: int) -> None:
        redis = get_redis_client()
        key = self._build_key(token)
        await redis.set(name=key, value="1", ex=ttl_seconds)

    async def exists(self, token: str) -> bool:
        redis = get_redis_client()
        key = self._build_key(token)
        return bool(await redis.exists(key))
