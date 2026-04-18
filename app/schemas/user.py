"""用户相关 HTTP 请求/响应体。"""

from pydantic import BaseModel, Field

from app.enums.user_status import UserStatus


class PageMeta(BaseModel):
    """分页元数据（与统一响应内层 ``meta`` 对齐）。"""

    current_page: int = Field(..., ge=1, description="当前页码")
    last_page: int = Field(..., ge=1, description="最后一页页码")
    total: int = Field(..., ge=0, description="总条数")
    page_size: int = Field(..., ge=1, description="每页条数")


class LoginRequest(BaseModel):
    """登录请求体。"""

    username: str = Field(..., min_length=1, max_length=64, description="用户名")
    password: str = Field(..., min_length=1, max_length=128, description="密码")


class UserPublic(BaseModel):
    """返回给前端的用户信息（不含密码）。"""

    id: str
    username: str
    nickname: str
    status: UserStatus


class UserListPayload(BaseModel):
    """用户列表接口中 ``data`` 字段的内层结构：列表 + 分页。"""

    data: list[UserPublic]
    meta: PageMeta


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


class UserUpdateStatusRequest(BaseModel):
    """修改用户状态请求体。"""

    status: UserStatus = Field(..., description="状态（activation/locking）")
