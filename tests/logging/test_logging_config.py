import pytest
from pydantic import ValidationError

from app.config.logging import LoggingSettings


def test_logging_defaults_to_json_stdout_stream() -> None:
    settings = LoggingSettings(_env_file=None)

    assert settings.level == "INFO"
    assert settings.format == "json"
    assert settings.access_enabled is True
    assert settings.access_exclude_routes == frozenset({"/health"})
    assert settings.active_handlers == ("stdout",)
    assert settings.handlers == {
        "stdout": {
            "driver": "stream",
            "stream": "stdout",
        }
    }


def test_logging_rejects_unknown_level() -> None:
    with pytest.raises(ValidationError):
        LoggingSettings.model_validate({"level": "TRACE"})


def test_logging_reads_text_format_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_FORMAT", "text")

    settings = LoggingSettings(_env_file=None)

    assert settings.format == "text"


def test_logging_rejects_unknown_format() -> None:
    with pytest.raises(ValidationError):
        LoggingSettings.model_validate({"format": "console"})


def test_logging_rejects_invalid_excluded_route() -> None:
    with pytest.raises(ValidationError, match="必须以 '/' 开头"):
        LoggingSettings(access_exclude_routes=frozenset({"health"}), _env_file=None)
