"""访问令牌存储：登录后将 token 写入 Redis，并用于中间件校验。"""

from redis.asyncio import Redis

from app.infrastructure.redis.client import get_redis_client


class AccessTokenStore:
    """Redis token 存储，key 设计为 ``auth:access_token:{token}``。"""

    key_prefix = "auth:access_token:"

    @staticmethod
    def _build_key(token: str) -> str:
        return f"{AccessTokenStore.key_prefix}{token}"

    async def save(self, token: str, ttl_seconds: int) -> None:
        redis: Redis = get_redis_client()
        key = self._build_key(token)
        await redis.set(name=key, value="1", ex=ttl_seconds)

    async def exists(self, token: str) -> bool:
        redis: Redis = get_redis_client()
        key = self._build_key(token)
        return bool(await redis.exists(key))
