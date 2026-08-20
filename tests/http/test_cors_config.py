import pytest
from pydantic import ValidationError

from app.config.cors import CorsSettings


def test_cors_defaults_are_safe_for_wildcard_origin() -> None:
    settings = CorsSettings(_env_file=None)

    assert settings.allow_origins == ["*"]
    assert settings.allow_methods == ["*"]
    assert settings.allow_headers == ["*"]
    assert settings.allow_credentials is False
    assert settings.expose_headers == []
    assert settings.max_age == 600


def test_cors_environment_is_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", '["https://app.example.com"]')
    monkeypatch.setenv("CORS_ALLOW_METHODS", '["GET", "POST"]')
    monkeypatch.setenv("CORS_ALLOW_HEADERS", '["Authorization"]')
    monkeypatch.setenv("CORS_ALLOW_CREDENTIALS", "true")
    monkeypatch.setenv("CORS_EXPOSE_HEADERS", '["X-Request-ID"]')
    monkeypatch.setenv("CORS_MAX_AGE", "1200")

    settings = CorsSettings(_env_file=None)

    assert settings.allow_origins == ["https://app.example.com"]
    assert settings.allow_methods == ["GET", "POST"]
    assert settings.allow_headers == ["Authorization"]
    assert settings.allow_credentials is True
    assert settings.expose_headers == ["X-Request-ID"]
    assert settings.max_age == 1200


def test_wildcard_origin_cannot_be_combined_with_credentials() -> None:
    with pytest.raises(ValidationError, match="CORS_ALLOW_ORIGINS"):
        CorsSettings(
            allow_origins=["*"],
            allow_credentials=True,
            _env_file=None,
        )


def test_explicit_origin_can_be_combined_with_credentials() -> None:
    settings = CorsSettings(
        allow_origins=["https://app.example.com"],
        allow_credentials=True,
        _env_file=None,
    )

    assert settings.allow_credentials is True


def test_cors_max_age_cannot_be_negative() -> None:
    with pytest.raises(ValidationError):
        CorsSettings(max_age=-1, _env_file=None)
