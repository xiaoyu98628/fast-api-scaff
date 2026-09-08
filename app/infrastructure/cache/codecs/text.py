"""在字符串与 UTF-8 缓存字节之间转换。"""


class TextCacheCodec:
    """提供显式文本边界，底层缓存仍只接收 bytes。"""

    @staticmethod
    def encode(value: str) -> bytes:
        return value.encode()

    @staticmethod
    def decode(value: bytes) -> str:
        return value.decode()
