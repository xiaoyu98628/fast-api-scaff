"""通过借用的 Redis 连接执行脚本，不持有场景策略或资源生命周期。"""

from app.infrastructure.cache.contracts.script import RedisScriptArgument
from app.infrastructure.cache.errors import CacheOperationError
from app.infrastructure.cache.storages.redis.base import BaseRedisStorage


class RedisScriptExecutor(BaseRedisStorage):
    """提供原始脚本执行与驱动异常转换，结果语义由调用方负责。"""

    async def execute(self, script: str, keys: tuple[str, ...], args: tuple[RedisScriptArgument, ...]) -> object:
        """执行已由受管客户端规范化的 key；原样返回结果并传播任务取消。"""

        try:
            return await self._client.eval(script, len(keys), *keys, *args)
        except Exception as error:
            raise CacheOperationError("Redis 脚本执行失败") from error
