"""LogManager：读取 ``config/logging`` 声明，装配 handler 与 logger（对齐 Laravel LogManager）。"""

import logging
from logging import Handler, Logger
from pathlib import Path

from app.infrastructure.logging.channel import ChannelDefinition
from app.infrastructure.logging.handlers import build_console_handler, build_file_handler
from config.config import config
from config.logging import LoggingConfig

_configured = False


class LogManager:
    def __init__(self, settings: LoggingConfig) -> None:
        self._settings = settings
        self._level = settings.level
        self._console_handler: Handler | None = None
        self._file_handlers: dict[str, Handler] = {}

    def configure(self) -> None:
        global _configured
        if _configured:
            return

        channels = self._channels()

        if self._settings.console_enabled:
            self._console_handler = build_console_handler(self._settings, level_name=self._level)

        for name, channel in channels.items():
            self._file_handlers[name] = build_file_handler(channel.path, channel, self._settings)

        self._wire_app(channels["app"])
        self._wire_named_channels(channels, ("request", "exception"))
        self._wire_db(channels["db"])
        self._wire_console_fallback()
        self._silence_noisy_loggers()

        _configured = True

    def _channels(self) -> dict[str, ChannelDefinition]:
        channels: dict[str, ChannelDefinition] = {}
        for name, channel in self._settings.channels.items():
            channels[name] = ChannelDefinition(
                name=name,
                logger=channel.logger,
                path=Path(channel.path),
                level=channel.level,
                driver=channel.driver,
                also=tuple(channel.also),
                console=channel.console,
            )
        return channels

    def _wire_app(self, channel: ChannelDefinition) -> None:
        handlers: list[Handler] = [self._file_handlers["app"]]
        if self._console_handler is not None and channel.console:
            handlers.append(self._console_handler)
        self._attach(logging.getLogger(channel.logger), handlers, level_name=self._level)

    def _wire_named_channels(self, channels: dict[str, ChannelDefinition], names: tuple[str, ...]) -> None:
        for name in names:
            channel = channels[name]
            self._attach(
                logging.getLogger(channel.logger),
                [self._file_handlers[name]],
                level_name=channel.level,
            )

    def _wire_db(self, channel: ChannelDefinition) -> None:
        handlers = [self._file_handlers["db"]]
        logger_names = (channel.logger, *channel.also)
        for logger_name in logger_names:
            self._attach(logging.getLogger(logger_name), handlers, level_name=channel.level)

    @staticmethod
    def _attach(logger: Logger, handlers: list[Handler], *, level_name: str) -> None:
        logger.handlers.clear()
        logger.setLevel(getattr(logging, level_name.upper(), logging.DEBUG))
        logger.propagate = False
        for handler in handlers:
            logger.addHandler(handler)

    def _wire_console_fallback(self) -> None:
        if self._console_handler is None:
            return

        for logger_name in ("uvicorn", "uvicorn.error"):
            self._attach(logging.getLogger(logger_name), [self._console_handler], level_name=self._level)

        root_logger = logging.getLogger()
        root_logger.handlers.clear()
        root_logger.setLevel(logging.WARNING)
        root_logger.addHandler(self._console_handler)

    def _silence_noisy_loggers(self) -> None:
        logging.getLogger("uvicorn.access").handlers.clear()
        logging.getLogger("uvicorn.access").propagate = False

        py_warnings = logging.getLogger("py.warnings")
        py_warnings.handlers.clear()
        py_warnings.addHandler(logging.NullHandler())
        py_warnings.setLevel(logging.WARNING)
        py_warnings.propagate = False


def configure_logging() -> None:
    LogManager(config().logging).configure()
