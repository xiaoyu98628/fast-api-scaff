import ssl
from functools import partial

from memcachio import Client

from app.config.cache import MemcachedCacheSettings
from app.infrastructure.cache.backends.memcached import MemcachedCacheBackend
from app.infrastructure.cache.contracts.backend import CacheBackend
from app.infrastructure.cache.contracts.provider import CacheBackendDefinition


class MemcachedCacheProvider:
    driver = "memcached"

    def prepare(self, raw_config: dict[str, object]) -> CacheBackendDefinition:
        settings = MemcachedCacheSettings.model_validate(raw_config)
        return CacheBackendDefinition(
            key_prefix=settings.key_prefix,
            factory=partial(self._create, settings),
        )

    async def _create(self, settings: MemcachedCacheSettings) -> CacheBackend:
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
