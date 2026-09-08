"""创建并运行应用的 Console 命令入口。"""

from app.bootstrap.console.application import ConsoleHost
from app.bootstrap.console.logging import configure_console_logging
from app.config.settings import load_settings
from app.interfaces.console.cli import create_console, run_console

# 命令发现需要可复用的 Typer 应用，故在模块导入时完成一次宿主装配。
settings = load_settings()
configure_console_logging(settings)

_console = ConsoleHost(settings)
app = create_console(_console)


def main() -> None:
    """执行 Console 应用，并统一处理结果展示与退出码。"""

    run_console(app, _console.presenter)


if __name__ == "__main__":
    main()
