from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy import URL


@dataclass(frozen=True, slots=True)
class DatabaseEngineSpec:
    """创建 SQLAlchemy Engine 所需的 URL 和驱动参数。"""

    url: URL
    options: Mapping[str, object]
