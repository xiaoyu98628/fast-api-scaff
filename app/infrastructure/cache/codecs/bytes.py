"""提供不做转换的 bytes 缓存编解码器。"""


class BytesCacheCodec:
    """让已经是 bytes 的调用方复用统一 Codec 接口。"""

    @staticmethod
    def encode(value: bytes) -> bytes:
        """原样返回待写入字节。"""

        return value

    @staticmethod
    def decode(value: bytes) -> bytes:
        """原样返回已读取字节。"""

        return value
