"""创建并运行应用的 Console 命令入口。"""

from app.bootstrap.console.application import ConsoleHost
from app.bootstrap.console.logging import configure_console_logging
from app.config.settings import load_settings
from app.interfaces.console.cli import create_console, run_console
from app.interfaces.console.presentation import ConsolePresenter


def _run(presenter: ConsolePresenter) -> None:
    """在统一错误边界内加载配置并执行一次 Console 命令。"""

    settings = load_settings()
    configure_console_logging(settings)
    console = ConsoleHost(settings, presenter=presenter)
    create_console(console)()


def main() -> None:
    """执行 Console 应用，并统一处理结果展示与退出码。"""

    presenter = ConsolePresenter()
    run_console(lambda: _run(presenter), presenter)


if __name__ == "__main__":
    main()
