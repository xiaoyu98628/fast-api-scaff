from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from app.infrastructure.cache.resource import CacheResource

type CacheResourceFactory = Callable[[], Awaitable[CacheResource]]


@dataclass(frozen=True, slots=True)
class CacheResourceDefinition:
    """已经完成配置校验、等待延迟创建的缓存资源定义。"""

    key_prefix: str
    factory: CacheResourceFactory


class CacheProvider(Protocol):
    """缓存驱动配置校验和资源创建入口。"""

    driver: str

    def prepare(self, raw_config: dict[str, object]) -> CacheResourceDefinition: ...
