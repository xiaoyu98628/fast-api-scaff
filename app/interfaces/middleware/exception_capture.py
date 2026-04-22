"""统一异常拦截中间件：兜底捕获中间件链路异常并输出统一错误响应。"""

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.common.enums.error_code import ErrorCode
from app.common.errors.code_builder import get_error_code_builder
from app.common.errors.handler import (
    build_request_validation_error_response,
    render_known_exception,
)
from app.common.response.json import JsonResponse
from app.common.utils.logger import Log


def register_exception_capture(app: FastAPI) -> None:
    """统一异常出口（仅此一处注册）：挂载捕获中间件，并挂接校验异常 handler。

    ``RequestValidationError`` 在 FastAPI 路由栈内被处理，不会作为未捕获异常传到
    ``BaseHTTPMiddleware``，因此必须与中间件在同一入口补充 ``exception_handler``，
    响应体仍由 ``build_request_validation_error_response`` 生成，与中间件分支一致。
    """

    @app.exception_handler(RequestValidationError)
    async def _request_validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        trace_id = getattr(request.state, "trace_id", None)
        return build_request_validation_error_response(exc, trace_id=trace_id)

    app.add_middleware(ExceptionCaptureMiddleware)


class ExceptionCaptureMiddleware(BaseHTTPMiddleware):
    """统一异常出口：中间件阶段异常也走项目标准错误响应。"""

    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except BaseException as exc:  # noqa: BLE001 - 统一收口后再按类型映射
            trace_id = getattr(request.state, "trace_id", "-")
            method = request.method
            path = request.url.path
            if isinstance(exc, Exception):
                status_code = getattr(exc, "status_code", "-")
                error_code = getattr(exc, "code", "-")
                message = getattr(exc, "message", str(exc))
                detail = "-"
                if isinstance(exc, StarletteHTTPException):
                    detail = str(exc.detail)
                elif isinstance(exc, RequestValidationError):
                    detail = str(exc.errors()[:3])
                Log.error(
                    "Captured exception in middleware chain: %s %s -> type=%s status=%s code=%s message=%s detail=%s",
                    method,
                    path,
                    exc.__class__.__name__,
                    status_code,
                    error_code,
                    message,
                    detail,
                    trace_id=trace_id,
                )
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
                tid = getattr(request.state, "trace_id", None)
                return build_request_validation_error_response(exc, trace_id=tid)
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
