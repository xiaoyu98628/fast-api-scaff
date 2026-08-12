from fastapi import FastAPI

from app.bootstrap.build import build_application_container
from app.bootstrap.configure import configure_app
from app.bootstrap.lifespan import create_lifespan


def create_app() -> FastAPI:
    app = FastAPI(
        lifespan=create_lifespan(build_application_container),
    )

    configure_app(app)

    return app
