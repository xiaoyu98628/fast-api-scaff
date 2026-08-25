from functools import partial
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr
from redis.asyncio import Redis

from app.infrastructure.cache.backends.redis import RedisCacheBackend
from app.infrastructure.cache.contracts.backend import CacheBackend
from app.infrastructure.cache.contracts.provider import CacheBackendDefinition


class RedisCacheSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    driver: Literal["redis"]
    key_prefix: str = ""
    host: str = Field(min_length=1)
    port: int = Field(default=6379, ge=1, le=65535)
    database: int = Field(default=0, ge=0)
    username: str | None = Field(default=None, min_length=1)
    password: SecretStr | None = Field(default=None, min_length=1)
    ssl: bool = False
    max_connections: int = Field(default=10, ge=1)
    connect_timeout: float = Field(default=5.0, gt=0)
    read_timeout: float = Field(default=5.0, gt=0)


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
