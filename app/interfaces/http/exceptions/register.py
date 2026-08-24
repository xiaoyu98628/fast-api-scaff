from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException

from app.interfaces.http.exceptions.error import HttpError
from app.interfaces.http.exceptions.handlers import (
    handle_http_error,
    handle_http_exception,
    handle_request_validation_error,
    handle_unexpected_exception,
)


def register_exception_handlers(app: FastAPI) -> None:
    """注册 HTTP 请求链路使用的统一异常处理器。"""
    app.add_exception_handler(HttpError, handle_http_error)
    app.add_exception_handler(RequestValidationError, handle_request_validation_error)
    app.add_exception_handler(HTTPException, handle_http_exception)
    app.add_exception_handler(Exception, handle_unexpected_exception)
