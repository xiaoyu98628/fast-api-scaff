from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config.base import BASE_SETTINGS_CONFIG


class CacheSettings(BaseSettings):
    """应用启动时读取的缓存配置。"""

    model_config = SettingsConfigDict(
        **BASE_SETTINGS_CONFIG,
        env_prefix="CACHE_",
        env_nested_delimiter="__",
        frozen=True,
    )

    default: str | None = None
    namespace: str = ""
    default_ttl: int | None = Field(default=300, gt=0)
    connections: dict[str, dict[str, object]] = Field(default_factory=dict)


class BaseCacheSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    key_prefix: str = ""


class RedisCacheSettings(BaseCacheSettings):
    driver: Literal["redis"]
    host: str = Field(min_length=1)
    port: int = Field(default=6379, ge=1, le=65535)
    database: int = Field(default=0, ge=0)
    username: str | None = Field(default=None, min_length=1)
    password: SecretStr | None = Field(default=None, min_length=1)
    ssl: bool = False
    max_connections: int = Field(default=10, ge=1)
    connect_timeout: float = Field(default=5.0, gt=0)
    read_timeout: float = Field(default=5.0, gt=0)


class MemcachedCacheSettings(BaseCacheSettings):
    driver: Literal["memcached"]
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


class MemoryCacheSettings(BaseCacheSettings):
    driver: Literal["memory"]
