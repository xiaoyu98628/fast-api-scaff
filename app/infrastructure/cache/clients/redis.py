"""为需要 Redis 原子语义的适配器提供受控客户端。"""

from app.infrastructure.cache.clients.managed import ManagedCacheClient
from app.infrastructure.cache.contracts.redis import RedisAtomicStorage
from app.infrastructure.cache.contracts.script import RedisScriptArgument
from app.infrastructure.cache.key import CacheKeyBuilder


class ManagedRedisCacheClient(ManagedCacheClient):
    """在公共缓存能力之外提供 Redis TTL 和受控脚本执行能力。"""

    def __init__(
        self,
        storage: RedisAtomicStorage,
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

        return await self._redis_storage.strings.expire(
            self._key_builder.build(key),
            resolved_ttl,
        )

    async def ttl(self, key: str) -> int:
        """读取规范化后 key 的 Redis TTL 状态。"""

        return await self._redis_storage.strings.ttl(self._key_builder.build(key))
