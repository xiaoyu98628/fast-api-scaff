"""认证接口：登录等。"""

from fastapi import APIRouter, Depends
from starlette.requests import Request

from app.application.user.service import UserService
from app.common.response.json import JsonResponse
from app.interfaces.schemas.user import LoginRequest, LoginResponse, UserPublic

router = APIRouter(prefix="/auth", tags=["auth"])


def get_user_service() -> UserService:
    return UserService()


@router.post(path="/login", summary="登录")
async def login(
    request: Request,
    body: LoginRequest,
    service: UserService = Depends(get_user_service),
) -> JsonResponse[LoginResponse]:
    result = await service.login(body.username, body.password)
    data = LoginResponse(
        access_token=result.access_token,
        token_type=result.token_type,
        expires_in=result.expires_in,
        user=UserPublic(
            id=result.user.id,
            username=result.user.username,
            nickname=result.user.nickname,
        ),
    )
    return JsonResponse.success(
        data=data,
        message="登录成功",
        trace_id=getattr(request.state, "trace_id", None),
    )
