"""验证日志 Handler 驱动的注册和配置转换。"""

import pytest

from app.infrastructure.logging.drivers.registry import (
    DEFAULT_LOGGING_DRIVERS,
    LoggingDriverRegistry,
)
from app.infrastructure.logging.drivers.stream import build_stream_handler
from app.infrastructure.logging.errors import LoggingConfigurationError


def test_stream_driver_builds_stdout_handler_definition() -> None:
    handler = build_stream_handler(
        {
            "driver": "stream",
            "stream": "stdout",
        }
    )

    assert handler == {
        "class": "logging.StreamHandler",
        "stream": "ext://sys.stdout",
    }


def test_default_drivers_contains_stream_builder() -> None:
    assert DEFAULT_LOGGING_DRIVERS.drivers == ("stream",)
    assert DEFAULT_LOGGING_DRIVERS.get("stream") is build_stream_handler


def test_driver_registry_rejects_empty_name() -> None:
    with pytest.raises(LoggingConfigurationError, match="名称不能为空"):
        LoggingDriverRegistry((("", build_stream_handler),))


def test_driver_registry_rejects_duplicate_name() -> None:
    with pytest.raises(LoggingConfigurationError, match="重复注册"):
        LoggingDriverRegistry(
            (
                ("stream", build_stream_handler),
                ("stream", build_stream_handler),
            )
        )


def test_driver_registry_extension_does_not_modify_default() -> None:
    def build_custom_handler(_raw_config: dict[str, object]) -> dict[str, object]:
        return {"class": "logging.NullHandler"}

    extended = DEFAULT_LOGGING_DRIVERS.extended(("custom", build_custom_handler))

    assert extended.drivers == ("stream", "custom")
    assert extended.get("custom") is build_custom_handler
    assert DEFAULT_LOGGING_DRIVERS.drivers == ("stream",)


def test_driver_registry_replacement_is_explicit_and_does_not_modify_default() -> None:
    def build_replacement_handler(_raw_config: dict[str, object]) -> dict[str, object]:
        return {"class": "logging.NullHandler"}

    replaced = DEFAULT_LOGGING_DRIVERS.replaced("stream", build_replacement_handler)

    assert replaced.drivers == ("stream",)
    assert replaced.get("stream") is build_replacement_handler
    assert DEFAULT_LOGGING_DRIVERS.get("stream") is build_stream_handler


def test_driver_registry_rejects_replacing_unknown_driver() -> None:
    with pytest.raises(LoggingConfigurationError, match="未注册"):
        DEFAULT_LOGGING_DRIVERS.replaced("missing", build_stream_handler)
