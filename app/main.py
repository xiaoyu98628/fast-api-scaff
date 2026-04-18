from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.openapi import setup_openapi_security
from app.api.router import api_router
from app.infrastructure.database import close_db
from app.infrastructure.logging.setup import setup_logging
from app.infrastructure.redis import close_redis
from app.middleware import register_middleware
from config.config import get_config


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_redis()
    await close_db()


def create_app() -> FastAPI:
    config = get_config()
    setup_logging(config.logging)

    app = FastAPI(
        title=config.app.name,
        debug=config.app.debug,
        lifespan=lifespan,
    )

    register_middleware(app)
    app.include_router(api_router)
    setup_openapi_security(app)

    @app.get(path="/health", summary="健康检测")
    async def health():
        return {"message": "Hello World"}

    return app


app = create_app()


def main() -> None:
    import uvicorn

    config = get_config()
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=config.app.port,
        reload=config.app.debug,
    )


if __name__ == "__main__":
    main()
