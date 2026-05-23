from abc import ABC, abstractmethod

from sqlalchemy.ext.asyncio import AsyncEngine

from config.database import DatabaseConfig, DbDriver


class Connector(ABC):
    """连接器基类，负责建立底层 Engine（对应 Laravel Connectors\\Connector）。"""

    driver: DbDriver

    @abstractmethod
    def connect(self, database_config: DatabaseConfig) -> AsyncEngine:
        """根据配置创建 Engine。"""
