"""与 HTTP 无关的通用响应壳；接口层可直接返回本模型或由 FastAPI 序列化。

错误响应中的 ``code`` 推荐使用 10 位字符串（如 ``4040011001``）以避免前导 ``0`` 丢失。
"""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class JsonResponse(BaseModel, Generic[T]):
    """统一 API 响应结构。"""

    code: int | str = 200
    message: str = "success"
    data: T | None = None
    trace_id: str | None = None

    @classmethod
    def success(
        cls,
        data: T | None = None,
        message: str = "success",
        code: int | str = 200,
        trace_id: str | None = None,
    ) -> "JsonResponse[T]":
        return cls(code=code, message=message, data=data, trace_id=trace_id)

    @classmethod
    def error(
        cls,
        message: str = "error",
        code: int | str = 0,
        data: Any | None = None,
        trace_id: str | None = None,
    ) -> "JsonResponse[Any]":
        return cls(code=code, message=message, data=data, trace_id=trace_id)
