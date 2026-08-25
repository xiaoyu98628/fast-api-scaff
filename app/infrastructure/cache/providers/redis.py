from functools import partial

from redis.asyncio import Redis

from app.config.cache import RedisCacheSettings
from app.infrastructure.cache.backends.redis import RedisCacheBackend
from app.infrastructure.cache.contracts.backend import CacheBackend
from app.infrastructure.cache.contracts.provider import CacheBackendDefinition


class RedisCacheProvider:
    driver = "redis"

    def prepare(self, raw_config: dict[str, object]) -> CacheBackendDefinition:
        settings = RedisCacheSettings.model_validate(raw_config)
        return CacheBackendDefinition(
            key_prefix=settings.key_prefix,
            factory=partial(self._create, settings),
        )

    async def _create(self, settings: RedisCacheSettings) -> CacheBackend:
        client = Redis(
            host=settings.host,
            port=settings.port,
            db=settings.database,
            username=settings.username,
            password=settings.password.get_secret_value() if settings.password is not None else None,
            ssl=settings.ssl,
            max_connections=settings.max_connections,
            socket_connect_timeout=settings.connect_timeout,
            socket_timeout=settings.read_timeout,
            decode_responses=False,
        )
        return RedisCacheBackend(client)
