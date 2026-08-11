from fastapi import FastAPI

from app.bootstrap.lifespan import lifespan


def create_app() -> FastAPI:
    app = FastAPI(
        lifespan=lifespan,
    )

    return app
