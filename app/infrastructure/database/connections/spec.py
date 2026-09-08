"""定义 Provider 与 Engine 工厂之间的驱动无关资源规格。"""

from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy import URL


@dataclass(frozen=True, slots=True)
class DatabaseEngineSpec:
    """创建 SQLAlchemy Engine 所需的 URL、驱动参数和日志参数。"""

    url: URL
    options: Mapping[str, object]
    log_queries: bool = False
    slow_query_ms: int = 500
