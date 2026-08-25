import json


class BytesCacheCodec:
    @staticmethod
    def encode(value: bytes) -> bytes:
        return value

    @staticmethod
    def decode(value: bytes) -> bytes:
        return value


class TextCacheCodec:
    @staticmethod
    def encode(value: str) -> bytes:
        return value.encode()

    @staticmethod
    def decode(value: bytes) -> str:
        return value.decode()


class JsonCacheCodec:
    @staticmethod
    def encode(value: object) -> bytes:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()

    @staticmethod
    def decode(value: bytes) -> object:
        return json.loads(value)
