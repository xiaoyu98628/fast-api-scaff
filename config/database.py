from enum import StrEnum
from typing import Final, Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

from paths import ENV_FILE


class DbDriver(StrEnum):
    MYSQL = "mysql"
    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"


_ASYNC_DRIVER: Final[dict[DbDriver, str]] = {
    DbDriver.MYSQL: "mysql+aiomysql",
    DbDriver.SQLITE: "sqlite+aiosqlite",
    DbDriver.POSTGRESQL: "postgresql+asyncpg",
}

_SYNC_DRIVER: Final[dict[DbDriver, str]] = {
    DbDriver.MYSQL: "mysql+pymysql",
    DbDriver.SQLITE: "sqlite",
    DbDriver.POSTGRESQL: "postgresql+psycopg2",
}

_PORT_DEFAULTS: Final[dict[DbDriver, int]] = {
    DbDriver.MYSQL: 3306,
    DbDriver.POSTGRESQL: 5432,
}


class DatabaseConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        env_prefix="DB_",
        extra="ignore",
    )

    driver: DbDriver = Field(default=DbDriver.MYSQL, description="数据库类型")
    host: str = Field(default="127.0.0.1", description="主机")
    port: int | None = Field(default=None, description="端口；未设置时按驱动使用默认值")
    database: str = Field(default="fast-api", description="库名或 SQLite 文件路径")
    username: str = Field(default="", description="用户名")
    password: str = Field(default="", description="密码")
    prefix: str = Field(default="", description="表名前缀")
    charset: str = Field(default="utf8mb4", description="字符集（仅 MySQL）")

    echo: bool = False
    pool_size: int = 10
    max_overflow: int = 20

    @model_validator(mode="after")
    def _apply_driver_defaults(self) -> Self:
        if self.driver != DbDriver.SQLITE and self.port is None:
            self.port = _PORT_DEFAULTS[self.driver]
        return self

    def _drivername(self, *, async_: bool) -> str:
        return (_ASYNC_DRIVER if async_ else _SYNC_DRIVER)[self.driver]

    def _network_port(self) -> int:
        return self.port if self.port is not None else _PORT_DEFAULTS[self.driver]

    def _build_url(self, drivername: str) -> URL:
        match self.driver:
            case DbDriver.SQLITE:
                return URL.create(drivername=drivername, database=self.database)
            case DbDriver.MYSQL:
                return URL.create(
                    drivername=drivername,
                    username=self.username,
                    password=self.password,
                    host=self.host,
                    port=self._network_port(),
                    database=self.database,
                    query={"charset": self.charset},
                )
            case DbDriver.POSTGRESQL:
                return URL.create(
                    drivername=drivername,
                    username=self.username,
                    password=self.password,
                    host=self.host,
                    port=self._network_port(),
                    database=self.database,
                )

    @property
    def url(self) -> URL:
        """异步连接 URL（create_async_engine）。"""
        return self._build_url(self._drivername(async_=True))

    @property
    def sync_url(self) -> str:
        """同步连接 URL 字符串（Alembic 等）。"""
        return self._build_url(self._drivername(async_=False)).render_as_string(
            hide_password=False
        )
