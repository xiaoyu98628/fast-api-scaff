"""请求访问日志：每个请求一行（``app.request`` → request.log）。"""

import json
import logging
import time
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import ClientDisconnect, Request

from app.infrastructure.context.request_scope import get_trace_id
from config.config import config

SENSITIVE_KEYS = frozenset({"password", "token", "access_token", "refresh_token", "authorization"})
_SKIP_PATHS = frozenset({"/health", "/favicon.ico"})
_LOG_JSON_MAX_LEN = 8000

logger = logging.getLogger("app.request")


def _json_for_log(obj: Any, *, max_len: int = _LOG_JSON_MAX_LEN) -> str:
    try:
        text = json.dumps(obj, ensure_ascii=False, default=str)
    except TypeError:
        text = str(obj)
    if len(text) > max_len:
        return f"{text[: max_len - 20]}...<truncated len={len(text)}>"
    return text


def _mask_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: "***" if key.lower() in SENSITIVE_KEYS else _mask_payload(value)
            for key, value in payload.items()
        }
    if isinstance(payload, list):
        return [_mask_payload(item) for item in payload]
    return payload


async def _extract_request_params(request: Request) -> dict[str, Any]:
    params: dict[str, Any] = {"query": dict(request.query_params.multi_items())}

    try:
        body = await request.body()
        if not body:
            return params
    except ClientDisconnect:
        params["error"] = "client_disconnected_before_body_read"
        return params
    except Exception as exc:
        params["error"] = f"body_read_error: {exc}"
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
    """记录每个 HTTP 请求的单行访问日志。"""

    async def dispatch(self, request: Request, call_next):
        if request.url.path in _SKIP_PATHS:
            return await call_next(request)

        started = time.perf_counter()
        log_settings = config().logging
        client_ip = request.client.host if request.client else "-"
        trace_id = get_trace_id()
        query = request.url.query or None
        params = await _extract_request_params(request) if log_settings.request_body_enabled else None

        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            extra: dict[str, Any] = {
                "event": "http.access",
                "method": request.method,
                "path": request.url.path,
                "query": query,
                "status_code": status_code,
                "duration_ms": duration_ms,
                "client_ip": client_ip,
                "trace_id": trace_id,
            }
            if params is not None:
                extra["params"] = params

            if log_settings.json_enabled:
                logger.info(
                    '%s %s %s %.2fms trace_id=%s',
                    request.method,
                    request.url.path,
                    status_code,
                    duration_ms,
                    trace_id,
                    extra=extra,
                )
            else:
                message = (
                    f'{client_ip} "{request.method} {request.url.path}" '
                    f"{status_code} {duration_ms}ms trace_id={trace_id}"
                )
                if query:
                    message = f'{message} query="{query}"'
                if params is not None:
                    message = f"{message} params={_json_for_log(params)}"
                logger.info(message, extra=extra)
