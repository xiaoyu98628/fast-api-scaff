"""提供查看应用运行信息的 Console 命令。"""

from dataclasses import dataclass
from datetime import datetime

from app.config.settings import Settings
from app.interfaces.console.command import ConsoleCommand


@dataclass(frozen=True, slots=True)
class ApplicationInfo:
    """描述可安全展示的应用和资源配置摘要。"""

    name: str
    version: str
    environment: str
    debug: bool
    timezone: str
    database_connections: tuple[str, ...]
    cache_connections: tuple[str, ...]
    queue_connections: tuple[str, ...]
    vector_connections: tuple[str, ...]


def get_application_info(settings: Settings) -> ApplicationInfo:
    """从配置快照生成应用信息，不初始化外部资源。"""

    local_time = datetime.now().astimezone()
    return ApplicationInfo(
        name=settings.app.name,
        version=settings.app.version,
        environment=settings.app.env,
        debug=settings.app.debug,
        timezone=f"{local_time.tzname()} ({local_time.strftime('%z')})",
        database_connections=tuple(settings.database.connections),
        cache_connections=tuple(settings.cache.connections),
        queue_connections=tuple(settings.queue.connections),
        vector_connections=tuple(settings.vector.connections),
    )


class AppInfoConsoleCommand(ConsoleCommand):
    """注册并处理 ``app info`` 命令。"""

    group = "app"
    group_help = "查看应用运行信息。"
    name = "info"
    help = "显示应用配置和资源连接信息。"

    def handle(self) -> None:
        """收集应用摘要并通过统一 Presenter 输出。"""

        result = get_application_info(self._console.settings)
        self._console.presenter.result(result)
