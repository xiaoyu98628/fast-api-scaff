"""提供登录、当前用户查询和退出登录端点。"""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Response, status

from app.contexts.user.application.auth_dto import LoginCommand
from app.contexts.user.application.auth_errors import AuthApplicationError
from app.contexts.user.jobs.login_succeeded import LoginSucceededJob
from app.infrastructure.logging.record import log_extra
from app.infrastructure.queue.errors import QueueError
from app.infrastructure.queue.job import job_reference
from app.interfaces.http.context import require_request_id
from app.interfaces.http.controllers.v1.auth.dependencies import AuthServiceDependency, SessionCredentialDependency
from app.interfaces.http.controllers.v1.auth.errors import auth_error_to_http
from app.interfaces.http.controllers.v1.auth.openapi import AUTH_REQUIRED_RESPONSE, AUTH_USER_NOT_FOUND_RESPONSE, AUTH_VALIDATION_RESPONSE
from app.interfaces.http.controllers.v1.auth.schemas import LoginRequest, TokenResponse
from app.interfaces.http.controllers.v1.users.schemas import UserResponse
from app.interfaces.http.dependencies.container import provide_application_container
from app.interfaces.http.dependencies.response import JsonResponseFactoryDependency
from app.interfaces.http.shared.response.json import JsonResponse
from app.runtime.container import ApplicationContainer

router = APIRouter(prefix="/auth", tags=["auth"])
_logger = logging.getLogger(__name__)


async def _publish_login_succeeded(
    container: ApplicationContainer,
    user_id: UUID,
    request_id: str,
) -> None:
    """在响应后尽力发布登录成功任务，并记录队列边界失败。"""

    try:
        await container.queues.dispatch(
            LoginSucceededJob(user_id=user_id),
            correlation_id=request_id,
        )
    except QueueError:
        # 异步副作用失败不能改变已经完成的认证结果，只记录稳定任务类型供诊断。
        _logger.exception(
            "Login succeeded job dispatch failed",
            extra=log_extra("user.login_succeeded.dispatch_failed", job_type=job_reference(LoginSucceededJob)),
        )


@router.post(
    "/login",
    response_model=JsonResponse[TokenResponse],
    responses={401: AUTH_REQUIRED_RESPONSE, 404: AUTH_USER_NOT_FOUND_RESPONSE, 422: AUTH_VALIDATION_RESPONSE},
)
async def login(
    payload: LoginRequest,
    service: AuthServiceDependency,
    responses: JsonResponseFactoryDependency,
    response: Response,
    background_tasks: BackgroundTasks,
    container: Annotated[ApplicationContainer, Depends(provide_application_container)],
) -> JsonResponse[TokenResponse]:
    """验证登录请求、签发会话，并安排登录成功任务。"""

    request_id = require_request_id()
    try:
        token = await service.login(LoginCommand(username=payload.username, password=payload.password))
    except AuthApplicationError as error:
        raise auth_error_to_http(error) from None

    # 登录响应先返回，队列发布作为 FastAPI BackgroundTask 在响应后执行。
    background_tasks.add_task(
        _publish_login_succeeded,
        container,
        token.user_id,
        request_id,
    )
    # Token 响应不得被浏览器或中间代理缓存。
    response.headers["Cache-Control"] = "no-store"
    return responses.success(TokenResponse.from_dto(token))


@router.get("/me", response_model=JsonResponse[UserResponse], responses={401: AUTH_REQUIRED_RESPONSE})
async def current_user(
    credential: SessionCredentialDependency,
    service: AuthServiceDependency,
    responses: JsonResponseFactoryDependency,
    response: Response,
) -> JsonResponse[UserResponse]:
    """根据 Bearer 会话返回当前启用用户。"""

    try:
        user = await service.current_user(credential)
    except AuthApplicationError as error:
        raise auth_error_to_http(error) from None

    response.headers["Cache-Control"] = "no-store"
    return responses.success(UserResponse.from_dto(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_class=Response, responses={401: AUTH_REQUIRED_RESPONSE})
async def logout(credential: SessionCredentialDependency, service: AuthServiceDependency) -> Response:
    """删除服务器端会话并返回无正文响应。"""

    await service.logout(credential)
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers={"Cache-Control": "no-store"})
