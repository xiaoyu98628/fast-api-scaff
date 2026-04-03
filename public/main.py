from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1 import api_router
from app.middleware import register_middleware
from config.config import get_config

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

def create_app() -> FastAPI:
    config = get_config()

    app = FastAPI(
        title=config.app.app_name,
        debug=config.app.app_debug,
        lifespan=lifespan,
    )

    register_middleware(app)
    app.include_router(api_router)

    @app.get(path="/health", summary="健康检测")
    async def health():
        return {"message": "Hello World"}

    return app

app = create_app()

if __name__ == "__main__":
    import uvicorn

    config = get_config()
    uvicorn.run("app.main:app", host=config.app.app_host, port=config.app.app_port, reload=config.app.app_debug)