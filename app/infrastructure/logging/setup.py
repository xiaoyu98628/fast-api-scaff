"""日志注册：按通道挂载文件/控制台；业务代码使用标准库 ``logging.getLogger(__name__)`` 即可。"""

import logging
from logging import Handler, Logger

from app.infrastructure.logging.handlers import build_console_handler, build_file_handler
from config.config import config

_configured = False


def _attach(logger: Logger, handlers: list[Handler], *, level_name: str) -> None:
    logger.handlers.clear()
    logger.setLevel(getattr(logging, level_name.upper(), logging.DEBUG))
    logger.propagate = False
    for handler in handlers:
        logger.addHandler(handler)


def configure_logging() -> None:
    global _configured
    if _configured:
        return

    cfg = config()
    log_settings = cfg.logging
    level = log_settings.resolved_level(app_debug=cfg.app.debug)
    channels = log_settings.channels(cfg.app.name, app_debug=cfg.app.debug)

    console_handler = build_console_handler(log_settings, level_name=level) if log_settings.console_enabled else None

    channel_handlers: dict[str, Handler] = {}
    for key, channel in channels.items():
        channel_handlers[key] = build_file_handler(channel.filename, channel, log_settings)

    app_channel = channels["app"]
    app_handlers: list[Handler] = [channel_handlers["app"]]
    if console_handler is not None:
        app_handlers.append(console_handler)
    _attach(logging.getLogger(app_channel.logger), app_handlers, level_name=level)

    for key in ("request", "exception"):
        channel = channels[key]
        _attach(logging.getLogger(channel.logger), [channel_handlers[key]], level_name=channel.level)

    db_channel = channels["db"]
    db_handlers = [channel_handlers["db"]]
    for logger_name in ("sqlalchemy.engine", "sqlalchemy.pool"):
        _attach(logging.getLogger(logger_name), db_handlers, level_name=db_channel.level)

    if console_handler is not None:
        for logger_name in ("uvicorn", "uvicorn.error"):
            _attach(logging.getLogger(logger_name), [console_handler], level_name=level)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(logging.WARNING)
    if console_handler is not None:
        root_logger.addHandler(console_handler)

    # 使用 app.request → request.log 记录访问日志，关闭 uvicorn 自带 access 避免重复。
    logging.getLogger("uvicorn.access").handlers.clear()
    logging.getLogger("uvicorn.access").propagate = False

    py_warnings = logging.getLogger("py.warnings")
    py_warnings.handlers.clear()
    py_warnings.addHandler(logging.NullHandler())
    py_warnings.setLevel(logging.WARNING)
    py_warnings.propagate = False

    _configured = True
