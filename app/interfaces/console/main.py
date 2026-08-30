import typer

from app.interfaces.console.application import ConsoleApplication
from app.interfaces.console.discovery import discover_console_commands
from app.interfaces.console.registry import ConsoleCommandRegistry


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
        typer.echo(f"{settings.app.name} {settings.app.version}")
        raise typer.Exit()

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


app = create_console()


def main() -> None:
    app()
