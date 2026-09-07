from app.bootstrap.console.application import ConsoleHost
from app.bootstrap.console.logging import configure_console_logging
from app.config.settings import load_settings
from app.interfaces.console.cli import create_console, run_console

settings = load_settings()
configure_console_logging(settings)

_console = ConsoleHost(settings)
app = create_console(_console)


def main() -> None:
    run_console(app, _console.presenter)


if __name__ == "__main__":
    main()
