from dataclasses import dataclass
from typing import Protocol

from app.infrastructure.database.connections.spec import DatabaseEngineSpec


@dataclass(frozen=True, slots=True)
class DatabaseResourceDefinition:
    """已经完成配置校验、等待延迟创建的数据库资源定义。"""

    engine_spec: DatabaseEngineSpec


class DatabaseProvider(Protocol):
    """数据库驱动配置校验和 Engine 配置构建入口。"""

    @property
    def drivers(self) -> tuple[str, ...]: ...

    def prepare(self, raw_config: dict[str, object]) -> DatabaseResourceDefinition: ...
