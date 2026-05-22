from enum import StrEnum
from functools import cached_property
from pathlib import Path
from typing import Final

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

from paths import DATABASE_DIR, ENV_FILE


class DbDriver(StrEnum):
    MYSQL = "mysql"
    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"

ASYNC_DRIVERS: Final[dict[DbDriver, str]] = {
    DbDriver.MYSQL: "mysql+aiomysql",
    DbDriver.SQLITE: "sqlite+aiosqlite",
    DbDriver.POSTGRESQL: "postgresql+asyncpg",
}

SYNC_DRIVERS: Final[dict[DbDriver, str]] = {
    DbDriver.MYSQL: "mysql+pymysql",
    DbDriver.SQLITE: "sqlite",
    DbDriver.POSTGRESQL: "postgresql+psycopg2",
}


class DatabaseConfig(BaseSettings):
    """数据库配置"""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        env_prefix="DB_",
        extra="ignore",
    )

    # 当前默认连接
    connection: DbDriver = Field(default=DbDriver.MYSQL, alias="CONNECTION", description="默认连接名")

    # 通用配置
    host: str = Field(default="127.0.0.1", description="主机")
    port: int | None = Field(default=None, description="端口；未设置时按驱动使用默认值")

    database: str = Field(default="fast-api", description="库名")
    username: str = Field(default="", description="用户名")
    password: str = Field(default="", description="密码")

    # 表前缀
    prefix: str = Field(default="", description="表名前缀")

    # mysql 专用
    charset: str = Field(default="utf8mb4", description="字符集")

    # sqlite 专用
    sqlite_path: Path = Field(default_factory=lambda: DATABASE_DIR / "database.db", description="SQLite 文件路径")

    # sqlalchemy
    echo: bool = False
    pool_size: int = 10
    max_overflow: int = 20

    def _build_url(self, driver: DbDriver, drivername: str) -> URL:
        match driver:
            case DbDriver.SQLITE:
                return URL.create(
                    drivername=drivername,
                    database=str(self.sqlite_path)
                )
            case DbDriver.MYSQL:
                return URL.create(
                    drivername=drivername,
                    username=self.username,
                    password=self.password,
                    host=self.host,
                    port=self.port or 3306,
                    database=self.database,
                    query={"charset": self.charset},
                )
            case DbDriver.POSTGRESQL:
                return URL.create(
                    drivername=drivername,
                    username=self.username,
                    password=self.password,
                    host=self.host,
                    port=self.port or 5432,
                    database=self.database,
                )

    def _build_connections(
            self,
            drivers: dict[DbDriver, str],
            *,
            as_string: bool = False,
    ) -> dict[DbDriver, URL | str]:
        """ 构建连接集合 """
        result = {}
        for driver, drivername in drivers.items():
            url = self._build_url(driver, drivername)
            result[driver] = (
                url.render_as_string(hide_password=False)
                if as_string
                else url
            )

        return result

    @cached_property
    def async_connections(self) -> dict[DbDriver, URL | str]:
        """异步连接"""
        return self._build_connections(ASYNC_DRIVERS)

    @cached_property
    def sync_connections(self) -> dict[DbDriver, URL | str]:
        """同步连接"""
        return self._build_connections( SYNC_DRIVERS, as_string=True, )
