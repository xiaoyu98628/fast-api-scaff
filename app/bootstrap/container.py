from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from anyio import CancelScope

from app.contexts.user.composition import UserContext
from app.infrastructure.cache.manager import CacheManager
from app.infrastructure.database.manager import DatabaseManager
from app.infrastructure.http.manager import HttpClientManager

type AsyncCallback = Callable[[], Awaitable[None]]
type Callback = Callable[[], None]


@dataclass(frozen=True, slots=True)
class ApplicationContainer:
    """保存应用入口依赖并统一管理应用级资源的生命周期。"""

    databases: DatabaseManager
    caches: CacheManager
    http: HttpClientManager
    users: UserContext
    startup_callbacks: tuple[AsyncCallback, ...] = ()
    async_shutdown_callbacks: tuple[AsyncCallback, ...] = ()
    shutdown_callbacks: tuple[Callback, ...] = ()

    async def start(self) -> None:
        for callback in self.startup_callbacks:
            await callback()

    async def aclose(self) -> None:
        errors: list[BaseException] = []

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
        errors: list[BaseException] = []

        for callback in reversed(self.shutdown_callbacks):
            try:
                callback()
            except BaseException as error:
                errors.append(error)

        if errors:
            raise BaseExceptionGroup("Application shutdown callbacks failed", errors)
