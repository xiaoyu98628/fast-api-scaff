from fastapi import FastAPI

from app.bootstrap.lifespan import create_lifespan


def create_app() -> FastAPI:
    app = FastAPI(
        lifespan=create_lifespan(),
    )

    return app
