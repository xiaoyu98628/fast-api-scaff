"""提供不进入生产驱动注册表的缓存测试替身。"""

from app.infrastructure.cache.contracts.provider import CacheResourceDefinition
from app.infrastructure.cache.errors import CacheConfigurationError
from app.infrastructure.cache.resource import CacheResource


class FakeCacheConnection:
    """提供无需外部服务的测试生命周期。"""

    def __init__(self) -> None:
        self.closed = False

    async def ping(self) -> bool:
        """报告测试连接是否仍然开放。"""

        return not self.closed

    async def aclose(self) -> None:
        """标记测试连接已经关闭。"""

        self.closed = True


class FakeCacheStorage:
    """为缓存管理器测试提供最小字节级 KV 行为。"""

    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}

    async def get(self, key: str) -> bytes | None:
        """读取测试值，未命中时返回 None。"""

        return self.values.get(key)

    async def set(self, key: str, value: bytes, ttl: int | None) -> bool:
        """保存测试值；TTL 已由生产公共客户端完成校验。"""

        self.values[key] = value
        return True

    async def delete(self, key: str) -> bool:
        """删除测试值，并返回删除前是否存在。"""

        return self.values.pop(key, None) is not None

    async def exists(self, key: str) -> bool:
        """报告测试值是否存在。"""

        return key in self.values


class FakeCacheProvider:
    """为测试装配独立连接和 Storage，不注册到生产默认集合。"""

    def __init__(self, driver: str = "fake") -> None:
        self.driver = driver

    def prepare(self, raw_config: dict[str, object]) -> CacheResourceDefinition:
        """校验测试配置，并返回延迟资源定义。"""

        unexpected = set(raw_config) - {"driver", "key_prefix"}
        key_prefix = raw_config.get("key_prefix", "")
        if unexpected or not isinstance(key_prefix, str):
            raise CacheConfigurationError("Fake 缓存配置不合法")
        return CacheResourceDefinition(key_prefix=key_prefix, factory=self._create)

    async def _create(self) -> CacheResource:
        """为单个命名连接创建隔离的测试资源。"""

        return CacheResource(
            connection=FakeCacheConnection(),
            storage=FakeCacheStorage(),
        )
