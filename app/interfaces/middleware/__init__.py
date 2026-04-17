"""HTTP 中间件：与具体业务无关的横切逻辑（如 trace、query 解码）。"""

from fastapi import FastAPI

from app.interfaces.middleware.auth_token import AuthTokenMiddleware
from app.interfaces.middleware.cors import CorsMiddleware
from app.interfaces.middleware.exception_capture import ExceptionCaptureMiddleware
from app.interfaces.middleware.query_param_decode import QueryParamDecodeMiddleware
from app.interfaces.middleware.request_log import RequestLogMiddleware
from app.interfaces.middleware.trace_id import TraceIdMiddleware


def register_middleware(app: FastAPI) -> None:
    app.add_middleware(TraceIdMiddleware)
    app.add_middleware(RequestLogMiddleware)
    app.add_middleware(AuthTokenMiddleware)
    app.add_middleware(CorsMiddleware)
    app.add_middleware(QueryParamDecodeMiddleware)
    # 统一异常拦截需放最外层（最后注册），兜住中间件链路抛出的异常。
    app.add_middleware(ExceptionCaptureMiddleware)
