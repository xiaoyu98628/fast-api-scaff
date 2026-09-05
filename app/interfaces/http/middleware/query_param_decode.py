import base64
import binascii
import json
from urllib.parse import quote, unquote, urlencode

from starlette.datastructures import QueryParams
from starlette.types import ASGIApp, Receive, Scope, Send

DECODED_F_STATE_KEY = "decoded_f_params"


def encode_query_param(payload: dict[str, object]) -> str:
    """将字典编码为兼容查询参数封装协议的字符串。"""
    json_str = json.dumps(
        payload,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    url_encoded = quote(json_str)
    b64_encoded = base64.b64encode(url_encoded.encode()).decode()
    return b64_encoded.rstrip("=")


def decode_query_param(value: str) -> dict[str, object] | None:
    """解码兼容 JSON、URL 编码和 Base64 组合格式的查询参数。"""
    if not value:
        return None

    encoded = value.replace(" ", "+")
    padding = len(encoded) % 4
    if padding:
        encoded += "=" * (4 - padding)

    try:
        decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
        payload: object = json.loads(unquote(decoded))
    except binascii.Error, UnicodeDecodeError, json.JSONDecodeError:
        return None

    if not isinstance(payload, dict):
        return None

    return {str(key): item for key, item in payload.items()}


class QueryParamDecodeMiddleware:
    """将查询字符串中的编码参数展开为下游可读取的普通查询参数。"""

    def __init__(self, app: ASGIApp, *, param_name: str = "f") -> None:
        if not param_name:
            raise ValueError("编码查询参数名不能为空")

        self.app = app
        self.param_name = param_name

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        encoded_value = QueryParams(scope.get("query_string", b"")).get(self.param_name)
        if not encoded_value:
            await self.app(scope, receive, send)
            return

        decoded_params = decode_query_param(encoded_value)
        if decoded_params is None:
            await self.app(scope, receive, send)
            return

        decoded_scope = dict(scope)
        decoded_scope["query_string"] = urlencode(decoded_params, doseq=True).encode("utf-8")

        state = dict(scope.get("state", {}))
        state[DECODED_F_STATE_KEY] = decoded_params
        decoded_scope["state"] = state

        try:
            await self.app(decoded_scope, receive, send)
        finally:
            # 外层访问日志需要下游匹配的路由模板，查询和 state 仍保持隔离。
            if "route" in decoded_scope:
                scope["route"] = decoded_scope["route"]
