"""用户接口：RESTful 资源路径 + store/show/update/destroy 命名。"""

from fastapi import APIRouter, Depends
from starlette.requests import Request

from app.application.user.service import UserService
from app.common.response.json import JsonResponse
from app.interfaces.schemas.user import (
    UserPublic,
    UserStoreRequest,
    UserUpdateStatusRequest,
    UserUpdateRequest,
)

router = APIRouter(prefix="/users", tags=["users"])


def get_user_service() -> UserService:
    return UserService()


@router.post(path="", summary="新增用户")
async def store(
    request: Request,
    body: UserStoreRequest,
    service: UserService = Depends(get_user_service),
) -> JsonResponse[UserPublic]:
    result = await service.store(
        username=body.username,
        password=body.password,
        nickname=body.nickname,
    )
    data = UserPublic(id=result.id, username=result.username, nickname=result.nickname, status=result.status)
    return JsonResponse.success(
        data=data,
        message="创建成功",
        trace_id=getattr(request.state, "trace_id", None),
    )


@router.get(path="/{user_id}", summary="用户详情")
async def show(
    request: Request,
    user_id: str,
    service: UserService = Depends(get_user_service),
) -> JsonResponse[UserPublic]:
    result = await service.show(user_id)
    data = UserPublic(id=result.id, username=result.username, nickname=result.nickname, status=result.status)
    return JsonResponse.success(
        data=data,
        message="ok",
        trace_id=getattr(request.state, "trace_id", None),
    )


@router.patch(path="/{user_id}", summary="更新用户")
async def update(
    request: Request,
    user_id: str,
    body: UserUpdateRequest,
    service: UserService = Depends(get_user_service),
) -> JsonResponse[UserPublic]:
    result = await service.update(
        user_id,
        nickname=body.nickname,
        password=body.password,
    )
    data = UserPublic(id=result.id, username=result.username, nickname=result.nickname, status=result.status)
    return JsonResponse.success(
        data=data,
        message="更新成功",
        trace_id=getattr(request.state, "trace_id", None),
    )


@router.delete(path="/{user_id}", summary="删除用户（软删除）")
async def destroy(
    request: Request,
    user_id: str,
    service: UserService = Depends(get_user_service),
) -> JsonResponse[None]:
    await service.destroy(user_id)
    return JsonResponse.success(
        data=None,
        message="删除成功",
        trace_id=getattr(request.state, "trace_id", None),
    )


@router.patch(path="/{user_id}/status", summary="修改用户状态")
async def update_status(
    request: Request,
    user_id: str,
    body: UserUpdateStatusRequest,
    service: UserService = Depends(get_user_service),
) -> JsonResponse[UserPublic]:
    result = await service.update_status(user_id, status=body.status)
    data = UserPublic(id=result.id, username=result.username, nickname=result.nickname, status=result.status)
    return JsonResponse.success(
        data=data,
        message="状态修改成功",
        trace_id=getattr(request.state, "trace_id", None),
    )
