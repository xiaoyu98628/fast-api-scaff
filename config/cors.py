"""跨域配置（前缀 ``CORS_``）。"""

from pydantic_settings import BaseSettings, SettingsConfigDict

from config import BASE_DIR


class CorsSettings(BaseSettings):
    """CORS 相关环境变量。"""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR.joinpath(".env"),
        env_file_encoding="utf-8",
        env_prefix="CORS_",
        extra="ignore",
    )

    allow_origins: list[str] = ["*"]
    allow_methods: list[str] = ["*"]
    allow_headers: list[str] = ["*"]
    allow_credentials: bool = True
    allowed_origins_patterns: list[str] = []
    exposed_headers: list[str] = []
    max_age: int = 600
