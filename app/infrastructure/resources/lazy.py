import asyncio
from collections.abc import Awaitable, Callable


class AsyncLazy[T]:
    """并发安全地延迟创建和关闭单个异步资源。"""

    def __init__(
        self,
        factory: Callable[[], Awaitable[T]],
        closer: Callable[[T], Awaitable[None]],
    ) -> None:
        self._factory = factory
        self._closer = closer
        self._value: T | None = None
        self._lock = asyncio.Lock()
        self._closed = False

    @property
    def initialized(self) -> bool:
        return self._value is not None

    def begin_close(self) -> None:
        """在等待初始化或释放资源前，同步阻止新的获取。"""
        self._closed = True

    async def get(self) -> T:
        if self._closed:
            raise RuntimeError("异步资源已经关闭")

        async with self._lock:
            if self._closed:
                raise RuntimeError("异步资源已经关闭")

            if self._value is None:
                self._value = await self._factory()

            if self._closed:
                raise RuntimeError("异步资源已经关闭")

            return self._value

    async def aclose(self) -> None:
        self.begin_close()
        async with self._lock:
            if self._value is None:
                return

            await self._closer(self._value)
            self._value = None
