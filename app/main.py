"""创建供 ASGI Server 导入的 HTTP 应用实例。"""

from app.bootstrap.http.application import create_app
from app.bootstrap.http.logging import configure_http_logging
from app.config.settings import load_settings

# ASGI Server 通过 ``app.main:app`` 导入本模块，因此在模块加载时完成宿主装配。
settings = load_settings()
configure_http_logging(settings)

app = create_app(settings)


if __name__ == "__main__":
    import uvicorn

    # 直接执行模块时复用同一应用配置，并关闭 Uvicorn 的重复访问日志。
    uvicorn.run(
        app="app.main:app",
        reload=settings.app.debug,
        access_log=False,
        log_config=None,
    )
