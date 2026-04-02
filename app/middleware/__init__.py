"""中间件。"""

from fastapi import FastAPI

from app.middleware.query_param_decode import QueryParamDecodeMiddleware
from app.middleware.trace_id import TraceIdMiddleware


def register_middleware(app: FastAPI) -> None:
    app.add_middleware(TraceIdMiddleware)
    app.add_middleware(QueryParamDecodeMiddleware)
