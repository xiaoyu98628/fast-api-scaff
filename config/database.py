from functools import cached_property

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from config.settings import BASE_SETTINGS_CONFIG
from paths import BASE_DIR


class ConnectionConfig(BaseModel):
    """单个数据库连接配置（对应 Laravel connections 数组中的一项）。"""

    driver: str
    host: str | None = None
    port: int | None = None
    database: str | None = None
    username: str | None = None
    password: str | None = None
    charset: str | None = None
    prefix: str = ""


class DatabaseConfig(BaseSettings):
    """数据库配置（对应 Laravel config/database.php）。"""

    model_config = SettingsConfigDict(
        **BASE_SETTINGS_CONFIG,
        env_prefix="DB_",
    )

    connection: str = Field(default="mysql", description="默认连接名")
    echo: bool = Field(default=False, description="是否打印 SQL 语句")
    pool_size: int = Field(default=10, description="连接池大小")
    max_overflow: int = Field(default=20, description="连接池溢出大小")

    mysql_host: str = Field(default="127.0.0.1", description="MySQL 主机")
    mysql_port: int = Field(default=3306, description="MySQL 端口")
    mysql_database: str = Field(default="fast-api", description="MySQL 库名")
    mysql_username: str = Field(default="", description="MySQL 用户名")
    mysql_password: str = Field(default="", description="MySQL 密码")
    mysql_prefix: str = Field(default="", description="MySQL 表名前缀")
    mysql_charset: str = Field(default="utf8mb4", description="MySQL 字符集")

    pgsql_host: str = Field(default="127.0.0.1", description="PostgreSQL 主机")
    pgsql_port: int = Field(default=5432, description="PostgreSQL 端口")
    pgsql_database: str = Field(default="fast-api", description="PostgreSQL 库名")
    pgsql_username: str = Field(default="", description="PostgreSQL 用户名")
    pgsql_password: str = Field(default="", description="PostgreSQL 密码")
    pgsql_prefix: str = Field(default="", description="PostgreSQL 表名前缀")

    sqlite_database: str = Field(default="database/database.sqlite", description="SQLite 文件路径")

    @cached_property
    def connections(self) -> dict[str, ConnectionConfig]:
        return {
            "mysql": ConnectionConfig(
                driver="mysql",
                host=self.mysql_host,
                port=self.mysql_port,
                database=self.mysql_database,
                username=self.mysql_username,
                password=self.mysql_password,
                charset=self.mysql_charset,
                prefix=self.mysql_prefix,
            ),
            "sqlite": ConnectionConfig(
                driver="sqlite",
                database=str(BASE_DIR / self.sqlite_database),
            ),
            "pgsql": ConnectionConfig(
                driver="pgsql",
                host=self.pgsql_host,
                port=self.pgsql_port,
                database=self.pgsql_database,
                username=self.pgsql_username,
                password=self.pgsql_password,
                prefix=self.pgsql_prefix,
            ),
        }

    def configuration(self, name: str) -> ConnectionConfig:
        try:
            return self.connections[name]
        except KeyError:
            raise ValueError(f"Database connection [{name}] not configured.") from None
