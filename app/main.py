from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.infrastructure.database.database_manager import get_database_manager
from config.config import config


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await get_database_manager().disconnect()


def create_app() -> FastAPI:
    """创建 FastAPI 应用。"""
    configure = config()

    app = FastAPI(
        title=configure.app.name,
        debug=configure.app.debug,
        lifespan=lifespan,
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
