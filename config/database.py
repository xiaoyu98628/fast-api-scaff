from enum import StrEnum
from functools import cached_property
from typing import Final

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

from paths import BASE_DIR, ENV_FILE


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
    connection: DbDriver = Field(default=DbDriver.MYSQL, description="默认连接名")

    # mysql
    mysql_host: str = Field(default="127.0.0.1", description="主机")
    mysql_port: int = Field(default=3306, description="端口")
    mysql_database: str = Field(default="fast-api", description="库名")
    mysql_username: str = Field(default="", description="用户名")
    mysql_password: str = Field(default="", description="密码")
    mysql_prefix: str = Field(default="", description="表名前缀")
    mysql_charset: str = Field(default="utf8mb4", description="字符集")

    # postgresql
    postgresql_host: str = Field(default="127.0.0.1", description="主机")
    postgresql_port: int = Field(default=5432, description="端口")
    postgresql_database: str = Field(default="fast-api", description="库名")
    postgresql_username: str = Field(default="", description="用户名")
    postgresql_password: str = Field(default="", description="密码")
    postgresql_prefix: str = Field(default="", description="表名前缀")

    # sqlite
    sqlite_file: str = Field(default="database/database.sqlite", description="SQLite 文件名")

    # sqlalchemy
    echo: bool = Field(default=False, description="是否打印 SQL 语句")
    pool_size: int = Field(default=10, description="连接池大小")
    max_overflow: int = Field(default=20, description="连接池溢出大小")

    def _build_url(self, driver: DbDriver, drivername: str) -> URL:
        match driver:
            case DbDriver.SQLITE:
                return URL.create(
                    drivername=drivername,
                    database=f"{BASE_DIR}/{self.sqlite_file}"
                )
            case DbDriver.MYSQL:
                return URL.create(
                    drivername=drivername,
                    username=self.mysql_username,
                    password=self.mysql_password,
                    host=self.mysql_host,
                    port=self.mysql_port,
                    database=self.mysql_database,
                    query={"charset": self.mysql_charset},
                )
            case DbDriver.POSTGRESQL:
                return URL.create(
                    drivername=drivername,
                    username=self.postgresql_username,
                    password=self.postgresql_password,
                    host=self.postgresql_host,
                    port=self.postgresql_port,
                    database=self.postgresql_database,
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
        return self._build_connections(SYNC_DRIVERS, as_string=True)


if __name__ == '__main__':
    a = DatabaseConfig()

    print(a.sync_connections)
    print(a.async_connections)
