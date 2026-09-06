from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.bootstrap.container import ApplicationContainer
from app.contexts.user.application.auth_errors import AuthenticationRequiredError
from app.contexts.user.application.auth_service import AuthApplicationService
from app.contexts.user.application.session_token import SessionCredential
from app.interfaces.http.controllers.v1.auth.errors import auth_error_to_http
from app.interfaces.http.dependencies.container import provide_application_container

_bearer = HTTPBearer(auto_error=False, scheme_name="SessionBearer", description="登录接口返回的随机会话令牌")


def provide_auth_service(container: Annotated[ApplicationContainer, Depends(provide_application_container)]) -> AuthApplicationService:
    return container.users.auth


def provide_session_credential(
    authorization: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> SessionCredential:
    try:
        if authorization is None:
            raise AuthenticationRequiredError()
        return SessionCredential(token=authorization.credentials)
    except AuthenticationRequiredError as error:
        raise auth_error_to_http(error) from None


type AuthServiceDependency = Annotated[AuthApplicationService, Depends(provide_auth_service)]
type SessionCredentialDependency = Annotated[SessionCredential, Depends(provide_session_credential)]
