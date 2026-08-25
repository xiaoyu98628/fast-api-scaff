import pytest

from app.infrastructure.cache.codec import BytesCacheCodec, JsonCacheCodec, TextCacheCodec


def test_bytes_codec_preserves_value() -> None:
    value = b"value"

    assert BytesCacheCodec.decode(BytesCacheCodec.encode(value)) is value


def test_text_codec_uses_utf_8() -> None:
    value = "缓存"

    assert TextCacheCodec.decode(TextCacheCodec.encode(value)) == value


def test_json_codec_round_trip() -> None:
    value = {"name": "xiaoyu", "roles": ["admin"]}

    assert JsonCacheCodec.decode(JsonCacheCodec.encode(value)) == value


def test_json_codec_rejects_unsupported_values() -> None:
    with pytest.raises(TypeError):
        JsonCacheCodec.encode(object())
