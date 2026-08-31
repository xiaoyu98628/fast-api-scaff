from pydantic import BaseModel, ConfigDict, Field


class JsonResponse[T](BaseModel):
    """普通 JSON API 的统一响应结构。"""

    model_config = ConfigDict(frozen=True)

    code: str
    success: bool
    message: str
    data: T | None = None
    request_id: str | None = Field(default=None, exclude_if=lambda value: value is None)
