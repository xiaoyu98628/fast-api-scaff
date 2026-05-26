
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.infrastructure.context.request_scope import trace_id_for_json
from app.interfaces.http.support.response.code.contract import CodedEnum
from app.interfaces.http.support.response.code.error_code import ErrorCode
from app.interfaces.http.support.response.code.success_code import SuccessCode


class JsonResponse[T](BaseModel):
    """统一 API 响应结构。

    错误响应中的 ``code`` 推荐使用 10 位字符串，避免前导 ``0`` 丢失。
    """

    model_config = ConfigDict(populate_by_name=True)

    code: int | str = 200
    is_success: bool = Field(default=True, alias="success")
    message: str = "success"
    data: T | None = None
    trace_id: str | None = None

    @classmethod
    def success(
        cls,
        data: T | None = None,
        message: str | None = "success",
        code: CodedEnum = SuccessCode.SUCCESS_OK,
        trace_id: str | None = None,
    ) -> JsonResponse[T]:

        success_message = message if message is not None else code.message

        return cls(
            code=code.full_code(),
            is_success=True,
            message=success_message,
            data=data,
            trace_id=trace_id_for_json(explicit=trace_id),
        )

    @classmethod
    def error(
        cls,
        code: CodedEnum = ErrorCode.REQUEST_ERROR,
        message: str | None = None,
        data: Any | None = None,
        trace_id: str | None = None,
    ) -> JsonResponse[Any]:

        error_message = message if message is not None else code.message

        return cls(
            code=code.full_code(),
            is_success=False,
            message=error_message,
            data=data,
            trace_id=trace_id_for_json(explicit=trace_id),
        )
