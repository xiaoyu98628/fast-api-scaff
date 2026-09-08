"""配置 Console 宿主的日志输出约定。"""

from app.config.settings import Settings
from app.infrastructure.logging.configure import configure_logging
from app.infrastructure.logging.contracts.driver import LoggingHandlerConfig
from app.infrastructure.logging.drivers.registry import DEFAULT_LOGGING_DRIVERS
from app.infrastructure.logging.drivers.stream import build_stream_handler


def build_console_stream_handler(raw_config: dict[str, object]) -> LoggingHandlerConfig:
    """让 Console 的 stream 日志使用 stderr，保持 stdout 只包含命令结果。"""

    handler = build_stream_handler(raw_config)
    if handler.get("stream") == "ext://sys.stdout":
        handler["stream"] = "ext://sys.stderr"

    return handler


# Console 有意改变内置 stream 行为，因此使用显式替换而不是重复注册。
CONSOLE_LOGGING_DRIVERS = DEFAULT_LOGGING_DRIVERS.replaced("stream", build_console_stream_handler)


def configure_console_logging(settings: Settings) -> None:
    """使用 Console 宿主的标准流约定配置日志。"""

    configure_logging(settings, drivers=CONSOLE_LOGGING_DRIVERS)
