from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domain.user.entity import User
from app.domain.user.enums import UserStatus


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    nickname: str
    status: UserStatus
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_entity(cls, user: User) -> UserResponse:
        return cls(
            id=user.id,
            username=user.username,
            nickname=user.nickname,
            status=user.status,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )
