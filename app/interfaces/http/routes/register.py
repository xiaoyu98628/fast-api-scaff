"""注册宿主级路由和版本化业务 API。"""

from fastapi import FastAPI
from starlette.requests import Request

from app.interfaces.http.controllers.router import api_router
from app.interfaces.http.dependencies.response import JsonResponseFactoryDependency
from app.interfaces.http.shared.response.json import JsonResponse


async def health(request: Request, responses: JsonResponseFactoryDependency) -> JsonResponse[dict[str, str]]:
    """返回进程存活响应，不主动初始化或探测外部资源。"""

    return responses.success(data={"message": "ok"})


def register_routes(app: FastAPI) -> None:
    """先注册宿主健康检查，再挂载完整 API 路由树。"""

    app.add_api_route(
        path="/health",
        endpoint=health,
        methods=["GET"],
        tags=["health"],
        summary="健康检测",
        response_model=JsonResponse[dict[str, str]],
    )
    app.include_router(api_router)
