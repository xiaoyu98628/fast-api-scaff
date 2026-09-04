from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.contexts.user.application.dto import UserDTO
from app.contexts.user.domain.values import UserStatus


class CreateUserRequest(BaseModel):
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
    model_config = ConfigDict(extra="forbid")

    status: UserStatus


class UserResponse(BaseModel):
    id: UUID
    username: str
    email: str
    status: UserStatus
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_dto(cls, user: UserDTO) -> UserResponse:
        return cls(
            id=user.id,
            username=user.username,
            email=user.email,
            status=user.status,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )
