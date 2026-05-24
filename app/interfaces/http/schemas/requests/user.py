from pydantic import BaseModel, Field

from app.domain.user.enums import UserStatus
from app.interfaces.http.schemas.requests.pagination import PaginationQuery


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    nickname: str = Field(min_length=1, max_length=64)
    status: UserStatus = UserStatus.ACTIVATION


class UserUpdateRequest(BaseModel):
    nickname: str | None = Field(default=None, min_length=1, max_length=64)
    password: str | None = Field(default=None, min_length=6, max_length=128)
    status: UserStatus | None = None


class UserListQuery(PaginationQuery):
    keyword: str | None = Field(default=None, max_length=64)
