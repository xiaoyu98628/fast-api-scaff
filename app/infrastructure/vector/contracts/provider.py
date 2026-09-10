"""定义向量驱动 Provider 及延迟资源工厂。"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from app.infrastructure.vector.resource import VectorResource

type VectorResourceFactory = Callable[[], Awaitable[VectorResource]]


@dataclass(frozen=True, slots=True)
class VectorResourceDefinition:
    """保存严格校验后、尚未创建客户端的资源工厂。"""

    factory: VectorResourceFactory


class VectorProvider(Protocol):
    """把某个 driver 的原始配置转换为延迟资源定义。"""

    driver: str

    def prepare(self, raw_config: dict[str, object]) -> VectorResourceDefinition:
        """校验驱动配置并返回不产生外部连接的资源定义。"""

        ...
