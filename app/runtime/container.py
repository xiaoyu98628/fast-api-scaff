"""保存跨宿主共享的应用依赖并统一执行生命周期回调。"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from anyio import CancelScope

from app.contexts.user.composition import UserContext
from app.infrastructure.cache.manager import CacheManager
from app.infrastructure.database.manager import DatabaseManager
from app.infrastructure.http.manager import HttpClientManager
from app.infrastructure.queue.manager import QueueManager

type AsyncCallback = Callable[[], Awaitable[None]]
type Callback = Callable[[], None]


@dataclass(frozen=True, slots=True)
class ApplicationContainer:
    """保存应用入口依赖并统一管理应用级资源的生命周期。"""

    databases: DatabaseManager
    caches: CacheManager
    http: HttpClientManager
    queues: QueueManager
    users: UserContext
    startup_callbacks: tuple[AsyncCallback, ...] = ()
    async_shutdown_callbacks: tuple[AsyncCallback, ...] = ()
    shutdown_callbacks: tuple[Callback, ...] = ()

    async def start(self) -> None:
        """按声明顺序执行应用启动回调。"""

        for callback in self.startup_callbacks:
            await callback()

    async def aclose(self) -> None:
        """逆序执行全部异步和同步关闭回调，并聚合失败。"""

        errors: list[BaseException] = []

        # 关闭过程不接受外部取消，避免只释放部分资源。
        with CancelScope(shield=True):
            for callback in reversed(self.async_shutdown_callbacks):
                try:
                    await callback()
                except BaseException as error:
                    errors.append(error)

        try:
            self.close()
        except BaseExceptionGroup as error:
            errors.extend(error.exceptions)
        except BaseException as error:
            errors.append(error)

        if errors:
            raise BaseExceptionGroup("Application shutdown callbacks failed", errors)

    def close(self) -> None:
        """逆序执行同步关闭回调，并保留所有错误。"""

        errors: list[BaseException] = []

        for callback in reversed(self.shutdown_callbacks):
            try:
                callback()
            except BaseException as error:
                errors.append(error)

        if errors:
            raise BaseExceptionGroup("Application shutdown callbacks failed", errors)
