from abc import ABC, abstractmethod

from sqlalchemy import URL, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from config.database import ConnectionConfig, DatabaseConfig


class BaseConnector(ABC):
    """驱动连接器：根据连接配置组装 URL，支持异步（应用）与同步（迁移）。"""

    def connect(self, connection_config: ConnectionConfig, *, database_config: DatabaseConfig) -> AsyncEngine:
        url = self.make_async_url(connection_config)
        return create_async_engine(url, **self.engine_options(connection_config, database_config))

    def connect_sync(self, connection_config: ConnectionConfig, *, database_config: DatabaseConfig) -> Engine:
        url = self.make_sync_url(connection_config)
        return create_engine(url, **self.engine_options(connection_config, database_config))

    def engine_options(self, connection_config: ConnectionConfig, database_config: DatabaseConfig) -> dict:
        options: dict = {
            "echo": database_config.echo,
            "pool_size": database_config.pool_size,
            "max_overflow": database_config.max_overflow,
        }
        options.update(self._driver_engine_options(connection_config, database_config))
        return options

    def _driver_engine_options(self, connection_config: ConnectionConfig, database_config: DatabaseConfig) -> dict:
        """驱动特有引擎参数，由子类覆盖。"""
        return {}

    @abstractmethod
    def make_async_url(self, connection_config: ConnectionConfig) -> URL | str:
        """组装异步 SQLAlchemy URL。"""

    @abstractmethod
    def make_sync_url(self, connection_config: ConnectionConfig) -> URL | str:
        """组装同步 SQLAlchemy URL（Alembic / 迁移）。"""
