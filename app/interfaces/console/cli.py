"""创建 Console 命令树并统一转换进程级失败。"""

from collections.abc import Callable

import typer
from pydantic import ValidationError

from app.infrastructure.cache.errors import CacheError
from app.infrastructure.database.errors import DatabaseError
from app.infrastructure.http.errors import HttpError
from app.infrastructure.logging.errors import LoggingConfigurationError
from app.infrastructure.queue.errors import QueueError
from app.infrastructure.vector.errors import VectorError
from app.interfaces.console.contracts import ConsoleExecutor
from app.interfaces.console.discovery import discover_console_commands
from app.interfaces.console.exit_codes import ConsoleExitCode
from app.interfaces.console.presentation import ConsolePresenter
from app.interfaces.console.registry import ConsoleCommandRegistry
from app.runtime.trace import TraceContext, TraceIdFactory, bind_trace_context, new_trace_id

type ConsoleEntrypoint = Callable[[], None]


def create_console(console: ConsoleExecutor) -> typer.Typer:
    """自动发现命令并创建可独立调用的 Typer 应用。"""

    application = typer.Typer(
        help="应用命令行入口。",
        no_args_is_help=True,
        pretty_exceptions_enable=False,
    )

    def show_version(value: bool) -> None:
        """在执行普通命令解析前处理全局版本选项。"""

        if not value:
            return

        console.presenter.text(f"{console.settings.app.name} {console.settings.app.version}")
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
        """声明 Console 根命令及其全局选项。"""

        _ = version

    # 所有具体命令由发现机制提供，入口不直接依赖业务命令模块。
    registry = ConsoleCommandRegistry(application)
    for command in discover_console_commands(console):
        registry.register(command)

    return application


def run_console(
    entrypoint: ConsoleEntrypoint,
    presenter: ConsolePresenter,
    *,
    command_id_factory: TraceIdFactory = new_trace_id,
) -> None:
    """执行 Console 入口并将可预期运行错误转换为稳定退出码。"""

    command_id = command_id_factory()
    trace_context = TraceContext(correlation_id=command_id, command_id=command_id)
    with bind_trace_context(trace_context):
        try:
            entrypoint()
        except (ValidationError, LoggingConfigurationError, DatabaseError, CacheError, HttpError, QueueError, VectorError) as error:
            # 仅转换配置和基础设施边界错误，未知编程错误保留原始堆栈。
            presenter.error(error)
            raise SystemExit(ConsoleExitCode.FAILURE) from None
