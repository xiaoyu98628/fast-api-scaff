from functools import partial

from fastapi import FastAPI

from app.bootstrap.build import build_application_container
from app.bootstrap.configure import configure_app
from app.bootstrap.lifespan import create_lifespan
from app.config.settings import Settings, load_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings if settings is not None else load_settings()

    app = FastAPI(
        title=active_settings.app.name,
        version=active_settings.app.version,
        debug=active_settings.app.debug,
        lifespan=create_lifespan(partial(build_application_container, active_settings)),
    )

    configure_app(app)

    return app
