from typing import Any, Generic, TypeVar

from pydantic import BaseModel


T = TypeVar("T")


class JsonResponse(BaseModel, Generic[T]):
    """统一 API 响应结构。"""

    code: int = 200
    message: str = "success"
    data: T | None = None
    trace_id: str | None = None

    @classmethod
    def success(
        cls,
        data: T | None = None,
        message: str = "success",
        code: int = 200,
        trace_id: str | None = None,
    ) -> "JsonResponse[T]":
        return cls(code=code, message=message, data=data, trace_id=trace_id)

    @classmethod
    def error(
        cls,
        message: str = "error",
        code: int = 500,
        data: Any | None = None,
        trace_id: str | None = None,
    ) -> "JsonResponse[Any]":
        return cls(code=code, message=message, data=data, trace_id=trace_id)
