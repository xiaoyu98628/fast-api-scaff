from dataclasses import dataclass
from datetime import datetime

import typer

from app.bootstrap.container import ApplicationContainer
from app.config.settings import Settings
from app.interfaces.console.application import ConsoleApplication


@dataclass(frozen=True, slots=True)
class ApplicationInfo:
    name: str
    version: str
    environment: str
    debug: bool
    timezone: str
    database_connections: tuple[str, ...]
    cache_connections: tuple[str, ...]


async def get_application_info(container: ApplicationContainer, settings: Settings) -> ApplicationInfo:
    local_time = datetime.now().astimezone()
    return ApplicationInfo(
        name=settings.app.name,
        version=settings.app.version,
        environment=settings.app.env,
        debug=settings.app.debug,
        timezone=f"{local_time.tzname()} ({local_time.strftime('%z')})",
        database_connections=container.databases.connection_names,
        cache_connections=container.caches.connection_names,
    )


def build_app_commands(console: ConsoleApplication) -> typer.Typer:
    commands = typer.Typer(help="查看应用运行信息。")

    @commands.command("info")
    def info() -> None:
        result = console.run(get_application_info)
        typer.echo(f"name: {result.name}")
        typer.echo(f"version: {result.version}")
        typer.echo(f"environment: {result.environment}")
        typer.echo(f"debug: {str(result.debug).lower()}")
        typer.echo(f"timezone: {result.timezone}")
        typer.echo(f"database_connections: {','.join(result.database_connections) or '-'}")
        typer.echo(f"cache_connections: {','.join(result.cache_connections) or '-'}")

    return commands
