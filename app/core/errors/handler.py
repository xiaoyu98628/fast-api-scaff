"""统一异常映射工具。"""

from fastapi.responses import JSONResponse

from app.core.errors.biz_exception import BizException
from app.core.errors.system_exception import SystemException
from app.core.response.json import JsonResponse


def _build_error_response(*, status_code: int, code: int, message: str):
    body = JsonResponse.error(
        code=f"{code:010d}",
        message=message,
        data=None,
    ).model_dump(exclude_none=True)
    return JSONResponse(status_code=status_code, content=body)


def _extract_known_exception_from_group(exc_group: ExceptionGroup) -> BizException | SystemException | None:
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
