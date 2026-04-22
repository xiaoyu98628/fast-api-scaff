"""统一异常映射工具：将已知异常转换为统一响应。"""

import logging

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.common.exceptions.biz_exception import BizException
from app.common.errors.code_builder import get_error_code_builder
from app.common.exceptions.system_exception import SystemException
from app.common.enums.error_code import ErrorCode
from app.common.response.json import JsonResponse

logger = logging.getLogger("app.request")


def build_request_validation_error_response(
    exc: RequestValidationError,
    *,
    trace_id: str | None = None,
) -> JSONResponse:
    """请求体验证失败时的统一 JSON（低位与 HTTP 取自 ``ErrorCode.PARAMETER_ERROR``）。"""
    ec = ErrorCode.PARAMETER_ERROR
    http_status = ec.status_code()
    full = get_error_code_builder().build(http_status=http_status, partial=int(ec))
    body = JsonResponse.error(
        code=f"{full:010d}",
        message=ec.message(),
        data=exc.errors(),
        trace_id=trace_id,
    ).model_dump(exclude_none=True)
    return JSONResponse(status_code=http_status, content=body)


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
