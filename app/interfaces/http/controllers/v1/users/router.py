from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.contexts.user.application.dto import CreateUserCommand, UpdateUserCommand
from app.contexts.user.application.errors import UserApplicationError
from app.contexts.user.domain.errors import UserDomainError
from app.interfaces.http.controllers.v1.users.dependencies import UserServiceDependency
from app.interfaces.http.controllers.v1.users.errors import user_error_to_http
from app.interfaces.http.controllers.v1.users.schemas import CreateUserRequest, UpdateUserRequest, UserListResponse, UserResponse
from app.interfaces.http.dependencies.response import JsonResponseFactoryDependency
from app.interfaces.http.shared.response.codes.success_code import SuccessCode
from app.interfaces.http.shared.response.json import JsonResponse

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


@router.get("", response_model=JsonResponse[UserListResponse])
async def list_users(
    service: UserServiceDependency,
    responses: JsonResponseFactoryDependency,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> JsonResponse[UserListResponse]:
    page = await service.list(offset=offset, limit=limit)
    return responses.success(UserListResponse.from_dto(page))


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
