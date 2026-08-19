from app.bootstrap.container import ApplicationContainer
from app.config.settings import Settings
from app.platform.database.manager import DatabaseManager


def build_application_container(settings: Settings) -> ApplicationContainer:
    """构建并连接应用所需的组件。"""
    databases = DatabaseManager(settings.database)

    return ApplicationContainer(
        databases=databases,
        async_shutdown_callbacks=(databases.aclose,),
    )
