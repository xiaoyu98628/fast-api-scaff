from functools import partial

from fastapi import FastAPI

from app.bootstrap.build import build_application_container
from app.bootstrap.configure import configure_http_app
from app.bootstrap.lifespan import create_lifespan
from app.config.settings import Settings, load_settings
from app.interfaces.http.middleware.registry import build_http_middlewares


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings if settings is not None else load_settings()

    app = FastAPI(
        title=active_settings.app.name,
        summary=f"{active_settings.app.name} API 文档",
        description="基于 FastAPI 构建的后端 API 服务。",
        version=active_settings.app.version,
        debug=active_settings.app.debug,
        lifespan=create_lifespan(partial(build_application_container, active_settings)),
        middleware=build_http_middlewares(active_settings),
        swagger_ui_parameters={
            "filter": True,
            "displayRequestDuration": True,
        },
    )

    configure_http_app(app, active_settings)

    return app
