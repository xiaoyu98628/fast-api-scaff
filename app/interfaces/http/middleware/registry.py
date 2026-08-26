from starlette.middleware import Middleware

from app.config.settings import Settings
from app.interfaces.http.middleware.cors import build_cors_middleware
from app.interfaces.http.middleware.exception_capture import ExceptionCaptureMiddleware
from app.interfaces.http.middleware.query_param_decode import QueryParamDecodeMiddleware
from app.interfaces.http.middleware.request_id import build_request_id_middleware


def build_http_middlewares(settings: Settings) -> list[Middleware]:
    """按从外到内的顺序构建应用 HTTP 中间件。"""
    return [
        build_request_id_middleware(settings.app.service_code),
        build_cors_middleware(settings.cors),
        Middleware(ExceptionCaptureMiddleware, debug=settings.app.debug),
        Middleware(QueryParamDecodeMiddleware),
    ]
