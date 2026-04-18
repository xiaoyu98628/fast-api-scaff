"""JWT 相关配置（前缀 ``JWT_``）。"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from config import BASE_DIR


class JwtSettings(BaseSettings):
    """JWT 发行配置。"""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR.joinpath(".env"),
        env_file_encoding="utf-8",
        env_prefix="JWT_",
        extra="ignore",
    )

    secret_key: str = Field(
        default="please-change-me-at-least-32-bytes",
        description="JWT 签名密钥（HS256 建议至少 32 字节）。",
    )
    algorithm: str = Field(default="HS256", description="JWT 签名算法。")
    access_token_expire_minutes: int = Field(default=120, description="访问令牌有效期（分钟）。")
