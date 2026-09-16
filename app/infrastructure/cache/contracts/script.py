"""定义 Redis 脚本参数与不包含场景策略的执行协议。"""

from typing import Protocol

type RedisScriptArgument = str | bytes | int


class RedisScriptExecutor(Protocol):
    """为基础设施适配器执行受信任脚本，不解释脚本的业务结果。"""

    async def execute(self, script: str, keys: tuple[str, ...], args: tuple[RedisScriptArgument, ...]) -> object:
        """使用已规范化 key 执行脚本，返回原始结果，驱动故障转换为缓存异常。"""

        ...
