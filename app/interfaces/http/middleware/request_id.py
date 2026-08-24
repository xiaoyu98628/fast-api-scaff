from starlette.middleware import Middleware
from starlette.responses import JSONResponse as StarletteJsonResponse
from starlette_context import plugins
from starlette_context.middleware import RawContextMiddleware

from app.interfaces.http.shared.response.codes.builder import ResponseCodeBuilder
from app.interfaces.http.shared.response.codes.error_code import ErrorCode
from app.interfaces.http.shared.response.json import JsonResponse


def build_request_id_middleware(service_code: str) -> Middleware:
    """构建 X-Request-ID 中间件。"""
    return Middleware(
        RawContextMiddleware,
        plugins=(plugins.RequestIdPlugin(),),
        default_error_response=_build_invalid_request_id_response(service_code),
    )


def _build_invalid_request_id_response(service_code: str) -> StarletteJsonResponse:
    code = ErrorCode.BAD_REQUEST
    code_builder = ResponseCodeBuilder(service_code)

    payload = JsonResponse[object](
        code=code_builder.build(code),
        is_success=False,
        message=code.message,
        data=None,
    )

    return StarletteJsonResponse(
        status_code=code.status_code,
        content=payload.model_dump(mode="json"),
    )
