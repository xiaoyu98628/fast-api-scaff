"""异步 Redis 客户端单例；与 ``app.main`` lifespan 中 ``close_redis`` 配对释放。"""

from redis.asyncio import Redis

from config.config import get_config

_redis_client: Redis | None = None


def get_redis_client() -> Redis | None:
    """懒加载全局 ``Redis`` 连接，配置来自 ``REDIS_*`` 环境变量。"""
    global _redis_client
    if _redis_client is None:
        redis_config = get_config().redis
        _redis_client = Redis.from_url(
            redis_config.url,
            decode_responses=redis_config.decode_responses,
        )
    return _redis_client


async def ping_redis() -> bool:
    """健康检查用 PING；返回是否成功。"""
    redis = get_redis_client()
    return bool(await redis.ping())


async def close_redis() -> None:
    """关闭连接并清空模块级引用。"""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
    _redis_client = None
