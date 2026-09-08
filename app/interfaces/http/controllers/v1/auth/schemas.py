"""定义认证端点的 HTTP 请求与响应模型。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.contexts.user.application.auth_dto import TokenDTO


class LoginRequest(BaseModel):
    """校验登录请求字段并禁止额外输入。"""

    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=1024, repr=False, json_schema_extra={"writeOnly": True})


class TokenResponse(BaseModel):
    """向客户端返回 Bearer Token 及剩余有效秒数。"""

    access_token: str = Field(repr=False)
    token_type: Literal["bearer"] = "bearer"
    expires_in: int

    @classmethod
    def from_dto(cls, token: TokenDTO) -> TokenResponse:
        """从应用层 DTO 提取公开认证字段。"""

        return cls(access_token=token.access_token, expires_in=token.expires_in)
