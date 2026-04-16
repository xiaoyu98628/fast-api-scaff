"""请求访问日志中间件：分别记录请求进入和响应退出日志。"""

import json
import time
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.common.utils.logger import Log

SENSITIVE_KEYS = {"password", "token", "access_token", "refresh_token", "authorization"}


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


def _extract_response_result(response: Any) -> Any:
    content_type = getattr(response, "media_type", "") or ""
    raw_body = getattr(response, "body", b"")
    if isinstance(raw_body, str):
        raw_body = raw_body.encode("utf-8")
    if not isinstance(raw_body, (bytes, bytearray)) or not raw_body:
        return {"content_type": content_type, "body_preview": "<streaming or empty>"}

    text = raw_body.decode("utf-8", errors="ignore")
    if "application/json" in content_type:
        try:
            return _mask_payload(json.loads(text))
        except json.JSONDecodeError:
            return {"content_type": content_type, "body_preview": text[:500]}
    return {"content_type": content_type, "body_preview": text[:500]}


class RequestLogMiddleware(BaseHTTPMiddleware):
    """记录每个请求的访问日志。"""

    async def dispatch(self, request: Request, call_next):
        started = time.perf_counter()
        trace_id = getattr(request.state, "trace_id", "-")
        status_code = 500
        request_params = await _extract_request_params(request)
        Log.info(
            "--> %s %s",
            request.method,
            request.url.path,
            channel="request",
            trace_id=trace_id,
            extra={
                "client_ip": request.client.host if request.client else "-",
                "params": request_params,
            },
        )

        response_result: Any = "<no response>"
        try:
            response = await call_next(request)
            status_code = response.status_code
            response_result = _extract_response_result(response)
            return response
        finally:
            duration_ms = (time.perf_counter() - started) * 1000
            Log.info(
                "<-- %s %s -> %s (%.2f ms)",
                request.method,
                request.url.path,
                status_code,
                duration_ms,
                channel="request",
                trace_id=trace_id,
                extra={
                    "client_ip": request.client.host if request.client else "-",
                    "result": response_result,
                },
            )
