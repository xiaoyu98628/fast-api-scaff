"""按配置装配限流组件并校验所需的缓存能力。"""

from functools import partial

from app.config.rate_limit import RateLimitSettings
from app.infrastructure.cache.manager import CacheManager
from app.infrastructure.rate_limit.contracts import RateLimiter
from app.infrastructure.rate_limit.redis import RedisFixedWindowLimiter


def build_rate_limiter(settings: RateLimitSettings, caches: CacheManager) -> RateLimiter | None:
    """关闭时返回 None；启用时校验 Redis 配置，借用缓存资源且不建立网络连接。"""

    if not settings.enabled:
        return None

    cache_name = caches.require_redis(settings.cache)
    return RedisFixedWindowLimiter(
        client_factory=partial(caches.get_redis, cache_name),
        max_requests=settings.max_requests,
        window_seconds=settings.window_seconds,
    )
