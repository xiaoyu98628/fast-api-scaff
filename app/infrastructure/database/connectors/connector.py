from abc import ABC, abstractmethod

from sqlalchemy import URL
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from config.database import ConnectionConfig, DatabaseConfig


class BaseConnector(ABC):
    """驱动连接器：根据连接配置组装 URL 并创建 AsyncEngine。"""

    def connect(self, connection_config: ConnectionConfig, *, database_config: DatabaseConfig) -> AsyncEngine:
        url = self.make_url(connection_config)
        return create_async_engine(url, **self.engine_options(connection_config, database_config))

    @abstractmethod
    def make_url(self, connection_config: ConnectionConfig) -> URL | str:
        """组装 SQLAlchemy 连接 URL。"""

    @abstractmethod
    def engine_options(self, connection_config: ConnectionConfig, database_config: DatabaseConfig) -> dict:
        """返回传给 create_async_engine 的引擎参数。"""
