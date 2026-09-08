"""定义用户端点的 HTTP 请求与响应模型。"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.contexts.user.application.dto import UserDTO
from app.contexts.user.domain.values import UserStatus


class CreateUserRequest(BaseModel):
    """校验创建用户所需的基本资料和密码。"""

    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=32)
    email: str = Field(max_length=254)
    password: str = Field(min_length=8, max_length=128, repr=False)


class UpdateUserRequest(BaseModel):
    """完整更新可编辑的用户基本信息，不包含密码和状态。"""

    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=32)
    email: str = Field(max_length=254)


class ChangeUserStatusRequest(BaseModel):
    """限制状态修改请求只包含目标状态。"""

    model_config = ConfigDict(extra="forbid")

    status: UserStatus


class ResetUserPasswordRequest(BaseModel):
    """校验密码重置请求并隐藏密码表示。"""

    model_config = ConfigDict(extra="forbid")

    password: str = Field(min_length=8, max_length=128, repr=False)


class UserResponse(BaseModel):
    """定义用户聚合对 HTTP 客户端公开的字段。"""

    id: UUID
    username: str
    email: str
    status: UserStatus
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_dto(cls, user: UserDTO) -> UserResponse:
        """把应用层用户 DTO 转换为响应模型。"""

        return cls(
            id=user.id,
            username=user.username,
            email=user.email,
            status=user.status,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )
