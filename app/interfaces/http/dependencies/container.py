from fastapi import Request

from app.bootstrap.container import ApplicationContainer


def provide_application_container(request: Request) -> ApplicationContainer:
    """提供当前 FastAPI 应用持有的应用容器。"""
    container: ApplicationContainer = request.app.state.container
    return container
