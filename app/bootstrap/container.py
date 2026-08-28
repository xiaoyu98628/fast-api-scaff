from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.contexts.user.application.service import UserApplicationService
from app.infrastructure.cache.manager import CacheManager
from app.infrastructure.database.manager import DatabaseManager

type AsyncCallback = Callable[[], Awaitable[None]]
type Callback = Callable[[], None]


@dataclass(frozen=True, slots=True)
class ApplicationContainer:
    """保存应用入口依赖并统一管理应用级资源的生命周期。"""

    databases: DatabaseManager
    caches: CacheManager
    users: UserApplicationService
    startup_callbacks: tuple[AsyncCallback, ...] = ()
    async_shutdown_callbacks: tuple[AsyncCallback, ...] = ()
    shutdown_callbacks: tuple[Callback, ...] = ()

    async def start(self) -> None:
        for callback in self.startup_callbacks:
            await callback()

    async def aclose(self) -> None:
        errors: list[Exception] = []

        for callback in reversed(self.async_shutdown_callbacks):
            try:
                await callback()
            except Exception as error:
                errors.append(error)

        try:
            self.close()
        except ExceptionGroup as error:
            errors.extend(exception for exception in error.exceptions if isinstance(exception, Exception))

        if errors:
            raise ExceptionGroup("Application shutdown callbacks failed", errors)

    def close(self) -> None:
        errors: list[Exception] = []

        for callback in reversed(self.shutdown_callbacks):
            try:
                callback()
            except Exception as error:
                errors.append(error)

        if errors:
            raise ExceptionGroup("Application shutdown callbacks failed", errors)
