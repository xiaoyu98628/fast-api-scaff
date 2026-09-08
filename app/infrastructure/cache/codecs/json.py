"""在 JSON 兼容对象与 UTF-8 缓存字节之间转换。"""

import json


class JsonCacheCodec:
    """使用紧凑 JSON 表达缓存值，并保留非 ASCII 字符。"""

    @staticmethod
    def encode(value: object) -> bytes:
        """把 JSON 兼容对象编码为紧凑 UTF-8 字节。"""

        return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()

    @staticmethod
    def decode(value: bytes) -> object:
        """把 UTF-8 JSON 字节还原为 Python 对象。"""

        return json.loads(value)
