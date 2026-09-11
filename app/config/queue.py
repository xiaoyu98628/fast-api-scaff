"""定义队列连接、失败任务存储和 Worker 的严格配置模型。"""

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, TypeAdapter, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config.base import BASE_SETTINGS_CONFIG

_QUEUE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


def validate_queue_name(value: str) -> str:
    """校验跨 Redis、Kafka 和 RabbitMQ 共用的逻辑队列名。"""

    if not isinstance(value, str) or not value or len(value) > 200:
        raise ValueError("队列名必须是长度为 1–200 的字符串")
    if value in {".", ".."} or _QUEUE_NAME_PATTERN.fullmatch(value) is None:
        raise ValueError("队列名只能包含字母、数字、点、下划线和连字符")
    return value


def validate_worker_concurrency(value: int) -> int:
    """校验 Worker 和队列消费者共用的严格并发数。"""

    if type(value) is not int or not 1 <= value <= 1024:
        raise ValueError("concurrency 必须是 1–1024 的整数")
    return value


class ConnectionSettings(BaseModel):
    """保存所有队列驱动共享的发布参数。"""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True, allow_inf_nan=False)
    default_queue: str = Field(default="default", min_length=1, max_length=200)
    publish_timeout: float = Field(default=10.0, gt=0)

    @field_validator("default_queue")
    @classmethod
    def queue_name(cls, value: str) -> str:
        """确保配置队列名与运行时覆盖值遵守同一可移植规则。"""

        return validate_queue_name(value)


class RedisQueueSettings(ConnectionSettings):
    """校验 Redis Streams 连接、消费组和租约参数。"""

    driver: Literal["redis"]
    host: str = Field(default="127.0.0.1", min_length=1)
    port: int = Field(default=6379, ge=1, le=65535)
    database: int = Field(default=0, ge=0)
    username: str | None = Field(default=None, min_length=1)
    password: SecretStr | None = Field(default=None, min_length=1)
    ssl: bool = False
    max_connections: int = Field(default=10, ge=1)
    connect_timeout: float = Field(default=5.0, gt=0)
    group: str = Field(default="workers", min_length=1, pattern=r"^\S+$")
    prefix: str = "queue:"
    lease_seconds: float = Field(default=120.0, ge=3)
    command_timeout: float = Field(default=10.0, ge=2.0)


class KafkaQueueSettings(ConnectionSettings):
    """校验 Kafka Broker、消费组和 SASL 参数。"""

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
        """确保启用 SASL 时同时提供完整认证信息。"""

        if self.security_protocol.startswith("SASL") and (not self.username or self.password is None):
            raise ValueError("SASL 需要用户名与密码")
        return self


class RabbitMQQueueSettings(ConnectionSettings):
    """校验 RabbitMQ 连接和虚拟主机参数。"""

    driver: Literal["rabbitmq"]
    host: str = Field(default="127.0.0.1", min_length=1)
    port: int = Field(default=5672, ge=1, le=65535)
    virtual_host: str = Field(default="/", min_length=1)
    username: str = Field(default="guest", min_length=1)
    password: SecretStr = SecretStr("guest")
    ssl: bool = False
    connect_timeout: float = Field(default=5.0, gt=0)


type QueueConnection = RedisQueueSettings | KafkaQueueSettings | RabbitMQQueueSettings
# 使用 driver 判别字段直接选择模型，避免多个连接模型依次尝试并产生含混错误。
_CONNECTION_ADAPTER = TypeAdapter(Annotated[QueueConnection, Field(discriminator="driver")])


class FailedStoreSettings(BaseModel):
    """指定失败任务记录使用的数据库连接。"""

    model_config = ConfigDict(extra="forbid", frozen=True)
    database: str = "main"


class WorkerSettings(BaseModel):
    """限制 Worker 并发数及优雅关闭等待时间。"""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    concurrency: int = Field(default=4, ge=1, le=1024)
    shutdown_timeout_seconds: float = Field(default=30.0, gt=0)

    @field_validator("concurrency", mode="before")
    @classmethod
    def reject_non_integer_concurrency(cls, value: object) -> object:
        """允许环境变量数字字符串，但拒绝 bool 和浮点数的隐式转换。"""

        if type(value) is int:
            return value
        if isinstance(value, str) and value.isascii() and value.isdecimal():
            return value
        raise ValueError("concurrency 必须是整数或整数字符串")

    @field_validator("concurrency")
    @classmethod
    def strict_concurrency(cls, value: int) -> int:
        """复用运行时消费者的并发数约束。"""

        return validate_worker_concurrency(value)


class QueueSettings(BaseSettings):
    """应用启动时读取的队列原始配置快照。"""

    model_config = SettingsConfigDict(**BASE_SETTINGS_CONFIG, env_prefix="QUEUE_", env_nested_delimiter="__", frozen=True, allow_inf_nan=False)
    default: str | None = None
    connections: dict[str, dict[str, object]] = Field(default_factory=dict)
    failed: FailedStoreSettings = Field(default_factory=FailedStoreSettings)
    worker: WorkerSettings = Field(default_factory=WorkerSettings)
    max_message_bytes: int = Field(default=1_048_576, ge=256)


def parse_connection(raw: dict[str, object]) -> QueueConnection:
    """按 driver 将原始连接配置解析成对应的严格模型。"""

    return _CONNECTION_ADAPTER.validate_python(raw)
