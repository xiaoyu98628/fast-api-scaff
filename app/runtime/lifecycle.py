"""提供 HTTP、Console 和 Worker 共用的容器运行时。"""

from collections.abc import Callable

from app.runtime.container import ApplicationContainer

type ContainerFactory = Callable[[], ApplicationContainer]


class ApplicationRuntime:
    """管理非特定宿主的应用容器生命周期。"""

    def __init__(self, container_factory: ContainerFactory) -> None:
        """保存容器工厂；容器在首次启动前保持未创建状态。"""

        self._container_factory = container_factory
        self._container: ApplicationContainer | None = None

    @property
    def container(self) -> ApplicationContainer | None:
        """返回已经启动的容器；未启动或关闭后返回 None。"""

        return self._container

    async def start(self) -> ApplicationContainer:
        """创建并启动一次容器，启动失败时立即清理已建资源。"""

        if self._container is not None:
            raise RuntimeError("应用运行时已经启动")

        container = self._container_factory()
        self._container = container

        try:
            await container.start()
        except BaseException as startup_error:
            # 同时保留启动根因和回滚失败，避免清理异常覆盖最初错误。
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
        """幂等关闭当前容器，并在真正释放前清除公开引用。"""

        container = self._container
        # 先清空引用可阻止关闭回调间接重新获取正在释放的容器。
        self._container = None

        if container is not None:
            await container.aclose()

    async def __aenter__(self) -> ApplicationContainer:
        """启动容器并把所有权交给当前异步上下文。"""

        return await self.start()

    async def __aexit__(self, _error_type: object, _error: object, _traceback: object) -> None:
        """离开异步上下文时关闭其拥有的容器。"""

        await self.aclose()
