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
