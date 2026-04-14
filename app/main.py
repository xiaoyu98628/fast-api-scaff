"""
FastAPI 应用入口：组装中间件、挂载 API 路由、注册生命周期钩子。

ASGI 启动示例：``uvicorn app.main:app``。
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.infrastructure.db.session import close_db
from app.infrastructure.logging import setup_logging
from app.infrastructure.redis.client import close_redis
from app.interfaces.api import register_api_router
from app.interfaces.api.exception_handlers import register_exception_handlers
from app.interfaces.middleware import register_middleware
from config.config import get_config


@asynccontextmanager
async def lifespan(app: FastAPI):
    """进程退出前释放外部连接（Redis、DB 连接池）。"""
    yield
    await close_redis()
    await close_db()


def create_app() -> FastAPI:
    """构建并返回配置好的 ``FastAPI`` 实例（测试与 ASGI 服务器共用）。"""
    config = get_config()
    setup_logging(config.logging)

    app = FastAPI(
        title=config.app.name,
        debug=config.app.debug,
        lifespan=lifespan,
    )

    register_middleware(app)
    register_exception_handlers(app)
    register_api_router(app)

    return app


app = create_app()


def main() -> None:
    """命令行直接运行本模块时使用（等价于 uvicorn app.main:app）。"""
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
