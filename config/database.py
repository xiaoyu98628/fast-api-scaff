"""数据库连接与连接池参数（前缀 ``DB_``）；提供异步 URL 与 Alembic 用同步 URL。"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

from config import BASE_DIR


class DatabaseSettings(BaseSettings):
    """MySQL 示例：异步驱动 ``aiomysql``，迁移使用 ``pymysql``。"""
    model_config = SettingsConfigDict(
        env_file=BASE_DIR.joinpath(".env"),
        env_file_encoding="utf-8",
        env_prefix="DB_",
        extra="ignore",
    )

    host: str = "127.0.0.1"
    port: int = 3306
    database: str = "fast-api"
    username: str = "root"
    password: str = "root"

    echo: bool = False
    pool_size: int = 10
    max_overflow: int = 20

    charset: str = Field(
        default="utf8mb4",
        description="写入连接 URL 的 charset 参数，对应环境变量 DB_CHARSET。",
    )

    @property
    def url(self) -> URL:
        """数据库连接 URL（异步）"""
        return URL.create(
            drivername="mysql+aiomysql",
            username=self.username,
            password=self.password,
            host=self.host,
            port=self.port,
            database=self.database,
            query={"charset": self.charset},
        )

    @property
    def sync_url(self) -> str:
        """同步数据库连接 URL（用于 Alembic 等工具）"""
        u = URL.create(
            drivername="mysql+pymysql",
            username=self.username,
            password=self.password,
            host=self.host,
            port=self.port,
            database=self.database,
            query={"charset": self.charset},
        )
        return u.render_as_string(hide_password=False)
