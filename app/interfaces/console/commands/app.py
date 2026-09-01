from dataclasses import dataclass
from datetime import datetime

from app.config.settings import Settings
from app.interfaces.console.command import ConsoleCommand


@dataclass(frozen=True, slots=True)
class ApplicationInfo:
    name: str
    version: str
    environment: str
    debug: bool
    timezone: str
    database_connections: tuple[str, ...]
    cache_connections: tuple[str, ...]


def get_application_info(settings: Settings) -> ApplicationInfo:
    local_time = datetime.now().astimezone()
    return ApplicationInfo(
        name=settings.app.name,
        version=settings.app.version,
        environment=settings.app.env,
        debug=settings.app.debug,
        timezone=f"{local_time.tzname()} ({local_time.strftime('%z')})",
        database_connections=tuple(settings.database.connections),
        cache_connections=tuple(settings.cache.connections),
    )


class AppInfoConsoleCommand(ConsoleCommand):
    group = "app"
    group_help = "查看应用运行信息。"
    name = "info"
    help = "显示应用配置和资源连接信息。"

    def handle(self) -> None:
        result = get_application_info(self._console.settings_loader())
        self._console.presenter.result(result)
