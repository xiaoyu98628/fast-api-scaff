import typer

from app.interfaces.console.application import ConsoleApplication
from app.interfaces.console.commands.app import build_app_commands
from app.interfaces.console.commands.users import build_user_commands


def create_console(console: ConsoleApplication | None = None) -> typer.Typer:
    active_console = console if console is not None else ConsoleApplication()
    application = typer.Typer(
        name="scaff",
        help="fast-api-scaff 应用命令行入口。",
        no_args_is_help=True,
        pretty_exceptions_enable=False,
    )
    application.add_typer(build_app_commands(active_console), name="app")
    application.add_typer(build_user_commands(active_console), name="users")
    return application


app = create_console()


def main() -> None:
    app()
