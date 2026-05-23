
from fastapi import FastAPI

from app.interfaces.http.middleware.query_param_decode import QueryParamDecodeMiddleware


def register_middleware(app: FastAPI) -> None:

    app.add_middleware(QueryParamDecodeMiddleware)
