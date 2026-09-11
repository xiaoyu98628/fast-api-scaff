"""将应用日志设置装配为 Python logging 配置。"""

import logging.config

from pydantic import ValidationError

from app.config.settings import Settings
from app.infrastructure.logging.context import RuntimeContextFilter
from app.infrastructure.logging.drivers.registry import DEFAULT_LOGGING_DRIVERS, LoggingDriverRegistry
from app.infrastructure.logging.errors import LoggingConfigurationError
from app.infrastructure.logging.formatter import JsonLogFormatter, TextLogFormatter

_CORE_HANDLER_KEYS = frozenset({"filters", "formatter"})


def configure_logging(
    settings: Settings,
    *,
    drivers: LoggingDriverRegistry = DEFAULT_LOGGING_DRIVERS,
) -> None:
    """解析日志驱动并配置当前进程的 logging。"""

    handlers = _build_handlers(settings, drivers)
    active_handlers = list(settings.logging.active_handlers)

    # 保留第三方库已经创建的 logger，仅统一接管项目明确声明的命名空间。
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {
                "runtime_context": {
                    "()": RuntimeContextFilter,
                }
            },
            "formatters": {
                "json": {
                    "()": JsonLogFormatter,
                    "service": settings.app.name,
                    "environment": settings.app.env,
                    "service_version": settings.app.version,
                },
                "text": {
                    "()": TextLogFormatter,
                    "service": settings.app.name,
                    "environment": settings.app.env,
                    "service_version": settings.app.version,
                },
            },
            "handlers": handlers,
            "root": {
                "handlers": active_handlers,
                "level": "WARNING",
            },
            "loggers": {
                "app": {
                    "handlers": active_handlers,
                    "level": settings.logging.level,
                    "propagate": False,
                },
                "uvicorn": {
                    "handlers": active_handlers,
                    "level": settings.logging.level,
                    "propagate": False,
                },
                "uvicorn.access": {
                    # HTTPAccessLogMiddleware 已提供统一访问日志，关闭 Uvicorn 的重复输出。
                    "handlers": [],
                    "propagate": False,
                },
                "sqlalchemy": {
                    "handlers": active_handlers,
                    "level": "WARNING",
                    "propagate": False,
                },
            },
        }
    )


def _build_handlers(
    settings: Settings,
    drivers: LoggingDriverRegistry,
) -> dict[str, dict[str, object]]:
    """校验已启用 Handler，并通过注册表构建 dictConfig 片段。"""

    active_handlers = settings.logging.active_handlers
    if not active_handlers:
        raise LoggingConfigurationError("至少需要启用一个日志 Handler")

    if len(set(active_handlers)) != len(active_handlers):
        raise LoggingConfigurationError("启用的日志 Handler 不能重复")

    handlers: dict[str, dict[str, object]] = {}

    for name in active_handlers:
        raw_config = settings.logging.handlers.get(name)
        if raw_config is None:
            raise LoggingConfigurationError(f"启用的日志 Handler {name!r} 没有对应配置")

        driver = raw_config.get("driver")
        if not isinstance(driver, str) or not driver:
            raise LoggingConfigurationError(f"日志 Handler {name!r} 没有配置有效的 driver")

        builder = drivers.get(driver)
        if builder is None:
            raise LoggingConfigurationError(f"日志 Handler {name!r} 使用了不支持的驱动 {driver!r}")

        try:
            handler = builder(raw_config)
        except ValidationError as error:
            raise LoggingConfigurationError(f"日志 Handler {name!r} 配置不合法") from error

        reserved_keys = _CORE_HANDLER_KEYS.intersection(handler)
        if reserved_keys:
            rendered_keys = ", ".join(sorted(reserved_keys))
            raise LoggingConfigurationError(f"日志 Driver 不能配置 Core 保留字段：{rendered_keys}")

        # 格式和运行时关联上下文属于日志核心契约，不允许各驱动自行分叉。
        handlers[name] = {
            **handler,
            "formatter": settings.logging.format,
            "filters": ["runtime_context"],
        }

    return handlers
