from collections.abc import Callable

from app.bootstrap.container import ApplicationContainer

type ContainerFactory = Callable[[], ApplicationContainer]


class ApplicationRuntime:
    """管理非特定宿主的应用容器生命周期。"""

    def __init__(self, container_factory: ContainerFactory) -> None:
        self._container_factory = container_factory
        self._container: ApplicationContainer | None = None

    @property
    def container(self) -> ApplicationContainer | None:
        return self._container

    async def start(self) -> ApplicationContainer:
        if self._container is not None:
            raise RuntimeError("应用运行时已经启动")

        container = self._container_factory()
        self._container = container

        try:
            await container.start()
        except BaseException as startup_error:
            try:
                await self.aclose()
            except BaseException as cleanup_error:
                raise BaseExceptionGroup(
                    "Application startup and cleanup failed",
                    (startup_error, cleanup_error),
                ) from None

            raise

        return container

    async def aclose(self) -> None:
        container = self._container
        self._container = None

        if container is not None:
            await container.aclose()

    async def __aenter__(self) -> ApplicationContainer:
        return await self.start()

    async def __aexit__(self, _error_type: object, _error: object, _traceback: object) -> None:
        await self.aclose()
