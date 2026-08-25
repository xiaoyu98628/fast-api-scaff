from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from app.infrastructure.cache.contracts.backend import CacheBackend

type CacheBackendFactory = Callable[[], Awaitable[CacheBackend]]


@dataclass(frozen=True, slots=True)
class CacheBackendDefinition:
    """已经完成配置校验、等待延迟创建的缓存后端定义。"""

    key_prefix: str
    factory: CacheBackendFactory


class CacheProvider(Protocol):
    """缓存驱动配置校验和后端创建入口。"""

    driver: str

    def prepare(self, raw_config: dict[str, object]) -> CacheBackendDefinition: ...
