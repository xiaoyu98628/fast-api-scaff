from app.application.support.pagination import PageResult
from app.domain.user.entity import User
from app.interfaces.http.presenters.pagination import to_paginated as paginate_response
from app.interfaces.http.schemas.responses.pagination import PaginatedData
from app.interfaces.http.schemas.responses.user import UserResponse


def to_response(user: User) -> UserResponse:
    return UserResponse.from_entity(user)


def to_paginated(page: PageResult[User]) -> PaginatedData[UserResponse]:
    return paginate_response(page, to_response)
