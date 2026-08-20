from starlette.middleware import Middleware
from starlette_context import plugins
from starlette_context.middleware import RawContextMiddleware


def build_request_id_middleware() -> Middleware:
    """构建 X-Request-ID 中间件。"""
    return Middleware(
        RawContextMiddleware,
        plugins=(plugins.RequestIdPlugin(),),
    )
