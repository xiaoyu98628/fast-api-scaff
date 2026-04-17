"""用户相关 HTTP 请求/响应体。"""

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """登录请求体。"""

    username: str = Field(..., min_length=1, max_length=64, description="用户名")
    password: str = Field(..., min_length=1, max_length=128, description="密码")


class UserPublic(BaseModel):
    """返回给前端的用户信息（不含密码）。"""

    id: str
    username: str
    nickname: str


class LoginResponse(BaseModel):
    """登录成功响应体。"""

    access_token: str
    token_type: str
    expires_in: int
    user: UserPublic


class UserStoreRequest(BaseModel):
    """新增用户请求体（对应 ``store``）。"""

    username: str = Field(..., min_length=1, max_length=64, description="用户名")
    password: str = Field(..., min_length=1, max_length=128, description="密码")
    nickname: str = Field(..., min_length=1, max_length=64, description="昵称")


class UserUpdateRequest(BaseModel):
    """更新用户请求体（昵称与密码至少填一项）。"""

    nickname: str | None = Field(default=None, min_length=1, max_length=64, description="昵称")
    password: str | None = Field(default=None, min_length=1, max_length=128, description="新密码")
