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


def _build_error_response(*, status_code: int, code: int, message: str):
    body = JsonResponse.error(
        code=f"{code:010d}",
        message=message,
        data=None,
    ).model_dump(exclude_none=True)
    return JSONResponse(status_code=status_code, content=body)


def _extract_known_exception_from_group(exc_group: ExceptionGroup) -> BizException | SystemException | None:
    """从 ExceptionGroup 里提取首个业务/系统异常，便于统一按语义出参。"""
    stack: list[BaseException] = [exc_group]
    while stack:
        current = stack.pop()
        if isinstance(current, (BizException, SystemException)):
            return current
        if isinstance(current, ExceptionGroup):
            stack.extend(list(current.exceptions))
    return None


def render_known_exception(exc: BaseException):
    """将可识别异常转换为统一响应；不可识别返回 ``None``。"""
    if isinstance(exc, BizException):
        return _build_error_response(status_code=exc.status_code, code=exc.code, message=exc.message)
    if isinstance(exc, SystemException):
        return _build_error_response(status_code=exc.status_code, code=exc.code, message=exc.message)
    if isinstance(exc, ExceptionGroup):
        known_exc = _extract_known_exception_from_group(exc)
        if known_exc is not None:
            return render_known_exception(known_exc)
    return None


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理。"""

    @app.exception_handler(BizException)
    async def _biz_exception_handler(_, exc: BizException):
        return render_known_exception(exc)

    @app.exception_handler(SystemException)
    async def _system_exception_handler(_, exc: SystemException):
        return render_known_exception(exc)

    @app.exception_handler(ExceptionGroup)
    async def _exception_group_handler(_, exc: ExceptionGroup):
        rendered = render_known_exception(exc)
        if rendered is not None:
            return rendered
        logger.exception("Unhandled ExceptionGroup: %s", exc)
        code = get_error_code_builder().build(
            http_status=ErrorCode.INTERNAL_ERROR.status_code(),
            partial=int(ErrorCode.INTERNAL_ERROR),
        )
        return _build_error_response(
            status_code=ErrorCode.INTERNAL_ERROR.status_code(),
            code=code,
            message=ErrorCode.INTERNAL_ERROR.message(),
        )

    @app.exception_handler(Exception)
    async def _unhandled_exception(request, exc: Exception):
        if isinstance(exc, RequestValidationError):
            return await request_validation_exception_handler(request, exc)
        if isinstance(exc, StarletteHTTPException):
            return await http_exception_handler(request, exc)

        logger.exception("Unhandled exception: %s", exc)
        code = get_error_code_builder().build(
            http_status=ErrorCode.INTERNAL_ERROR.status_code(),
            partial=int(ErrorCode.INTERNAL_ERROR),
        )
        return _build_error_response(
            status_code=ErrorCode.INTERNAL_ERROR.status_code(),
            code=code,
            message=ErrorCode.INTERNAL_ERROR.message(),
        )
