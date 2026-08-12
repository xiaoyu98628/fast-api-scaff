from fastapi import FastAPI


def register_routes(app: FastAPI) -> None:
    @app.get(path="/health", summary="健康检测")
    async def health() -> dict[str, str]:
        return {"message": "ok"}
