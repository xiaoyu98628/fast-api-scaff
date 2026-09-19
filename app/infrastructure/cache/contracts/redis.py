"""定义 Redis String 过期操作及 Redis 存储能力的组合协议。"""

from typing import Protocol, runtime_checkable

from app.infrastructure.cache.contracts.script import RedisScriptExecutor
from app.infrastructure.cache.contracts.storage import KeyValueStorage


class RedisStringStorage(Protocol):
    """声明 Redis String 的过期时间操作。"""

    async def expire(self, key: str, ttl: int) -> bool:
        """更新已有 key 的 TTL。"""

        ...

    async def ttl(self, key: str) -> int:
        """返回 Redis TTL 状态值。"""

        ...


@runtime_checkable
class RedisAtomicStorage(KeyValueStorage, Protocol):
    """在公共 KV 能力之外暴露 Redis TTL 与脚本执行能力。"""

    @property
    def strings(self) -> RedisStringStorage:
        """返回借用的 String 操作入口。"""

        ...

    @property
    def scripts(self) -> RedisScriptExecutor:
        """返回借用的脚本执行入口。"""

        ...
