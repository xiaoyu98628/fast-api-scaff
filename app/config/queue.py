from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, TypeAdapter, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config.base import BASE_SETTINGS_CONFIG


class ConnectionSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True, allow_inf_nan=False)
    default_queue: str = Field(default="default", min_length=1, pattern=r"^\S+$")
    publish_timeout: float = Field(default=10.0, gt=0)


class MemoryQueueSettings(ConnectionSettings):
    driver: Literal["memory"]
    capacity: int = Field(default=1000, ge=1)


class RedisQueueSettings(ConnectionSettings):
    driver: Literal["redis"]
    url: SecretStr

    @field_validator("url")
    @classmethod
    def redis_url(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith(("redis://", "rediss://")):
            raise ValueError("需要 redis:// 或 rediss:// URL")
        return value

    group: str = Field(default="workers", min_length=1, pattern=r"^\S+$")
    prefix: str = "queue:"
    lease_seconds: float = Field(default=120.0, ge=3)
    command_timeout: float = Field(default=10.0, ge=2.0)


class KafkaQueueSettings(ConnectionSettings):
    driver: Literal["kafka"]
    bootstrap_servers: list[str] = Field(min_length=1)
    group: str = Field(default="workers", min_length=1, pattern=r"^\S+$")
    security_protocol: Literal["PLAINTEXT", "SSL", "SASL_PLAINTEXT", "SASL_SSL"] = "PLAINTEXT"
    sasl_mechanism: Literal["PLAIN", "SCRAM-SHA-256", "SCRAM-SHA-512"] = "PLAIN"
    username: str | None = None
    password: SecretStr | None = None
    max_poll_interval_ms: int = Field(default=300000, ge=1000)

    @model_validator(mode="after")
    def credentials(self) -> KafkaQueueSettings:
        if self.security_protocol.startswith("SASL") and (not self.username or self.password is None):
            raise ValueError("SASL 需要用户名与密码")
        return self


class RabbitMQQueueSettings(ConnectionSettings):
    driver: Literal["rabbitmq"]
    url: SecretStr

    @field_validator("url")
    @classmethod
    def amqp_url(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith(("amqp://", "amqps://")):
            raise ValueError("需要 amqp:// 或 amqps:// URL")
        return value


type QueueConnection = MemoryQueueSettings | RedisQueueSettings | KafkaQueueSettings | RabbitMQQueueSettings
_CONNECTION_ADAPTER = TypeAdapter(Annotated[QueueConnection, Field(discriminator="driver")])


class FailedStoreSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    database: str = "main"


class WorkerSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    concurrency: int = Field(default=4, ge=1, le=1024)
    shutdown_timeout_seconds: float = Field(default=30.0, gt=0)


class QueueSettings(BaseSettings):
    model_config = SettingsConfigDict(**BASE_SETTINGS_CONFIG, env_prefix="QUEUE_", env_nested_delimiter="__", frozen=True, allow_inf_nan=False)
    default: str | None = None
    connections: dict[str, dict[str, object]] = Field(default_factory=dict)
    failed: FailedStoreSettings = Field(default_factory=FailedStoreSettings)
    worker: WorkerSettings = Field(default_factory=WorkerSettings)
    max_message_bytes: int = Field(default=1_048_576, ge=256)


def parse_connection(raw: dict[str, object]) -> QueueConnection:
    return _CONNECTION_ADAPTER.validate_python(raw)
