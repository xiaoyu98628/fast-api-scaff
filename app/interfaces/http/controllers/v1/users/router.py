from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.contexts.user.application.dto import CreateUserCommand, UpdateUserCommand
from app.contexts.user.application.errors import UserApplicationError
from app.contexts.user.domain.errors import UserDomainError
from app.interfaces.http.controllers.v1.users.dependencies import UserServiceDependency
from app.interfaces.http.controllers.v1.users.errors import user_error_to_http
from app.interfaces.http.controllers.v1.users.schemas import CreateUserRequest, UpdateUserRequest, UserResponse
from app.interfaces.http.dependencies.response import JsonResponseFactoryDependency
from app.interfaces.http.shared.pagination import PageParams, PageResponse
from app.interfaces.http.shared.response.codes.success_code import SuccessCode
from app.interfaces.http.shared.response.json import JsonResponse
from app.interfaces.shared.pagination import PageMeta, calculate_total_pages

router = APIRouter(prefix="/users", tags=["users"])


@router.post(
    "",
    status_code=SuccessCode.CREATED.status_code,
    response_model=JsonResponse[UserResponse],
)
async def create_user(
    payload: CreateUserRequest,
    service: UserServiceDependency,
    responses: JsonResponseFactoryDependency,
) -> JsonResponse[UserResponse]:
    try:
        user = await service.create(
            CreateUserCommand(
                username=payload.username,
                email=payload.email,
                display_name=payload.display_name,
            )
        )
    except (UserApplicationError, UserDomainError) as error:
        raise user_error_to_http(error) from error

    return responses.success(UserResponse.from_dto(user), code=SuccessCode.CREATED)


@router.get("", response_model=JsonResponse[PageResponse[UserResponse]])
async def list_users(
    service: UserServiceDependency,
    responses: JsonResponseFactoryDependency,
    pagination: Annotated[PageParams, Query()],
) -> JsonResponse[PageResponse[UserResponse]]:
    pagination_input = pagination.to_input()
    result = await service.list(
        offset=pagination_input.offset,
        limit=pagination_input.limit,
    )
    return responses.success(
        PageResponse[UserResponse](
            items=[UserResponse.from_dto(user) for user in result.items],
            meta=PageMeta(
                page=pagination_input.page,
                limit=pagination_input.limit,
                total=result.total,
                total_pages=calculate_total_pages(
                    total=result.total,
                    limit=pagination_input.limit,
                ),
            ),
        )
    )


@router.get("/{user_id}", response_model=JsonResponse[UserResponse])
async def get_user(
    user_id: UUID,
    service: UserServiceDependency,
    responses: JsonResponseFactoryDependency,
) -> JsonResponse[UserResponse]:
    try:
        user = await service.get(user_id)
    except UserApplicationError as error:
        raise user_error_to_http(error) from error

    return responses.success(UserResponse.from_dto(user))


@router.put("/{user_id}", response_model=JsonResponse[UserResponse])
async def update_user(
    user_id: UUID,
    payload: UpdateUserRequest,
    service: UserServiceDependency,
    responses: JsonResponseFactoryDependency,
) -> JsonResponse[UserResponse]:
    try:
        user = await service.update(
            UpdateUserCommand(
                user_id=user_id,
                username=payload.username,
                email=payload.email,
                display_name=payload.display_name,
                status=payload.status,
            )
        )
    except (UserApplicationError, UserDomainError) as error:
        raise user_error_to_http(error) from error

    return responses.success(UserResponse.from_dto(user))


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_user(user_id: UUID, service: UserServiceDependency) -> Response:
    try:
        await service.delete(user_id)
    except UserApplicationError as error:
        raise user_error_to_http(error) from error

    return Response(status_code=status.HTTP_204_NO_CONTENT)
