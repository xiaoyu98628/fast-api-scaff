from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.infrastructure.database.manager import get_manager
from app.infrastructure.logging.manager import configure_logging
from app.interfaces.http.handlers.register import register_exception_handlers
from app.interfaces.http.middleware.register import register_middleware
from app.interfaces.http.routers.register import register_route
from config.config import config


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await get_manager().disconnect()


def create_app() -> FastAPI:
    """创建 FastAPI 应用。"""
    configure_logging()

    configure = config()

    app = FastAPI(
        title=configure.app.name,
        debug=configure.app.debug,
        lifespan=lifespan,
    )

    # 注册中间件
    register_middleware(app=app)
    register_exception_handlers(app=app)
    # 注册路由
    register_route(app=app)

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
