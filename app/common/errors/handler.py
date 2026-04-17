"""FastAPI 全局异常处理注册。"""

import logging

from fastapi import FastAPI
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.common.errors.biz_exception import BizException
from app.common.errors.code_builder import get_error_code_builder
from app.common.errors.system_exception import SystemException
from app.common.enums.error_code import ErrorCode
from app.common.response.json import JsonResponse

logger = logging.getLogger("app.request")


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理。"""

    @app.exception_handler(BizException)
    async def _biz_exception_handler(_, exc: BizException) -> JSONResponse:
        body = JsonResponse.error(
            code=f"{exc.code:010d}",
            message=exc.message,
            data=None,
        ).model_dump(exclude_none=True)
        return JSONResponse(status_code=exc.status_code, content=body)

    @app.exception_handler(SystemException)
    async def _system_exception_handler(_, exc: SystemException) -> JSONResponse:
        body = JsonResponse.error(
            code=f"{exc.code:010d}",
            message=exc.message,
            data=None,
        ).model_dump(exclude_none=True)
        return JSONResponse(status_code=exc.status_code, content=body)

    @app.exception_handler(Exception)
    async def _unhandled_exception(request, exc: Exception) -> JSONResponse:
        if isinstance(exc, RequestValidationError):
            return await request_validation_exception_handler(request, exc)
        if isinstance(exc, StarletteHTTPException):
            return await http_exception_handler(request, exc)

        logger.exception("Unhandled exception: %s", exc)
        code = get_error_code_builder().build(
            http_status=ErrorCode.INTERNAL_ERROR.status_code(),
            partial=int(ErrorCode.INTERNAL_ERROR),
        )
        body = JsonResponse.error(
            code=f"{code:010d}",
            message=ErrorCode.INTERNAL_ERROR.message(),
            data=None,
        ).model_dump(exclude_none=True)
        return JSONResponse(status_code=ErrorCode.INTERNAL_ERROR.status_code(), content=body)
