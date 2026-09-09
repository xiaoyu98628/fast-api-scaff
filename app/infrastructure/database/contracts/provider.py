"""定义数据库 Provider 的扩展契约和校验结果。"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncEngine

from app.infrastructure.database.connections.spec import DatabaseEngineSpec

type DatabaseEngineConfigurator = Callable[[AsyncEngine], None]


@dataclass(frozen=True, slots=True)
class DatabaseResourceDefinition:
    """已经完成配置校验、等待延迟创建的数据库资源定义。"""

    engine_spec: DatabaseEngineSpec
    configure_engine: DatabaseEngineConfigurator | None = None


class DatabaseProvider(Protocol):
    """数据库驱动配置校验和 Engine 配置构建入口。"""

    @property
    def drivers(self) -> tuple[str, ...]:
        """返回该 Provider 能处理的全部驱动名称。"""

        ...

    def prepare(self, raw_config: dict[str, object]) -> DatabaseResourceDefinition:
        """严格校验原始配置，并返回尚未创建 Engine 的资源定义。"""

        ...
