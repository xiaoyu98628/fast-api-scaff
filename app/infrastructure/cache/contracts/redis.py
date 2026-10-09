"""定义 Redis 数据类型操作及存储能力的组合协议。"""

from typing import Protocol, runtime_checkable

from app.infrastructure.cache.contracts.script import RedisScriptExecutor
from app.infrastructure.cache.contracts.storage import KeyValueStorage


class RedisKeyStorage(Protocol):
    """声明与值类型无关的 Redis Key 操作。"""

    async def delete(self, key: str) -> bool:
        """删除 key，返回是否存在。"""
        ...

    async def exists(self, key: str) -> bool:
        """返回 key 是否存在。"""
        ...

    async def expire(self, key: str, ttl: int) -> bool:
        """更新已有 key 的 TTL。"""

        ...

    async def ttl(self, key: str) -> int:
        """返回 Redis TTL 状态值。"""

        ...


class RedisStringStorage(Protocol):
    """声明 Redis String 的字节读写和条件写入操作。"""

    async def get(self, key: str) -> bytes | None:
        """读取字节值，key 不存在时返回 None。"""
        ...

    async def set(self, key: str, value: bytes, ttl: int | None) -> bool:
        """写入字节值和可选秒级 TTL。"""
        ...

    async def set_if_absent(self, key: str, value: bytes, ttl_ms: int) -> bool:
        """以 NX 和毫秒 TTL 写入，返回是否成功创建。"""
        ...


class RedisHashStorage(Protocol):
    """声明 Hash 字节字段读写。"""

    async def get_all(self, key: str) -> dict[bytes, bytes]:
        """读取全部字段，缺失时返回空字典。"""
        ...

    async def set(self, key: str, mapping: dict[str, bytes]) -> int:
        """写入指定字段，返回新增字段数。"""
        ...


class RedisSetStorage(Protocol):
    """声明单成员 Set 写入。"""

    async def add(self, key: str, member: bytes) -> bool:
        """成员首次加入返回 True，已存在返回 False。"""
        ...


class RedisSortedSetStorage(Protocol):
    """声明有序集合的字节成员查询和写入能力。"""

    async def add(self, key: str, member: bytes, score: int | float, *, nx: bool) -> bool:
        """添加或更新成员，返回是否新增，nx 为真时不更新已有成员。"""
        ...

    async def remove(self, key: str, member: bytes) -> bool:
        """移除成员，返回是否存在。"""
        ...

    async def range_by_score(self, key: str, minimum: int | float, maximum: int | float, *, offset: int, count: int) -> tuple[bytes, ...]:
        """读取闭区间内按分数升序排列的成员，不移除成员。"""

        ...


@runtime_checkable
class RedisStorageProtocol(KeyValueStorage, Protocol):
    """在公共 KV 能力之外暴露 Redis 数据类型和脚本执行能力。"""

    @property
    def keys(self) -> RedisKeyStorage:
        """返回借用的通用 Key 操作入口。"""
        ...

    @property
    def hashes(self) -> RedisHashStorage:
        """返回借用的 Hash 操作入口。"""
        ...

    @property
    def sets(self) -> RedisSetStorage:
        """返回借用的 Set 操作入口。"""
        ...

    @property
    def strings(self) -> RedisStringStorage:
        """返回借用的 String 操作入口。"""

        ...

    @property
    def sorted_sets(self) -> RedisSortedSetStorage:
        """返回借用的 Sorted Set 操作入口。"""

        ...

    @property
    def scripts(self) -> RedisScriptExecutor:
        """返回借用的脚本执行入口。"""

        ...
