"""定义请求校验错误在 OpenAPI 中展示的数据模型。"""

from pydantic import BaseModel, ConfigDict


class ValidationErrorDetail(BaseModel):
    """请求参数校验失败时返回的单项详情。"""

    model_config = ConfigDict(frozen=True)

    type: str
    location: list[str | int]
    message: str
