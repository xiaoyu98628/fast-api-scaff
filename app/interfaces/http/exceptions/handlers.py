"""把 FastAPI、Starlette 和项目异常转换为统一 JSON 响应。"""

from collections.abc import Mapping

from fastapi import Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse as StarletteJsonResponse
from starlette.responses import Response

from app.interfaces.http.dependencies.response import provide_json_response_factory
from app.interfaces.http.exceptions.error import HttpError
from app.interfaces.http.shared.response.codes.contract import CodeContract, CodeDefinition
from app.interfaces.http.shared.response.codes.error_code import ErrorCode

_HTTP_ERROR_CODES: dict[int, ErrorCode] = {
    400: ErrorCode.BAD_REQUEST,
    401: ErrorCode.UNAUTHORIZED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.ROUTE_NOT_FOUND,
    405: ErrorCode.METHOD_NOT_ALLOWED,
    409: ErrorCode.CONFLICT,
    422: ErrorCode.VALIDATION_ERROR,
    429: ErrorCode.TOO_MANY_REQUESTS,
    500: ErrorCode.INTERNAL_ERROR,
}


async def render_exception(request: Request, exception: Exception) -> Response:
    """将 HTTP 请求链路中的异常分派给对应的统一响应处理器。"""

    if isinstance(exception, HttpError):
        return await handle_http_error(request, exception)

    if isinstance(exception, RequestValidationError):
        return await handle_request_validation_error(request, exception)

    if isinstance(exception, HTTPException):
        return await handle_http_exception(request, exception)

    return await handle_unexpected_exception(request, exception)


async def handle_http_error(request: Request, exception: Exception) -> Response:
    """渲染接口层主动抛出的 HttpError。"""

    if not isinstance(exception, HttpError):
        raise TypeError("handle_http_error 只能处理 HttpError")

    # 无论调用方提供了什么内容，5xx 都只返回稳定的通用错误，避免泄露内部信息。
    if exception.code.status_code >= 500:
        return _render_error(request, ErrorCode.INTERNAL_ERROR)

    return _render_error(
        request,
        exception.code,
        message=exception.message,
        data=exception.data,
        headers=exception.headers,
    )


async def handle_request_validation_error(
    request: Request,
    exception: Exception,
) -> Response:
    """把 FastAPI 请求校验失败转换为精简字段列表。"""

    if not isinstance(exception, RequestValidationError):
        raise TypeError("handle_request_validation_error 只能处理 RequestValidationError")

    return _render_error(
        request,
        ErrorCode.VALIDATION_ERROR,
        data=_build_validation_data(exception),
    )


async def handle_http_exception(request: Request, exception: Exception) -> Response:
    """统一处理 Starlette 路由错误及其他 HTTPException。"""

    if not isinstance(exception, HTTPException):
        raise TypeError("handle_http_exception 只能处理 HTTPException")

    # 非错误 HTTPException 保留 Starlette 原生语义，不强行包装为失败响应。
    if exception.status_code < 400:
        return await http_exception_handler(request, exception)

    code = _resolve_http_error_code(exception.status_code)
    message, data = _resolve_http_exception_content(exception)

    return _render_error(
        request,
        code,
        message=message,
        data=data,
        headers=exception.headers,
    )


async def handle_unexpected_exception(request: Request, _exception: Exception) -> Response:
    """把未知异常隐藏为不包含内部细节的 500 响应。"""

    return _render_error(request, ErrorCode.INTERNAL_ERROR)


def _resolve_http_error_code(status_code: int) -> CodeContract:
    """按 HTTP 状态选择内置码，未知状态使用同类通用定义。"""

    code = _HTTP_ERROR_CODES.get(status_code)
    if code is not None:
        return code

    template = ErrorCode.INTERNAL_ERROR if status_code >= 500 else ErrorCode.BAD_REQUEST

    return CodeDefinition(
        code=template.code,
        message=template.message,
        status_code=status_code,
    )


def _resolve_http_exception_content(exception: HTTPException) -> tuple[str | None, object | None]:
    """只保留允许暴露给客户端的 HTTPException 内容。"""

    # 5xx、路由不存在和方法不允许统一使用项目文案，不透传框架或内部详情。
    if exception.status_code >= 500:
        return None, None

    if exception.status_code in {404, 405}:
        return None, None

    if isinstance(exception.detail, str):
        return exception.detail, None

    return None, exception.detail


def _build_validation_data(exception: RequestValidationError) -> list[dict[str, object]]:
    """提取错误类型、位置和消息，不回显客户端输入值。"""

    errors: list[dict[str, object]] = []

    for error in exception.errors():
        errors.append(
            {
                "type": error["type"],
                "location": list(error["loc"]),
                "message": error["msg"],
            }
        )

    return errors


def _render_error(
    request: Request,
    code: CodeContract,
    *,
    message: str | None = None,
    data: object | None = None,
    headers: Mapping[str, str] | None = None,
) -> Response:
    """通过当前应用的响应工厂生成最终 Starlette 响应。"""

    responses = provide_json_response_factory(request)
    payload = responses.error(
        code,
        message=message,
        data=data,
    )

    return StarletteJsonResponse(
        status_code=code.status_code,
        content=payload.model_dump(mode="json"),
        headers=headers,
    )
