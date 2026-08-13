from app.bootstrap.container import ApplicationContainer
from app.config.settings import Settings


def build_application_container(_settings: Settings) -> ApplicationContainer:
    """构建并连接应用所需的组件。"""
    return ApplicationContainer()
