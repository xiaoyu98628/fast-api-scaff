from fastapi import APIRouter, Depends

from app.application.user.service import UserService
from app.interfaces.http.deps.user import get_user_service
from app.interfaces.http.presenters.user import to_paginated, to_response
from app.interfaces.http.schemas.requests.user import UserCreateRequest, UserListQuery, UserUpdateRequest
from app.interfaces.http.schemas.responses.pagination import PaginatedData
from app.interfaces.http.schemas.responses.user import UserResponse
from app.interfaces.http.support.response.code.success_code import SuccessCode
from app.interfaces.http.support.response.json import JsonResponse

router = APIRouter(prefix="/users", tags=["users"])


@router.get("")
async def list_users(
    query: UserListQuery = Depends(),
    service: UserService = Depends(get_user_service),
) -> JsonResponse[PaginatedData[UserResponse]]:
    result = await service.list_users(page=query.page, page_size=query.page_size, keyword=query.keyword)
    return JsonResponse.success(data=to_paginated(result))


@router.post("")
async def create_user(
    body: UserCreateRequest,
    service: UserService = Depends(get_user_service),
) -> JsonResponse[UserResponse]:
    user = await service.create_user(
        username=body.username,
        password=body.password,
        nickname=body.nickname,
        status=body.status,
    )
    return JsonResponse.success(data=to_response(user), code=SuccessCode.SUCCESS_CREATED)


@router.get("/{user_id}")
async def get_user(user_id: str, service: UserService = Depends(get_user_service)) -> JsonResponse[UserResponse]:
    user = await service.get_user(user_id)
    return JsonResponse.success(data=to_response(user))


@router.put("/{user_id}")
async def update_user(
    user_id: str,
    body: UserUpdateRequest,
    service: UserService = Depends(get_user_service),
) -> JsonResponse[UserResponse]:
    user = await service.update_user(
        user_id,
        nickname=body.nickname,
        password=body.password,
        status=body.status,
    )
    return JsonResponse.success(data=to_response(user))


@router.delete("/{user_id}")
async def delete_user(user_id: str, service: UserService = Depends(get_user_service)) -> JsonResponse[None]:
    await service.delete_user(user_id)
    return JsonResponse.success(data=None, code=SuccessCode.SUCCESS_OK)
