from collections.abc import Callable

import typer
from pydantic import ValidationError

from app.infrastructure.cache.errors import CacheError
from app.infrastructure.database.errors import DatabaseError
from app.infrastructure.http.errors import HttpError
from app.infrastructure.logging.errors import LoggingConfigurationError
from app.interfaces.console.application import ConsoleApplication
from app.interfaces.console.discovery import discover_console_commands
from app.interfaces.console.exit_codes import ConsoleExitCode
from app.interfaces.console.presentation import ConsolePresenter
from app.interfaces.console.registry import ConsoleCommandRegistry

type ConsoleEntrypoint = Callable[[], None]


def create_console(console: ConsoleApplication | None = None) -> typer.Typer:
    active_console = console if console is not None else ConsoleApplication()
    application = typer.Typer(
        help="应用命令行入口。",
        no_args_is_help=True,
        pretty_exceptions_enable=False,
    )

    def show_version(value: bool) -> None:
        if not value:
            return

        settings = active_console.settings_loader()
        active_console.presenter.text(f"{settings.app.name} {settings.app.version}")
        raise typer.Exit(code=ConsoleExitCode.SUCCESS)

    @application.callback()
    def root(
        version: bool = typer.Option(
            False,
            "--version",
            callback=show_version,
            is_eager=True,
            help="显示应用名称和版本。",
        ),
    ) -> None:
        _ = version

    registry = ConsoleCommandRegistry(application)
    for command in discover_console_commands(active_console):
        registry.register(command)

    return application


_console = ConsoleApplication()
app = create_console(_console)


def run_console(entrypoint: ConsoleEntrypoint, presenter: ConsolePresenter) -> None:
    """执行 Console 入口并将可预期运行错误转换为稳定退出码。"""
    try:
        entrypoint()
    except (ValidationError, LoggingConfigurationError, DatabaseError, CacheError, HttpError) as error:
        presenter.error(error)
        raise SystemExit(ConsoleExitCode.FAILURE) from None


def main() -> None:
    run_console(app, _console.presenter)
