"""定义向量存储命名连接及各驱动的严格配置模型。"""

from ipaddress import IPv6Address
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config.base import BASE_SETTINGS_CONFIG
from app.runtime.paths import STORAGE_DIR


class VectorSettings(BaseSettings):
    """读取向量存储默认连接和命名连接原始配置。"""

    model_config = SettingsConfigDict(
        **BASE_SETTINGS_CONFIG,
        env_prefix="VECTOR_",
        env_nested_delimiter="__",
        frozen=True,
    )

    default: str | None = None
    connections: dict[str, dict[str, object]] = Field(default_factory=dict)


class BaseVectorConnectionSettings(BaseModel):
    """保存全部向量驱动共用的严格校验规则。"""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        hide_input_in_errors=True,
        allow_inf_nan=False,
    )


class LocalVectorConnectionSettings(BaseVectorConnectionSettings):
    """保存嵌入式向量存储的本地路径。"""

    path: str = Field(min_length=1)

    @property
    def resolved_path(self) -> Path:
        """保留绝对路径，并把相对路径解析到 storage 目录。"""

        path = Path(self.path)
        return path if path.is_absolute() else STORAGE_DIR / path


class RemoteVectorConnectionSettings(BaseVectorConnectionSettings):
    """保存远程向量服务共用的地址和认证。"""

    host: str = Field(default="127.0.0.1", min_length=1)
    username: str | None = Field(default=None, min_length=1)
    password: SecretStr | None = Field(default=None, min_length=1)
    ssl: bool = False

    @field_validator("host")
    @classmethod
    def validate_host(cls, host: str) -> str:
        """要求只配置主机名或裸 IPv6，协议和端口由独立字段表达。"""

        if host != host.strip() or any(character.isspace() for character in host):
            raise ValueError("host 不能包含空白字符")
        if "://" in host or "/" in host:
            raise ValueError("host 只能包含主机名或 IP，不能包含协议、端口或路径")
        if ":" in host:
            try:
                IPv6Address(host)
            except ValueError as error:
                raise ValueError("host 中不能包含端口；IPv6 地址应使用不带方括号的完整地址") from error
        return host

    @property
    def url_host(self) -> str:
        """返回适合拼接 URL 的主机表示，并为 IPv6 添加方括号。"""

        return f"[{self.host}]" if ":" in self.host else self.host

    @model_validator(mode="after")
    def validate_basic_auth(self) -> RemoteVectorConnectionSettings:
        """确保 Basic Auth 用户名和密码同时配置或同时省略。"""

        if (self.username is None) != (self.password is None):
            raise ValueError("username 和 password 必须同时配置或同时省略")
        return self


class MilvusLocalVectorSettings(LocalVectorConnectionSettings):
    """配置使用单个本地文件的 Milvus Lite。"""

    driver: Literal["milvus"]
    mode: Literal["local"]
    timeout: float = Field(default=10.0, gt=0)


class MilvusRemoteVectorSettings(RemoteVectorConnectionSettings):
    """配置远程 Milvus Standalone、Distributed 或托管实例。"""

    driver: Literal["milvus"]
    mode: Literal["remote"]
    port: int = Field(default=19530, ge=1, le=65535)
    database: str = Field(default="default", min_length=1, max_length=255)
    timeout: float = Field(default=10.0, gt=0)


class ChromaLocalVectorSettings(LocalVectorConnectionSettings):
    """配置使用本地持久化目录的 Chroma。"""

    driver: Literal["chroma"]
    mode: Literal["local"]
    tenant: str = Field(default="default_tenant", min_length=1)
    database: str = Field(default="default_database", min_length=1)


class ChromaRemoteVectorSettings(RemoteVectorConnectionSettings):
    """配置远程 Chroma Server、代理认证或 Chroma Cloud。"""

    driver: Literal["chroma"]
    mode: Literal["remote"]
    port: int = Field(default=8000, ge=1, le=65535)
    tenant: str = Field(default="default_tenant", min_length=1)
    database: str = Field(default="default_database", min_length=1)
    api_key: SecretStr | None = Field(default=None, min_length=1)
    timeout: float = Field(default=10.0, gt=0)

    @model_validator(mode="after")
    def validate_authentication(self) -> ChromaRemoteVectorSettings:
        """禁止同时使用代理 Basic Auth 和 Chroma API Key。"""

        if self.api_key is not None and self.username is not None:
            raise ValueError("Chroma api_key 不能与 username/password 同时配置")
        return self


class ElasticsearchVectorSettings(RemoteVectorConnectionSettings):
    """配置远程 Elasticsearch 集群的异步客户端。"""

    driver: Literal["elasticsearch"]
    mode: Literal["remote"]
    port: int = Field(default=9200, ge=1, le=65535)
    verify_certs: bool = True
    ca_certs: str | None = Field(default=None, min_length=1)
    connections_per_node: int = Field(default=10, ge=1)
    max_retries: int = Field(default=3, ge=0)
    retry_on_timeout: bool = True
    timeout: float = Field(default=10.0, gt=0)


type VectorConnectionSettings = (
    MilvusLocalVectorSettings | MilvusRemoteVectorSettings | ChromaLocalVectorSettings | ChromaRemoteVectorSettings | ElasticsearchVectorSettings
)


def parse_vector_connection(raw_config: dict[str, object]) -> VectorConnectionSettings:
    """按 driver 和 mode 选择严格配置模型。"""

    driver = raw_config.get("driver")
    mode = raw_config.get("mode")
    model: type[VectorConnectionSettings]

    match (driver, mode):
        case ("milvus", "local"):
            model = MilvusLocalVectorSettings
        case ("milvus", "remote"):
            model = MilvusRemoteVectorSettings
        case ("chroma", "local"):
            model = ChromaLocalVectorSettings
        case ("chroma", "remote"):
            model = ChromaRemoteVectorSettings
        case ("elasticsearch", "remote"):
            model = ElasticsearchVectorSettings
        case _:
            raise ValueError(f"不支持向量驱动或运行模式：driver={driver!r}, mode={mode!r}")

    return model.model_validate(raw_config)
