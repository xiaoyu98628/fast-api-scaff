"""Redis 连接串构建（前缀 ``REDIS_*``）。"""

from pydantic_settings import BaseSettings, SettingsConfigDict

from config import BASE_DIR


class RedisSettings(BaseSettings):
    """Redis 配置。"""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR.joinpath(".env"),
        env_file_encoding="utf-8",
        env_prefix="REDIS_",
        extra="ignore",
    )

    host: str = "127.0.0.1"
    port: int = 6379
    db: int = 0
    password: str | None = None
    decode_responses: bool = True

    @property
    def url(self) -> str:
        if self.password:
            return f"redis://:{self.password}@{self.host}:{self.port}/{self.db}"
        return f"redis://{self.host}:{self.port}/{self.db}"
