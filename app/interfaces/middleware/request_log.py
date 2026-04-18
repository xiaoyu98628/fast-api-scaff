"""请求访问日志中间件：分别记录请求进入和响应退出日志。"""

import json
import time
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.common.utils.logger import Log

SENSITIVE_KEYS = {"password", "token", "access_token", "refresh_token", "authorization"}

_LOG_JSON_MAX_LEN = 8000


def _json_for_log(obj: Any, *, max_len: int = _LOG_JSON_MAX_LEN) -> str:
    """单行写入日志文件：Formatter 未展开 ``extra`` 时仍能看到请求/响应内容。"""
    try:
        text = json.dumps(obj, ensure_ascii=False, default=str)
    except TypeError:
        text = str(obj)
    if len(text) > max_len:
        return f"{text[: max_len - 20]}...<truncated len={len(text)}>"
    return text


def _mask_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        masked: dict[str, Any] = {}
        for key, value in payload.items():
            if key.lower() in SENSITIVE_KEYS:
                masked[key] = "***"
            else:
                masked[key] = _mask_payload(value)
        return masked
    if isinstance(payload, list):
        return [_mask_payload(item) for item in payload]
    return payload


async def _extract_request_params(request: Request) -> dict[str, Any]:
    params: dict[str, Any] = {"query": dict(request.query_params.multi_items())}
    body = await request.body()
    if not body:
        return params

    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            params["body"] = json.loads(body)
            return _mask_payload(params)
        except json.JSONDecodeError:
            params["body"] = body.decode("utf-8", errors="ignore")[:500]
            return _mask_payload(params)

    params["body"] = body.decode("utf-8", errors="ignore")[:500]
    return _mask_payload(params)


class RequestLogMiddleware(BaseHTTPMiddleware):
    """记录每个请求的访问日志。"""

    async def dispatch(self, request: Request, call_next):
        started = time.perf_counter()
        trace_id = getattr(request.state, "trace_id", "-")
        status_code = 500
        client_ip = request.client.host if request.client else "-"
        request_params = await _extract_request_params(request)
        params_text = _json_for_log(request_params)
        Log.info(
            "--> %s %s | ip=%s | params=%s",
            request.method,
            request.url.path,
            client_ip,
            params_text,
            channel="request",
            trace_id=trace_id,
            extra={
                "client_ip": client_ip,
                "params": request_params,
            },
        )

        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration_ms = (time.perf_counter() - started) * 1000
            Log.info(
                "<-- %s %s -> %s (%.2f ms) | ip=%s",
                request.method,
                request.url.path,
                status_code,
                duration_ms,
                client_ip,
                channel="request",
                trace_id=trace_id,
                extra={"client_ip": client_ip},
            )
