import base64
import json
import urllib.parse
from typing import Any


class DataCodec:
    """
    JSON + URL + Base64 编解码器
    """

    @staticmethod
    def encode(payload: dict[str, Any]) -> str:
        """
        编码字典数据为 URL 安全的字符串

        Args:
            payload: 要编码的字典数据

        Returns:
            编码后的字符串
        """
        # 1. dict -> JSON
        json_str = json.dumps(
            payload,
            separators=(",", ":"),   # 去空格（更贴近 PHP）
            ensure_ascii=False       # 支持中文
        )

        # 2. URL 编码
        url_encoded = urllib.parse.quote(json_str)

        # 3. Base64 编码并移除填充符
        b64_encoded = base64.b64encode(url_encoded.encode()).decode()

        # 4. 去掉 '='
        return b64_encoded.rstrip("=")

    @staticmethod
    def decode(encode_str: str) -> dict[str, Any]:
        """
        解码字符串为字典数据

        Args:
            encode_str: 编码后的字符串

        Returns:
            解码后的字典，失败时返回空字典
        """
        if not encode_str:
            return {}

        # 1. 处理空格和补齐 Base64 填充符
        data = encode_str.replace(" ", "+")
        padding = len(data) % 4
        if padding:
            data += "=" * (4 - padding)

        try:
            # 3. base64 解码
            decoded = base64.b64decode(data).decode()

            # URL 解码
            url_decoded = urllib.parse.unquote(decoded)

            # JSON 解析
            return json.loads(url_decoded)
        except Exception:
            return {}
