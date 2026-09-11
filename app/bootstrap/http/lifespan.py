"""把应用容器生命周期接入 FastAPI lifespan。"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.bootstrap.http.logging import ApplicationLogEvent
from app.infrastructure.logging.record import log_extra
from app.runtime.lifecycle import ApplicationRuntime, ContainerFactory

_APPLICATION_LOGGER = logging.getLogger("app.bootstrap.lifecycle")


def create_lifespan(container_factory: ContainerFactory):
    """创建负责启动、暴露和关闭应用容器的 lifespan 管理器。"""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """在接受请求前启动容器，并在退出阶段保证资源释放。"""

        _APPLICATION_LOGGER.info("Application starting", extra=log_extra(ApplicationLogEvent.STARTING))

        runtime = ApplicationRuntime(container_factory)
        container_exposed = False

        try:
            try:
                container = await runtime.start()
            except BaseException:
                _APPLICATION_LOGGER.exception("Application startup failed", extra=log_extra(ApplicationLogEvent.START_FAILED))
                raise

            # 仅在完整启动成功后暴露容器，防止请求读取半初始化依赖。
            app.state.container = container
            container_exposed = True
            _APPLICATION_LOGGER.info("Application started", extra=log_extra(ApplicationLogEvent.STARTED))
            yield
        finally:
            # ApplicationRuntime 的关闭操作可重复调用，因此启动失败也走同一清理路径。
            _APPLICATION_LOGGER.info("Application stopping", extra=log_extra(ApplicationLogEvent.STOPPING))

            try:
                await runtime.aclose()
            except BaseException:
                _APPLICATION_LOGGER.exception("Application shutdown failed", extra=log_extra(ApplicationLogEvent.STOP_FAILED))
                raise
            finally:
                if container_exposed:
                    del app.state.container

            _APPLICATION_LOGGER.info("Application stopped", extra=log_extra(ApplicationLogEvent.STOPPED))

    return lifespan
