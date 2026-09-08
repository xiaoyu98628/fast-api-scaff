"""定义普通 JSON API 的统一响应载荷。"""

from pydantic import BaseModel, ConfigDict, Field


class JsonResponse[T](BaseModel):
    """普通 JSON API 的统一响应结构。"""

    model_config = ConfigDict(frozen=True)

    code: str
    success: bool
    message: str
    data: T | None = None
    # HTTP 请求之外构造响应时没有 Request ID，此时直接省略字段而不是输出 null。
    request_id: str | None = Field(default=None, exclude_if=lambda value: value is None)
