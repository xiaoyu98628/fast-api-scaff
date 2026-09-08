"""建立请求上下文并维护 X-Request-ID 响应契约。"""

import logging

from starlette.middleware import Middleware
from starlette.requests import HTTPConnection, Request
from starlette.responses import JSONResponse as StarletteJsonResponse
from starlette_context import plugins
from starlette_context.errors import MiddleWareValidationError
from starlette_context.middleware import RawContextMiddleware

from app.infrastructure.logging.record import log_extra
from app.interfaces.http.logging import HttpLogEvent
from app.interfaces.http.shared.response.codes.builder import ResponseCodeBuilder
from app.interfaces.http.shared.response.codes.error_code import ErrorCode
from app.interfaces.http.shared.response.factory import JsonResponseFactory

_REQUEST_ID_LOGGER = logging.getLogger("app.interfaces.http.request_id")


class RequestIdMiddleware(RawContextMiddleware):
    """建立请求上下文，并安全记录非法 Request ID。"""

    async def set_context(self, request: Request | HTTPConnection) -> dict[object, object]:
        """创建请求上下文，并在插件拒绝 ID 时记录有限元数据。"""

        try:
            return await super().set_context(request)
        except MiddleWareValidationError:
            _REQUEST_ID_LOGGER.warning(
                "HTTP request rejected due to invalid request ID",
                extra=log_extra(
                    HttpLogEvent.INVALID_REQUEST_ID,
                    method=request.scope.get("method"),
                    status_code=ErrorCode.BAD_REQUEST.status_code,
                ),
            )
            raise


def build_request_id_middleware(service_code: str) -> Middleware:
    """构建 X-Request-ID 中间件。"""

    return Middleware(
        RequestIdMiddleware,
        plugins=(plugins.RequestIdPlugin(),),
        default_error_response=_build_invalid_request_id_response(service_code),
    )


def _build_invalid_request_id_response(service_code: str) -> StarletteJsonResponse:
    """为上下文插件预先构建符合统一响应格式的 400 响应。"""

    # 中间件创建时还没有 FastAPI app.state，因此在这里创建独立响应工厂。
    code = ErrorCode.BAD_REQUEST
    responses = JsonResponseFactory(
        code_builder=ResponseCodeBuilder(service_code),
    )
    payload = responses.error(code)

    return StarletteJsonResponse(
        status_code=code.status_code,
        content=payload.model_dump(mode="json"),
    )
