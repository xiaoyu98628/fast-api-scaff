from collections.abc import Callable
from functools import partial

from fastapi import FastAPI

from app.bootstrap.build import build_application_container
from app.bootstrap.http.lifespan import create_lifespan
from app.config.settings import Settings, load_settings
from app.interfaces.http.exceptions.register import register_exception_handlers
from app.interfaces.http.middleware.registry import build_http_middlewares
from app.interfaces.http.routes.register import register_routes
from app.interfaces.http.shared.response.codes.builder import ResponseCodeBuilder
from app.interfaces.http.shared.response.factory import JsonResponseFactory
from app.runtime.container import ApplicationContainer

type ContainerBuilder = Callable[[Settings], ApplicationContainer]


def create_app(
    settings: Settings | None = None,
    *,
    container_builder: ContainerBuilder = build_application_container,
) -> FastAPI:
    active_settings = settings if settings is not None else load_settings()

    app = FastAPI(
        title=active_settings.app.name,
        summary=f"{active_settings.app.name} API 文档",
        description="基于 FastAPI 构建的后端 API 服务。",
        version=active_settings.app.version,
        debug=active_settings.app.debug,
        lifespan=create_lifespan(partial(container_builder, active_settings)),
        middleware=build_http_middlewares(active_settings),
        swagger_ui_parameters={
            "filter": True,
            "displayRequestDuration": True,
        },
    )

    app.state.json_response_factory = JsonResponseFactory(
        code_builder=ResponseCodeBuilder(active_settings.app.service_code),
    )
    register_exception_handlers(app)
    register_routes(app)

    return app
