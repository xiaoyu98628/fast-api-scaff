
from fastapi import FastAPI

from app.interfaces.http.middleware.cors import CorsMiddleware
from app.interfaces.http.middleware.query_param_decode import QueryParamDecodeMiddleware
from app.interfaces.http.middleware.request_log import RequestLogMiddleware
from app.interfaces.http.middleware.request_scope import RequestScopeMiddleware


def register_middleware(app: FastAPI) -> None:

    # 先注册的内层、后注册的外层；RequestScope 须在 RequestLog 外侧，请求日志才能读到 trace_id。
    app.add_middleware(RequestLogMiddleware)

    app.add_middleware(RequestScopeMiddleware)
    app.add_middleware(QueryParamDecodeMiddleware)
    # Cors 须在最外层，异常 handler 直接返回的错误响应也要带上 CORS 头。
    app.add_middleware(CorsMiddleware)
