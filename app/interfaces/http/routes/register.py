from fastapi import FastAPI
from starlette.requests import Request

from app.interfaces.http.controllers.router import api_router
from app.interfaces.http.shared.response.json import JsonResponse


async def health(request: Request) -> JsonResponse[dict[str, str]]:
    return JsonResponse.success(data={"message": "ok"})


def register_routes(app: FastAPI) -> None:
    app.add_api_route(
        path="/health",
        endpoint=health,
        methods=["GET"],
        tags=["health"],
        summary="健康检测",
        response_model=JsonResponse[dict[str, str]],
    )
    app.include_router(api_router)
