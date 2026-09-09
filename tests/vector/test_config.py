"""验证向量连接环境读取、驱动分派和跨字段约束。"""

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config.vector import (
    ChromaLocalVectorSettings,
    ChromaRemoteVectorSettings,
    ElasticsearchVectorSettings,
    MilvusLocalVectorSettings,
    MilvusRemoteVectorSettings,
    VectorSettings,
    parse_vector_connection,
)
from app.infrastructure.vector.errors import VectorConfigurationError
from app.infrastructure.vector.manager import VectorStoreManager
from app.infrastructure.vector.models import VectorCollectionSpec, VectorPoint, validate_limit
from app.runtime.paths import PROJECT_ROOT, STORAGE_DIR


def test_nested_environment_is_loaded_as_raw_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VECTOR_DEFAULT", "knowledge")
    monkeypatch.setenv("VECTOR_CONNECTIONS__KNOWLEDGE__DRIVER", "milvus")
    monkeypatch.setenv("VECTOR_CONNECTIONS__KNOWLEDGE__MODE", "remote")
    monkeypatch.setenv("VECTOR_CONNECTIONS__KNOWLEDGE__HOST", "127.0.0.1")
    monkeypatch.setenv("VECTOR_CONNECTIONS__KNOWLEDGE__PORT", "19530")
    monkeypatch.setenv("VECTOR_CONNECTIONS__KNOWLEDGE__USERNAME", "root")
    monkeypatch.setenv("VECTOR_CONNECTIONS__KNOWLEDGE__PASSWORD", "secret")

    settings = VectorSettings(_env_file=None)

    assert settings.default == "knowledge"
    assert settings.connections["knowledge"] == {
        "driver": "milvus",
        "mode": "remote",
        "host": "127.0.0.1",
        "port": 19530,
        "username": "root",
        "password": "secret",
    }


def test_sample_environment_contains_valid_vector_connections(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in tuple(os.environ):
        if name.startswith("VECTOR_"):
            monkeypatch.delenv(name)

    settings = VectorSettings(_env_file=PROJECT_ROOT / "sample.env")
    manager = VectorStoreManager(settings)

    assert manager.default_name == "chroma_local"
    assert manager.connection_names == (
        "chroma_local",
        "milvus_local",
        "milvus_remote",
        "chroma_remote",
        "search",
    )


@pytest.mark.parametrize(
    ("raw_config", "expected_type"),
    [
        ({"driver": "milvus", "mode": "local", "path": "vectors/milvus.db"}, MilvusLocalVectorSettings),
        ({"driver": "milvus", "mode": "remote", "host": "milvus"}, MilvusRemoteVectorSettings),
        ({"driver": "chroma", "mode": "local", "path": "vectors/chroma"}, ChromaLocalVectorSettings),
        ({"driver": "chroma", "mode": "remote", "host": "chroma"}, ChromaRemoteVectorSettings),
        ({"driver": "elasticsearch", "mode": "remote", "host": "elasticsearch"}, ElasticsearchVectorSettings),
    ],
)
def test_parser_supports_every_builtin_mode(raw_config: dict[str, object], expected_type: type[object]) -> None:
    assert isinstance(parse_vector_connection(raw_config), expected_type)


@pytest.mark.parametrize(
    "raw_config",
    [
        {"driver": "milvus", "mode": "remote"},
        {"driver": "chroma", "mode": "remote"},
        {"driver": "elasticsearch", "mode": "remote"},
    ],
)
def test_remote_vector_driver_defaults_host_to_loopback(raw_config: dict[str, object]) -> None:
    settings = parse_vector_connection(raw_config)

    assert isinstance(settings, MilvusRemoteVectorSettings | ChromaRemoteVectorSettings | ElasticsearchVectorSettings)
    assert settings.host == "127.0.0.1"


def test_chroma_remote_timeout_and_ipv6_host_are_preserved() -> None:
    chroma = parse_vector_connection({"driver": "chroma", "mode": "remote", "host": "chroma", "timeout": 2.5})
    milvus = parse_vector_connection({"driver": "milvus", "mode": "remote", "host": "::1"})

    assert isinstance(chroma, ChromaRemoteVectorSettings)
    assert chroma.timeout == 2.5
    assert isinstance(milvus, MilvusRemoteVectorSettings)
    assert milvus.host == "::1"


@pytest.mark.parametrize(
    ("model", "driver"),
    [(MilvusLocalVectorSettings, "milvus"), (ChromaLocalVectorSettings, "chroma")],
)
def test_local_relative_path_is_resolved_under_storage(
    model: type[MilvusLocalVectorSettings | ChromaLocalVectorSettings],
    driver: str,
) -> None:
    settings = model.model_validate({"driver": driver, "mode": "local", "path": "vectors/data"})

    assert settings.resolved_path == STORAGE_DIR / Path("vectors/data")


@pytest.mark.parametrize(
    "raw_config",
    [
        {"driver": "milvus", "mode": "remote", "host": ""},
        {"driver": "milvus", "mode": "remote", "host": "milvus", "username": "root"},
        {"driver": "chroma", "mode": "remote", "host": "chroma", "password": "secret"},
        {
            "driver": "chroma",
            "mode": "remote",
            "host": "chroma",
            "username": "root",
            "password": "secret",
            "api_key": "token",
        },
        {"driver": "elasticsearch", "mode": "local", "path": "vectors/es"},
    ],
)
def test_invalid_address_authentication_or_mode_is_rejected(raw_config: dict[str, object]) -> None:
    with pytest.raises((ValidationError, ValueError)):
        parse_vector_connection(raw_config)


def test_driver_config_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        parse_vector_connection({"driver": "chroma", "mode": "local", "path": "vectors/chroma", "timeout": 2})


@pytest.mark.parametrize("key", ["id", "vector", "bad.key", "1st_kind", "_vector_record"])
def test_point_metadata_rejects_reserved_or_nonportable_keys(key: str) -> None:
    with pytest.raises(VectorConfigurationError):
        VectorPoint(id="doc-1", vector=(1.0, 0.0), metadata={key: "value"})


def test_point_vector_rejects_boolean_and_non_finite_values() -> None:
    with pytest.raises(VectorConfigurationError):
        VectorPoint(id="doc-1", vector=(True, float("nan")))


@pytest.mark.parametrize("value", [-(2**63) - 1, 2**63])
def test_point_metadata_rejects_integers_outside_signed_64_bit(value: int) -> None:
    with pytest.raises(VectorConfigurationError, match="64 位"):
        VectorPoint(id="doc-1", vector=(1.0,), metadata={"sequence": value})


def test_boolean_dimension_and_limit_are_rejected() -> None:
    with pytest.raises(VectorConfigurationError, match="维度"):
        VectorCollectionSpec(name="knowledge", dimension=True)
    with pytest.raises(VectorConfigurationError, match="limit"):
        validate_limit(True)


def test_point_id_uses_cross_driver_utf8_byte_limit() -> None:
    with pytest.raises(VectorConfigurationError, match="512 字节"):
        VectorPoint(id="界" * 171, vector=(1.0,))


def test_collection_dimension_uses_cross_driver_limit() -> None:
    with pytest.raises(VectorConfigurationError, match="4096"):
        VectorCollectionSpec(name="knowledge", dimension=4097)
