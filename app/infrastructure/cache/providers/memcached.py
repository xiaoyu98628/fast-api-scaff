import ssl
from functools import partial
from typing import Literal

from memcachio import Client
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from app.infrastructure.cache.backends.memcached import MemcachedCacheBackend
from app.infrastructure.cache.contracts.backend import CacheBackend
from app.infrastructure.cache.contracts.provider import CacheBackendDefinition


class MemcachedCacheSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    driver: Literal["memcached"]
    key_prefix: str = ""
    host: str = Field(min_length=1)
    port: int = Field(default=11211, ge=1, le=65535)
    username: str | None = Field(default=None, min_length=1)
    password: SecretStr | None = Field(default=None, min_length=1)
    ssl: bool = False
    min_connections: int = Field(default=1, ge=1)
    max_connections: int = Field(default=10, ge=1)
    connect_timeout: float = Field(default=5.0, gt=0)
    read_timeout: float = Field(default=5.0, gt=0)
    blocking_timeout: float = Field(default=5.0, gt=0)

    @model_validator(mode="after")
    def validate_connection(self) -> MemcachedCacheSettings:
        if self.min_connections > self.max_connections:
            raise ValueError("min_connections 不能大于 max_connections")

        if (self.username is None) != (self.password is None):
            raise ValueError("username 和 password 必须同时配置或同时省略")

        return self


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
