from pydantic import BaseModel, ConfigDict, Field
from starlette_context import context
from starlette_context.header_keys import HeaderKeys

from app.interfaces.http.shared.response.codes.builder import get_response_code_builder
from app.interfaces.http.shared.response.codes.contract import CodeContract
from app.interfaces.http.shared.response.codes.error_code import ErrorCode
from app.interfaces.http.shared.response.codes.success_code import SuccessCode


class JsonResponse[T](BaseModel):
    """普通 JSON API 的统一响应结构。"""

    model_config = ConfigDict(
        frozen=True,
        populate_by_name=True,
        serialize_by_alias=True,
    )

    code: str
    is_success: bool = Field(alias="success")
    message: str
    data: T | None = None
    request_id: str | None = Field(default=None, exclude_if=lambda value: value is None)

    @staticmethod
    def success[DataT](
        data: DataT,
        *,
        code: CodeContract = SuccessCode.OK,
        message: str | None = None,
        request_id: str | None = None,
    ) -> JsonResponse[DataT]:
        if not 200 <= code.status_code < 300:
            raise ValueError("成功响应必须使用 2xx 响应码")

        return JsonResponse(
            code=get_response_code_builder().build(code),
            is_success=True,
            message=message if message is not None else code.message,
            data=data,
            request_id=_resolve_request_id(request_id),
        )

    @staticmethod
    def error(
        code: CodeContract = ErrorCode.BAD_REQUEST,
        *,
        message: str | None = None,
        data: object | None = None,
        request_id: str | None = None,
    ) -> JsonResponse[object]:
        if code.status_code < 400:
            raise ValueError("错误响应必须使用 4xx 或 5xx 响应码")

        return JsonResponse(
            code=get_response_code_builder().build(code),
            is_success=False,
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
