from dataclasses import dataclass
from typing import Self

from pydantic import BaseModel, ConfigDict, Field
from starlette_context import context
from starlette_context.header_keys import HeaderKeys

from app.interfaces.http.shared.response.codes.builder import ResponseCodeBuilder
from app.interfaces.http.shared.response.codes.contract import CodeContract
from app.interfaces.http.shared.response.codes.error_code import ErrorCode
from app.interfaces.http.shared.response.codes.success_code import SuccessCode


class ApiResponse[T](BaseModel):
    """普通 JSON API 的统一响应结构。"""

    model_config = ConfigDict(frozen=True)

    code: str
    success: bool
    message: str
    data: T | None = None
    request_id: str | None = Field(default=None, exclude_if=lambda value: value is None)


@dataclass(frozen=True, slots=True)
class ApiResponseFactory:
    """使用当前服务编码构造统一 JSON 响应。"""

    code_builder: ResponseCodeBuilder

    @classmethod
    def from_service_code(cls, service_code: str) -> Self:
        return cls(code_builder=ResponseCodeBuilder(service_code))

    def success[T](
        self,
        data: T,
        *,
        code: CodeContract = SuccessCode.OK,
        message: str | None = None,
        request_id: str | None = None,
    ) -> ApiResponse[T]:
        if not 200 <= code.status_code < 300:
            raise ValueError("成功响应必须使用 2xx 响应码")

        return ApiResponse(
            code=self.code_builder.build(code),
            success=True,
            message=message if message is not None else code.message,
            data=data,
            request_id=_resolve_request_id(request_id),
        )

    def error(
        self,
        code: CodeContract = ErrorCode.BAD_REQUEST,
        *,
        message: str | None = None,
        data: object | None = None,
        request_id: str | None = None,
    ) -> ApiResponse[object]:
        if code.status_code < 400:
            raise ValueError("错误响应必须使用 4xx 或 5xx 响应码")

        return ApiResponse(
            code=self.code_builder.build(code),
            success=False,
            message=message if message is not None else code.message,
            data=data,
            request_id=_resolve_request_id(request_id),
        )


def _resolve_request_id(explicit: str | None) -> str | None:
    if explicit is not None:
        return explicit

    if not context.exists():
        return None

    request_id = context.get(HeaderKeys.request_id)
    return str(request_id) if request_id is not None else None
