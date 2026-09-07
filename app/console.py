from app.bootstrap.console.application import ConsoleHost
from app.interfaces.console.cli import create_console, run_console

_console = ConsoleHost()
app = create_console(_console)


def main() -> None:
    run_console(app, _console.presenter)


if __name__ == "__main__":
    main()
