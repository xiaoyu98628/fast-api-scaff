from pydantic import BaseModel, ConfigDict


class ValidationErrorDetail(BaseModel):
    """请求参数校验失败时返回的单项详情。"""

    model_config = ConfigDict(frozen=True)

    type: str
    location: list[str | int]
    message: str
