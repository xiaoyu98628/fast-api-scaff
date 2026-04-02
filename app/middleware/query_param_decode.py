from typing import Any, Dict
from urllib.parse import urlencode

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.utils.codec import DataCodec


def _rewrite_query_params(request: Request, params: Dict[str, Any]) -> None:
    new_query_string = urlencode(params, doseq=True)
    request.scope["query_string"] = new_query_string.encode("utf-8")


class QueryParamDecodeMiddleware(BaseHTTPMiddleware):
    """将 query 中的加密参数解码为普通参数。"""

    param_name: str = "f"

    async def dispatch(self, request: Request, call_next):
        # 获取查询参数
        query_params = dict(request.query_params)

        # =========================
        # 1️⃣ 处理 f 参数（加密数据）
        # =========================
        encoded_value = query_params.get(self.param_name, None)

        if not encoded_value:
            return await call_next(request)

        # =========================
        # 2️⃣ 解密（安全保护）
        # =========================
        try:
            decoded_data = DataCodec.decode(encoded_value)
        except Exception:
            # ❗解密失败：直接忽略，不影响业务
            return await call_next(request)

        # =========================
        # 3️⃣ 校验数据类型
        # =========================
        if not isinstance(decoded_data, dict):
            return await call_next(request)

        # =========================
        # 4️⃣  重写 request（核心）
        # =========================
        _rewrite_query_params(request, decoded_data)

        return await call_next(request)

