from abc import ABC, abstractmethod
from typing import ClassVar

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from config.database import DatabaseConfig, DbDriver


class BaseConnector(ABC):
    """驱动连接器：根据配置创建 AsyncEngine。"""

    driver: ClassVar[DbDriver]

    def connect(self, database_config: DatabaseConfig) -> AsyncEngine:
        url = database_config.async_connections[self.driver]
        return create_async_engine(url, **self.engine_options(database_config))

    @abstractmethod
    def engine_options(self, database_config: DatabaseConfig) -> dict:
        """返回传给 create_async_engine 的引擎参数。"""
