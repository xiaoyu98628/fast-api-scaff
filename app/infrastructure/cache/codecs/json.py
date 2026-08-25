import json


class JsonCacheCodec:
    @staticmethod
    def encode(value: object) -> bytes:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()

    @staticmethod
    def decode(value: bytes) -> object:
        return json.loads(value)
