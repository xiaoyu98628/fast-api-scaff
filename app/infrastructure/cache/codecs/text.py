class TextCacheCodec:
    @staticmethod
    def encode(value: str) -> bytes:
        return value.encode()

    @staticmethod
    def decode(value: bytes) -> str:
        return value.decode()
