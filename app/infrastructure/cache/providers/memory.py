"""把 Memory 配置转换为进程内缓存资源定义。"""

from app.config.cache import MemoryCacheSettings
from app.infrastructure.cache.connections.memory import MemoryCacheConnection
from app.infrastructure.cache.contracts.provider import CacheResourceDefinition
from app.infrastructure.cache.resource import CacheResource
from app.infrastructure.cache.storages.memory import MemoryCacheStorage


class MemoryCacheProvider:
    """装配不依赖外部服务的连接和字节 Storage。"""

    driver = "memory"

    def prepare(self, raw_config: dict[str, object]) -> CacheResourceDefinition:
        """校验 Memory 驱动只包含支持的配置字段。"""

        settings = MemoryCacheSettings.model_validate(raw_config)
        return CacheResourceDefinition(
            key_prefix=settings.key_prefix,
            factory=self._create,
        )

    async def _create(self) -> CacheResource:
        """为单个 Manager 生命周期创建独立内存字典。"""

        connection = MemoryCacheConnection()
        return CacheResource(
            connection=connection,
            storage=MemoryCacheStorage(connection),
        )
