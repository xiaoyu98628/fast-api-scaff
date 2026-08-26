import pytest
from pydantic import ValidationError

from app.config.logging import LoggingSettings


def test_logging_defaults_to_stdout_stream() -> None:
    settings = LoggingSettings(_env_file=None)

    assert settings.level == "INFO"
    assert settings.access_enabled is True
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
