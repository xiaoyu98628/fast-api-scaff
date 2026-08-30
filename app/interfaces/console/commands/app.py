from dataclasses import dataclass
from datetime import datetime

import typer

from app.interfaces.console.command import ConsoleCommand
from app.interfaces.console.context import ConsoleContext


@dataclass(frozen=True, slots=True)
class ApplicationInfo:
    name: str
    version: str
    environment: str
    debug: bool
    timezone: str
    database_connections: tuple[str, ...]
    cache_connections: tuple[str, ...]


async def get_application_info(context: ConsoleContext) -> ApplicationInfo:
    local_time = datetime.now().astimezone()
    return ApplicationInfo(
        name=context.settings.app.name,
        version=context.settings.app.version,
        environment=context.settings.app.env,
        debug=context.settings.app.debug,
        timezone=f"{local_time.tzname()} ({local_time.strftime('%z')})",
        database_connections=context.container.databases.connection_names,
        cache_connections=context.container.caches.connection_names,
    )


class AppInfoConsoleCommand(ConsoleCommand):
    group = "app"
    group_help = "查看应用运行信息。"
    name = "info"
    help = "显示应用配置和资源连接信息。"

    def handle(self) -> None:
        result = self._console.run(get_application_info)
        typer.echo(f"name: {result.name}")
        typer.echo(f"version: {result.version}")
        typer.echo(f"environment: {result.environment}")
        typer.echo(f"debug: {str(result.debug).lower()}")
        typer.echo(f"timezone: {result.timezone}")
        typer.echo(f"database_connections: {','.join(result.database_connections) or '-'}")
        typer.echo(f"cache_connections: {','.join(result.cache_connections) or '-'}")
