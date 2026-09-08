"""提供用户创建、查询、修改和删除 HTTP 端点。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.contexts.user.application.dto import ChangeUserStatusCommand, CreateUserCommand, ResetUserPasswordCommand, UpdateUserCommand
from app.contexts.user.application.errors import UserApplicationError
from app.contexts.user.domain.errors import UserDomainError
from app.interfaces.http.controllers.v1.users.dependencies import UserServiceDependency
from app.interfaces.http.controllers.v1.users.errors import user_error_to_http
from app.interfaces.http.controllers.v1.users.openapi import (
    USER_CONFLICT_RESPONSE,
    USER_NOT_FOUND_RESPONSE,
    USER_VALIDATION_ERROR_RESPONSE,
)
from app.interfaces.http.controllers.v1.users.schemas import (
    ChangeUserStatusRequest,
    CreateUserRequest,
    ResetUserPasswordRequest,
    UpdateUserRequest,
    UserResponse,
)
from app.interfaces.http.dependencies.response import JsonResponseFactoryDependency
from app.interfaces.http.shared.pagination import PageParams, PageResponse, build_page_response
from app.interfaces.http.shared.response.codes.success_code import SuccessCode
from app.interfaces.http.shared.response.json import JsonResponse

router = APIRouter(prefix="/users", tags=["users"])


@router.post(
    "",
    status_code=SuccessCode.CREATED.status_code,
    response_model=JsonResponse[UserResponse],
    responses={
        409: USER_CONFLICT_RESPONSE,
        422: USER_VALIDATION_ERROR_RESPONSE,
    },
)
async def create_user(
    payload: CreateUserRequest,
    service: UserServiceDependency,
    responses: JsonResponseFactoryDependency,
) -> JsonResponse[UserResponse]:
    """把创建请求转换为应用命令并返回 201 响应。"""

    try:
        user = await service.create(
            CreateUserCommand(
                username=payload.username,
                email=payload.email,
                password=payload.password,
            )
        )
    except (UserApplicationError, UserDomainError) as error:
        raise user_error_to_http(error) from error

    return responses.success(UserResponse.from_dto(user), code=SuccessCode.CREATED)


@router.get(
    "",
    response_model=JsonResponse[PageResponse[UserResponse]],
    responses={422: USER_VALIDATION_ERROR_RESPONSE},
)
async def list_users(
    service: UserServiceDependency,
    responses: JsonResponseFactoryDependency,
    pagination: Annotated[PageParams, Query()],
) -> JsonResponse[PageResponse[UserResponse]]:
    """查询一页用户并转换为统一分页响应。"""

    result = await service.list(
        offset=pagination.offset,
        limit=pagination.limit,
    )
    return responses.success(
        build_page_response(
            items=result.items,
            total=result.total,
            pagination=pagination,
            item_mapper=UserResponse.from_dto,
        )
    )


@router.get(
    "/{user_id}",
    response_model=JsonResponse[UserResponse],
    responses={
        404: USER_NOT_FOUND_RESPONSE,
        422: USER_VALIDATION_ERROR_RESPONSE,
    },
)
async def get_user(
    user_id: UUID,
    service: UserServiceDependency,
    responses: JsonResponseFactoryDependency,
) -> JsonResponse[UserResponse]:
    """按路径 UUID 返回单个用户。"""

    try:
        user = await service.get(user_id)
    except UserApplicationError as error:
        raise user_error_to_http(error) from error

    return responses.success(UserResponse.from_dto(user))


@router.put(
    "/{user_id}",
    response_model=JsonResponse[UserResponse],
    responses={
        404: USER_NOT_FOUND_RESPONSE,
        409: USER_CONFLICT_RESPONSE,
        422: USER_VALIDATION_ERROR_RESPONSE,
    },
)
async def update_user(
    user_id: UUID,
    payload: UpdateUserRequest,
    service: UserServiceDependency,
    responses: JsonResponseFactoryDependency,
) -> JsonResponse[UserResponse]:
    """完整更新用户可编辑的基本资料。"""

    try:
        user = await service.update(
            UpdateUserCommand(
                user_id=user_id,
                username=payload.username,
                email=payload.email,
            )
        )
    except (UserApplicationError, UserDomainError) as error:
        raise user_error_to_http(error) from error

    return responses.success(UserResponse.from_dto(user))


@router.patch(
    "/{user_id}/status",
    response_model=JsonResponse[UserResponse],
    responses={
        404: USER_NOT_FOUND_RESPONSE,
        422: USER_VALIDATION_ERROR_RESPONSE,
    },
)
async def change_user_status(
    user_id: UUID,
    payload: ChangeUserStatusRequest,
    service: UserServiceDependency,
    responses: JsonResponseFactoryDependency,
) -> JsonResponse[UserResponse]:
    """单独修改用户账户状态。"""

    try:
        user = await service.change_status(
            ChangeUserStatusCommand(
                user_id=user_id,
                status=payload.status,
            )
        )
    except (UserApplicationError, UserDomainError) as error:
        raise user_error_to_http(error) from error

    return responses.success(UserResponse.from_dto(user))


@router.put(
    "/{user_id}/password",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses={
        404: USER_NOT_FOUND_RESPONSE,
        422: USER_VALIDATION_ERROR_RESPONSE,
    },
)
async def reset_user_password(
    user_id: UUID,
    payload: ResetUserPasswordRequest,
    service: UserServiceDependency,
) -> Response:
    """重置用户密码并返回无正文响应。"""

    try:
        await service.reset_password(
            ResetUserPasswordCommand(
                user_id=user_id,
                password=payload.password,
            )
        )
    except (UserApplicationError, UserDomainError) as error:
        raise user_error_to_http(error) from error

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses={
        404: USER_NOT_FOUND_RESPONSE,
        422: USER_VALIDATION_ERROR_RESPONSE,
    },
)
async def delete_user(user_id: UUID, service: UserServiceDependency) -> Response:
    """删除指定用户并返回无正文响应。"""

    try:
        await service.delete(user_id)
    except UserApplicationError as error:
        raise user_error_to_http(error) from error

    return Response(status_code=status.HTTP_204_NO_CONTENT)
