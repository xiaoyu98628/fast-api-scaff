"""统一异常拦截中间件：兜底捕获中间件链路异常并输出统一错误响应。"""

import logging

from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.common.enums.error_code import ErrorCode
from app.common.errors.code_builder import get_error_code_builder
from app.common.errors.handler import render_known_exception
from app.common.response.json import JsonResponse

logger = logging.getLogger("app.request")


class ExceptionCaptureMiddleware(BaseHTTPMiddleware):
    """统一异常出口：中间件阶段异常也走项目标准错误响应。"""

    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except BaseException as exc:  # noqa: BLE001 - 统一收口后再按类型映射
            rendered = render_known_exception(exc)
            if rendered is not None:
                return rendered
            if isinstance(exc, StarletteHTTPException):
                code = get_error_code_builder().build(
                    http_status=exc.status_code,
                    partial=exc.status_code,
                )
                body = JsonResponse.error(
                    code=f"{code:010d}",
                    message=str(exc.detail),
                    data=None,
                ).model_dump(exclude_none=True)
                return JSONResponse(status_code=exc.status_code, content=body)
            if isinstance(exc, RequestValidationError):
                code = get_error_code_builder().build(http_status=422, partial=422)
                body = JsonResponse.error(
                    code=f"{code:010d}",
                    message="请求参数校验失败",
                    data=exc.errors(),
                ).model_dump(exclude_none=True)
                return JSONResponse(status_code=422, content=body)

            logger.exception("Unhandled exception in middleware chain: %s", exc)
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
