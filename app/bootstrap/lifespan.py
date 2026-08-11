from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI


def create_lifespan():
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:

        yield

    return lifespan
