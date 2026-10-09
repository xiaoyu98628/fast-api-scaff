"""为适配器提供统一键规则的 Redis 数据类型与受控脚本客户端。"""

from math import isnan

from app.infrastructure.cache.clients.managed import ManagedCacheClient
from app.infrastructure.cache.contracts.redis import RedisStorageProtocol
from app.infrastructure.cache.contracts.script import RedisScriptArgument
from app.infrastructure.cache.key import CacheKeyBuilder


class ManagedRedisCacheClient(ManagedCacheClient):
    """在公共缓存能力之外提供 Redis 数据类型和脚本执行能力。"""

    def __init__(
        self,
        storage: RedisStorageProtocol,
        key_builder: CacheKeyBuilder,
        default_ttl: int | None,
    ) -> None:
        """保存 Redis 聚合 Storage，同时复用公共 key 与 TTL 规则。"""

        super().__init__(storage, key_builder, default_ttl)
        self._redis_storage = storage

    async def execute_script(self, script: str, *, keys: tuple[str, ...], args: tuple[RedisScriptArgument, ...] = ()) -> object:
        """执行随代码发布的受信任脚本；所有 key 加前缀，结果由调用适配器校验。

        仅供基础设施适配器使用，不接受用户输入的脚本。脚本必须通过 KEYS 访问键，
        不从 ARGV 或脚本文本拼接键；该约定不是 Lua 沙箱，也不自动处理跨槽请求。
        """

        if not isinstance(script, str) or not script.strip():
            raise ValueError("Redis 脚本不能为空")
        if not isinstance(keys, tuple) or not keys:
            raise ValueError("Redis 脚本必须显式提供非空 key 元组")
        if not isinstance(args, tuple) or any(type(value) not in (str, bytes, int) for value in args):
            raise ValueError("Redis 脚本参数必须为字符串、字节或整数元组")
        normalized = tuple(self._key_builder.build(key) for key in keys)
        return await self._redis_storage.scripts.execute(script, normalized, args)

    async def expire(self, key: str, *, ttl: int) -> bool:
        """更新规范化后 key 的正整数 TTL，返回 key 是否存在。"""

        resolved_ttl = self._resolve_ttl(ttl)
        if resolved_ttl is None:
            raise ValueError("Redis 过期时间必须是正整数")

        return await self._redis_storage.keys.expire(
            self._key_builder.build(key),
            resolved_ttl,
        )

    async def ttl(self, key: str) -> int:
        """读取规范化后 key 的 Redis TTL 状态。"""

        return await self._redis_storage.keys.ttl(self._key_builder.build(key))

    async def set_if_absent(self, key: str, value: bytes, *, ttl_ms: int) -> bool:
        """以正整数毫秒 TTL 条件写入字节值，已存在返回 False；不使用默认 TTL。"""
        if not isinstance(value, bytes):
            raise TypeError("缓存值必须是 bytes")
        if type(ttl_ms) is not int or ttl_ms <= 0:
            raise ValueError("ttl_ms 必须为正整数")
        return await self._redis_storage.strings.set_if_absent(self._key_builder.build(key), value, ttl_ms)

    async def hash_get_all(self, key: str) -> dict[bytes, bytes]:
        """读取 Hash 全部字节字段，缺失时返回空字典，不进行业务解码。"""
        return await self._redis_storage.hashes.get_all(self._key_builder.build(key))

    async def hash_set(self, key: str, mapping: dict[str, bytes]) -> int:
        """写入非空字段字典，字段名为非空字符串，值为字节；返回新增字段数。"""
        if not isinstance(mapping, dict) or not mapping:
            raise ValueError("Hash 字段字典不能为空")
        if any(not isinstance(field, str) or not field or not isinstance(value, bytes) for field, value in mapping.items()):
            raise TypeError("Hash 字段必须为非空字符串，值必须为 bytes")
        return await self._redis_storage.hashes.set(self._key_builder.build(key), mapping)

    async def set_add(self, key: str, member: bytes) -> bool:
        """添加单个字节成员，已存在返回 False，不自动设置或刷新 TTL。"""
        if not isinstance(member, bytes):
            raise TypeError("Set 成员必须是 bytes")
        return await self._redis_storage.sets.add(self._key_builder.build(key), member)

    async def sorted_set_add(self, key: str, member: bytes, *, score: int | float, nx: bool = False) -> bool:
        """添加或更新单个成员，返回是否新增；nx 为真时保留已有分数。"""
        if not isinstance(member, bytes):
            raise TypeError("Sorted Set 成员必须是 bytes")
        _validate_score(score)
        if type(nx) is not bool:
            raise TypeError("Sorted Set nx 必须为 bool")
        return await self._redis_storage.sorted_sets.add(self._key_builder.build(key), member, score, nx=nx)

    async def sorted_set_remove(self, key: str, member: bytes) -> bool:
        """移除单个字节成员，返回是否存在；不读取或解释成员内容。"""
        if not isinstance(member, bytes):
            raise TypeError("Sorted Set 成员必须是 bytes")
        return await self._redis_storage.sorted_sets.remove(self._key_builder.build(key), member)

    async def sorted_set_range_by_score(
        self, key: str, *, minimum: int | float, maximum: int | float, count: int, offset: int = 0
    ) -> tuple[bytes, ...]:
        """读取闭区间内的字节成员，按分数升序和同分成员字节顺序返回。

        边界支持正负无穷；offset 为非负整数，count 为正整数。不移除成员，
        Redis 故障转换为 CacheOperationError，任务取消继续传播。
        """
        for bound in (minimum, maximum):
            _validate_score(bound)
        if type(offset) is not int or offset < 0 or type(count) is not int or count <= 0:
            raise ValueError("Sorted Set offset 必须为非负整数，count 必须为正整数")
        return await self._redis_storage.sorted_sets.range_by_score(self._key_builder.build(key), minimum, maximum, offset=offset, count=count)


def _validate_score(score: int | float) -> None:
    """拒绝 Redis 不接受的 NaN，以及混入分数的布尔值和非数字。"""
    if type(score) not in (int, float) or isinstance(score, float) and isnan(score):
        raise ValueError("Sorted Set 分数必须为数字且不能为 NaN")
