"""保存进程内缓存数据和可替换的单调时钟。"""

import time
from collections.abc import Callable


class MemoryCacheConnection:
    """保存单进程数据；不提供跨进程共享、后台清理或显式并发锁。"""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._values: dict[str, tuple[bytes, float | None]] = {}

    @property
    def values(self) -> dict[str, tuple[bytes, float | None]]:
        """提供给同一资源内的 Memory Storage 访问底层数据。"""

        return self._values

    def now(self) -> float:
        """返回只用于计算相对 TTL 的单调时间。"""

        return self._clock()

    async def ping(self) -> bool:
        """进程内资源构造完成后始终可用。"""

        return True

    async def aclose(self) -> None:
        """清空当前进程持有的全部缓存数据。"""

        self._values.clear()
