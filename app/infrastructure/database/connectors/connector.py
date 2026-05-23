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

    @abstractmethod
    def make_async_url(self, connection_config: ConnectionConfig) -> URL | str:
        """组装异步 SQLAlchemy URL。"""

    @abstractmethod
    def make_sync_url(self, connection_config: ConnectionConfig) -> URL | str:
        """组装同步 SQLAlchemy URL（Alembic / 迁移）。"""

    @abstractmethod
    def engine_options(self, connection_config: ConnectionConfig, database_config: DatabaseConfig) -> dict:
        """返回传给 create_engine / create_async_engine 的引擎参数。"""
