from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.contexts.user.application.dto import UserDTO, UserPageDTO
from app.contexts.user.domain.values import UserStatus


class CreateUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=32)
    email: str = Field(max_length=254)
    display_name: str = Field(min_length=1, max_length=80)


class UpdateUserRequest(CreateUserRequest):
    status: UserStatus


class UserResponse(BaseModel):
    id: UUID
    username: str
    email: str
    display_name: str
    status: UserStatus
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_dto(cls, user: UserDTO) -> UserResponse:
        return cls(
            id=user.id,
            username=user.username,
            email=user.email,
            display_name=user.display_name,
            status=user.status,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )


class UserListResponse(BaseModel):
    items: list[UserResponse]
    total: int
    offset: int
    limit: int

    @classmethod
    def from_dto(cls, page: UserPageDTO) -> UserListResponse:
        return cls(
            items=[UserResponse.from_dto(user) for user in page.items],
            total=page.total,
            offset=page.offset,
            limit=page.limit,
        )
