from fastapi import FastAPI

from app.interfaces.http.response.json import ApiResponse, ApiResponseFactory


def register_routes(app: FastAPI, responses: ApiResponseFactory) -> None:
    @app.get(
        path="/health",
        tags=["system"],
        summary="健康检测",
        response_model=ApiResponse[dict[str, str]],
    )
    async def health() -> ApiResponse[dict[str, str]]:
        return responses.success(data={"message": "ok"})
