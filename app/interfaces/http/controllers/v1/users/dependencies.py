from typing import Annotated

from fastapi import Depends

from app.bootstrap.container import ApplicationContainer
from app.contexts.user.application.service import UserApplicationService
from app.interfaces.http.dependencies.container import provide_application_container

type ApplicationContainerDependency = Annotated[ApplicationContainer, Depends(provide_application_container)]


def provide_user_service(container: ApplicationContainerDependency) -> UserApplicationService:
    """提供用户 Controller 所需的应用服务。"""
    return container.users.service


type UserServiceDependency = Annotated[UserApplicationService, Depends(provide_user_service)]
