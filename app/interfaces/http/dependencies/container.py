"""提供从 FastAPI 应用状态读取容器的依赖。"""

from fastapi import Request

from app.runtime.container import ApplicationContainer


def provide_application_container(request: Request) -> ApplicationContainer:
    """提供当前 FastAPI 应用持有的应用容器。"""

    # lifespan 只在容器启动成功后写入该状态，因此请求不会取得半初始化容器。
    container: ApplicationContainer = request.app.state.container
    return container
