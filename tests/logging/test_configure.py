import logging.config

import pytest

from app.config.app import AppSettings
from app.config.cache import CacheSettings
from app.config.cors import CorsSettings
from app.config.database import DatabaseSettings
from app.config.logging import LoggingSettings
from app.config.settings import Settings
from app.infrastructure.logging.configure import configure_logging
from app.infrastructure.logging.drivers.registry import DEFAULT_LOGGING_DRIVERS
from app.infrastructure.logging.errors import LoggingConfigurationError


def build_settings(logging_settings: LoggingSettings) -> Settings:
    return Settings(
        app=AppSettings(_env_file=None),
        database=DatabaseSettings(_env_file=None),
        cache=CacheSettings(_env_file=None),
        cors=CorsSettings(_env_file=None),
        logging=logging_settings,
    )


def test_configure_logging_resolves_active_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def capture_config(config: dict[str, object]) -> None:
        captured.update(config)

    monkeypatch.setattr(logging.config, "dictConfig", capture_config)

    configure_logging(build_settings(LoggingSettings(_env_file=None)))

    assert captured["handlers"] == {
        "stdout": {
            "class": "logging.StreamHandler",
            "filters": ["request_context"],
            "formatter": "json",
            "stream": "ext://sys.stdout",
        }
    }


def test_configure_logging_rejects_missing_active_handler() -> None:
    settings = build_settings(
        LoggingSettings(
            active_handlers=("missing",),
            handlers={},
            _env_file=None,
        )
    )

    with pytest.raises(LoggingConfigurationError, match="没有对应配置"):
        configure_logging(settings)


def test_configure_logging_accepts_extended_driver_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def build_custom_handler(_raw_config: dict[str, object]) -> dict[str, object]:
        return {
            "class": "logging.NullHandler",
        }

    def capture_config(config: dict[str, object]) -> None:
        captured.update(config)

    monkeypatch.setattr(logging.config, "dictConfig", capture_config)
    settings = build_settings(
        LoggingSettings(
            active_handlers=("custom",),
            handlers={"custom": {"driver": "custom"}},
            _env_file=None,
        )
    )

    configure_logging(
        settings,
        drivers={
            **DEFAULT_LOGGING_DRIVERS,
            "custom": build_custom_handler,
        },
    )

    assert captured["handlers"] == {
        "custom": {
            "class": "logging.NullHandler",
            "filters": ["request_context"],
            "formatter": "json",
        }
    }


def test_configure_logging_rejects_unknown_driver() -> None:
    settings = build_settings(
        LoggingSettings(
            handlers={"output": {"driver": "file"}},
            active_handlers=("output",),
            _env_file=None,
        )
    )

    with pytest.raises(LoggingConfigurationError, match="不支持的驱动"):
        configure_logging(settings)


def test_configure_logging_rejects_driver_owned_formatter() -> None:
    def build_invalid_handler(_raw_config: dict[str, object]) -> dict[str, object]:
        return {
            "class": "logging.NullHandler",
            "formatter": "custom",
        }

    settings = build_settings(
        LoggingSettings(
            handlers={"output": {"driver": "invalid"}},
            active_handlers=("output",),
            _env_file=None,
        )
    )

    with pytest.raises(LoggingConfigurationError, match="Core 保留字段"):
        configure_logging(settings, drivers={"invalid": build_invalid_handler})
