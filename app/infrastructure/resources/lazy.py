"""提供可并发访问且可显式关闭的异步懒加载资源。"""

import asyncio
from collections.abc import Awaitable, Callable


class AsyncLazy[T]:
    """并发安全地延迟创建和关闭单个异步资源。"""

    def __init__(
        self,
        factory: Callable[[], Awaitable[T]],
        closer: Callable[[T], Awaitable[None]],
    ) -> None:
        """保存创建与关闭回调，但暂不创建实际资源。"""

        self._factory = factory
        self._closer = closer
        self._value: T | None = None
        self._lock = asyncio.Lock()
        self._closed = False

    @property
    def initialized(self) -> bool:
        """返回底层资源当前是否已经成功创建。"""

        return self._value is not None

    def begin_close(self) -> None:
        """在等待初始化或释放资源前，同步阻止新的获取。"""

        self._closed = True

    async def get(self) -> T:
        """创建或复用资源，并保证并发调用只执行一次工厂。"""

        if self._closed:
            raise RuntimeError("异步资源已经关闭")

        # 创建和关闭共用同一把锁，避免资源刚创建就与关闭操作交错。
        async with self._lock:
            if self._closed:
                raise RuntimeError("异步资源已经关闭")

            if self._value is None:
                self._value = await self._factory()

            if self._closed:
                raise RuntimeError("异步资源已经关闭")

            return self._value

    async def aclose(self) -> None:
        """禁止后续访问，并关闭已经创建的底层资源。"""

        # 先同步封闭入口，使等待锁的新调用也不能再次取得资源。
        self.begin_close()
        async with self._lock:
            if self._value is None:
                return

            # 仅在成功关闭后清空引用，失败时保留状态供上层记录或重试。
            await self._closer(self._value)
            self._value = None
