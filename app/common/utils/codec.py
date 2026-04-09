"""Query 参数等场景的轻量编解码（非加密）；敏感数据请走 ``SensitiveDataCodec`` 或专用加解密。"""

import base64
import json
import urllib.parse
from typing import Any


class DataCodec:
    """JSON → URL 编码 → Base64 的链式编解码，用于中间件展开 ``f`` 参数。"""

    @staticmethod
    def encode(payload: dict[str, Any]) -> str:
        """字典 → 可放在 URL 中的紧凑字符串。"""
        json_str = json.dumps(
            payload,
            separators=(",", ":"),
            ensure_ascii=False,
        )

        url_encoded = urllib.parse.quote(json_str)

        b64_encoded = base64.b64encode(url_encoded.encode()).decode()

        return b64_encoded.rstrip("=")

    @staticmethod
    def decode(encode_str: str) -> dict[str, Any]:
        """解码失败返回空字典，调用方需自行判断是否有效。"""
        if not encode_str:
            return {}

        data = encode_str.replace(" ", "+")
        padding = len(data) % 4
        if padding:
            data += "=" * (4 - padding)

        try:
            decoded = base64.b64decode(data).decode()

            url_decoded = urllib.parse.unquote(decoded)

            return json.loads(url_decoded)
        except Exception:
            return {}


class SensitiveDataCodec:
    """占位：接入 KMS / 对称加密等后再实现具体算法。"""

    @staticmethod
    def encrypt(plaintext: str):
        """加密明文（待实现）。"""
        pass

    @staticmethod
    def decrypt(encoded: str) -> str:
        """解密密文（待实现）。"""
        pass


if __name__ == "__main__":
    encoded_str = DataCodec.encode(
        {
            "name": "张三",
            "age": 18,
            "sex": "男",
        }
    )
    print("编码:", encoded_str)

    decoded_dic = DataCodec.decode(encoded_str)
    print("解码:", decoded_dic)
