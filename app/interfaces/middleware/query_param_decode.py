"""将 query 中名为 ``f`` 的编码参数解码并展开为普通查询参数（失败则原样放行）。"""

from typing import Any
from urllib.parse import urlencode

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.common.utils.codec import DataCodec


def _rewrite_query_params(request: Request, params: dict[str, Any]) -> None:
    new_query_string = urlencode(params, doseq=True)
    request.scope["query_string"] = new_query_string.encode("utf-8")


class QueryParamDecodeMiddleware(BaseHTTPMiddleware):
    """将 query 中的加密参数解码为普通参数。"""

    param_name: str = "f"

    async def dispatch(self, request: Request, call_next):
        query_params = dict(request.query_params)

        encoded_value = query_params.get(self.param_name, None)

        if not encoded_value:
            return await call_next(request)

        try:
            decoded_data = DataCodec.decode(encoded_value)
        except Exception:
            return await call_next(request)

        if not isinstance(decoded_data, dict):
            return await call_next(request)

        _rewrite_query_params(request, decoded_data)

        return await call_next(request)
