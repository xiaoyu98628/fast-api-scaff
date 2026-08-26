import time
from collections.abc import Callable


class MemoryCacheConnection:
    """保存单进程内存缓存的数据资源并管理其生命周期。"""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._values: dict[str, tuple[bytes, float | None]] = {}

    @property
    def values(self) -> dict[str, tuple[bytes, float | None]]:
        return self._values

    def now(self) -> float:
        return self._clock()

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        self._values.clear()
