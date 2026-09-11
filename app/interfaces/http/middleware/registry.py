"""集中声明 HTTP 中间件及其执行顺序。"""

from starlette.middleware import Middleware

from app.config.settings import Settings
from app.interfaces.http.middleware.access_log import build_access_log_middleware
from app.interfaces.http.middleware.cors import build_cors_middleware
from app.interfaces.http.middleware.exception_capture import ExceptionCaptureMiddleware
from app.interfaces.http.middleware.query_param_decode import QueryParamDecodeMiddleware
from app.interfaces.http.middleware.request_id import build_request_id_middleware
from app.interfaces.http.middleware.trace_context import TraceContextMiddleware


def build_http_middlewares(settings: Settings) -> list[Middleware]:
    """按从外到内的顺序构建应用 HTTP 中间件。"""

    # CORS 和 Request ID 位于外层，使错误响应也能带上对应响应头和请求上下文。
    middlewares = [
        build_cors_middleware(settings.cors),
        build_request_id_middleware(settings.app.service_code),
        Middleware(TraceContextMiddleware),
    ]

    if settings.logging.access_enabled:
        middlewares.append(
            build_access_log_middleware(
                exclude_routes=settings.logging.access_exclude_routes,
            )
        )

    # 异常捕获包裹查询参数解码，确保解码链路异常也使用统一错误响应。
    middlewares.extend(
        [
            Middleware(ExceptionCaptureMiddleware, debug=settings.app.debug),
            Middleware(QueryParamDecodeMiddleware),
        ]
    )

    return middlewares
