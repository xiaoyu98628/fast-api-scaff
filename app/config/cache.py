from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config.base import BASE_SETTINGS_CONFIG


class CacheSettings(BaseSettings):
    """应用启动时读取的缓存原始配置快照。"""

    model_config = SettingsConfigDict(
        **BASE_SETTINGS_CONFIG,
        env_prefix="CACHE_",
        env_nested_delimiter="__",
        frozen=True,
    )

    default: str | None = None
    key_prefix: str = ""
    connections: dict[str, dict[str, object]] = Field(default_factory=dict)


class BaseCacheConnectionSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    key_prefix: str | None = None

    def resolve_key_prefix(self, default: str) -> str:
        return self.key_prefix if self.key_prefix is not None else default


class PooledCacheConnectionSettings(BaseCacheConnectionSettings):
    max_connections: int = Field(default=10, ge=1)
    connect_timeout: float = Field(default=5.0, gt=0)
    read_timeout: float = Field(default=5.0, gt=0)


class RedisConnectionSettings(PooledCacheConnectionSettings):
    driver: Literal["redis"]
    host: str = Field(min_length=1)
    port: int = Field(default=6379, ge=1, le=65535)
    database: int = Field(default=0, ge=0)
    username: str | None = None
    password: SecretStr | None = None
    ssl: bool = False


class MemcachedConnectionSettings(PooledCacheConnectionSettings):
    driver: Literal["memcached"]
    host: str = Field(min_length=1)
    port: int = Field(default=11211, ge=1, le=65535)
    username: str = Field(min_length=1)
    password: SecretStr = Field(min_length=1)
    ssl: bool = False
    min_connections: int = Field(default=1, ge=1)
    blocking_timeout: float = Field(default=5.0, gt=0)

    @model_validator(mode="after")
    def validate_pool_size(self) -> MemcachedConnectionSettings:
        if self.min_connections > self.max_connections:
            raise ValueError("min_connections 不能大于 max_connections")

        return self


type CacheConnectionSettings = Annotated[
    RedisConnectionSettings | MemcachedConnectionSettings,
    Field(discriminator="driver"),
]
