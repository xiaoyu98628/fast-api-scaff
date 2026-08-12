from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.bootstrap.container import ApplicationContainer

type ContainerFactory = Callable[[], ApplicationContainer]


def create_lifespan(container_factory: ContainerFactory):
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        container = container_factory()
        app.state.container = container

        try:
            await container.start()
            yield
        finally:
            await container.aclose()

    return lifespan
