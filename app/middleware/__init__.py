"""中间件。"""

from fastapi import FastAPI

from app.middleware.auth_token import AuthTokenMiddleware
from app.middleware.cors import CorsMiddleware
from app.middleware.exception_capture import ExceptionCaptureMiddleware
from app.middleware.query_param_decode import QueryParamDecodeMiddleware
from app.middleware.request_log import RequestLogMiddleware
from app.middleware.trace_id import TraceIdMiddleware


def register_middleware(app: FastAPI) -> None:
    # 先注册的内层、后注册的外层；请求先经外层。TraceId 须在外层，请求日志才能读到 trace_id。
    app.add_middleware(RequestLogMiddleware)
    app.add_middleware(TraceIdMiddleware)
    app.add_middleware(AuthTokenMiddleware)
    app.add_middleware(CorsMiddleware)
    app.add_middleware(QueryParamDecodeMiddleware)
    app.add_middleware(ExceptionCaptureMiddleware)
