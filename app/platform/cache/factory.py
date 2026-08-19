import ssl

from memcachio import Client
from pydantic import SecretStr
from redis.asyncio import Redis

from app.config.cache import CacheConnectionSettings, MemcachedConnectionSettings, RedisConnectionSettings
from app.platform.cache.backends.memcached_cache import MemcachedCache
from app.platform.cache.backends.redis_cache import RedisCache
from app.platform.cache.client import CacheClient


async def create_cache_client(
    settings: CacheConnectionSettings,
    default_key_prefix: str = "",
) -> CacheClient:
    """创建缓存客户端，不主动连接缓存服务。"""
    key_prefix = settings.resolve_key_prefix(default_key_prefix)

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
            return RedisCache(client=client, key_prefix=key_prefix)
        case MemcachedConnectionSettings():
            ssl_context = ssl.create_default_context() if settings.ssl else None
            client: Client[bytes] = Client(
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
            return MemcachedCache(client=client, key_prefix=key_prefix)


async def close_cache_client(client: CacheClient) -> None:
    await client.aclose()


def _secret_value(secret: SecretStr | None) -> str | None:
    return secret.get_secret_value() if secret is not None else None
