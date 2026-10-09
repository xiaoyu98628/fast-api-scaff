"""验证数据库主键生成的 ULID 编码边界和 UUID 持久化表示。"""

import re
from collections.abc import Callable
from uuid import UUID

import pytest

import app.infrastructure.database.identifiers as identifiers

_ULID_PATTERN = re.compile(r"[0-7][0-9a-hjkmnp-tv-z]{25}")
_CROCKFORD_VALUES = {character: index for index, character in enumerate("0123456789abcdefghjkmnpqrstvwxyz")}


def test_new_ulid_uses_canonical_lowercase_alphabet() -> None:
    assert _ULID_PATTERN.fullmatch(identifiers.new_ulid())


@pytest.mark.parametrize("timestamp_ms", [0, 1_797_206_400_123, (1 << 48) - 1])
def test_new_ulid_preserves_complete_timestamp_and_random_bits(timestamp_ms: int, monkeypatch: pytest.MonkeyPatch) -> None:
    random_bytes = bytes(range(10))
    monkeypatch.setattr(identifiers, "time_ns", lambda: timestamp_ms * 1_000_000)
    monkeypatch.setattr(identifiers, "token_bytes", lambda length: random_bytes if length == 10 else pytest.fail("ULID 必须使用 80 位随机数"))

    value = identifiers.new_ulid()
    decoded = 0
    for character in value:
        decoded = (decoded << 5) | _CROCKFORD_VALUES[character]

    assert _ULID_PATTERN.fullmatch(value)
    assert decoded >> 80 == timestamp_ms
    assert decoded & ((1 << 80) - 1) == int.from_bytes(random_bytes, "big")


@pytest.mark.parametrize("timestamp_ms", [-1, 1 << 48])
def test_new_ulid_rejects_timestamp_outside_unsigned_range(timestamp_ms: int, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(identifiers, "time_ns", lambda: timestamp_ms * 1_000_000)

    with pytest.raises(OverflowError, match="48 位"):
        identifiers.new_ulid()


def test_new_ulid_retains_random_component_in_same_millisecond(monkeypatch: pytest.MonkeyPatch) -> None:
    random_values = iter((bytes(10), (1).to_bytes(10, "big")))
    monkeypatch.setattr(identifiers, "time_ns", lambda: 1_797_206_400_123_000_000)
    monkeypatch.setattr(identifiers, "token_bytes", lambda length: next(random_values))

    first = identifiers.new_ulid()
    second = identifiers.new_ulid()

    assert first[:10] == second[:10]
    assert first[10:] != second[10:]


@pytest.mark.parametrize(("factory", "version"), [(identifiers.new_uuid4, 4), (identifiers.new_uuid7, 7)])
def test_uuid_primary_key_supports_both_persistence_formats(factory: Callable[[], UUID], version: int) -> None:
    value = factory()

    assert isinstance(value, UUID)
    assert value.version == version
    assert re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", str(value))
    assert re.fullmatch(r"[0-9a-f]{32}", value.hex)
    assert UUID(str(value)) == UUID(hex=value.hex) == value
