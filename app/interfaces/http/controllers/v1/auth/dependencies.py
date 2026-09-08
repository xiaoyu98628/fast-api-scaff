"""提供认证控制器使用的服务和 Bearer 会话凭据。"""

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.contexts.user.application.auth_errors import AuthenticationRequiredError
from app.contexts.user.application.auth_service import AuthApplicationService
from app.contexts.user.application.session_token import SessionCredential
from app.interfaces.http.controllers.v1.auth.errors import auth_error_to_http
from app.interfaces.http.dependencies.container import provide_application_container
from app.runtime.container import ApplicationContainer

# 禁用 HTTPBearer 的自动错误，以便凭据缺失和格式错误都遵循统一响应契约。
_bearer = HTTPBearer(auto_error=False, scheme_name="SessionBearer", description="登录接口返回的随机会话令牌")


def provide_auth_service(container: Annotated[ApplicationContainer, Depends(provide_application_container)]) -> AuthApplicationService:
    """从用户上下文取得认证应用服务。"""

    return container.users.auth


def provide_session_credential(
    authorization: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> SessionCredential:
    """把可选 Bearer 头转换为严格会话凭据或统一 401 异常。"""

    try:
        if authorization is None:
            raise AuthenticationRequiredError()
        return SessionCredential(token=authorization.credentials)
    except AuthenticationRequiredError as error:
        raise auth_error_to_http(error) from None


# 控制器只依赖标注类型，不直接访问应用容器或安全解析器。
type AuthServiceDependency = Annotated[AuthApplicationService, Depends(provide_auth_service)]
type SessionCredentialDependency = Annotated[SessionCredential, Depends(provide_session_credential)]
