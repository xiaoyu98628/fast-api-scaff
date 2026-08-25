import pytest
from pydantic import ValidationError

from app.config.cache import CacheSettings
from app.infrastructure.cache.providers.memcached import MemcachedCacheSettings


def test_nested_environment_is_loaded_as_raw_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CACHE_DEFAULT", "session")
    monkeypatch.setenv("CACHE_NAMESPACE", "fast-api-scaff")
    monkeypatch.setenv("CACHE_DEFAULT_TTL", "300")
    monkeypatch.setenv("CACHE_CONNECTIONS__SESSION__DRIVER", "redis")
    monkeypatch.setenv("CACHE_CONNECTIONS__SESSION__HOST", "127.0.0.1")
    monkeypatch.setenv("CACHE_CONNECTIONS__SESSION__DATABASE", "2")

    settings = CacheSettings(_env_file=None)

    assert settings.default == "session"
    assert settings.namespace == "fast-api-scaff"
    assert settings.default_ttl == 300
    assert settings.connections == {
        "session": {
            "driver": "redis",
            "host": "127.0.0.1",
            "database": 2,
        }
    }


@pytest.mark.parametrize(
    ("username", "password"),
    [(None, None), ("user", "secret")],
)
def test_memcached_authentication_is_optional_but_must_be_complete(
    username: str | None,
    password: str | None,
) -> None:
    settings = MemcachedCacheSettings(
        driver="memcached",
        host="127.0.0.1",
        username=username,
        password=password,
    )

    assert settings.username == username


@pytest.mark.parametrize(
    ("username", "password"),
    [("user", None), (None, "secret")],
)
def test_memcached_rejects_partial_authentication(username: str | None, password: str | None) -> None:
    with pytest.raises(ValidationError, match="同时配置"):
        MemcachedCacheSettings(
            driver="memcached",
            host="127.0.0.1",
            username=username,
            password=password,
        )


def test_memcached_pool_minimum_cannot_exceed_maximum() -> None:
    with pytest.raises(ValidationError, match="min_connections"):
        MemcachedCacheSettings(
            driver="memcached",
            host="127.0.0.1",
            min_connections=2,
            max_connections=1,
        )


@pytest.mark.parametrize("ttl", [0, -1])
def test_default_ttl_must_be_positive(ttl: int) -> None:
    with pytest.raises(ValidationError, match="default_ttl"):
        CacheSettings(default_ttl=ttl, _env_file=None)
