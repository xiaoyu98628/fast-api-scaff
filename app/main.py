"""
FastAPI 应用入口：组装中间件、挂载 API 路由、注册生命周期钩子。

ASGI 启动示例：``uvicorn app.main:app``。
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.infrastructure.db.session import close_db
from app.infrastructure.logging.setup import setup_logging
from app.infrastructure.redis.client import close_redis
from app.interfaces.api.register import register_api_router
from app.interfaces.middleware.register import register_middleware
from config.setting import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """进程退出前释放外部连接（Redis、DB 连接池）。"""
    yield
    await close_redis()
    await close_db()


def create_app() -> FastAPI:
    """构建并返回配置好的 ``FastAPI`` 实例（测试与 ASGI 服务器共用）。"""
    setting = settings()
    setup_logging(setting.logging)

    app = FastAPI(
        title=setting.app.name,
        debug=setting.app.debug,
        lifespan=lifespan,
    )

    register_middleware(app)
    register_api_router(app)

    return app


app = create_app()


def main() -> None:
    """命令行直接运行本模块时使用（等价于 uvicorn app.main:app）。"""
    import uvicorn

    setting = settings()
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=setting.app.port,
        reload=setting.app.debug,
    )


if __name__ == "__main__":
    main()
