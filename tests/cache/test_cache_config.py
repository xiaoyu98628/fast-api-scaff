import pytest
from pydantic import ValidationError

from app.config.cache import CacheSettings, MemcachedConnectionSettings, RedisConnectionSettings


def test_raw_settings_do_not_validate_connection_semantics() -> None:
    settings = CacheSettings(
        default="missing",
        connections={"broken": {"driver": "memcached"}},
        _env_file=None,
    )

    assert settings.default == "missing"
    assert settings.connections == {"broken": {"driver": "memcached"}}


def test_nested_environment_is_loaded_as_raw_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CACHE_DEFAULT", "session")
    monkeypatch.setenv("CACHE_KEY_PREFIX", "shared:")
    monkeypatch.setenv("CACHE_CONNECTIONS__SESSION__DRIVER", "redis")
    monkeypatch.setenv("CACHE_CONNECTIONS__SESSION__HOST", "127.0.0.1")
    monkeypatch.setenv("CACHE_CONNECTIONS__SESSION__DATABASE", "2")

    settings = CacheSettings(_env_file=None)

    assert settings.default == "session"
    assert settings.key_prefix == "shared:"
    assert settings.connections == {
        "session": {
            "driver": "redis",
            "host": "127.0.0.1",
            "database": 2,
        }
    }


@pytest.mark.parametrize(
    ("connection_prefix", "default_prefix", "expected"),
    [
        (None, "shared:", "shared:"),
        ("session:", "shared:", "session:"),
        ("", "shared:", ""),
    ],
)
def test_connection_key_prefix_overrides_global_default(
    connection_prefix: str | None,
    default_prefix: str,
    expected: str,
) -> None:
    settings = RedisConnectionSettings(
        driver="redis",
        host="127.0.0.1",
        key_prefix=connection_prefix,
    )

    assert settings.resolve_key_prefix(default_prefix) == expected


def test_cache_drivers_share_pool_defaults_and_allow_connection_override() -> None:
    redis = RedisConnectionSettings(
        driver="redis",
        host="127.0.0.1",
        max_connections=20,
    )
    memcached = MemcachedConnectionSettings(
        driver="memcached",
        host="127.0.0.1",
        username="user",
        password="secret",
    )

    assert redis.max_connections == 20
    assert redis.connect_timeout == 5.0
    assert redis.read_timeout == 5.0
    assert memcached.max_connections == 10
    assert memcached.connect_timeout == 5.0
    assert memcached.read_timeout == 5.0


def test_memcached_requires_authentication() -> None:
    with pytest.raises(ValidationError):
        MemcachedConnectionSettings.model_validate({"driver": "memcached", "host": "127.0.0.1"})


def test_memcached_pool_minimum_cannot_exceed_maximum() -> None:
    with pytest.raises(ValidationError, match="min_connections"):
        MemcachedConnectionSettings(
            driver="memcached",
            host="127.0.0.1",
            username="user",
            password="secret",
            min_connections=2,
            max_connections=1,
        )
