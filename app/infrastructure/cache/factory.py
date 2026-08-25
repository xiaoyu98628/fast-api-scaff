import ssl

from memcachio import Client
from pydantic import SecretStr
from redis.asyncio import Redis

from app.config.cache import CacheConnectionSettings, MemcachedConnectionSettings, MemoryConnectionSettings, RedisConnectionSettings
from app.infrastructure.cache.backends.memcached import MemcachedCacheBackend
from app.infrastructure.cache.backends.memory import MemoryCacheBackend
from app.infrastructure.cache.backends.redis import RedisCacheBackend
from app.infrastructure.cache.contracts.backend import CacheBackend


async def create_cache_backend(settings: CacheConnectionSettings) -> CacheBackend:
    """创建缓存后端，不主动连接远程缓存服务。"""
    match settings:
        case RedisConnectionSettings():
            client = Redis(
                host=settings.host,
                port=settings.port,
                db=settings.database,
                username=settings.username,
                password=_secret_value(settings.password),
                ssl=settings.ssl,
                max_connections=settings.max_connections,
                socket_connect_timeout=settings.connect_timeout,
                socket_timeout=settings.read_timeout,
                decode_responses=False,
            )
            return RedisCacheBackend(client)
        case MemcachedConnectionSettings():
            ssl_context = ssl.create_default_context() if settings.ssl else None
            if settings.username is None or settings.password is None:
                client: Client[bytes] = Client(
                    (settings.host, settings.port),
                    decode_responses=False,
                    ssl_context=ssl_context,
                    min_connections=settings.min_connections,
                    max_connections=settings.max_connections,
                    connect_timeout=settings.connect_timeout,
                    read_timeout=settings.read_timeout,
                    blocking_timeout=settings.blocking_timeout,
                )
            else:
                client = Client(
                    (settings.host, settings.port),
                    decode_responses=False,
                    username=settings.username,
                    password=settings.password.get_secret_value(),
                    ssl_context=ssl_context,
                    min_connections=settings.min_connections,
                    max_connections=settings.max_connections,
                    connect_timeout=settings.connect_timeout,
                    read_timeout=settings.read_timeout,
                    blocking_timeout=settings.blocking_timeout,
                )
            return MemcachedCacheBackend(client)
        case MemoryConnectionSettings():
            return MemoryCacheBackend()


def _secret_value(secret: SecretStr | None) -> str | None:
    return secret.get_secret_value() if secret is not None else None
