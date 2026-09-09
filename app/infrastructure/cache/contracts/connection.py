"""定义缓存原生连接的健康检查与关闭契约。"""

from typing import Protocol


class CacheConnection(Protocol):
    """缓存原生连接资源需要实现的生命周期能力。"""

    async def ping(self) -> bool:
        """执行驱动原生健康检查并返回是否成功。"""

        ...

    async def aclose(self) -> None:
        """释放驱动拥有的连接资源。"""

        ...
