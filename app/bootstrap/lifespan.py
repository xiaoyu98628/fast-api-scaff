import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.bootstrap.logging import ApplicationLogEvent
from app.bootstrap.runtime import ApplicationRuntime, ContainerFactory
from app.infrastructure.logging.record import log_extra

_APPLICATION_LOGGER = logging.getLogger("app.bootstrap.lifecycle")


def create_lifespan(container_factory: ContainerFactory):
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        _APPLICATION_LOGGER.info("Application starting", extra=log_extra(ApplicationLogEvent.STARTING))

        runtime = ApplicationRuntime(container_factory)

        try:
            try:
                container = await runtime.start()
            except Exception:
                _APPLICATION_LOGGER.exception("Application startup failed", extra=log_extra(ApplicationLogEvent.START_FAILED))
                raise

            app.state.container = container
            _APPLICATION_LOGGER.info("Application started", extra=log_extra(ApplicationLogEvent.STARTED))
            yield
        finally:
            _APPLICATION_LOGGER.info("Application stopping", extra=log_extra(ApplicationLogEvent.STOPPING))

            try:
                await runtime.aclose()
            except Exception:
                _APPLICATION_LOGGER.exception("Application shutdown failed", extra=log_extra(ApplicationLogEvent.STOP_FAILED))
                raise

            _APPLICATION_LOGGER.info("Application stopped", extra=log_extra(ApplicationLogEvent.STOPPED))

    return lifespan
