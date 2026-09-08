"""提供用户控制器需要的应用服务依赖。"""

from typing import Annotated

from fastapi import Depends

from app.contexts.user.application.service import UserApplicationService
from app.interfaces.http.dependencies.container import provide_application_container
from app.runtime.container import ApplicationContainer

# 先把容器依赖命名，避免每个业务服务提供器重复声明 FastAPI 元数据。
type ApplicationContainerDependency = Annotated[ApplicationContainer, Depends(provide_application_container)]


def provide_user_service(container: ApplicationContainerDependency) -> UserApplicationService:
    """提供用户 Controller 所需的应用服务。"""

    return container.users.service


type UserServiceDependency = Annotated[UserApplicationService, Depends(provide_user_service)]
