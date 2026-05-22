
from fastapi import FastAPI

from config.config import config


def create_app() -> FastAPI:
    """创建 FastAPI 应用。"""
    configure = config()

    app = FastAPI(
        title=configure.app.name,
        debug=configure.app.debug,
    )

    @app.get(path="/health", summary="健康检测")
    async def health():
        return {"message": "Hello World"}

    return app

app = create_app()

def main() -> None:
    import uvicorn

    configure = config()
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=configure.app.port,
        reload=configure.app.debug,
    )


if __name__ == "__main__":
    main()
