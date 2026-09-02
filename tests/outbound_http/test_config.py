import os

import pytest
from pydantic import ValidationError

from app.config.http import HttpPoolSettings, HttpSettings
from app.runtime.paths import PROJECT_ROOT


def test_nested_environment_is_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTP_TIMEOUT__CONNECT", "1.5")
    monkeypatch.setenv("HTTP_POOL__MAX_CONNECTIONS", "40")
    monkeypatch.setenv("HTTP_STREAM_POOL__MAX_KEEPALIVE_CONNECTIONS", "5")
    monkeypatch.setenv("HTTP_POOL_WARNING_RATIO", "0.75")
    monkeypatch.setenv("HTTP_MAX_RESPONSE_BYTES", "2048")
    monkeypatch.setenv("HTTP_TRUST_ENV", "true")

    settings = HttpSettings(_env_file=None)

    assert settings.timeout.connect == 1.5
    assert settings.pool.max_connections == 40
    assert settings.stream_pool.max_keepalive_connections == 5
    assert settings.pool_warning_ratio == 0.75
    assert settings.max_response_bytes == 2048
    assert settings.trust_env is True


def test_keepalive_capacity_cannot_exceed_total_capacity() -> None:
    with pytest.raises(ValidationError, match="max_keepalive_connections"):
        HttpPoolSettings(max_connections=1, max_keepalive_connections=2)


@pytest.mark.parametrize("value", [0, -0.1, 1.1])
def test_pool_warning_ratio_must_be_within_valid_range(value: float) -> None:
    with pytest.raises(ValidationError, match="pool_warning_ratio"):
        HttpSettings(pool_warning_ratio=value, _env_file=None)


def test_sample_environment_contains_valid_http_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in tuple(os.environ):
        if name.startswith("HTTP_"):
            monkeypatch.delenv(name)

    settings = HttpSettings(_env_file=PROJECT_ROOT / "sample.env")

    assert settings.pool.max_connections >= settings.pool.max_keepalive_connections
    assert settings.stream_pool.max_connections >= settings.stream_pool.max_keepalive_connections
    assert settings.max_response_bytes > 0
